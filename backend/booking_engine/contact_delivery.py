"""Bounded Contact consumers. Database admission commits before provider I/O."""
from datetime import datetime,timezone
from .contact_messages import render_contact_message,seal_message,open_message
from .email_delivery import EmailFailure
from .receipt_view import timestamp
from .recovery import delay_for
from .google_delivery import ATTENTION
from .google_oauth import GoogleFailure
from .google_workspace import WorkspaceFailure


def run_contact_email_once(store,sender,keys):
    store.expire_enquiry_codes()
    job=store.claim_enquiry_delivery('email')
    if job is None:return {'processed':0}
    provider,error,attention=None,None,False
    try:
        if job.get('message_ciphertext') is not None:
            payload=open_message(keys,job)
            encrypted,digest=job['message_ciphertext'],job['message_digest']
        else:
            payload=render_contact_message(job,keys)
            encrypted,digest=seal_message(keys,job,payload)
        begun=store.begin_enquiry_send(job,encrypted,digest)
        if begun is None:return {'processed':0,'deferred':True}
        # Use the committed snapshot, not a newly rendered retry. No plaintext
        # message or unkeyed code-containing hash is stored in the database.
        payload=open_message(keys,begun)
        if timestamp(begun['deadline_at'])<=datetime.now(timezone.utc):
            raise EmailFailure('email_deadline_passed')
        provider=sender.send(payload,job['id'],begun['first_attempt_at'])
    except EmailFailure as failure:
        error=failure.code
        attention=error in ('email_message_invalid','email_snapshot_conflict','email_payload_invalid',
            'email_configuration_rejected','email_payload_rejected','email_retry_window_closed','email_deadline_passed')
    saved=store.finish_enquiry_delivery(job,provider,error,attention,delay_for(job['attempts']))
    return {'processed':int(saved),'retry':not saved}


def run_contact_google_once(store,services,*,transport=None):
    from .contact_records import copy_enquiry_record
    job=store.claim_enquiry_delivery('google')
    if job is None:return {'processed':0}
    provider,error,attention=None,None,False
    try:
        provider=copy_enquiry_record(store,services,job,transport=transport)
    except (GoogleFailure,WorkspaceFailure) as failure:
        error=str(failure);attention=error in ATTENTION
    saved=store.finish_enquiry_delivery(job,provider,error,attention,delay_for(job['attempts']))
    return {'processed':int(saved),'retry':not saved}
