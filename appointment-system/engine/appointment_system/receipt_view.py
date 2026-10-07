"""Explicit customer-facing projection; never serialize a database row directly."""

from datetime import datetime
import re
from uuid import UUID

from .access import authorize_receipt
from .payment_policy import Appointment, CheckoutEvidence, Order, Payment, Resolution, customer_actions


def timestamp(value):
    if value is None:
        return None
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Invalid saved timestamp.')
    return result


def email_copy_view(value,*,sending_ready=None):
    fields={'operation_id','booking_revision','state','has_booking_email','target_hint','next_request_at','remaining_requests','can_request','blocked_reason'}
    states={'not_requested','pending','processing','provider_accepted','delivered','superseded','needs_attention'}
    reasons={'delivery_pending','delivery_unknown','cooldown','quota','destination_unavailable','copy_unavailable','booking_unavailable',None}
    if (type(value) is not dict or set(value)!=fields or type(value['state']) is not str or value['state'] not in states
        or type(value['has_booking_email']) is not bool or type(value['can_request']) is not bool
        or type(value['remaining_requests']) is not int or not 0<=value['remaining_requests']<=3
        or value['blocked_reason'] is not None and type(value['blocked_reason']) is not str
        or value['blocked_reason'] not in reasons or value['can_request']!=(value['blocked_reason'] is None)):
        raise ValueError('Invalid saved email-copy state.')
    result=dict(value)
    if value['operation_id'] is None:
        if value['booking_revision'] is not None or value['state']!='not_requested' or value['target_hint'] is not None:
            raise ValueError('Invalid saved email-copy identity.')
    else:
        if type(value['operation_id']) is not str or value['state']=='not_requested':raise ValueError('Invalid saved email-copy identity.')
        operation=UUID(value['operation_id'])
        if not operation.int or str(operation)!=value['operation_id'] or type(value['booking_revision']) is not int or not 1<=value['booking_revision']<=2147483647:
            raise ValueError('Invalid saved email-copy identity.')
    hint=value['target_hint']
    if hint is not None and (type(hint) is not str or len(hint)>254 or not re.fullmatch(r'[^\s@]\*\*\*@[^\s@]+',hint)):
        raise ValueError('Invalid saved email-copy destination hint.')
    if value['next_request_at'] is not None:result['next_request_at']=timestamp(value['next_request_at']).isoformat()
    if sending_ready is False and result['can_request']:
        result.update(can_request=False,blocked_reason='copy_unavailable')
    return result


def receipt_view(snapshot, request_id, secret, key,*,sending_ready=None):
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
    if snapshot.get('booking_product_enabled') is False:
        actions=dict(customer_message_code='contact_support',next_actions=['check_status','contact_support'])
    # Final route may further restrict resume when provider recovery is stale.
    # This read-only view never exposes payment-launch credentials.
    if 'resume_payment' in actions['next_actions']:
        actions = dict(customer_message_code='time_reserved', next_actions=['check_payment','check_status'])
    meeting_state=row['meeting_state']
    meet_url = row.get('meet_url') if state == Appointment.CONFIRMED and meeting_state == 'ready' else None
    if meet_url is not None and (not isinstance(meet_url,str) or not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',meet_url)):
        meet_url=None
        meeting_state='needs_attention'
    if state==Appointment.CONFIRMED and row.get('meeting_mode')=='google_meet' and meeting_state=='ready' and meet_url is None:
        meeting_state='needs_attention'
    captured=row['captured_paise']
    refunded=row['refunded_paise']
    if type(captured) is not int or type(refunded) is not int or not 0<=refunded<=captured:
        raise ValueError('Invalid saved payment amounts.')
    result=dict(
        captured_paise=captured,refunded_paise=refunded,
        request_id=str(request_id), appointment_state=state.value,
        order_state=evidence.order.value, payment_state=evidence.payment.value,
        service_name=row['service_name'], amount_paise=row['amount_paise'], currency=row['currency'],
        starts_at=timestamp(row['starts_at']).isoformat(), ends_at=timestamp(row['ends_at']).isoformat(),
        timezone=row['practice_timezone'], server_now=now.isoformat(), hold_expires_at=deadline.isoformat(),
        payment_checked_at=row.get('payment_checked_at'),
        payment_evidence_source='provider_observation' if row.get('payment_checked_at') else 'unobserved',
        meeting_state=meeting_state, meet_url=meet_url, acknowledgement_state=row['acknowledgement_state'],
        meeting_email_state=row['meeting_email_state'], **actions,
    )
    if 'booking_revision' in row:
        if type(row['booking_revision']) is not int or not 1<=row['booking_revision']<=2147483647:
            raise ValueError('Invalid saved booking revision.')
        result['booking_revision']=row['booking_revision']
    if 'meeting_mode' in row:
        if row['meeting_mode'] not in ('google_meet','internal'):raise ValueError('Invalid saved meeting mode.')
        result['meeting_mode']=row['meeting_mode']
    if 'email_copy' in row:
        result['email_copy']=email_copy_view(row['email_copy'],sending_ready=sending_ready)
    return result
