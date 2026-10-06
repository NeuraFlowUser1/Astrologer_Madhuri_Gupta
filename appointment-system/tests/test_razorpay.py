import hashlib
import hmac
import json
import unittest
from uuid import uuid4

import httpx
from appointment_system.razorpay import (
    Credentials, Razorpay, RazorpayFailure, order_receipt, payment_matches, verify_checkout,
)


class RazorpayTests(unittest.TestCase):
    def credentials(self):
        return Credentials('ExampleSynthetic','test','test-v1','rzp_test_synthetic','synthetic-secret')

    def test_credentials_pin_merchant_mode_and_version_without_repr_secret(self):
        credentials = self.credentials()
        self.assertTrue(credentials.matches_intent('acc_ExampleSynthetic','test','test-v1'))
        for values in (('other','test','test-v1'),('ExampleSynthetic','live','test-v1'),
                       ('ExampleSynthetic','test','old-version')):
            self.assertFalse(credentials.matches_intent(*values))
        self.assertNotIn('synthetic-secret',repr(credentials))
        self.assertNotIn('rzp_test_synthetic',repr(credentials))
        with self.assertRaises(RazorpayFailure):
            Credentials('ExampleSynthetic','live','v1','rzp_test_synthetic','secret')

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

    def test_order_payload_response_binding_and_neutral_order_receipt(self):
        booking = uuid4()
        receipt = order_receipt(booking,'test')
        self.assertTrue(receipt.startswith('bt_'))
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

    def test_retired_account_cannot_create_and_reads_use_only_its_assigned_reader(self):
        from unittest.mock import Mock
        adapter=Razorpay(self.credentials());adapter.creation_allowed=False
        with self.assertRaisesRegex(RazorpayFailure,'payment_account_retired'):adapter.create_order(uuid4(),100)
        reader=Mock(spec=['_request']);reader._request.return_value={'id':'order_saved'};adapter.read_adapter=reader
        self.assertEqual(adapter.order('order_saved'),{'id':'order_saved'})
        reader._request.assert_called_once_with('GET','orders/order_saved',payload=None,params=None)
        with self.assertRaises(RazorpayFailure):Razorpay(None)

    def test_invalid_amount_and_search_boundaries_never_send_a_provider_request(self):
        calls=[]
        adapter=Razorpay(self.credentials(),transport=httpx.MockTransport(lambda request:calls.append(request)))
        for amount in (True,0,-1,1.5,'100'):
            with self.subTest(amount=amount),self.assertRaises(ValueError):adapter.create_order(uuid4(),amount)
        for values in ({'skip':True},{'skip':-1},{'from_time':1},{'to_time':1},
            {'from_time':True,'to_time':1},{'from_time':2,'to_time':1},{'from_time':0,'to_time':2**63}):
            with self.subTest(values=values),self.assertRaises(ValueError):adapter.orders_page(uuid4(),**values)
        for mode,format in [('unknown','provider-receipt-v1'),('test','unknown')]:
            with self.assertRaises(ValueError):order_receipt(uuid4(),mode,format)
        self.assertEqual(calls,[])

    def test_reconciliation_requests_keep_exact_resource_and_frozen_search_window(self):
        calls=[]
        def provider(request):calls.append(request);return httpx.Response(200,json={'items':[]})
        adapter=Razorpay(self.credentials(),transport=httpx.MockTransport(provider));reference=uuid4()
        for method,reference_value,path in [('order','order_saved','orders/order_saved'),('payment','pay_saved','payments/pay_saved'),
            ('refund','rfnd_saved','refunds/rfnd_saved'),('dispute','disp_saved','disputes/disp_saved'),
            ('order_payments','order_saved','orders/order_saved/payments')]:
            getattr(adapter,method)(reference_value);self.assertEqual(calls[-1].method,'GET');self.assertEqual(calls[-1].url.path,'/v1/'+path)
        adapter.orders_page(reference,skip=90,from_time=0,to_time=100)
        self.assertEqual(dict(calls[-1].url.params),{'receipt':order_receipt(reference,'test'),'count':'100','skip':'90','from':'0','to':'100'})
        adapter.orders_page(reference);self.assertNotIn('from',calls[-1].url.params)

    def test_missing_oversize_nonobject_or_wrong_content_success_never_proves_a_payment(self):
        for method in ('GET','POST'):
            for response in (httpx.Response(404),httpx.Response(200,json=[]),httpx.Response(200,text='{}'),
                httpx.Response(200,content=b'x'*262145,headers={'content-type':'application/json'})):
                calls=[]
                def provider(request):calls.append(request);return response
                adapter=Razorpay(self.credentials(),transport=httpx.MockTransport(provider))
                with self.subTest(method=method,status=response.status_code),self.assertRaises(RazorpayFailure) as failure:
                    adapter._request(method,'orders')
                self.assertEqual(failure.exception.uncertain,method=='POST');self.assertEqual(len(calls),1)

    def test_order_identity_is_checked_even_after_successful_creation_status(self):
        reference=uuid4();receipt=order_receipt(reference,'test')
        good=dict(id='order_saved',entity='order',receipt=receipt,amount=100,currency='INR',partial_payment=False)
        for changed in ({'id':'pay_wrong'},{'entity':'payment'},{'receipt':'foreign'},{'amount':True},{'currency':'USD'},{'partial_payment':True}):
            adapter=Razorpay(self.credentials(),transport=httpx.MockTransport(lambda request:httpx.Response(201,json=good|changed)))
            with self.subTest(changed=changed),self.assertRaisesRegex(RazorpayFailure,'payment_order_mismatch') as failure:adapter.create_order(reference,100)
            self.assertTrue(failure.exception.uncertain)


if __name__=='__main__':
    unittest.main()
