"""Durable reservation and bounded, receipt-authorized payment launch."""

from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .access import AccessDenied, COOKIE_NAME, authorize_context, parse_context,context_identifier
from .errors import Rejected
from .connection import StorageUnavailable
from .models import BookingRequest
from .order_creation import create_once
from .payment_evidence import PaymentEvidence
from .razorpay import RazorpayFailure,saved_order_receipt
from .receipt_view import receipt_view, timestamp
from .recovery import _items
from .security import receipt_digest


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


def pinned(accounts, row):
    if accounts is None:
        raise StorageUnavailable('Payments are not configured.')
    return accounts.pinned(row['merchant_id'], row['mode'], row['credential_version'])


def resume_checkout(store, accounts, settings, request_id, secret, wake):
    saved = store.receipt_snapshot(request_id)
    view = receipt_view(saved, request_id, secret, settings.receipt_key)
    row = saved['booking']
    if saved.get('booking_product_enabled') is False:
        return dict(receipt=view,checkout=None)
    if (view['appointment_state'] != 'held' or row['order_state'] != 'ready'
            or row.get('resolved_at') is not None or view['payment_state'] in
            ('captured', 'refunded', 'partially_refunded', 'needs_attention')):
        return dict(receipt=view, checkout=None)
    adapter = pinned(accounts, row)
    job = store.claim_checkout_resume(row['booking_id'])
    if not job:
        return dict(receipt=view, checkout=None, retry_after=15)
    launch = False
    error = None
    followup_cursor = job['recovery_cursor']
    try:
        order = adapter.order(row['provider_order_id'])
        if (order.get('id') != row['provider_order_id'] or order.get('entity') != 'order'
                or order.get('receipt') != saved_order_receipt(row)
                or type(order.get('amount')) is not int or order['amount'] != row['amount_paise']
                or order.get('currency') != row['currency'] or order.get('partial_payment', False) is not False):
            raise RazorpayFailure('payment_order_mismatch')
        items = _items(adapter.order_payments(row['provider_order_id']))
        # A full page is ambiguous, not proof that every attempt was inspected.
        if len(items) >= 100:
            raise RazorpayFailure('payment_response_incomplete')
        try:
            evidence = [PaymentEvidence.model_validate(item) for item in items]
        except (ValueError,Rejected):
            raise RazorpayFailure('payment_response_invalid') from None
        if (len({item.id for item in evidence}) != len(evidence)
                or any(item.order_id != row['provider_order_id'] for item in evidence)):
            raise RazorpayFailure('payment_response_invalid')
        # Persist at most two financially relevant observations per HTTP call.
        # Larger sets stay with the durable, cursor-based recovery consumer.
        relevant = [item for item in evidence if item.status != 'failed' or item.captured or item.amount_refunded]
        if len(evidence) > 2:
            followup_cursor = max(1, followup_cursor)
        # Failed attempts also replace older pending observations in receipts.
        # Financial/pending evidence takes priority within the bounded batch.
        ordered = relevant + [item for item in evidence if item not in relevant]
        for item in ordered[:2]:
            store.observe_payment(row['context_id'], row['booking_id'], row, item)
        launch = (not relevant and order.get('status') in ('created', 'attempted')
            and type(order.get('amount_paid')) is int and order['amount_paid'] == 0
            and type(order.get('amount_due')) is int and order['amount_due'] == row['amount_paise']
            and all(item.amount == row['amount_paise'] and item.currency == row['currency'] for item in evidence))
    except RazorpayFailure as exc:
        error = exc.code
    # Lease fencing prevents a slow request returning a launch after another
    # worker took ownership. Database commit failure propagates, never launches.
    finished = store.finish_checkout_resume(job, 15, followup_cursor, job['order_search_skip'], error=error)
    if wake is not None:
        wake.publish()
    current = receipt_view(store.receipt_snapshot(request_id), request_id, secret, settings.receipt_key)
    if (finished is not True or not launch or current['appointment_state'] != 'held'
            or current['payment_state'] not in ('unobserved', 'failed_observed')
            or store.checkout_launchable(row['booking_id']) is not True):
        return dict(receipt=current, checkout=None, retry_after=15)
    current = dict(current, next_actions=['resume_payment', 'check_status'])
    return dict(receipt=current, checkout=dict(key_id=adapter.credentials.key_id,
        order_id=row['provider_order_id'], amount_paise=row['amount_paise'], currency=row['currency']))


