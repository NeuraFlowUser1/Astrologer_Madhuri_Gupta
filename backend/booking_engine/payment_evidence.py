"""Minimized, strictly typed payment facts fetched through pinned credentials."""

from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,model_validator

from .razorpay import RazorpayFailure
from .security import request_fingerprint


class PaymentEvidence(BaseModel):
    model_config=ConfigDict(strict=True,extra='ignore',frozen=True)
    entity: Literal['payment']
    id: str = Field(pattern=r'^pay_[A-Za-z0-9]{1,64}$')
    order_id: str = Field(pattern=r'^order_[A-Za-z0-9]{1,64}$')
    status: Literal['created','authorized','captured','refunded','failed']
    amount: int = Field(ge=0)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    amount_refunded: int = Field(ge=0)
    captured: bool

    @model_validator(mode='after')
    def refund_not_over_amount(self):
        if self.amount_refunded>self.amount:
            raise ValueError('Invalid refunded amount')
        return self

    @property
    def digest(self):
        return request_fingerprint(self.model_dump(mode='json'))


def fetch_and_record(store,adapter,context_id,booking_id,payment_id,*,require_refund=False):
    """Used by authenticated recovery/callback handlers, never raw browser data."""
    intent=store.order_intent(context_id,booking_id)
    if not intent or not adapter.credentials.matches_intent(
        intent.get('merchant_id'),intent.get('mode'),intent.get('credential_version')
    ):
        raise RazorpayFailure('payment_identity_mismatch')
    response=adapter.payment(payment_id)
    try:
        evidence=PaymentEvidence.model_validate(response)
    except ValueError:
        raise RazorpayFailure('payment_response_invalid') from None
    if require_refund and evidence.amount_refunded<=0:
        raise RazorpayFailure('refund_not_reflected')
    if evidence.id != payment_id:
        raise RazorpayFailure('payment_response_invalid')
    return store.observe_payment(context_id,booking_id,intent,evidence)
