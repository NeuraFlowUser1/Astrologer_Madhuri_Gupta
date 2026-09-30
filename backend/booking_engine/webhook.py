"""Authenticate raw payment events, then save only references for recovery."""

import hashlib
import json
import re
from dataclasses import dataclass,field

from .razorpay import identifier,merchant_identity,verify_signature

MAX_WEBHOOK_BYTES=131072
SUPPORTED_EVENTS=frozenset(('payment.authorized','payment.captured','payment.failed','order.paid',
                            'refund.processed'))


class InvalidWebhook(Exception):
    pass


class EventConflict(Exception):
    pass


@dataclass(frozen=True)
class WebhookAccount:
    merchant_id: str
    mode: str
    signing_secrets: tuple[str,...] = field(repr=False)

    def __post_init__(self):
        if (merchant_identity(self.merchant_id) is None or self.mode not in ('test','live')
                or not isinstance(self.signing_secrets,tuple) or not 1<=len(self.signing_secrets)<=2
                or any(not isinstance(v,str) or len(v)<16 for v in self.signing_secrets)):
            raise ValueError('Webhook account configuration is incomplete.')


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key]=value
    return result


def accept_webhook(store,account,body,signature,event_id,*,on_saved=None):
    if (not isinstance(body,bytes) or not 0<len(body)<=MAX_WEBHOOK_BYTES
            or not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',event_id)
            or not any(verify_signature(body,signature,secret) for secret in account.signing_secrets)):
        raise InvalidWebhook()
    try:
        event=json.loads(body,object_pairs_hook=_unique_object)
        if (not isinstance(event,dict) or event.get('entity')!='event'
                or merchant_identity(event.get('account_id'))!=merchant_identity(account.merchant_id)
                or event.get('event') not in SUPPORTED_EVENTS):
            raise ValueError('Unexpected event')
        payload=event.get('payload',{})
        payment=payload.get('payment',{}).get('entity',{})
        refund=payload.get('refund',{}).get('entity',{})
        order=payload.get('order',{}).get('entity',{})
        payment_id=payment.get('id') or refund.get('payment_id')
        order_id=payment.get('order_id') or order.get('id')
        if not payment_id and not order_id:
            raise ValueError('Missing provider reference')
        if payment_id:
            identifier(payment_id,'pay')
        if order_id:
            identifier(order_id,'order')
        minimal=dict(event=event['event'],payment_id=payment_id,order_id=order_id)
        if refund.get('id'):
            minimal['refund_id']=identifier(refund['id'],'rfnd')
    except (ValueError,TypeError,AttributeError,UnicodeError,RecursionError):
        raise InvalidWebhook() from None
    digest=hashlib.sha256(body).hexdigest()
    saved=store.save_provider_event('razorpay',merchant_identity(account.merchant_id),account.mode,event_id,digest,minimal)
    if saved!=digest:
        raise EventConflict()
    if on_saved is not None:
        on_saved()
    return {'received':True}
