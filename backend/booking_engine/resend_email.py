"""One bounded Resend send attempt for an already committed, frozen mail job.

The caller owns SQL claim, immutable content, budget and appointment revision
checks. This transport never retries or falls back to Gmail/SMTP. An accepted
provider ID is not a claim of delivery to the recipient's inbox.
"""

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

REPLY_TO='sarsajyotish@gmail.com'
ENDPOINT='https://api.resend.com/emails'


class EmailFailure(Exception):
    def __init__(self,code,*,definitely_rejected=False):
        super().__init__(code)
        self.code=code
        self.definitely_rejected=definitely_rejected


@dataclass(frozen=True)
class ResendSender:
    api_key:str=field(repr=False)
    transport:object=field(default=None,repr=False,compare=False)

    def __post_init__(self):
        if not isinstance(self.api_key,str) or not re.fullmatch(r're_[A-Za-z0-9_-]{16,256}',self.api_key):
            raise ValueError('Email sending configuration is incomplete.')

    @classmethod
    def from_environment(cls,environment):
        return cls(environment.get('SARSA_RESEND_API_KEY',''))

    def send(self,payload,job_id,first_attempt_at,*,now=None):
        instant=timestamp(now) if now else datetime.now(timezone.utc)
        try:
            first=timestamp(first_attempt_at)
            # A bounded clock difference between database and function must not
            # strand a freshly committed send. Large future times still fail closed.
            if first is None or first>instant+timedelta(seconds=5) or instant>=first+timedelta(hours=23):
                raise EmailFailure('email_retry_window_closed')
            job=str(UUID(str(job_id)))
            fields={'from','to','reply_to','subject','text','html','tags'}
            if (not isinstance(payload,dict) or set(payload)!=fields or payload['from']!=SENDER or payload['reply_to']!=REPLY_TO
                    or not isinstance(payload['to'],list) or len(payload['to'])!=1
                    or payload['tags']!=[{'name':'project','value':PROJECT_TAG},{'name':'job_id','value':job}]
                    or any(not isinstance(payload[n],str) or not payload[n] for n in ('subject','text','html'))
                    or len(payload['subject'])>200 or any(c in payload['subject'] for c in '\r\n')):
                raise ValueError()
            validate_email(payload['to'][0],check_deliverability=False)
            raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            if len(raw)>16384:
                raise ValueError()
        except (ValueError,TypeError,EmailNotValidError):
            raise EmailFailure('email_payload_invalid',definitely_rejected=True) from None
        try:
            with httpx.Client(transport=self.transport,timeout=10,trust_env=False,follow_redirects=False) as client:
                with client.stream('POST',ENDPOINT,content=raw,headers={
                    'Authorization':'Bearer '+self.api_key,'Content-Type':'application/json','Accept':'application/json',
                    'Idempotency-Key':'sarsa004/'+job}) as response:
                    if response.status_code!=200:
                        rejected=response.status_code in (400,401,403,404,405,422,429)
                        code=('email_allowance_or_rate_limit' if response.status_code==429 else
                              'email_configuration_rejected' if response.status_code in (401,403,404,405) else
                              'email_payload_rejected' if response.status_code in (400,422) else 'email_send_unconfirmed')
                        raise EmailFailure(code,definitely_rejected=rejected)
                    if response.headers.get('content-type','').split(';')[0].strip()!='application/json':
                        raise EmailFailure('email_send_unconfirmed')
                    body=bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body)>16384:
                            raise EmailFailure('email_send_unconfirmed')
                    result=json.loads(body,object_pairs_hook=_unique_object)
                    if not isinstance(result,dict):
                        raise ValueError()
                    return str(UUID(result['id']))
        except (httpx.HTTPError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise EmailFailure('email_send_unconfirmed') from None
