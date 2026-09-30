import hashlib
import hmac
import json
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.booking_engine.access import COOKIE_NAME,new_context
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.policy import policy_snapshot,policy_version
from backend.booking_engine.rate_limit import risk_digest
from backend.booking_engine.webhook import EventConflict,InvalidWebhook,WebhookAccount,accept_webhook

ORIGIN='https://sarsa.example.invalid'
SECRET='synthetic-webhook-secret'


def event_body():
    return json.dumps(dict(entity='event',account_id='acc_sarsaTest',event='payment.captured',
       payload={'payment':{'entity':{'id':'pay_synthetic','order_id':'order_synthetic',
                                    'email':'private@example.invalid','contact':'+919876543210'}}})).encode()


def signed(body):
    return hmac.new(SECRET.encode(),body,hashlib.sha256).hexdigest()


class WebhookTests(unittest.TestCase):
    def account(self):
        return WebhookAccount('sarsaTest','test',(SECRET,))

    def test_authenticate_then_persist_only_minimal_references(self):
        store=Mock(); body=event_body()
        store.save_provider_event.return_value=hashlib.sha256(body).hexdigest()
        self.assertEqual(accept_webhook(store,self.account(),body,signed(body),'evt_synthetic'),{'received':True})
        args=store.save_provider_event.call_args.args
        self.assertEqual(args[:4],('razorpay','sarsaTest','test','evt_synthetic'))
        self.assertEqual(args[-1],dict(event='payment.captured',payment_id='pay_synthetic',order_id='order_synthetic'))
        self.assertNotIn('private@example.invalid',str(args))
        self.assertNotIn(SECRET,repr(self.account()))

    def test_bad_signature_account_duplicate_json_and_id_never_persist(self):
        for body,signature,event_id in ((event_body(),'0'*64,'evt_synthetic'),
              (event_body().replace(b'acc_sarsaTest',b'acc_other'),None,'evt_synthetic'),
              (b'{"entity":"event","entity":"other"}',None,'evt_synthetic'),
              (event_body(),None,'bad/id')):
            store=Mock()
            with self.assertRaises(InvalidWebhook):
                accept_webhook(store,self.account(),body,signature or signed(body),event_id)
            store.save_provider_event.assert_not_called()

    def test_commit_failure_or_conflicting_event_not_acknowledged(self):
        body=event_body(); store=Mock()
        store.save_provider_event.side_effect=StorageUnavailable('commit uncertain')
        with self.assertRaises(StorageUnavailable):
            accept_webhook(store,self.account(),body,signed(body),'evt_synthetic')
        store.save_provider_event.side_effect=None
        store.save_provider_event.return_value='a'*64
        with self.assertRaises(EventConflict):
            accept_webhook(store,self.account(),body,signed(body),'evt_synthetic')

    def test_rotation_accepts_previous_signing_secret(self):
        body=event_body(); store=Mock()
        store.save_provider_event.return_value=hashlib.sha256(body).hexdigest()
        account=WebhookAccount('sarsaTest','test',('new-synthetic-secret',SECRET))
        self.assertTrue(accept_webhook(store,account,body,signed(body),'evt_synthetic')['received'])


