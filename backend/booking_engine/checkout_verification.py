"""Receipt-authorized browser callback; a browser success is never payment proof."""

from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .access import AccessDenied
from .connection import StorageUnavailable
from .payment_evidence import fetch_and_record
from .razorpay import RazorpayFailure, merchant_identity, verify_checkout
from .receipt_view import receipt_view
from .security import request_fingerprint


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    razorpay_order_id: str = Field(pattern=r'^order_[A-Za-z0-9]{1,64}$')
    razorpay_payment_id: str = Field(pattern=r'^pay_[A-Za-z0-9]{1,64}$')
    razorpay_signature: str = Field(pattern=r'^[0-9a-f]{64}$')


def add_checkout_verification_route(app, store, settings, accounts, browser_request, limit, wake):
    @app.post('/api/checkout/verify-payment')
    def verify_payment(request: Request, body: VerificationRequest):
        browser_request(request)
        # Costly provider verification uses the durable checkout quota, not the
        # higher read-only receipt polling quota. It needs no live context cookie.
        limit(request, 'checkout')
        secret = request.headers.get('x-booking-receipt')
        saved = store.receipt_snapshot(body.request_id)
        receipt_view(saved, body.request_id, secret, settings.receipt_key)
        row = saved['booking']
        if row.get('provider_order_id') != body.razorpay_order_id:
            raise AccessDenied()
        if accounts is None:
            raise StorageUnavailable('Payment verification is not configured.')
        try:
            adapter = accounts.pinned(row['merchant_id'], row['mode'], row['credential_version'])
            if not verify_checkout(row['provider_order_id'], body.razorpay_payment_id,
                                   body.razorpay_signature, adapter.credentials.key_secret):
                raise AccessDenied()
            # Save the authenticated reference before the remote read. A crash
            # or timeout must not lose a payment ID that the order listing has
            # not yet exposed. The consumer still fetches authoritative facts.
            reference = dict(event='checkout.verified', payment_id=body.razorpay_payment_id,
                             order_id=row['provider_order_id'])
            digest = request_fingerprint(reference)
            committed = store.save_provider_event('razorpay', merchant_identity(row['merchant_id']),
                row['mode'], 'checkout-verify:' + body.razorpay_payment_id, digest, reference)
            if committed != digest:
                raise StorageUnavailable('Payment reference could not be saved.')
            fetch_and_record(store, adapter, row['context_id'], row['booking_id'],
                             body.razorpay_payment_id)
        except RazorpayFailure:
            # Existing order remains recoverable. Do not report a failed payment
            # or offer a second checkout because a provider read was unavailable.
            store.wake_payment_recovery(row['booking_id'])
            if wake is not None:
                wake.publish()
            current = receipt_view(store.receipt_snapshot(body.request_id), body.request_id,
                                   secret, settings.receipt_key)
            return JSONResponse(dict(receipt=current, verification='pending'), 202)
        # observe_payment commits before any wake or response. Re-read the
        # canonical projection, including late-payment/refund/review outcomes.
        if wake is not None:
            wake.publish()
        current = receipt_view(store.receipt_snapshot(body.request_id), body.request_id,
                               secret, settings.receipt_key)
        return dict(receipt=current, verification='checked')
