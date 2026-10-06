"""Authenticate raw payment events, then save only references for recovery."""

import hashlib
import json
import re
from dataclasses import dataclass,field

from .razorpay import identifier,merchant_identity,verify_signature
from .financial_resources import RESOURCE_EVENTS,signed_resource
from .razorpay import RazorpayFailure

MAX_WEBHOOK_BYTES=131072
SUPPORTED_EVENTS=frozenset(('payment.authorized','payment.captured','payment.failed','order.paid')) | RESOURCE_EVENTS


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
                or any(not isinstance(v,str) or not 16<=len(v)<=8192 for v in self.signing_secrets)):
            raise ValueError('Webhook account configuration is incomplete.')

@dataclass(frozen=True,repr=False)
class WebhookRegistry:
    accounts:tuple[WebhookAccount,...]=field(repr=False)

    def __post_init__(self):
        if type(self.accounts) is not tuple or not 1<=len(self.accounts)<=8 or any(type(a) is not WebhookAccount for a in self.accounts):
            raise ValueError('Invalid webhook registry.')

    def authenticate(self,body,signature):
        matches=[account for account in self.accounts
                 if any(verify_signature(body,signature,secret) for secret in account.signing_secrets)]
        if len(matches)!=1:raise InvalidWebhook()
        return matches[0]


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key]=value
    return result


def accept_webhook(store,account,body,signature,event_id,*,on_saved=None):
    if type(account) is WebhookRegistry:
        if type(body) is not bytes or not 0<len(body)<=MAX_WEBHOOK_BYTES:raise InvalidWebhook()
        account=account.authenticate(body,signature)
    if (not isinstance(body,bytes) or not 0<len(body)<=MAX_WEBHOOK_BYTES
            or not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',event_id)
            or not any(verify_signature(body,signature,secret) for secret in account.signing_secrets)):
        raise InvalidWebhook()
    try:
        event=json.loads(body,object_pairs_hook=_unique_object)
        if (not isinstance(event,dict) or event.get('entity')!='event'
                or merchant_identity(event.get('account_id'))!=merchant_identity(account.merchant_id)
                or not isinstance(event.get('event'),str)):
            raise ValueError('Unexpected event')
        if event['event'] not in SUPPORTED_EVENTS:
            if getattr(store,'buffers_original_events',False) is True:
                from .provider_ingress import persist_verified
                digest=hashlib.sha256(body).hexdigest()
                saved=persist_verified(store,'razorpay',merchant_identity(account.merchant_id),account.mode,event_id,digest,
                    {'event':event['event'],'unmapped':True},body)
                if saved!=digest:raise EventConflict()
                if on_saved is not None:on_saved()
                return {'received':True,'code':'payment_event_saved_for_review'}
            return {'received':True,'code':'payment_event_unsupported'}
        resource=signed_resource(event)
        payload=event.get('payload',{})
        payment=payload.get('payment',{}).get('entity',{})
        refund=payload.get('refund',{}).get('entity',{})
        order=payload.get('order',{}).get('entity',{})
        payment_id=payment.get('id') or (resource['payment_id'] if resource else None)
        order_id=payment.get('order_id') or order.get('id')
        if not payment_id and not order_id:
            raise ValueError('Missing provider reference')
        if payment_id:
            identifier(payment_id,'pay')
            if resource and payment_id != resource['payment_id']:
                raise ValueError('Financial parent conflict')
        if order_id:
            identifier(order_id,'order')
        minimal=dict(event=event['event'],payment_id=payment_id,order_id=order_id)
        if resource:
            minimal['resource_fact']=resource
    except (ValueError,TypeError,AttributeError,UnicodeError,RecursionError,RazorpayFailure):
        raise InvalidWebhook() from None
    digest=hashlib.sha256(body).hexdigest()
    from .provider_ingress import persist_verified
    saved=persist_verified(store,'razorpay',merchant_identity(account.merchant_id),account.mode,event_id,digest,minimal,body)
    if saved!=digest:
        raise EventConflict()
    if on_saved is not None:
        on_saved()
    return {'received':True}
