"""One committed, protected booking-code send. No plaintext code is persisted."""
from datetime import datetime,timezone
import html,hmac

from .configuration import label
from .mail_identity import MailIdentity,tags_for
from .resend_email import EmailFailure
from .receipt_view import timestamp
from .serialization import canonical
from .recovery import delay_for


def message(keys,job):
    try:
        code=keys.open_code(job);identity=MailIdentity.current()
        lines=['Your appointment email code is: '+code,
               'It expires five minutes after it was requested. Enter it on the booking page.',
               'This code verifies your email. It does not confirm an appointment or payment.',
               'If you did not request it, ignore this email.',label()]
        return {'from':identity.sender,'to':[job['destination']],'reply_to':identity.reply_to,
          'subject':'Verify your appointment email — '+label(),'text':'\n\n'.join(lines),
          'html':'<!doctype html><html lang="en"><body>'+''.join('<p>'+html.escape(line)+'</p>' for line in lines)+'</body></html>',
          'tags':tags_for(job['id'],job['template_version'])}
    except (KeyError,ValueError,TypeError,AttributeError):
        raise EmailFailure('email_message_invalid',definitely_rejected=True) from None


def seal(keys,job,payload):
    value={'purpose':'appointment:v1:booking-verification-message','job_id':job['id'],
           'digest_key_id':keys.digest_key.active,'payload':payload}
    raw=canonical(value).decode()
    return keys.cipher.seal('booking-verification-message:'+job['id'],value),keys.digest('message',job['id'],raw)


def open_message(keys,job):
    try:
        value,raw=keys.cipher.read('booking-verification-message:'+job['id'],job['message_ciphertext'],
                                   purpose='appointment:v1:booking-verification-message')
        if (value['job_id']!=job['id'] or value['payload']['to']!=[job['destination']]
                or not hmac.compare_digest(keys.digest('message',job['id'],raw.decode(),key_id=value['digest_key_id']),job['message_digest'])):
            raise ValueError()
        return value['payload']
    except (KeyError,ValueError,TypeError,UnicodeError):
        raise EmailFailure('email_snapshot_conflict',definitely_rejected=True) from None


def run_booking_code_once(store,sender,keys,*,job=None):
    saved=store.claim_booking_code(job)
    if saved is None:return {'processed':0}
    provider,error,review=None,None,False
    rejected=False;advice=0
    try:
        if saved['message_ciphertext'] is not None:
            payload=open_message(keys,saved);encrypted=saved['message_ciphertext'];digest=saved['message_digest']
        else:
            payload=message(keys,saved);encrypted,digest=seal(keys,saved,payload)
        binding=sender.binding(saved,payload)
        begun=store.begin_booking_code(saved,encrypted,digest,binding)
        if begun is None:return {'processed':0,'deferred':True}
        payload=open_message(keys,begun)
        if timestamp(begun['code_expires_at'])<=datetime.now(timezone.utc):
            raise EmailFailure('email_deadline_passed')
        provider=sender.send(payload,saved['id'],begun['first_attempt_at'],binding=binding,expected_reply_to=payload['reply_to'])
    except EmailFailure as failure:
        error=failure.code;rejected=failure.definitely_rejected;advice=failure.retry_after
        review=error in ('email_snapshot_conflict','email_message_invalid','email_payload_invalid','email_configuration_rejected',
                        'email_payload_rejected','email_retry_window_closed','email_idempotency_conflict')
    accepted=store.finish_booking_code(saved,provider,error,review,max(advice,delay_for(saved['attempts'])),rejected)
    return {'processed':int(accepted),'retry':not accepted}
