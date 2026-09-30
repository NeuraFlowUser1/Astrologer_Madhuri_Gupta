import base64
import hashlib
import unittest
from unittest.mock import Mock,patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.booking_engine.google_worker import WorkerKey
from backend.booking_engine.recovery_worker import add_recovery_worker_routes,checked_plan,LANES
from backend.booking_engine.wake import WakePublisher
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.webhook import accept_webhook,EventConflict
from backend.booking_engine.tests.test_http_and_events import event_body,signed
from backend.booking_engine.tests import test_http_and_events as webhook_tests, test_hosting as hosting_tests, test_email_events as email_tests
from backend.booking_engine.tests.test_hosting import ORIGIN,key
from backend.booking_engine.hosting import create_hosted_application

SECRET=base64.urlsafe_b64encode(b'x'*32).decode()
URL='https://sarsa-booking-recovery.neuraflowindia.workers.dev/wake'


class RecoveryWorkerTests(unittest.TestCase):
    def test_maintenance_requires_worker_authority_and_has_bounded_counts(self):
        store=Mock();store.cleanup_temporary_records.return_value={'processed':1,'removed':{'attempts':2,'sessions':1,'limits':0}}
        app=FastAPI();add_recovery_worker_routes(app,store,WorkerKey(SECRET));client=TestClient(app)
        path='/api/internal/recovery/maintenance';headers={'authorization':'Bearer '+SECRET}
        self.assertEqual(client.post(path,json={}).status_code,401)
        self.assertEqual(client.post(path,json={'limit':10000},headers=headers).status_code,422)
        store.cleanup_temporary_records.assert_not_called()
        response=client.post(path,json={},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['removed']['attempts'],2)
        for value in ({'processed':True,'removed':{'attempts':1,'sessions':0,'limits':0}},
                      {'processed':0,'removed':{'attempts':1,'sessions':0,'limits':0}},
                      {'processed':1,'removed':{'attempts':501,'sessions':0,'limits':0}}):
            store.cleanup_temporary_records.return_value=value
            with self.assertRaises(ValueError):client.post(path,json={},headers=headers)

    def test_private_empty_request_and_validated_minimal_plan(self):
        store=Mock();store.recovery_plan.return_value={'lanes':dict.fromkeys(LANES),'attention':False}
        app=FastAPI();add_recovery_worker_routes(app,store,WorkerKey(SECRET));client=TestClient(app)
        path='/api/internal/recovery/plan';headers={'authorization':'Bearer '+SECRET}
        self.assertEqual(client.post(path,json={}).status_code,401)
        self.assertEqual(client.post(path,json={'job':'private'},headers=headers).status_code,422)
        store.recovery_plan.assert_not_called()
        response=client.post(path,json={},headers=headers)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['version'],1)
        self.assertEqual(set(response.json()),{'application','version','lanes','attention'})
        self.assertEqual(client.post('/api/internal/recovery/payment',json={},headers=headers).status_code,503)
        store.claim_payment_recovery.assert_not_called()

    def test_invalid_plan_never_claims_success(self):
        for value in ({},{'lanes':{},'attention':False},{'lanes':dict.fromkeys(LANES,True),'attention':False},
                {'lanes':dict.fromkeys(LANES,901),'attention':False}):
            with self.assertRaises(ValueError):checked_plan(value)

    def test_optional_bad_keys_do_not_disable_owner_or_receipt_access(self):
        fixture=hosting_tests.HostingTests();fixture.setUp()
        for changes in ({'SARSA_RECOVERY_WORKER_KEY':'invalid'}, {'SARSA_RECOVERY_WORKER_KEY':key(b'a')},
                        {'SARSA_WAKE_KEY':'invalid','SARSA_WAKE_URL':URL}):
            with patch('psycopg.connect') as connect:
                app=create_hosted_application(dict(fixture.environment,**changes))
                self.assertIn('/studio',{r.path for r in app.routes})
                response=TestClient(app,base_url=ORIGIN).post('/api/internal/recovery/plan',json={})
                self.assertEqual(response.status_code,503)
            connect.assert_not_called()

    def test_recovery_key_cannot_authorize_email_or_google(self):
        fixture=hosting_tests.HostingTests();fixture.setUp()
        env=dict(fixture.environment,SARSA_RECOVERY_WORKER_KEY=SECRET,
                 SARSA_GOOGLE_WORKER_KEY=key(b'g'),SARSA_EMAIL_WORKER_KEY=key(b'e'))
        client=TestClient(create_hosted_application(env),base_url=ORIGIN)
        for path in ('/api/internal/email/events','/api/internal/google/run'):
            self.assertEqual(client.post(path,json={},headers={'authorization':'Bearer '+SECRET}).status_code,401)


