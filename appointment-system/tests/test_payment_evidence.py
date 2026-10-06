import unittest
from unittest.mock import Mock
from uuid import uuid4

from appointment_system.payment_evidence import PaymentEvidence,fetch_and_record
from appointment_system.razorpay import Credentials,RazorpayFailure


class EvidenceTests(unittest.TestCase):
    def payload(self):
        return dict(entity='payment',id='pay_synthetic',order_id='order_synthetic',status='captured',
                    amount=210000,currency='INR',amount_refunded=0,captured=True)

    def test_only_minimal_strict_facts_and_stable_digest(self):
        payload=self.payload()
        evidence=PaymentEvidence(**payload,email='private@example.invalid',card={'last4':'1234'})
        self.assertNotIn('email',evidence.model_dump())
        self.assertNotIn('card',evidence.model_dump())
        self.assertEqual(evidence.digest,PaymentEvidence(**payload).digest)
        for changes in ({'amount':True},{'amount':'210000'},{'captured':'true'},
                        {'amount_refunded':210001},{'order_id':'invalid'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                PaymentEvidence(**(payload|changes))

    def test_refund_event_waits_for_provider_payment_evidence(self):
        store,adapter=Mock(),Mock()
        store.order_intent.return_value=dict(merchant_id='ExampleTest',mode='test',credential_version='v1')
        adapter.credentials=Credentials('ExampleTest','test','v1','rzp_test_synthetic','synthetic-secret')
        adapter.payment.return_value=self.payload()
        with self.assertRaises(RazorpayFailure) as failure:
            fetch_and_record(store,adapter,uuid4(),uuid4(),'pay_synthetic',require_refund=True)
        self.assertEqual(failure.exception.code,'refund_not_reflected')
        store.observe_payment.assert_not_called()

    def test_fetch_through_pinned_account_before_recording(self):
        store,adapter=Mock(),Mock()
        store.order_intent.return_value=dict(merchant_id='ExampleTest',mode='test',credential_version='v1')
        adapter.credentials=Credentials('ExampleTest','test','v1','rzp_test_synthetic','synthetic-secret')
        adapter.payment.return_value=self.payload()
        fetch_and_record(store,adapter,uuid4(),uuid4(),'pay_synthetic')
        self.assertEqual(store.observe_payment.call_count,1)
        adapter.payment.return_value=dict(self.payload(),id='pay_other')
        with self.assertRaises(RazorpayFailure):
            fetch_and_record(store,adapter,uuid4(),uuid4(),'pay_synthetic')
        self.assertEqual(store.observe_payment.call_count,1)
        store.order_intent.return_value['mode']='live'
        with self.assertRaises(RazorpayFailure):
            fetch_and_record(store,adapter,uuid4(),uuid4(),'pay_synthetic')
        self.assertEqual(adapter.payment.call_count,2)


if __name__=='__main__':
    unittest.main()
