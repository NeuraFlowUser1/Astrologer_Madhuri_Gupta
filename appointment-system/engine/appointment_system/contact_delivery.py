"""Bounded Contact consumers. Database admission commits before provider I/O."""
from datetime import datetime,timezone
from .contact_messages import render_contact_message,seal_message,open_message
from .email_delivery import EmailFailure
from .receipt_view import timestamp
from .recovery import delay_for
from .google_delivery import ATTENTION
from .google_oauth import GoogleFailure
from .google_workspace import WorkspaceFailure


def run_contact_email_once(store,sender,keys,*,kind=None):
    store.expire_enquiry_codes()
    if kind not in (None,'verification','notification'):raise ValueError('contact_lane_invalid')
    job=store.claim_enquiry_delivery(kind or 'email')
    if job is None:return {'processed':0}
    accepted=store.mail_acceptance('contact',job)
    if accepted in ('accepted','conflict'):return {'processed':1,'attention':accepted=='conflict'}
    job=dict(job,template_version=job.get('render_version',job.get('template_version',1)))
    provider,error,attention=None,None,False
    rejected,advice=False,0
    try:
        if job.get('message_ciphertext') is not None:
            payload=open_message(keys,job)
            encrypted,digest=job['message_ciphertext'],job['message_digest']
        else:
            payload=render_contact_message(job,keys)
            encrypted,digest=seal_message(keys,job,payload)
        binding=sender.binding(job,payload)
        begun=store.begin_enquiry_send(job,encrypted,digest,binding=binding)
        if begun is None:return {'processed':0,'deferred':True}
        job=dict(job,message_digest=begun.get('message_digest',digest))
        # Use the committed snapshot, not a newly rendered retry. No plaintext
        # message or unkeyed code-containing hash is stored in the database.
        payload=open_message(keys,dict(begun,payload=job['payload']))
        quota_retry=(begun['kind'] in ('acknowledgement','practice_notice') and not begun.get('prior_send_uncertain',False)
                     and begun.get('last_error_code') in ('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))
        if timestamp(begun['deadline_at'])<=datetime.now(timezone.utc) and not quota_retry:
            raise EmailFailure('email_deadline_passed')
        provider=sender.send(payload,job['id'],begun['first_attempt_at'],expected_reply_to=payload['reply_to'],binding=binding)
    except EmailFailure as failure:
        error=failure.code
        rejected=failure.definitely_rejected;advice=failure.retry_after
        attention=error in ('email_message_invalid','email_snapshot_conflict','email_payload_invalid',
            'email_configuration_rejected','email_payload_rejected','email_retry_window_closed','email_deadline_passed','email_idempotency_conflict')
    saved=store.finish_enquiry_delivery(job,provider,error,attention,max(advice,delay_for(job['attempts'])),rejected=rejected)
    return {'processed':int(saved),'retry':not saved}


def run_contact_google_once(store,services,*,transport=None,resource=None):
    from .contact_records import copy_enquiry_record
    if resource not in (None,'client_sheet','agency_sheet'):raise ValueError('contact_lane_invalid')
    job=store.claim_enquiry_delivery(resource or 'google')
    if job is None:return {'processed':0}
    provider,error,attention=None,None,False
    try:
        provider=copy_enquiry_record(store,services,job,transport=transport)
    except (GoogleFailure,WorkspaceFailure) as failure:
        error=str(failure);attention=error in ATTENTION
    saved=store.finish_enquiry_delivery(job,provider,error,attention,delay_for(job['attempts']))
    return {'processed':int(saved),'retry':not saved}