class HttpTests(unittest.TestCase):
    def setup_client(self,webhooks=False):
        store=Mock()
        store.consume_limit.return_value={'allowed':True,'retry_after':1}
        store.scheduling_snapshot.return_value=dict(server_now=datetime.now(timezone.utc),schedule_browsing_open=False,public_open=False,
            policy_version=policy_version(),specification=policy_snapshot(),claims=[])
        settings=Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32)
        app=create_application(store,settings,verified_client_address=lambda request:'192.0.2.1',
            webhook_account=WebhookAccount('sarsaTest','test',(SECRET,)) if webhooks else None)
        return store,TestClient(app,base_url=ORIGIN)

    def test_closed_intake_does_not_disable_receipt_recovery(self):
        store,client=self.setup_client()
        response=client.get('/api/availability',params={'service_id':'numerology','day':'2026-09-29'})
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['code'],'booking_unavailable')
        store.receipt_snapshot.return_value={'server_now':datetime.now(timezone.utc),'booking':None}
        response=client.post('/api/checkout/status',json={'request_id':str(uuid4())},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,403)
        store.receipt_snapshot.assert_called_once()
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_valid_receipt_remains_readable_while_intake_closed(self):
        from backend.booking_engine.tests.test_access_and_views import ReceiptViewTests
        snapshot,request,secret,key=ReceiptViewTests().fixture()
        store,client=self.setup_client()
        store.receipt_snapshot.return_value=snapshot
        response=client.post('/api/checkout/status',json={'request_id':str(request)},
            headers={'Origin':ORIGIN,'x-booking-receipt':secret})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['appointment_state'],'confirmed')
        self.assertNotIn(secret,response.text)
        self.assertNotIn('private@example.invalid',response.text)
        store.scheduling_snapshot.assert_not_called()

    def test_no_email_lookup_wrong_origin_or_exposed_validation_values(self):
        store,client=self.setup_client()
        response=client.post('/api/checkout/status',json={'request_id':str(uuid4())},headers={'Origin':ORIGIN+'.evil'})
        self.assertEqual(response.status_code,403)
        store.receipt_snapshot.assert_not_called()
        response=client.post('/api/checkout/status',json={'email':'private@example.invalid'},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,422)
        self.assertNotIn('private@example.invalid',response.text)
        self.assertEqual(client.get('/api/bookings').status_code,410)

    def test_unexpected_error_response_has_no_private_details_or_cache(self):
        store,client=self.setup_client()
        client=TestClient(client.app,base_url=ORIGIN,raise_server_exceptions=False)
        store.consume_limit.side_effect=RuntimeError('synthetic-private-detail')
        response=client.get('/api/booking-policy')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('synthetic-private-detail',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_limit_outage_and_quota_fail_closed(self):
        store,client=self.setup_client()
        store.consume_limit.side_effect=StorageUnavailable('offline')
        self.assertEqual(client.get('/api/booking-policy').status_code,503)
        store.consume_limit.side_effect=None
        store.consume_limit.return_value={'allowed':False,'retry_after':37}
        response=client.get('/api/booking-policy')
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['retry-after'],'37')

    def test_context_cookie_only_after_committed_creation_and_secure_flags(self):
        store,client=self.setup_client()
        store.scheduling_snapshot.return_value['schedule_browsing_open']=True
        response=client.post('/api/checkout-context',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'ready':True})
        cookie=response.headers['set-cookie']
        for flag in ('Secure','HttpOnly','SameSite=strict','Path=/','Max-Age=86400'):
            self.assertIn(flag,cookie)
        self.assertIn(COOKIE_NAME,cookie)
        self.assertNotIn(store.create_context.call_args.args[1],response.text)
        client.cookies.clear()
        store.create_context.side_effect=StorageUnavailable('uncertain commit')
        response=client.post('/api/checkout-context',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,503)
        self.assertNotIn('set-cookie',response.headers)

    def test_body_limit_content_type_and_raw_signature(self):
        store,client=self.setup_client(webhooks=True)
        response=client.post('/api/checkout-context',content=b'x'*16385,headers={'content-type':'application/json','Origin':ORIGIN})
        self.assertEqual(response.status_code,413)
        store.create_context.assert_not_called()
        response=client.post('/api/checkout-context',content=b'{}')
        self.assertEqual(response.status_code,415)
        body=event_body(); store.save_provider_event.return_value=hashlib.sha256(body).hexdigest()
        response=client.post('/api/webhooks/razorpay',content=body,headers={'content-type':'application/json',
            'x-razorpay-signature':signed(body),'x-razorpay-event-id':'evt_synthetic'})
        self.assertEqual(response.status_code,200)
        store.consume_limit.assert_not_called()
        store.save_provider_event.side_effect=StorageUnavailable('uncertain')
        response=client.post('/api/webhooks/razorpay',content=body,headers={'content-type':'application/json',
            'x-razorpay-signature':signed(body),'x-razorpay-event-id':'evt_synthetic'})
        self.assertEqual(response.status_code,503)

    def test_risk_keys_are_private_and_ipv6_rotation_shares_quota(self):
        key=b'a'*32
        self.assertEqual(risk_digest('2001:db8:abcd:1234::1',key),risk_digest('2001:db8:abcd:1234::2',key))
        self.assertEqual(risk_digest('::ffff:192.0.2.1',key),risk_digest('192.0.2.1',key))
        self.assertNotIn('192.0.2.1',risk_digest('192.0.2.1',key))
        with self.assertRaises(StorageUnavailable):
            risk_digest('192.0.2.1, 192.0.2.2',key)


if __name__=='__main__':
    unittest.main()
