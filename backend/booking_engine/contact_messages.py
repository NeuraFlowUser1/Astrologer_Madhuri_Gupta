"""Versioned contact emails. Codes exist only in memory or protected ciphertext."""
import html
import hmac
import json
from uuid import UUID
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
                                job['generation'],timestamp(job['code_expires_at']))
            subject='Verify your enquiry — Sarsa Jyotish Sansthan'
            lines=['Your enquiry verification code is: '+code,
                   'This code expires five minutes after it was requested. Enter it on the enquiry page.',
                   'If you did not request this code, you can ignore this email.']
        elif kind=='acknowledgement':
            subject='We received your enquiry — Sarsa Jyotish Sansthan'
            lines=['Your enquiry has been saved. This is not an appointment confirmation.',
                   'Enquiry reference: '+reference,
                   'To choose a consultation time, visit https://www.sarsajyotishsansthan.com/#/booking',
                   'For help, reply to this email.']
        elif kind=='practice_notice':
            subject='A new enquiry — Sarsa Jyotish Sansthan'
            lines=['A verified enquiry has been saved. This is not an appointment booking.',
                   'Enquiry reference: '+reference,
                   'Its record is queued for the Enquiries tab of your Sarsa client records.']
        else:raise ValueError()
        destination=REPLY_TO if kind=='practice_notice' else job['payload']['email']
        if destination!=job['destination']:raise ValueError()
        return {'from':SENDER,'to':[destination],'reply_to':REPLY_TO,'subject':subject,
                'text':'\n\n'.join(lines),'html':'<!doctype html><html lang="en"><body>'+''.join('<p>'+html.escape(v)+'</p>' for v in lines)+'</body></html>',
                'tags':[{'name':'project','value':PROJECT_TAG},{'name':'job_id','value':job_id}]}
    except (KeyError,ValueError,TypeError,AttributeError):
        raise EmailFailure('email_message_invalid',definitely_rejected=True) from None


def seal_message(keys,job,payload):
    body={'purpose':'sarsa004-contact-message-v1','job_id':str(UUID(str(job['id']))),'payload':payload}
    raw=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)
    return keys.cipher.encrypt(raw.encode()).decode(),keys.digest('message',raw)


def open_message(keys,job):
    from cryptography.fernet import InvalidToken
    try:
        encrypted=job['message_ciphertext']
        if not isinstance(encrypted,str) or len(encrypted)>32768:raise ValueError()
        raw=keys.cipher.decrypt(encrypted.encode()).decode()
        data=json.loads(raw)
        if (not isinstance(data,dict) or set(data)!={'purpose','job_id','payload'}
            or data['purpose']!='sarsa004-contact-message-v1' or data['job_id']!=str(UUID(str(job['id'])))
            or not hmac.compare_digest(keys.digest('message',raw),job['message_digest'])):raise ValueError()
        payload=data['payload']
        if payload['to']!=[job['destination']]:raise ValueError()
        return payload
    except (InvalidToken,KeyError,ValueError,TypeError,UnicodeError):
        raise EmailFailure('email_snapshot_conflict',definitely_rejected=True) from None
