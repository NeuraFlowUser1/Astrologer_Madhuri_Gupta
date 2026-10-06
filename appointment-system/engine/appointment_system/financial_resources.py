"""Minimized refund/dispute facts, separate from appointment and money totals.

Only a pinned provider GET can mark a fact as fetched. A signed notification is
retained with its own provenance while a failed GET stays recoverable. No
method in this module transfers money or changes appointment capacity.
"""
import hashlib
import json
from .razorpay import RazorpayFailure, identifier

REFUND_EVENTS = frozenset(('refund.created','refund.processed','refund.failed','refund.speed_changed'))
DISPUTE_EVENTS = frozenset('payment.dispute.' + name for name in
                          ('created','won','lost','closed','under_review','action_required'))
RESOURCE_EVENTS = REFUND_EVENTS | DISPUTE_EVENTS
MAX_UNIX_TIME = 4102444800


def _integer(value, *, minimum=0, maximum=MAX_UNIX_TIME):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid provider number.')
    return value


def resource_fact(value, kind, *, resource_id=None, payment_id=None):
    """Validate provider shape and retain no notes, card or dispute evidence."""
    try:
        if not isinstance(value,dict) or kind not in ('refund','dispute') or value.get('entity') != kind:
            raise ValueError()
        identity = identifier(value.get('id'),'rfnd' if kind == 'refund' else 'disp')
        payment = identifier(value.get('payment_id'),'pay')
        if (resource_id is not None and identity != resource_id) or (payment_id is not None and payment != payment_id):
            raise ValueError()
        statuses = ('pending','processed','failed') if kind == 'refund' else ('open','under_review','won','lost','closed')
        if value.get('status') not in statuses or value.get('currency') != 'INR':
            raise ValueError()
        fact = dict(version=1,kind=kind,id=identity,payment_id=payment,status=value['status'],
                    amount=_integer(value.get('amount'),minimum=1,maximum=2147483647),
                    currency='INR',created_at=_integer(value.get('created_at'),minimum=1),
                    updated_at=None,respond_by=None,speed_requested=None,speed_processed=None)
        if value.get('updated_at') is not None:
            fact['updated_at'] = _integer(value['updated_at'],minimum=fact['created_at'])
        if kind == 'dispute' and value.get('respond_by') is not None:
            fact['respond_by'] = _integer(value['respond_by'],minimum=fact['created_at'])
        if kind == 'refund':
            for name in ('speed_requested','speed_processed'):
                speed = value.get(name)
                if speed is not None and speed not in ('normal','optimum','instant'):
                    raise ValueError()
                fact[name] = speed
        return fact
    except (ValueError,TypeError,KeyError,AttributeError):
        raise RazorpayFailure('financial_resource_invalid') from None


def signed_resource(event):
    kind = event.get('event')
    if kind not in RESOURCE_EVENTS:
        return None
    family = 'refund' if kind in REFUND_EVENTS else 'dispute'
    try:
        return resource_fact(event['payload'][family]['entity'],family)
    except (ValueError,TypeError,KeyError,AttributeError):
        raise RazorpayFailure('financial_resource_invalid') from None


def digest(fact):
    return hashlib.sha256(json.dumps(fact,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def fetch_resource(adapter, signed):
    response = (adapter.refund(signed['id']) if signed['kind']=='refund' else adapter.dispute(signed['id']))
    return resource_fact(response,signed['kind'],resource_id=signed['id'],payment_id=signed['payment_id'])


def payment_fact(value, *, payment_id, order_id, amount):
    """Validate the fetched parent without confirming a disputed appointment."""
    try:
        if (not isinstance(value,dict) or value.get('entity')!='payment' or value.get('id')!=payment_id
                or value.get('order_id')!=order_id or value.get('currency')!='INR'
                or _integer(value.get('amount'),minimum=1,maximum=2147483647)!=amount
                or value.get('status') not in ('created','authorized','captured','refunded','failed')
                or type(value.get('captured')) is not bool):
            raise ValueError()
        refunded = _integer(value.get('amount_refunded'),maximum=amount)
        return dict(entity='payment',id=payment_id,order_id=order_id,status=value['status'],
                    amount=amount,currency='INR',amount_refunded=refunded,captured=value['captured'])
    except (ValueError,TypeError,AttributeError):
        raise RazorpayFailure('financial_parent_invalid') from None


def recovery_delay(job):
    """Database timestamps choose cadence; age never removes the obligation."""
    from datetime import datetime,timedelta,timezone
    def instant(value):
        if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
        if not isinstance(value,datetime) or value.tzinfo is None:raise ValueError('Invalid recovery timestamp')
        return value.astimezone(timezone.utc)
    now=instant(job['server_now'])
    started=job.get('attempted_at') or job.get('created_at') or job.get('received_at') or now
    age=max(timedelta(0),now-instant(started))
    return 86400 if age>=timedelta(days=7) else 3600 if age>=timedelta(days=1) else 900
