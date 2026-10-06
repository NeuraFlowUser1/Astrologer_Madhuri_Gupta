"""Versioned contact emails. Codes exist only in memory or protected ciphertext."""
import html
import hmac
import json
from uuid import UUID
from .configuration import label,origin
from .mail_identity import tags_for
from .email_events import SENDER,PROJECT_TAG
from .resend_email import REPLY_TO,EmailFailure
from .receipt_view import timestamp


def render_contact_message(job,keys):
    try:
        job_id=str(UUID(str(job['id'])))
        reference=str(UUID(str(job['request_id'])))
        kind=job['kind']
        if kind=='verification':
            code=keys.open_code(job['code_ciphertext'],reference,job['payload']['email'],
                                job['generation'],timestamp(job['code_expires_at']),format=job['code_format'])
            subject='Verify your enquiry — '+label()
            lines=['Your enquiry verification code is: '+code,
                   'This code expires five minutes after it was requested. Enter it on the enquiry page.',
                   'If you did not request this code, you can ignore this email.']
        elif kind=='acknowledgement':
            subject='We received your enquiry — '+label()
            invitation='For information, visit '+origin()
            lines=['Your enquiry has been saved. This is not an appointment confirmation.',
                   'Enquiry reference: '+reference,invitation,'For help, reply to this email.']
        elif kind=='practice_notice':
            subject='A new enquiry — '+label()
            lines=['A verified enquiry has been saved. This is not an appointment booking.',
                   'Enquiry reference: '+reference,
                   'Its record is queued for your enquiry records.']
        else:raise ValueError()
        destination=REPLY_TO if kind=='practice_notice' else job['payload']['email']
        if destination!=job['destination']:raise ValueError()
        reply=job['payload']['email'] if kind=='practice_notice' and job.get('template_version',1)>=2 else REPLY_TO
        return {'from':SENDER,'to':[destination],'reply_to':reply,'subject':subject,
                'text':'\n\n'.join(lines),'html':'<!doctype html><html lang="en"><body>'+''.join('<p>'+html.escape(v)+'</p>' for v in lines)+'</body></html>',
                'tags':tags_for(job_id,job.get('template_version',1))}
    except (KeyError,ValueError,TypeError,AttributeError):
        raise EmailFailure('email_message_invalid',definitely_rejected=True) from None


def seal_message(keys,job,payload):
    from .serialization import canonical
    identifier=str(UUID(str(job['id'])))
    body={'purpose':'appointment:v1:enquiry-message','job_id':identifier,'payload':payload,
          'digest_key_id':keys.digest_key.active}
    raw=canonical(body).decode()
    return keys.cipher.seal(keys.record('message',identifier),body),keys.digest('message',identifier,raw)


def open_message(keys,job):
    from cryptography.fernet import InvalidToken
    try:
        encrypted=job['message_ciphertext']
        identifier=str(UUID(str(job['id'])));format=job['message_format']
        if not isinstance(encrypted,str) or len(encrypted)>32768:raise ValueError()
        data,raw_bytes=keys.cipher.read(keys.record('message',identifier),encrypted,
            format=format,purpose='appointment:v1:enquiry-message')
        raw=raw_bytes.decode()
        expected={'purpose','job_id','payload'}|({'digest_key_id'} if format=='v1' else set())
        digest=(keys.digest('message',identifier,raw,key_id=data['digest_key_id']) if format=='v1'
                else keys.digest('message',raw,format=job['message_digest_format']))
        if (set(data)!=expected or data['job_id']!=identifier
            or not hmac.compare_digest(digest,job['message_digest'])):raise ValueError()
        payload=data['payload']
        if payload['to']!=[job['destination']]:raise ValueError()
        old_versioned=job.get('mail_format') in ('resend-legacy-job-v1','resend-legacy-untagged-job-v1')
        expected_reply=job['payload']['email'] if job['kind']=='practice_notice' and (job.get('template_version',1)>=2 or old_versioned) else REPLY_TO
        if payload['reply_to']!=expected_reply:raise ValueError()
        return payload
    except (InvalidToken,KeyError,ValueError,TypeError,UnicodeError):
        raise EmailFailure('email_snapshot_conflict',definitely_rejected=True) from None
