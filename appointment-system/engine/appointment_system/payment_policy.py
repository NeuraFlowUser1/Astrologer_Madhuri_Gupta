"""Conservative customer actions from stored evidence, never browser success.

This projection cannot release capacity or clear an unresolved context. Those
writes belong in the context-first transaction. Failed attempts or empty provider
lists never imply that an exposed order is closed.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Appointment(StrEnum):
    HELD = "held"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REVIEW = "payment_review"


class Order(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    CREATING = "creating"
    UNKNOWN = "creation_unknown"
    READY = "ready"
    FAILED = "failed"


class Payment(StrEnum):
    UNOBSERVED = "unobserved"
    PENDING = "pending"
    CAPTURED = "captured"
    FAILED = "failed_observed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    ATTENTION = "needs_attention"


class Resolution(StrEnum):
    CONFIRMED = "confirmed"
    NEVER_ATTEMPTED = "never_attempted_abandoned"
    REJECTED = "creation_definitely_rejected"
    TERMINAL = "provider_terminal"
    STUDIO = "studio_reviewed"


@dataclass(frozen=True)
class CheckoutEvidence:
    appointment: Appointment
    order: Order
    payment: Payment
    hold_expires_at: datetime
    order_attempted_at: datetime | None = None
    order_id: str | None = None
    resolution: Resolution | None = None
    resolved_at: datetime | None = None

    def __post_init__(self):
        for value, kind in ((self.appointment, Appointment), (self.order, Order),
                            (self.payment, Payment)):
            if not isinstance(value, kind):
                raise ValueError("Unknown checkout state")
        if self.resolution is not None and not isinstance(self.resolution, Resolution):
            raise ValueError("Unknown resolution")
        if (self.resolution is None) != (self.resolved_at is None):
            raise ValueError("Incomplete resolution evidence")
        for value in (self.hold_expires_at, self.order_attempted_at, self.resolved_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Timezone-aware timestamps required")
        if self.order == Order.NOT_ATTEMPTED and (self.order_attempted_at or self.order_id):
            raise ValueError("Contradictory unattempted order")
        if self.order == Order.READY and not self.order_id:
            raise ValueError("Ready order requires provider identity")
        if self.order != Order.NOT_ATTEMPTED and self.order_attempted_at is None:
            raise ValueError("Attempt evidence required")
        if self.resolution == Resolution.CONFIRMED and self.appointment not in (Appointment.CONFIRMED, Appointment.CANCELLED):
            raise ValueError("Confirmed resolution requires an established appointment")
        if self.resolution == Resolution.NEVER_ATTEMPTED and self.order != Order.NOT_ATTEMPTED:
            raise ValueError("Attempted order cannot use unattempted resolution")
        if self.resolution == Resolution.REJECTED and (self.order != Order.FAILED or self.order_id):
            raise ValueError("Rejection does not prove an existing order closed")


def customer_actions(evidence, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware server time required")
    if evidence.resolved_at is not None and evidence.resolved_at > now:
        raise ValueError("Future resolution")
    if evidence.appointment == Appointment.CANCELLED:
        return {"customer_message_code": "appointment_cancelled", "next_actions": ["contact_support"]}
    if evidence.appointment == Appointment.CONFIRMED:
        # Financial exceptions do not silently cancel a valid appointment.
        actions = ["check_status"]
        # A new, separately acknowledged appointment may follow a conclusively
        # settled one. An unresolved/changed financial fact cannot release it.
        if evidence.payment == Payment.CAPTURED and evidence.resolution == Resolution.CONFIRMED:
            actions.append("choose_new_time")
        return {"customer_message_code": "appointment_confirmed", "next_actions": actions}
    if (evidence.appointment == Appointment.REVIEW or
            evidence.payment in (Payment.CAPTURED, Payment.REFUNDED, Payment.PARTIALLY_REFUNDED, Payment.ATTENTION)):
        return {"customer_message_code": "payment_needs_review", "next_actions": ["contact_support", "check_status"]}
    if evidence.resolution is not None:
        return {"customer_message_code": "choose_new_time", "next_actions": ["choose_new_time"]}
    if (evidence.appointment == Appointment.HELD and evidence.hold_expires_at > now
            and evidence.order == Order.READY):
        return {"customer_message_code": "time_reserved", "next_actions": ["resume_payment", "check_status"]}
    # Even a never-attempted expired hold must be abandoned transactionally
    # before another request may race with order creation.
    return {"customer_message_code": "checking_payment", "next_actions": ["check_status", "contact_support"]}
