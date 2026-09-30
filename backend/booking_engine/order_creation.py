"""One durable creation claim, followed by at most one external order request.

The route must authenticate receipt/context and enforce intake readiness before
calling. This coordinator never confirms an appointment or opens a new checkout.
Reconciliation of ambiguous results is a separate saved-work consumer.
"""

from .razorpay import RazorpayFailure


def create_once(store, adapter, context_id, booking_id):
    intent = store.order_intent(context_id,booking_id)
    if (not intent or intent.get('currency') != 'INR'
            or type(intent.get('amount_paise')) is not int or intent['amount_paise'] <= 0
            or not adapter.credentials.matches_intent(
                intent.get('merchant_id'),intent.get('mode'),intent.get('credential_version'))):
        raise RazorpayFailure('payment_identity_mismatch')
    # A thrown/uncertain commit stops here. It cannot authorize a provider call.
    if not store.start_order_creation(context_id,booking_id):
        return 'check_saved_status'
    try:
        order = adapter.create_order(booking_id,intent['amount_paise'])
    except RazorpayFailure:
        # All unsuccessful POST observations remain conservative. Authentication
        # failure is not independently persisted proof that an order is terminal.
        store.record_order_creation(context_id,booking_id,intent,None)
        return 'check_saved_status'
    # If this save fails, propagate uncertainty. The committed creating state
    # remains recoverable; do not issue another external order request.
    store.record_order_creation(context_id,booking_id,intent,order['id'])
    return 'check_saved_status'