class WakeTests(unittest.TestCase):
    def test_fixed_empty_request_and_matching_response(self):
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(202,json={'application':'004-sarsa-jyotish-sansthan','queued':True})
        publisher=WakePublisher(URL,SECRET,httpx.MockTransport(handler))
        self.assertTrue(publisher.publish());self.assertEqual(len(seen),1)
        self.assertEqual(seen[0].content,b'{}');self.assertNotIn(SECRET,repr(publisher))
        self.assertEqual(seen[0].url.host,'sarsa-booking-recovery.neuraflowindia.workers.dev')

    def test_timeout_rejection_wrong_identity_and_redirect_are_not_retried(self):
        for response in (httpx.Response(202,json={'queued':True}),httpx.Response(500),
                httpx.Response(302,headers={'location':'https://other.invalid'}),
                httpx.Response(202,headers={'content-type':'application/json'},content=b' '*1025),httpx.ReadTimeout('private')):
            seen=[]
            def handler(request):
                seen.append(request)
                if isinstance(response,Exception):raise response
                return response
            with self.assertLogs('backend.booking_engine.wake',level='WARNING') as logged:
                self.assertFalse(WakePublisher(URL,SECRET,httpx.MockTransport(handler)).publish())
            self.assertEqual(len(seen),1);self.assertNotIn('private',str(logged.output))

    def test_other_project_or_arbitrary_url_rejected(self):
        for url in ('http://sarsa-booking-recovery.neuraflowindia.workers.dev/wake',
                    'https://astro-advice.synthetic.workers.dev/wake',URL+'?url=x',URL.replace('workers.dev','evil.invalid')):
            with self.assertRaises(ValueError):WakePublisher(url,SECRET)

    def test_payment_wake_only_after_committed_matching_event(self):
        body=event_body();store=Mock();wake=Mock(return_value=False);account=webhook_tests.WebhookTests().account()
        store.save_provider_event.side_effect=StorageUnavailable('unknown')
        with self.assertRaises(StorageUnavailable):accept_webhook(store,account,body,signed(body),'evt_synthetic',on_saved=wake)
        wake.assert_not_called()
        store.save_provider_event.side_effect=None;store.save_provider_event.return_value='wrong'
        with self.assertRaises(EventConflict):accept_webhook(store,account,body,signed(body),'evt_synthetic',on_saved=wake)
        wake.assert_not_called()
        store.save_provider_event.return_value=hashlib.sha256(body).hexdigest()
        self.assertEqual(accept_webhook(store,account,body,signed(body),'evt_synthetic',on_saved=wake),{'received':True})
        wake.assert_called_once_with()

    def test_email_wake_only_for_own_committed_event(self):
        fixture=email_tests.EmailEventTests();fixture.setUp();wake=Mock(return_value=False)
        body,headers=fixture.signed()
        fixture.receiver.receive(fixture.store,body,headers,on_saved=wake)
        wake.assert_called_once_with();wake.reset_mock()
        fixture.event['data']['tags']['project']='003'
        body,headers=fixture.signed()
        fixture.receiver.receive(fixture.store,body,headers,on_saved=wake)
        wake.assert_not_called()
        fixture.event['data']['tags']['project']='sarsa004'
        fixture.store.save_provider_event.side_effect=StorageUnavailable('unknown')
        body,headers=fixture.signed()
        with self.assertRaises(StorageUnavailable):fixture.receiver.receive(fixture.store,body,headers,on_saved=wake)
        wake.assert_not_called()
