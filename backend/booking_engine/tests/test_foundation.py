import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError
from backend.booking_engine.models import BookingInput
from backend.booking_engine.payment_policy import Appointment, Order, Payment, Resolution, CheckoutEvidence, customer_actions
from backend.booking_engine.security import new_secret, receipt_digest, receipt_matches, request_fingerprint

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


class PaymentActionsTests(unittest.TestCase):
    def evidence(self, **overrides):
        return replace(CheckoutEvidence(Appointment.EXPIRED, Order.READY, Payment.UNOBSERVED,
                        NOW-timedelta(minutes=1), NOW-timedelta(minutes=12), 'order_example'), **overrides)

    def test_expiry_empty_provider_results_and_failed_attempt_do_not_allow_repayment(self):
        for payment in (Payment.UNOBSERVED, Payment.PENDING, Payment.FAILED):
            for order in (Order.READY, Order.UNKNOWN, Order.CREATING):
                with self.subTest(payment=payment, order=order):
                    result = customer_actions(self.evidence(payment=payment,order=order), NOW)
                    self.assertNotIn('choose_new_time', result['next_actions'])
                    self.assertNotIn('resume_payment', result['next_actions'])

    def test_never_attempted_requires_serialized_abandonment(self):
        evidence = self.evidence(order=Order.NOT_ATTEMPTED, order_id=None, order_attempted_at=None)
        self.assertNotIn('choose_new_time', customer_actions(evidence,NOW)['next_actions'])
        resolved = replace(evidence,resolution=Resolution.NEVER_ATTEMPTED,resolved_at=NOW)
        self.assertEqual(customer_actions(resolved,NOW)['next_actions'], ['choose_new_time'])

    def test_late_capture_requires_review_even_after_operator_resolution(self):
        evidence = self.evidence(payment=Payment.CAPTURED,resolution=Resolution.STUDIO,resolved_at=NOW)
        self.assertEqual(customer_actions(evidence,NOW)['customer_message_code'], 'payment_needs_review')

    def test_existing_payable_order_resumes_without_new_selection(self):
        evidence = self.evidence(appointment=Appointment.HELD, hold_expires_at=NOW+timedelta(minutes=1))
        self.assertEqual(customer_actions(evidence,NOW)['next_actions'], ['resume_payment','check_status'])

    def test_confirmed_refund_does_not_silently_cancel_appointment(self):
        evidence = self.evidence(appointment=Appointment.CONFIRMED, payment=Payment.REFUNDED)
        self.assertEqual(customer_actions(evidence,NOW)['customer_message_code'], 'appointment_confirmed')

    def test_unknown_and_inconsistent_evidence_rejected(self):
        for changes in ({'order':'made_up'}, {'order':Order.NOT_ATTEMPTED},
                        {'resolution':Resolution.REJECTED,'resolved_at':NOW},
                        {'resolved_at':NOW}, {'hold_expires_at':datetime(2026,9,28)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.evidence(**changes)


class ReceiptTests(unittest.TestCase):
    def test_receipt_bound_to_request_and_signing_key(self):
        request = uuid4()
        secret, key = new_secret(), b'a'*32
        digest = receipt_digest(request, secret, key)
        self.assertTrue(receipt_matches(request,secret,key,digest))
        self.assertFalse(receipt_matches(uuid4(),secret,key,digest))
        self.assertFalse(receipt_matches(request,new_secret(),key,digest))
        self.assertFalse(receipt_matches(request,secret,b'b'*32,digest))
        self.assertFalse(receipt_matches(request,None,key,digest))
        self.assertNotIn(secret,digest)

    def test_fingerprint_stable_order_but_not_changed_values(self):
        self.assertEqual(request_fingerprint({'a':1,'b':2}),request_fingerprint({'b':2,'a':1}))
        self.assertNotEqual(request_fingerprint({'a':1}),request_fingerprint({'a':2}))
        with self.assertRaises(ValueError):
            request_fingerprint({'a':float('nan')})


class BookingInputTests(unittest.TestCase):
    def payload(self, **changes):
        result = dict(request_id=str(uuid4()),full_name='Test Customer',email='test@example.com',
                      phone='+91 98765 43210',service_id='kundli',quote_version='a'*64,
                      starts_at='2026-10-01T10:00:00+05:30')
        result.update(changes)
        return result

    def test_required_contacts_and_no_otp(self):
        value = BookingInput(**self.payload())
        self.assertEqual(value.phone,'+919876543210')
        self.assertIsNone(value.birth_date)
        for field in ('email','phone'):
            p = self.payload()
            del p[field]
            with self.assertRaises(ValidationError):
                BookingInput(**p)
        with self.assertRaises(ValidationError):
            BookingInput(**self.payload(verification_token='not-accepted'))

    def test_same_instant_has_one_canonical_retry_fingerprint(self):
        first=self.payload(starts_at='2026-10-01T10:00:00+05:30')
        second=dict(first,starts_at='2026-10-01T04:30:00Z')
        self.assertEqual(request_fingerprint(BookingInput(**first).model_dump(mode='json')),
                         request_fingerprint(BookingInput(**second).model_dump(mode='json')))

    def test_bad_phone_and_ambiguous_time_rejected(self):
        for changes in ({'phone':'9876543210'}, {'phone':'+91123'},
                        {'phone':'+919876543210 ext 123'}, {'email':'bad'},
                        {'starts_at':'2026-10-01T10:00:00'}, {'birth_date':'2026-02-30'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                BookingInput(**self.payload(**changes))


if __name__ == '__main__':
    unittest.main()
