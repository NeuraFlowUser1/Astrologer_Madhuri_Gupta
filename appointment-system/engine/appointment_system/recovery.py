"""Bounded recovery of saved work; never creates another Razorpay order.

One claimed job per call bounds provider requests; lease expiry fences job
completion if a slow provider outlasts it. The external
scheduler repeats these calls. No appointment-date/receipt-expiry cutoff can
silently discard unresolved money. Missing credentials leave work pending.
"""

from .payment_evidence import fetch_and_record,PaymentEvidence
from .razorpay import Razorpay,RazorpayFailure,identifier,merchant_identity,saved_order_receipt
from .receipt_view import timestamp
from .financial_resources import fetch_resource,payment_fact,digest,recovery_delay


class Accounts:
    def __init__(self,adapters,*,current_versions):
        self._adapters={}
        for adapter in adapters:
            c=adapter.credentials
            key=(merchant_identity(c.merchant_id),c.mode,c.version)
            if key in self._adapters:
                raise ValueError('Duplicate payment credential identity.')
            self._adapters[key]=adapter
        self._current=dict(current_versions)

    def pinned(self,merchant,mode,version):
        adapter=self._adapters.get((merchant_identity(merchant),mode,version))
        if adapter is None:
            raise RazorpayFailure('payment_configuration_missing')
        return adapter

    def current(self,merchant,mode):
        identity=merchant_identity(merchant)
        return self.pinned(identity,mode,self._current.get((identity,mode)))


def _items(response):
    if (not isinstance(response,dict) or response.get('entity')!='collection'
            or not isinstance(response.get('items'),list) or len(response['items'])>100
            or type(response.get('count')) is not int or response['count']!=len(response['items'])
            or any(not isinstance(item,dict) for item in response['items'])):
        raise RazorpayFailure('payment_response_invalid')
    return response['items']


def _matching_order(order,job):
    try:
        identifier(order.get('id'),'order')
    except (ValueError,AttributeError):
        return False
    return (order.get('entity')=='order' and order.get('receipt')==saved_order_receipt(job)
            and type(order.get('amount')) is int and order['amount']==job['amount_paise']
            and order.get('currency')==job['currency'] and order.get('partial_payment',False) is False)


def delay_for(attempt):
    return min(3600,15*(2**min(max(int(attempt)-1,0),8)))


def run_payment_recovery_once(store,accounts):
    jobs=store.claim_payment_recovery(limit=1)
    if not jobs:
        return {'processed':0}
    job=jobs[0]
    cursor,search_skip=job['recovery_cursor'],job['order_search_skip']
    delay=recovery_delay(job) if job.get('server_now') else delay_for(job['attempts'])
    error=None
    try:
        if job['state']=='not_attempted':
            if timestamp(job['hold_expires_at'])<=timestamp(job['server_now']):
                store.abandon_unattempted(job['context_id'],job['booking_id'])
            delay=15
        else:
            adapter=accounts.pinned(job['merchant_id'],job['mode'],job['credential_version'])
            order_id=job['provider_order_id']
            if not order_id:
                items=_items(adapter.orders_page(job['booking_id'],skip=search_skip,
                    receipt_format=job['provider_receipt_format'],
                    **({'from_time':int(timestamp(job['order_search_from']).timestamp()),
                        'to_time':int(timestamp(job['order_search_until']).timestamp())} if isinstance(adapter,Razorpay) else {})))
                candidates=[item for item in items if item.get('receipt')==saved_order_receipt(job)]
                if any(not _matching_order(item,job) for item in candidates):
                    raise RazorpayFailure('payment_order_mismatch')
                matches=candidates
                if len(matches)>1:
                    store.advance_order_search(job,sorted(set(item['id'] for item in matches))[:2],len(items)<100)
                    raise RazorpayFailure('payment_order_mismatch')
                result=store.advance_order_search(job,sorted(set(item['id'] for item in matches))[:2],len(items)<100)
                if not isinstance(result,dict):raise RazorpayFailure('payment_response_invalid')
                search_skip=search_skip+90 if len(items)==100 else 0
                if result.get('code')=='conflict':raise RazorpayFailure('payment_order_mismatch')
                if result.get('code')=='match':
                    order_id=identifier(result.get('order_id'),'order')
                    remote=adapter.order(order_id)
                    if not _matching_order(remote,job):raise RazorpayFailure('payment_order_mismatch')
                    store.record_order_creation(job['context_id'],job['booking_id'],job,order_id)
            if order_id:
                items=_items(adapter.order_payments(order_id))
                payment_ids=[]
                for item in items:
                    if item.get('entity')!='payment' or item.get('order_id')!=order_id:
                        raise RazorpayFailure('payment_response_invalid')
                    try:
                        payment_ids.append(identifier(item.get('id'),'pay'))
                    except ValueError:
                        raise RazorpayFailure('payment_response_invalid') from None
                payment_ids=sorted(set(payment_ids))
                if payment_ids:
                    start=cursor%len(payment_ids)
                    selected=payment_ids[start:start+2]
                    for payment_id in selected:
                        fetch_and_record(store,adapter,job['context_id'],job['booking_id'],payment_id)
                    cursor=(start+len(selected))%len(payment_ids)
                # Empty list is only an observation. Never abandon/re-create.
    except RazorpayFailure as exc:
        # Generic provider faults retain the durable job; no sensitive provider
        # response is written to a public message or log.
        error=exc.code
    saved=store.finish_payment_recovery(job,delay,cursor,search_skip,error=error)
    return {'processed':1 if saved is True else 0,'retry':saved is not True or error is not None}


