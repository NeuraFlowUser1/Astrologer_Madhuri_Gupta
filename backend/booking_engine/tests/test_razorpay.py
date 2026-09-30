import hashlib
import hmac
import json
import unittest
from uuid import uuid4

import httpx
from backend.booking_engine.razorpay import (
    Credentials, Razorpay, RazorpayFailure, order_receipt, payment_matches, verify_checkout,
)


class RazorpayTests(unittest.TestCase):
    def credentials(self):
        return Credentials('sarsaSynthetic','test','test-v1','rzp_test_synthetic','synthetic-secret')

    def test_credentials_pin_merchant_mode_and_version_without_repr_secret(self):
        credentials = self.credentials()
        self.assertTrue(credentials.matches_intent('acc_sarsaSynthetic','test','test-v1'))
        for values in (('other','test','test-v1'),('sarsaSynthetic','live','test-v1'),
                       ('sarsaSynthetic','test','old-version')):
            self.assertFalse(credentials.matches_intent(*values))
        self.assertNotIn('synthetic-secret',repr(credentials))
        self.assertNotIn('rzp_test_synthetic',repr(credentials))
        with self.assertRaises(RazorpayFailure):
            Credentials('sarsaSynthetic','live','v1','rzp_test_synthetic','secret')

    def test_no_automatic_retry_after_ambiguous_creation(self):
        requests = []
        def handler(request):
            requests.append(request)
            raise httpx.ReadTimeout('synthetic failure')
        adapter = Razorpay(self.credentials(),transport=httpx.MockTransport(handler))
        with self.assertRaises(RazorpayFailure) as failure:
            adapter.create_order(uuid4(),210000)
        self.assertTrue(failure.exception.uncertain)
        self.assertEqual(len(requests),1)
        self.assertNotIn('synthetic-secret',str(failure.exception))

    def test_order_payload_response_binding_and_distinct_sarsa_receipt(self):
        booking = uuid4()
        receipt = order_receipt(booking,'test')
        self.assertTrue(receipt.startswith('s4t_'))
        self.assertLessEqual(len(receipt),40)
        def handler(request):
            self.assertEqual(str(request.url),'https://api.razorpay.com/v1/orders')
            payload = json.loads(request.content)
            self.assertEqual(payload,dict(amount=210000,currency='INR',receipt=receipt,partial_payment=False))
            return httpx.Response(200,json=dict(payload,id='order_synthetic',entity='order'))
        adapter = Razorpay(self.credentials(),transport=httpx.MockTransport(handler))
        self.assertEqual(adapter.create_order(booking,210000)['id'],'order_synthetic')
        adapter = Razorpay(self.credentials(),transport=httpx.MockTransport(
            lambda request: httpx.Response(200,json=dict(id='order_wrong',entity='order',amount=1,currency='INR',receipt=receipt))))
        with self.assertRaises(RazorpayFailure) as failure:
            adapter.create_order(booking,210000)
        self.assertTrue(failure.exception.uncertain)

    def test_redirect_auth_error_and_invalid_success_stay_uncertain(self):
        for status, content in ((302,b''),(401,b''),(403,b''),(500,b''),(200,b'not-json')):
            with self.subTest(status=status):
                calls=[]
                def handler(request):
                    calls.append(request)
                    return httpx.Response(status,content=content,headers={'location':'https://example.invalid','content-type':'application/json'})
                adapter = Razorpay(self.credentials(),transport=httpx.MockTransport(handler))
                with self.assertRaises(RazorpayFailure) as failure:
                    adapter.create_order(uuid4(),210000)
                self.assertTrue(failure.exception.uncertain)
                self.assertEqual(len(calls),1)

    def test_signature_uses_saved_order_and_capture_requires_complete_match(self):
        signature=hmac.new(b'secret',b'order_saved|pay_example',hashlib.sha256).hexdigest()
        self.assertTrue(verify_checkout('order_saved','pay_example',signature,'secret'))
        self.assertFalse(verify_checkout('order_other','pay_example',signature,'secret'))
        payment=dict(entity='payment',id='pay_example',order_id='order_saved',amount=210000,
                     currency='INR',status='captured',captured=True,amount_refunded=0)
        def matches(value):
            return payment_matches(value,payment_id='pay_example',order_id='order_saved',amount=210000)
        self.assertTrue(matches(payment))
        for key,value in (('amount',True),('amount',1),('currency','USD'),('status','authorized'),
                          ('captured',False),('amount_refunded',1),('order_id','order_other')):
            self.assertFalse(matches(dict(payment,**{key:value})))


if __name__=='__main__':
    unittest.main()
