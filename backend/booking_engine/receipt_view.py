"""Explicit customer-facing projection; never serialize a database row directly."""

from datetime import datetime
import re

from .access import authorize_receipt
from .payment_policy import Appointment, CheckoutEvidence, Order, Payment, Resolution, customer_actions


def timestamp(value):
    if value is None:
        return None
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Invalid saved timestamp.')
    return result


def receipt_view(snapshot, request_id, secret, key):
    now = timestamp(snapshot['server_now'])
    row = snapshot.get('booking')
    if row:
        row = dict(row)
        for name in ('receipt_expires_at', 'receipt_revoked_at'):
            row[name] = timestamp(row.get(name))
    authorize_receipt(row, request_id, secret, key, now)
    state = Appointment(row['state'])
    deadline = timestamp(row['hold_expires_at'])
    if state == Appointment.HELD and deadline <= now:
        state = Appointment.EXPIRED
    evidence = CheckoutEvidence(
        state, Order(row['order_state']), Payment(row['payment_state']), deadline,
        timestamp(row.get('attempted_at')), row.get('provider_order_id'),
        Resolution(row['resolution']) if row.get('resolution') else None,
        timestamp(row.get('resolved_at')),
    )
    actions = customer_actions(evidence, now)
    # Final route may further restrict resume when provider recovery is stale.
    # This read-only view never exposes payment-launch credentials.
    if 'resume_payment' in actions['next_actions']:
        actions = dict(customer_message_code='time_reserved', next_actions=['check_payment','check_status'])
    meet_url = row.get('meet_url') if state == Appointment.CONFIRMED and row['meeting_state'] == 'ready' else None
    if meet_url is not None and (not isinstance(meet_url,str) or not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',meet_url)):
        raise ValueError('Invalid saved meeting.')
    captured=row['captured_paise']
    refunded=row['refunded_paise']
    if type(captured) is not int or type(refunded) is not int or not 0<=refunded<=captured:
        raise ValueError('Invalid saved payment amounts.')
    return dict(
        captured_paise=captured,refunded_paise=refunded,
        request_id=str(request_id), appointment_state=state.value,
        order_state=evidence.order.value, payment_state=evidence.payment.value,
        service_name=row['service_name'], amount_paise=row['amount_paise'], currency=row['currency'],
        starts_at=timestamp(row['starts_at']).isoformat(), ends_at=timestamp(row['ends_at']).isoformat(),
        timezone=row['practice_timezone'], server_now=now.isoformat(), hold_expires_at=deadline.isoformat(),
        payment_checked_at=row.get('payment_checked_at'),
        payment_evidence_source='provider_observation' if row.get('payment_checked_at') else 'unobserved',
        meeting_state=row['meeting_state'], meet_url=meet_url, acknowledgement_state=row['acknowledgement_state'],
        meeting_email_state=row['meeting_email_state'], **actions,
    )
