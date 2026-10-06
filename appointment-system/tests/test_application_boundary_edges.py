"""Request stream boundaries and provider failures never bypass application guards."""
import asyncio
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
from appointment_system.application import RequestBoundary,create_application
from appointment_system.configuration import installation
from appointment_system.secret_configuration import booking_settings
from appointment_system.webhook import InvalidWebhook,EventConflict
from .test_application import environment,PublicStore,Reader


class RequestStreamEdges(TestCase):
    def run_boundary(self,scope,packets):
        received=[],[]
        incoming,sent=received;pending=list(packets)
        async def receive():return pending.pop(0)
        async def send(message):sent.append(message)
        async def app(scope,receive,send):
            if scope['type']!='http':incoming.append(scope);return
            incoming.append(await receive());incoming.append(await receive())
            await send({'type':'http.response.start','status':200,'headers':[(b'cache-control',b'public'),(b'content-type',b'application/json')]})
            await send({'type':'http.response.body','body':b'{}'})
        asyncio.run(RequestBoundary(app)(scope,receive,send));return incoming,sent

    def test_stream_chunks_are_joined_once_and_following_disconnect_is_forwarded(self):
        scope={'type':'http','method':'POST','path':'/api/synthetic','headers':[(b'content-type',b'application/json')]}
        incoming,sent=self.run_boundary(scope,[{'type':'http.request','body':b'{','more_body':True},{'type':'http.request','body':b'}','more_body':False},{'type':'http.disconnect'}])
        self.assertEqual(incoming,[{'type':'http.request','body':b'{}','more_body':False},{'type':'http.disconnect'}])
        self.assertEqual([v for k,v in sent[0]['headers'] if k==b'cache-control'],[b'no-store'])
        self.assertIn((b'referrer-policy',b'no-referrer'),sent[0]['headers'])
        incoming,sent=self.run_boundary(scope,[{'type':'http.disconnect'}]);self.assertEqual((incoming,sent),([],[]))

    def test_non_http_lifecycle_is_forwarded_and_json_limits_remain_independent_of_body_chunks(self):
        scope={'type':'lifespan'};incoming,sent=self.run_boundary(scope,[]);self.assertEqual(incoming,[scope]);self.assertEqual(sent,[])
        base={'type':'http','method':'POST','path':'/api/synthetic','headers':[(b'content-type',b'application/json')]}
        for body,status in [(b'x'*16385,413),(b'{"a":1,"a":2}',422)]:
            incoming,sent=self.run_boundary(base,[{'type':'http.request','body':body,'more_body':False}]);self.assertEqual(incoming,[]);self.assertEqual(sent[0]['status'],status)


class ApplicationEdges(TestCase):
    def setUp(self):self.settings=booking_settings(environment());self.store=PublicStore()

    def test_insecure_settings_and_missing_trusted_address_resolver_never_create_an_application(self):
        for value in ('http://example.test','https://user@example.test','https://example.test/path','https://example.test?query','https://example.test#fragment'):
            with self.assertRaises(ValueError):replace(self.settings,origin=value)
        for changes in ({'receipt_key':None},{'context_key':None},{'risk_key':None}):
            with self.assertRaises(ValueError):replace(self.settings,**changes)
        with self.assertRaises(ValueError):create_application(self.store,self.settings,verified_client_address=None)

    def test_invalid_and_conflicting_provider_notifications_return_fixed_safe_results(self):
        mail=Mock();wake=Mock()
        app=create_application(self.store,self.settings,verified_client_address=lambda r:'127.0.0.1',projection_reader=Reader(True),webhook_account=object(),email_webhook=mail,wake_publisher=wake)
        with TestClient(app,base_url=installation()['origin']) as client:
            for failure,status,code in [(InvalidWebhook(),400,'invalid_event'),(EventConflict(),409,'event_conflict')]:
                mail.receive.side_effect=failure
                response=client.post('/api/webhooks/resend',json={});self.assertEqual(response.status_code,status);self.assertEqual(response.json(),{'code':code})
                with patch('appointment_system.application.accept_webhook',side_effect=failure):
                    response=client.post('/api/webhooks/razorpay',json={});self.assertEqual(response.status_code,status);self.assertEqual(response.json(),{'code':code})
            mail.receive.side_effect=None;mail.receive.return_value={'received':True}
            self.assertEqual(client.post('/api/webhooks/resend',json={}).json(),{'received':True})
            self.assertEqual(mail.receive.call_args.kwargs['on_saved'],wake.publish)

    def test_stale_or_invalid_context_gets_a_new_epoch_bound_cookie_and_closed_schedule_refuses_creation(self):
        app=create_application(self.store,self.settings,verified_client_address=lambda r:'127.0.0.1',projection_reader=Reader(True))
        with TestClient(app,base_url=installation()['origin']) as client:
            headers={'Origin':installation()['origin']}
            client.cookies.set('__Host-appointment-checkout','invalid',domain='practice.example.test',path='/')
            response=client.post('/api/checkout-context',json={},headers=headers);self.assertEqual(response.status_code,200)
            saved=next(iter(self.store.contexts.values()));saved['activation_epoch']='different-activation'
            response=client.post('/api/checkout-context',json={},headers=headers);self.assertEqual(response.status_code,200);self.assertEqual(len(self.store.contexts),2)
            self.store.public_policy=lambda:{'schedule_browsing_open':False}
            self.assertEqual(client.post('/api/checkout-context',json={},headers=headers).status_code,503)
            self.assertEqual(len(self.store.contexts),2)
