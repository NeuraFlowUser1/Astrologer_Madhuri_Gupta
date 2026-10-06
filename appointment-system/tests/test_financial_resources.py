"""Real provider shapes, minimized facts, and GET-only resource boundaries."""
import unittest
from unittest.mock import Mock
from appointment_system.financial_resources import RESOURCE_EVENTS,resource_fact,signed_resource,fetch_resource,payment_fact
from appointment_system.razorpay import RazorpayFailure

class ResourceCodecTests(unittest.TestCase):
    def resource(self,kind='refund',**changes):
        return dict(entity=kind,id=('rfnd_resource' if kind=='refund' else 'disp_resource'),payment_id='pay_resource',
            amount=100,currency='INR',status=('pending' if kind=='refund' else 'open'),created_at=1700000000,
            notes={'private':'must not survive'},evidence={'customer_communication':'must not survive'})|changes
    def test_all_documented_events_use_resource_state_and_strip_private_content(self):
        for name in RESOURCE_EVENTS:
            kind='refund' if name.startswith('refund.') else 'dispute'
            data=self.resource(kind,status='processed' if kind=='refund' else 'under_review')
            event=dict(event=name,payload={kind:{'entity':data}})
            fact=signed_resource(event)
            self.assertEqual(fact['status'],data['status'])
            self.assertNotIn('private',str(fact));self.assertNotIn('customer_communication',str(fact))
            self.assertEqual(len(fact),12)
    def test_strict_ids_numbers_states_timestamps_and_parent(self):
        for changes in [dict(id='disp_wrong'),dict(amount=True),dict(amount=0),dict(amount='100'),dict(amount=2147483648),
            dict(payment_id='order_wrong'),dict(currency='USD'),dict(status='complete'),dict(created_at=None),
            dict(created_at=True),dict(updated_at=1),dict(updated_at='1700000000'),dict(speed_processed='express')]:
            with self.subTest(changes=changes),self.assertRaises(RazorpayFailure):resource_fact(self.resource(**changes),'refund')
        for changes in [dict(respond_by=True),dict(respond_by=1699999999),dict(status='processed')]:
            with self.subTest(changes=changes),self.assertRaises(RazorpayFailure):resource_fact(self.resource('dispute',**changes),'dispute')
        with self.assertRaises(RazorpayFailure):resource_fact(self.resource(),'refund',payment_id='pay_foreign')
        self.assertIsNone(signed_resource({'event':'unsupported.real.event'}))
        with self.assertRaises(RazorpayFailure):signed_resource({'event':'refund.created','payload':{}})
    def test_get_failure_is_not_a_fetched_fact_and_identity_change_is_rejected(self):
        adapter=Mock();signed=resource_fact(self.resource(),'refund')
        adapter.refund.side_effect=RazorpayFailure('payment_credentials_rejected')
        with self.assertRaises(RazorpayFailure):fetch_resource(adapter,signed)
        adapter.refund.side_effect=None;adapter.refund.return_value=self.resource(payment_id='pay_foreign')
        with self.assertRaises(RazorpayFailure):fetch_resource(adapter,signed)
        adapter.refund.return_value=self.resource(status='processed')
        self.assertEqual(fetch_resource(adapter,signed)['status'],'processed')
        adapter.dispute.assert_not_called()
    def test_dispute_deadline_and_original_payment_are_checked_without_confirming(self):
        signed=resource_fact(self.resource('dispute',respond_by=1700086400),'dispute')
        adapter=Mock();adapter.dispute.return_value=self.resource('dispute',respond_by=1700086400,status='won')
        self.assertEqual(fetch_resource(adapter,signed)['respond_by'],1700086400)
        parent=dict(entity='payment',id='pay_resource',order_id='order_resource',status='captured',amount=100,
                    currency='INR',amount_refunded=0,captured=True,email='private@example.invalid')
        self.assertNotIn('email',payment_fact(parent,payment_id='pay_resource',order_id='order_resource',amount=100))
        for change in [dict(id='pay_foreign'),dict(order_id='order_foreign'),dict(amount=True),dict(captured=1),dict(amount_refunded=101)]:
            with self.subTest(change=change),self.assertRaises(RazorpayFailure):
                payment_fact(parent|change,payment_id='pay_resource',order_id='order_resource',amount=100)


class RecoveryCadenceTests(unittest.TestCase):
    def test_initial_daily_and_aged_obligations_use_bounded_cadence(self):
        from datetime import datetime,timedelta,timezone
        from appointment_system.financial_resources import recovery_delay
        now=datetime.now(timezone.utc)
        for age,expected in [(0,900),(23,900),(24,3600),(167,3600),(168,86400),(8760,86400)]:
            with self.subTest(hours=age):self.assertEqual(recovery_delay(dict(server_now=now,created_at=now-timedelta(hours=age))),expected)
        self.assertEqual(recovery_delay(dict(server_now=now,created_at=(now-timedelta(days=8)).isoformat())),86400)
        self.assertEqual(recovery_delay(dict(server_now=now,created_at=now+timedelta(hours=1))),900)
        with self.assertRaises(ValueError):recovery_delay(dict(server_now='bad time'))