def run_payment_event_once(store,accounts,*,source=None):
    if source not in (None,'resource','inbox'):raise ValueError('payment_lane_invalid')
    resources=[] if source=='inbox' else store.claim_financial_resources()
    if resources:
        job=resources[0];error=None
        try:
            provider=accounts.pinned(job['merchant_id'],job['mode'],job['credential_version'])
            parent=payment_fact(provider.payment(job['payment_id']),payment_id=job['payment_id'],
                order_id=job['order_id'],amount=job['amount_paise'])
            fact=fetch_resource(provider,job['fact'])
            outcome=store.observe_financial_resource(job['booking_id'],job,fact,'provider_fetch',digest(fact),parent)
            if outcome.get('attention_reason'):raise RazorpayFailure(outcome['attention_reason'])
            if fact['kind']=='refund':
                store.observe_payment(job['context_id'],job['booking_id'],job,PaymentEvidence.model_validate(parent))
        except RazorpayFailure as failure:error=failure.code
        saved=store.finish_financial_resource(job,recovery_delay(job),error)
        return {'processed':int(saved is True),'retry':saved is not True or error is not None}
    if source=='resource':return {'processed':0}
    jobs=store.claim_payment_events(limit=1)
    if not jobs:
        return {'processed':0}
    job=jobs[0]
    done=False
    error='payment_order_not_linked'
    try:
        adapter=accounts.current(job['account_id'],job['environment'])
        reference=job['payload']
        payment_id,order_id=reference.get('payment_id'),reference.get('order_id')
        if not order_id and payment_id:
            payment=adapter.payment(payment_id)
            if not isinstance(payment,dict) or payment.get('id')!=payment_id:
                raise RazorpayFailure('payment_response_invalid')
            order_id=payment.get('order_id')
        if not order_id:
            raise RazorpayFailure('payment_response_invalid')
        booking=store.find_order(job['account_id'],job['environment'],order_id)
        if booking:
            pinned=accounts.pinned(booking['merchant_id'],booking['mode'],booking['credential_version'])
            resource=reference.get('resource_fact')
            if resource:
                intent=store.order_intent(booking['context_id'],booking['booking_id'])
                parent=payment_fact(pinned.payment(payment_id),payment_id=payment_id,order_id=order_id,amount=intent['amount_paise'])
                store.observe_financial_resource(booking['booking_id'],intent,resource,'signed_webhook',job['body_hash'],parent)
                current=fetch_resource(pinned,resource)
                outcome=store.observe_financial_resource(booking['booking_id'],intent,current,'provider_fetch',digest(current),parent)
                if outcome.get('attention_reason') in ('refund_totals_conflict','financial_resource_conflict'):
                    raise RazorpayFailure(outcome['attention_reason'])
                if resource['kind']=='refund':
                    fetch_and_record(store,pinned,booking['context_id'],booking['booking_id'],payment_id,
                                     require_refund=current['status']=='processed')
            elif payment_id:
                fetch_and_record(store,pinned,booking['context_id'],booking['booking_id'],payment_id,
                                 require_refund=reference.get('event')=='refund.processed')
            else:
                # Order-only events wake the existing reconciliation job. They
                # are not themselves evidence of a captured payment.
                store.wake_payment_recovery(booking['booking_id'])
            done=True
            error=None
    except RazorpayFailure as exc:
        error=exc.code
    delay=recovery_delay(job) if job.get('server_now') else delay_for(job['attempts'])
    saved=store.finish_payment_event(job,done=done,delay=delay,error=error)
    return {'processed':1 if saved is True else 0,'retry':saved is not True or not done}
