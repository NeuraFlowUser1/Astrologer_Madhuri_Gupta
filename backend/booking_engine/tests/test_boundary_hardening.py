"""Additional negative-boundary checks, with synthetic data and no providers."""
import asyncio
import base64
import json
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from backend.booking_engine.application import Settings,RequestBoundary,create_application
from backend.booking_engine.access import COOKIE_NAME,new_context
from backend.booking_engine.contact import ContactSecrets,EnquiryInput,public_enquiry
from backend.booking_engine.contact_records import enquiry_values,verify_owner,prepare_enquiry_tab,write_enquiry_row,HEADERS,TAB_ID
from backend.booking_engine.google_workspace import WorkspaceFailure
from backend.booking_engine.webhook import InvalidWebhook
from backend.booking_engine.email_events import EmailWebhook
from backend.booking_engine.tests import test_http_and_events as http_fixture,test_contact as contact_fixture,test_contact_delivery as delivery_fixture,test_email_events as mail_fixture


class BoundaryHardeningTests(unittest.TestCase):
    def test_secure_settings_are_required_before_routes_exist(self):
        for origin,key in [('http://example.com',b'a'*32),('https://example.com/path',b'a'*32),('https://example.com',b'a')]:
            with self.subTest(origin=origin),self.assertRaises(ValueError):Settings(origin,key,b'b'*32,b'c'*32)
        with self.assertRaises(ValueError):create_application(Mock(),Mock(),verified_client_address=None)

    def test_streamed_request_is_bounded_once_and_disconnect_does_no_work(self):
        async def run(kind):
            requests=[];sent=[]
            messages=iter([{'type':'http.disconnect'}] if kind=='disconnect' else [
                {'type':'http.request','body':b'{','more_body':True},
                {'type':'http.request','body':b'}','more_body':False},
                {'type':'http.disconnect'}])
            async def receive():return next(messages)
            async def send(message):sent.append(message)
            async def app(scope,receive,send):
                if scope['type']=='http':requests.extend([await receive(),await receive()]);await send({'type':'http.response.start','status':200,'headers':[(b'cache-control',b'public')]})
                else:requests.append(scope['type'])
            scope={'type':'lifespan'} if kind=='lifespan' else {'type':'http','method':'POST','path':'/safe','headers':[(b'content-type',b'application/json')]}
            await RequestBoundary(app)(scope,receive,send)
            return requests,sent
        self.assertEqual(asyncio.run(run('disconnect')),([],[]))
        self.assertEqual(asyncio.run(run('lifespan'))[0],['lifespan'])
        requests,sent=asyncio.run(run('stream'))
        self.assertEqual(requests,[{'type':'http.request','body':b'{}','more_body':False},{'type':'http.disconnect'}])
        self.assertEqual(dict(sent[0]['headers'])[b'cache-control'],b'no-store')

    def test_checkout_context_reuses_valid_cookie_but_replaces_expired_or_missing_row(self):
        fixture=http_fixture.HttpTests();store,client=fixture.setup_client()
        store.scheduling_snapshot.return_value['schedule_browsing_open']=True
        identifier,token,digest=new_context(b'b'*32);now=datetime.now(timezone.utc)
        store.context_snapshot.return_value={'context':{'credential_digest':digest,'expires_at':(now+timedelta(hours=1)).isoformat()},'server_now':now.isoformat()}
        client.cookies.set(COOKIE_NAME,token)
        response=client.post('/api/checkout-context',json={},headers={'Origin':http_fixture.ORIGIN})
        self.assertEqual(response.status_code,200);self.assertNotIn('set-cookie',response.headers);store.create_context.assert_not_called()
        for row in (None,{'credential_digest':digest,'expires_at':(now-timedelta(seconds=1)).isoformat()}):
            store.create_context.reset_mock();store.context_snapshot.return_value={'context':row,'server_now':now.isoformat()}
            client.cookies.clear();client.cookies.set(COOKIE_NAME,token)
            response=client.post('/api/checkout-context',json={},headers={'Origin':http_fixture.ORIGIN})
            self.assertEqual(response.status_code,200);self.assertIn('set-cookie',response.headers);store.create_context.assert_called_once()
        for change in ({'schedule_browsing_open':False},{'schedule_browsing_open':True,'policy_version':'0'*64}):
            store.create_context.reset_mock();store.scheduling_snapshot.return_value.update(change)
            self.assertEqual(client.post('/api/checkout-context',json={},headers={'Origin':http_fixture.ORIGIN}).status_code,503)
            store.create_context.assert_not_called()

    def test_contact_key_shape_and_canonical_encoding_are_strict(self):
        fixture=contact_fixture.ContactTests();fixture.setUp();normal=json.loads(fixture.env['SARSA_CONTACT_KEYS'])
        noncanonical=normal['digest'][:-2]+('h' if normal['digest'][-2]=='g' else 'B')+'='
        changes=[{'digest':1},{'digest':noncanonical},{'encryption':None},{'encryption':[1]},
                 {'encryption':[normal['digest']]},{'encryption':[normal['encryption'][0]]*2},
                 {'encryption':['?'.ljust(44,'?')]},{'encryption':[normal['encryption'][0][:-2]+'B=']}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):ContactSecrets.from_environment({'SARSA_CONTACT_KEYS':json.dumps(dict(normal,**change))})
        with self.assertRaises(ValueError):ContactSecrets(b'wrong',Mock())
        with self.assertRaises(ValueError):EnquiryInput(**dict(fixture.body,message='contains\x7fcontrol'))
        for generation in (0,4,'1'):
            with self.assertRaises(ValueError):fixture.keys.challenge(fixture.identifier,'case@example.com',generation)

    def test_contact_code_and_status_reject_invalid_material_and_timestamp(self):
        fixture=contact_fixture.ContactTests();fixture.setUp();expires=datetime.now(timezone.utc)+timedelta(minutes=5)
        for encrypted in (None,'a'*8193,'not-encrypted'):
            with self.assertRaises(ValueError):fixture.keys.open_code(encrypted,fixture.identifier,'case@example.com',1,expires)
        for stamp in (None,datetime.now()):
            _,encrypted=fixture.keys.challenge(fixture.identifier,'case@example.com',1)
            with self.assertRaises(ValueError):fixture.keys.open_code(encrypted,fixture.identifier,'case@example.com',1,stamp)
        self.assertEqual(public_enquiry({'code':'contact_unavailable','private':'discard'}),{'code':'contact_unavailable'})
        with self.assertRaises(ValueError):public_enquiry(dict(fixture.result,code_expires_at=None))

    def test_enquiry_workbook_creates_header_and_fixed_tab_then_reuses_them(self):
        workspace=Mock();workspace.request.side_effect=[(200,{'sheets':[]}),(200,{}),(200,{}),(200,{})]
        with patch('backend.booking_engine.contact_records.verify_owner'):
            prepare_enquiry_tab(workspace,'synthetic',str(uuid4()))
        self.assertEqual([call.args[0] for call in workspace.request.call_args_list],['GET','POST','GET','PUT'])
        self.assertEqual(workspace.request.call_args.kwargs['body'],{'values':[HEADERS]})
        self.assertEqual(workspace.request.call_args.kwargs['params'],{'valueInputOption':'RAW'})
        self.assertEqual(workspace.request.call_args_list[1].kwargs['body']['requests'][0]['addSheet']['properties']['sheetId'],TAB_ID)

    def test_enquiry_layout_mismatch_or_invalid_row_never_writes(self):
        fixture=delivery_fixture.ContactDeliveryTests();fixture.setUp();values=enquiry_values(fixture.job)
        for data in ({'sheets':None},{'sheets':[{'properties':{'sheetId':TAB_ID,'title':'Wrong'}}]}):
            workspace=Mock();workspace.request.return_value=(200,data)
            with patch('backend.booking_engine.contact_records.verify_owner'),self.assertRaises(WorkspaceFailure):prepare_enquiry_tab(workspace,'synthetic',str(uuid4()))
            self.assertTrue(all(call.args[0]=='GET' for call in workspace.request.call_args_list))
        for values,row in ((values,True),(values,10001),(['wrong']+values[1:],2),(['x'*4001]+values[1:],2),(values[:1]+['bad-id']+values[2:],2)):
            workspace=Mock()
            with self.assertRaises(WorkspaceFailure):write_enquiry_row(workspace,{'spreadsheet_id':'synthetic','intent':str(uuid4()),'row':row,'values':values})
            workspace.request.assert_not_called()
        with self.assertRaises(WorkspaceFailure):enquiry_values({'id':'bad'})
        workspace=Mock();workspace.request.return_value=(200,{});workspace.validate_workbook.return_value='other'
        with self.assertRaises(WorkspaceFailure):verify_owner(workspace,'synthetic','intent')

    def test_mail_reports_reject_invalid_identity_and_signed_shapes(self):
        fixture=mail_fixture.EmailEventTests();fixture.setUp()
        for secrets in ([fixture.secret],(42,),('whsec_'+base64.b64encode(b'x').decode(),)):
            with self.assertRaises(ValueError):EmailWebhook(secrets)
        body,headers=fixture.signed()
        invalid=Headers(raw=[(key,b'bad/id' if key==b'svix-id' else value) for key,value in headers.raw])
        with self.assertRaises(InvalidWebhook):fixture.receiver.receive(fixture.store,body,invalid)
        for event in ([],dict(fixture.event,data=[]),dict(fixture.event,data={**fixture.event['data'],'tags':[]})):
            body,headers=fixture.signed(raw=json.dumps(event).encode())
            if isinstance(event,dict) and event['data'] and isinstance(event['data'],dict):
                self.assertEqual(fixture.receiver.receive(fixture.store,body,headers),{'received':True})
            else:
                with self.assertRaises(InvalidWebhook):fixture.receiver.receive(fixture.store,body,headers)
        fixture.store.save_provider_event.assert_not_called()

    def test_signed_webhook_conflict_is_retryable_and_wake_occurs_after_saved_evidence(self):
        fixture=http_fixture.HttpTests();store,client=fixture.setup_client(webhooks=True)
        body=http_fixture.event_body();headers={'content-type':'application/json','x-razorpay-signature':http_fixture.signed(body),'x-razorpay-event-id':'evt_synthetic'}
        store.save_provider_event.return_value='not-the-digest'
        self.assertEqual(client.post('/api/webhooks/razorpay',content=body,headers=headers).status_code,409)
        self.assertEqual(client.post('/api/webhooks/razorpay',json={},headers=headers).status_code,400)
        _,bare=fixture.setup_client()
        self.assertEqual(bare.post('/api/webhooks/razorpay',json={}).status_code,503)
        mail=mail_fixture.EmailEventTests();mail.setUp();mail.store.save_provider_event.return_value='other';mail.store.save_provider_event.side_effect=None
        app=create_application(mail.store,Settings(http_fixture.ORIGIN,b'a'*32,b'b'*32,b'c'*32),verified_client_address=lambda _:'192.0.2.1',email_webhook=mail.receiver)
        body,signed=mail.signed()
        response=TestClient(app).post('/api/webhooks/resend',content=body,headers=dict(signed,**{'content-type':'application/json'}))
        self.assertEqual(response.status_code,409)
