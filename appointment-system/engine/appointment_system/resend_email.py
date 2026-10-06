"""One bounded Resend send attempt for an already committed, frozen mail job.

The caller owns SQL claim, immutable content, budget and appointment revision
checks. This transport never retries or falls back to Gmail/SMTP. An accepted
provider ID is not a claim of delivery to the recipient's inbox.
"""
from .configuration import installation,owners,sender,project_id,label,worker_origin,origin
from .request_budget import observe_provider

from .request_budget import BudgetExpired,provider_timeout,chunks,remaining

import json
import re
from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
from uuid import UUID

import httpx
from email_validator import validate_email,EmailNotValidError

from .email_events import SENDER,PROJECT_TAG
from .receipt_view import timestamp
from .webhook import _unique_object
from .mail_outcomes import classify
from .mail_identity import MailIdentity,new_key,retained_key
from .email_configuration import connection

REPLY_TO=sender()['reply_to']
ENDPOINT='https://api.resend.com/emails'


def tagged_for(tags,job):
    bound=MailIdentity.current().binding(tags)
    return bound is not None and bound[0]==str(job)


class EmailFailure(Exception):
    def __init__(self,code,*,definitely_rejected=False,retryable=False,retry_after=0):
        super().__init__(code)
        self.code=code
        self.definitely_rejected=definitely_rejected
        self.retryable=retryable
        self.retry_after=retry_after


@dataclass(frozen=True)
class ResendSender:
    api_key:str=field(repr=False)
    transport:object=field(default=None,repr=False,compare=False)
    declared:object=field(default=None,repr=False,compare=False)

    def __post_init__(self):
        if not isinstance(self.api_key,str) or not re.fullmatch(r're_[A-Za-z0-9_-]{16,256}',self.api_key):
            raise ValueError('Email sending configuration is incomplete.')

    @classmethod
    def from_environment(cls,environment):
        declared=connection(environment['BOOKING_EMAIL_CONNECTION'])
        return cls(declared.pinned(declared.active_key_id),declared=declared)

    def binding(self,job,payload):
        """Select a saved identity before SQL freezes the first send attempt."""
        try:
            identifier=str(UUID(str(job['id'])))
            format=job.get('mail_format') or 'resend-v1'
            identity=self.declared.identity(format) if self.declared else MailIdentity.current()
            account=self.declared.account_id if self.declared else identity.event_account_id
            version=(job.get('mail_credential_version') or
                     (self.declared.active_key_id if self.declared else 'injected-test-key'))
            if self.declared:self.declared.pinned(version)
            if job.get('mail_account_id') not in (None,account) or not identity.accepts(payload,identifier):raise ValueError()
            key=job.get('mail_idempotency_key')
            if key is None:
                if job.get('first_attempt_at') is not None or format!='resend-v1':raise ValueError()
                key=new_key(identifier,int(identity.binding(payload['tags'])[1]))
            key=retained_key(key,identifier,identity,booking_id=job.get('booking_id'),
                            kind=job.get('mail_key_kind'),role=job.get('mail_key_role'))
            return {'account_id':account,'event_account_id':identity.event_account_id,
                    'credential_version':version,'format':format,'idempotency_key':key}
        except (ValueError,TypeError,KeyError,AttributeError):
            raise EmailFailure('email_snapshot_conflict',definitely_rejected=True) from None

    @observe_provider('resend')
    def send(self,payload,job_id,first_attempt_at,*,now=None,expected_reply_to=REPLY_TO,binding=None):
        instant=timestamp(now) if now else datetime.now(timezone.utc)
        try:
            first=timestamp(first_attempt_at)
            # A bounded clock difference between database and function must not
            # strand a freshly committed send. Large future times still fail closed.
            if first is None or first>instant+timedelta(seconds=5) or instant>=first+timedelta(hours=23):
                raise EmailFailure('email_retry_window_closed')
            job=str(UUID(str(job_id)))
            binding=binding or self.binding({'id':job},payload)
            if set(binding)!={'account_id','event_account_id','credential_version','format','idempotency_key'}:raise ValueError()
            identity=self.declared.identity(binding['format']) if self.declared else MailIdentity.current()
            if binding['account_id']!=(self.declared.account_id if self.declared else identity.event_account_id):raise ValueError()
            if binding['event_account_id']!=identity.event_account_id:raise ValueError()
            api_key=self.declared.pinned(binding['credential_version']) if self.declared else self.api_key
            fields={'from','to','reply_to','subject','text','html'}
            if identity.format!='resend-legacy-untagged-job-v1':fields.add('tags')
            reply=payload.get('reply_to') if isinstance(payload,dict) else None
            practice=payload.get('to')==[identity.reply_to] if isinstance(payload,dict) else False
            if (not isinstance(payload,dict) or set(payload)!=fields or not identity.accepts(payload,job) or reply!=expected_reply_to
                    or (expected_reply_to!=identity.reply_to and not practice)
                    or not isinstance(payload['to'],list) or len(payload['to'])!=1
                    or any(not isinstance(payload[n],str) or not payload[n] for n in ('subject','text','html'))
                    or len(payload['subject'])>200 or any(c in payload['subject'] for c in '\r\n')):
                raise ValueError()
            validate_email(payload['to'][0],check_deliverability=False,test_environment=installation()['environment']!='production')
            validate_email(reply,check_deliverability=False,test_environment=installation()['environment']!='production')
            raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            if len(raw)>16384:
                raise ValueError()
        except (ValueError,TypeError,EmailNotValidError):
            raise EmailFailure('email_payload_invalid',definitely_rejected=True) from None
        try:
            with httpx.Client(transport=self.transport,timeout=provider_timeout(10),trust_env=False,follow_redirects=False) as client:
                with client.stream('POST',ENDPOINT,content=raw,headers={
                    'Authorization':'Bearer '+api_key,'Content-Type':'application/json','Accept':'application/json',
                    'Idempotency-Key':binding['idempotency_key']}) as response:
                    body=bytearray()
                    for chunk in chunks(response):
                        body.extend(chunk)
                        if len(body)>16384:
                            raise EmailFailure('email_send_unconfirmed')
                    try:result=json.loads(body,object_pairs_hook=_unique_object)
                    except (ValueError,UnicodeError):result=None
                    if response.status_code!=200:
                        code,rejected,retryable,delay=classify(response.status_code,result,response.headers,now=instant)
                        raise EmailFailure(code,definitely_rejected=rejected,retryable=retryable,retry_after=delay)
                    if response.headers.get('content-type','').split(';')[0].strip()!='application/json':
                        raise EmailFailure('email_send_unconfirmed')
                    if not isinstance(result,dict):
                        raise ValueError()
                    return str(UUID(result['id']))
        except (BudgetExpired,httpx.HTTPError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise EmailFailure('email_send_unconfirmed') from None
