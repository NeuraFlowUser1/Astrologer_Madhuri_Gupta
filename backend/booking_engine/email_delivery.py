"""Bounded durable mail consumer; never run automatically at application import."""
import secrets
from datetime import datetime,timezone
from .receipt_view import timestamp
from .email_messages import render_message, message_hash
from .resend_email import EmailFailure


def run_email_delivery_once(store,sender):
    job=store.claim_email_delivery()
    if job is None:return {'processed':0}
    provider=None
    error=None
    attention=False
    try:
        payload=job.get('message_snapshot')
        if payload is None:
            payload=render_message(job)
        digest=message_hash(payload)
        if job.get('message_hash') is not None and job['message_hash']!=digest:
            raise EmailFailure('email_snapshot_conflict',definitely_rejected=True)
        # This returns only after the first-attempt and budget transaction commits.
        # A storage exception must propagate without calling the provider.
        begun=store.begin_email_send(job,payload,digest)
        if begun is None:return {'processed':0,'deferred':True}
        if timestamp(begun['send_deadline_at'])<=datetime.now(timezone.utc):
            raise EmailFailure('email_deadline_passed')
        provider=sender.send(begun['message_snapshot'],job['id'],begun['first_attempt_at'])
    except EmailFailure as failure:
        error=failure.code
        attention=error in ('email_message_invalid','email_payload_invalid','email_snapshot_conflict','email_retry_window_closed','email_configuration_rejected','email_payload_rejected','email_deadline_passed')
    delay=min(900,15*(2**min(job['attempts'],5))+secrets.randbelow(16))
    saved=store.finish_email_delivery(job,provider,error,attention,delay)
    return {'processed':1 if saved else 0,'retry':not saved}
