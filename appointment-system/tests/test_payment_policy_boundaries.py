"""Only conclusive stored financial evidence may authorize a new checkout."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from unittest import TestCase
from appointment_system.payment_policy import Appointment,Order,Payment,Resolution,CheckoutEvidence,customer_actions

class PaymentPolicyBoundaries(TestCase):
    def setUp(self):
        self.now=datetime(2026,10,4,12,tzinfo=timezone.utc)
        self.held=CheckoutEvidence(Appointment.HELD,Order.NOT_ATTEMPTED,Payment.UNOBSERVED,self.now+timedelta(minutes=10))

    def test_contradictory_or_incomplete_evidence_is_not_projected_to_a_customer(self):
        mutations=[{'appointment':'held'},{'order':'ready'},{'payment':'captured'},{'resolution':'confirmed'},
            {'resolution':Resolution.TERMINAL},{'resolved_at':self.now},{'hold_expires_at':self.now.replace(tzinfo=None)},
            {'order_attempted_at':self.now},{'order_id':'order_saved'}, {'order':Order.READY},
            {'order':Order.CREATING},{'resolution':Resolution.CONFIRMED,'resolved_at':self.now},
            {'order':Order.CREATING,'order_attempted_at':self.now,'resolution':Resolution.NEVER_ATTEMPTED,'resolved_at':self.now},
            {'resolution':Resolution.REJECTED,'resolved_at':self.now},
            {'order':Order.FAILED,'order_attempted_at':self.now,'order_id':'order_saved','resolution':Resolution.REJECTED,'resolved_at':self.now}]
        for mutation in mutations:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):replace(self.held,**mutation)
        with self.assertRaises(ValueError):customer_actions(self.held,self.now.replace(tzinfo=None))
        future=replace(self.held,resolution=Resolution.NEVER_ATTEMPTED,resolved_at=self.now+timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError,'Future resolution'):customer_actions(future,self.now)

    def test_failed_attempt_or_expired_hold_alone_never_allows_another_charge(self):
        for appointment in (Appointment.HELD,Appointment.EXPIRED):
            for order in (Order.CREATING,Order.UNKNOWN,Order.FAILED):
                evidence=replace(self.held,appointment=appointment,order=order,payment=Payment.FAILED,
                    order_attempted_at=self.now-timedelta(minutes=20),hold_expires_at=self.now-timedelta(minutes=1))
                response=customer_actions(evidence,self.now)
                self.assertEqual(response['customer_message_code'],'checking_payment')
                self.assertNotIn('choose_new_time',response['next_actions']);self.assertNotIn('resume_payment',response['next_actions'])
        evidence=replace(self.held,appointment=Appointment.EXPIRED,hold_expires_at=self.now-timedelta(minutes=1),
            resolution=Resolution.NEVER_ATTEMPTED,resolved_at=self.now)
        self.assertEqual(customer_actions(evidence,self.now)['next_actions'],['choose_new_time'])
        rejected=replace(evidence,order=Order.FAILED,order_attempted_at=self.now-timedelta(minutes=2),resolution=Resolution.REJECTED)
        self.assertEqual(customer_actions(rejected,self.now)['next_actions'],['choose_new_time'])

    def test_capture_refund_or_review_requires_resolution_without_cancelling_a_valid_appointment(self):
        for payment in (Payment.CAPTURED,Payment.REFUNDED,Payment.PARTIALLY_REFUNDED,Payment.ATTENTION):
            evidence=replace(self.held,payment=payment)
            self.assertEqual(customer_actions(evidence,self.now)['customer_message_code'],'payment_needs_review')
            confirmed=replace(evidence,appointment=Appointment.CONFIRMED)
            self.assertEqual(customer_actions(confirmed,self.now),{'customer_message_code':'appointment_confirmed','next_actions':['check_status']})
        review=replace(self.held,appointment=Appointment.REVIEW)
        self.assertEqual(customer_actions(review,self.now)['next_actions'],['contact_support','check_status'])
        settled=replace(self.held,appointment=Appointment.CONFIRMED,payment=Payment.CAPTURED,resolution=Resolution.CONFIRMED,resolved_at=self.now)
        self.assertEqual(customer_actions(settled,self.now)['next_actions'],['check_status','choose_new_time'])
        cancelled=replace(settled,appointment=Appointment.CANCELLED)
        self.assertEqual(customer_actions(cancelled,self.now),{'customer_message_code':'appointment_cancelled','next_actions':['contact_support']})

    def test_only_unexpired_saved_order_can_resume_payment(self):
        ready=replace(self.held,order=Order.READY,order_attempted_at=self.now-timedelta(minutes=1),order_id='order_saved')
        self.assertEqual(customer_actions(ready,self.now)['next_actions'],['resume_payment','check_status'])
        self.assertNotIn('resume_payment',customer_actions(ready,ready.hold_expires_at)['next_actions'])