def add_checkout_routes(app, store, settings, accounts, browser_request, limit, wake,*,verification_keys=None):
    @app.post('/api/checkout/resume')
    def resume(request: Request, body: ResumeRequest):
        browser_request(request)
        limit(request, 'checkout')
        try:
            return resume_checkout(store, accounts, settings, body.request_id,
                                   request.headers.get('x-booking-receipt'), wake)
        except RazorpayFailure:
            raise StorageUnavailable('Payment recovery is temporarily unavailable.') from None

    @app.post('/api/checkout')
    def checkout(request: Request, body: BookingRequest):
        browser_request(request)
        limit(request, 'checkout')
        secret = request.headers.get('x-booking-receipt')
        try:
            receipt_digest(body.request_id, secret, settings.receipt_key)
        except ValueError:
            raise AccessDenied() from None
        token=request.cookies.get(COOKIE_NAME)
        context_id=context_identifier(token,settings.context_key)
        snapshot = store.context_snapshot(context_id)
        row = snapshot.get('context')
        if row:
            row = dict(row, expires_at=timestamp(row['expires_at']))
        context_id,digest=parse_context(token,settings.context_key,row)
        authorize_context(row, digest, timestamp(snapshot['server_now']))
        expected = None
        if accounts is not None:
            configured = store.payment_intake()
            if isinstance(configured, dict):
                try:
                    adapter = accounts.current(configured['merchant_id'], configured['mode'])
                    if adapter.credentials.version == configured['credential_version']:
                        expected = configured
                except (KeyError, ValueError, RazorpayFailure):
                    pass
        # The transaction distinguishes existing commitments from a proven
        # uncommitted attempt before returning a safe-to-clear rejection.
        arguments={'expected_merchant':expected}
        if body.verification_grant is not None:arguments['verification_keys']=verification_keys
        result = store.reserve(context_id, body, secret, settings.receipt_key, **arguments)
        if result.get('code') not in ('reserved', 'existing'):
            code = result.get('code')
            messages = {
                'payment_not_configured': 'We could not start payment. No appointment has been confirmed. Please try again later or contact the practice.',
                'request_conflict': 'These details differ from your saved request. Please return to your booking.',
                'request_rejected': 'This request cannot be reused. Please choose a time again.',
                'checkout_in_progress': 'Please finish or check your existing booking first.',
                'intake_closed': 'Online booking is not available at the moment.',
                'quote_changed': 'The consultation details have changed. Please review them again.',
                'verification_required': 'Please verify your email before continuing.',
                'service_unavailable': 'Please choose an available consultation.',
                'invalid_time': 'Please choose an available appointment time.',
                'time_unavailable': 'That time is no longer available. Please choose another.',
                'context_expired': 'Please refresh the booking page before continuing.',
                'rate_limited': 'Please wait before trying another booking.',
            }
            if code not in messages:
                raise StorageUnavailable('Reservation outcome unavailable.')
            return JSONResponse(dict(code=code, message=messages[code]), 503 if code == 'payment_not_configured' else 429 if code == 'rate_limited' else 409)
        saved = store.receipt_snapshot(body.request_id)
        receipt_view(saved, body.request_id, secret, settings.receipt_key)
        row = saved['booking']
        if row['context_id'] != str(context_id) or row['booking_id'] != str(result['booking_id']):
            raise AccessDenied()
        try:
            adapter = pinned(accounts, row)
            create_once(store, adapter, context_id, row['booking_id'])
            if wake is not None:
                wake.publish()
            return resume_checkout(store, accounts, settings, body.request_id, secret, wake)
        except RazorpayFailure:
            # The committed reservation remains visible/recoverable. No new
            # request, another provider order, or automatic retry is invented.
            raise StorageUnavailable('Payment preparation is temporarily unavailable.') from None
