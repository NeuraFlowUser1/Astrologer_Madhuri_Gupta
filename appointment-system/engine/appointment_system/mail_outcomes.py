"""Allowlisted mail failures and bounded provider retry advice."""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

def retry_after(value, *, now=None):
    if not isinstance(value,str) or not 1<=len(value)<=80:
        return 0
    if value.isascii() and value.isdigit() and len(value)<=6:
        return min(86400,int(value))
    try:
        date=parsedate_to_datetime(value)
        if date.tzinfo is None:
            return 0
        seconds=(date-(now or datetime.now(timezone.utc))).total_seconds()
        return min(86400,max(0,math.ceil(seconds)))
    except (ValueError,TypeError,OverflowError):
        return 0

def classify(status, body, headers, *, now=None):
    name=body.get('name') if isinstance(body,dict) else None
    wait=retry_after(headers.get('Retry-After',''),now=now)
    if status==429:
        quota=name if name in ('daily_quota_exceeded','monthly_quota_exceeded') else None
        return quota or 'provider_rate_limited',True,True,max(wait,86400 if quota else 30)
    if status==409 and name=='invalid_idempotent_request':
        return 'email_idempotency_conflict',False,False,0
    if status==409 and name=='concurrent_idempotent_requests':
        return 'email_idempotency_in_progress',False,True,max(30,wait)
    if status in (400,401,403,404,405,422):
        return ('email_configuration_rejected' if status in (401,403,404,405) else 'email_payload_rejected'),True,False,wait
    return 'email_send_unconfirmed',False,status in (408,409) or status>=500,max(30,wait)

def unique_json(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate_response_key')
        result[key]=value
    return result
