"""Synthetic contact contracts: never sends messages or calls a real database."""
import base64
import json
import unittest
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from unittest.mock import Mock,patch
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.contact import ContactSecrets,EnquiryInput,enquiry_payload,public_enquiry
from backend.booking_engine.connection import StorageUnavailable

ORIGIN='https://sarsa.example'
class ContactTests(unittest.TestCase):
    def setUp(self):
        self.env={'SARSA_CONTACT_KEYS':json.dumps({'digest':base64.urlsafe_b64encode(b'x'*32).decode(),'encryption':[Fernet.generate_key().decode()]})}
        self.keys=ContactSecrets.from_environment(self.env)
        self.store=Mock();self.store.consume_limit.return_value={'allowed':True,'retry_after':60}
        self.wake=Mock();self.identifier=str(uuid4());self.receipt='a'*43
        self.body={'request_id':self.identifier,'name':'Synthetic Name','email':'CaseSensitive@example.com','phone':'','subject':'Consultation question','message':'A synthetic question.'}
        self.result={'code':'ok','request_id':self.identifier,'state':'awaiting_verification','generation':1,'server_now':'2030-01-01T00:00:00Z','code_expires_at':'2030-01-01T00:05:00Z','resend_after':'2030-01-01T00:01:00Z','sends_remaining':2,'verification_delivery':'queued'}
        self.store.start_enquiry.return_value=self.result
        self.store.enquiry_status.return_value=self.result
        self.store.enquiry_verification_context.return_value={'email':self.body['email'],'generation':1}
        self.app=create_application(self.store,Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32),verified_client_address=lambda _:'192.0.2.1',contact_secrets=self.keys,wake_publisher=self.wake,contact_delivery_ready=True)
        self.client=TestClient(self.app,base_url=ORIGIN,raise_server_exceptions=False)
        self.headers={'Origin':ORIGIN,'X-Enquiry-Receipt':self.receipt}
    def post(self,path,body=None,headers=None):
        return self.client.post('/api/contact/'+path,json=self.body if body is None else body,headers=self.headers if headers is None else headers)
    def test_optional_phone_and_preserved_email(self):
        body=EnquiryInput(**self.body);self.assertEqual(body.phone,'');self.assertEqual(body.email,'CaseSensitive@example.com')
        with self.assertRaises(ValidationError):EnquiryInput(**dict(self.body,phone='123'))
        with self.assertRaises(ValidationError):EnquiryInput(**dict(self.body,verificationToken='old-cache-token'))
    def test_start_saves_before_wake_and_exposes_no_secret_or_contact_fields(self):
        order=[];self.store.start_enquiry.side_effect=lambda *args:order.append('commit') or self.result
        self.wake.publish.side_effect=lambda:order.append('wake')
        response=self.post('start');self.assertEqual(response.status_code,200);self.assertEqual(order,['commit','wake'])
        for value in [self.body['email'],self.body['message'],self.receipt]:self.assertNotIn(value,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        args=self.store.start_enquiry.call_args.args;self.assertEqual(len(args[4]),64);self.assertNotIn('code',args[3]);self.assertNotIn(self.body['email'],args[5])
    def test_closed_intake_or_storage_failure_never_reports_received(self):
        self.store.start_enquiry.return_value={'code':'contact_unavailable'};self.assertEqual(self.post('start').status_code,503)
        self.store.start_enquiry.side_effect=StorageUnavailable('private detail');r=self.post('start');self.assertEqual(r.status_code,503);self.assertNotIn('private detail',r.text);self.wake.publish.assert_not_called()
    def test_origin_receipt_and_quota_are_required(self):
        for headers in [{},{'Origin':ORIGIN},{'Origin':'https://evil.example','X-Enquiry-Receipt':self.receipt}]:self.assertEqual(self.post('start',headers=headers).status_code,403)
        self.store.consume_limit.return_value={'allowed':False,'retry_after':60};self.assertEqual(self.post('start').status_code,429)
        self.store.start_enquiry.assert_not_called()
    def test_dedicated_keys_missing_does_not_enable_legacy_verification(self):
        app=create_application(self.store,Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32),verified_client_address=lambda _:'192.0.2.1')
        client=TestClient(app,base_url=ORIGIN,raise_server_exceptions=False)
        self.assertEqual(client.post('/api/contact/start',json=self.body,headers=self.headers).status_code,503)
    def test_keys_alone_cannot_enable_intake_before_delivery_is_connected(self):
        app=create_application(self.store,Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32),verified_client_address=lambda _:'192.0.2.1',contact_secrets=self.keys)
        client=TestClient(app,base_url=ORIGIN,raise_server_exceptions=False)
        self.assertEqual(client.post('/api/contact/start',json=self.body,headers=self.headers).status_code,503)
        self.assertEqual(client.post('/api/contact/resend',json={'request_id':self.identifier,'operation_id':str(uuid4())},headers=self.headers).status_code,503)
        self.store.start_enquiry.assert_not_called();self.store.resend_enquiry.assert_not_called()
    def test_code_cipher_and_digest_bound_to_enquiry_email_generation(self):
        digest,encrypted=self.keys.challenge(self.identifier,self.body['email'],1)
        expires=datetime.now(timezone.utc)+timedelta(minutes=5)
        code=self.keys.open_code(encrypted,self.identifier,self.body['email'],1,expires)
        self.assertEqual(len(code),6);self.assertTrue(code.isdecimal())
        self.assertEqual(digest,self.keys.digest('code',self.identifier,1,self.body['email'],code))
        for id,email,generation in [(str(uuid4()),self.body['email'],1),(self.identifier,'other@example.com',1),(self.identifier,self.body['email'],2)]:
            with self.assertRaises(ValueError):self.keys.open_code(encrypted,id,email,generation,expires)
        with self.assertRaises(ValueError):self.keys.open_code(encrypted,self.identifier,self.body['email'],1,datetime.now(timezone.utc)-timedelta(seconds=1))
        self.assertNotEqual(self.keys.digest('code',self.identifier,1,self.body['email'],code),self.keys.digest('receipt',self.identifier,code))
    def test_rotation_retains_pending_ciphertext(self):
        _,encrypted=self.keys.challenge(self.identifier,self.body['email'],1)
        raw=json.loads(self.env['SARSA_CONTACT_KEYS']);raw['encryption'].insert(0,Fernet.generate_key().decode())
        rotated=ContactSecrets.from_environment({'SARSA_CONTACT_KEYS':json.dumps(raw)})
        self.assertEqual(len(rotated.open_code(encrypted,self.identifier,self.body['email'],1,datetime.now(timezone.utc)+timedelta(minutes=5))),6)
    def test_wrong_malformed_and_duplicate_key_configuration_rejected(self):
        for raw in ['{}','null','{"digest":"x","digest":"y","encryption":[]}',json.dumps({'digest':'bad','encryption':[]})]:
            with self.assertRaises(ValueError):ContactSecrets.from_environment({'SARSA_CONTACT_KEYS':raw})
    def test_verify_uses_exact_code_and_stored_email_not_general_cache(self):
        self.store.verify_enquiry.return_value=dict(self.result,state='received')
        body={'request_id':self.identifier,'generation':1,'code':'000123'}
        self.assertEqual(self.post('verify',body).json()['state'],'received')
        args=self.store.verify_enquiry.call_args.args
        self.assertEqual(args[3],self.keys.digest('code',self.identifier,1,self.body['email'],'000123'))
        self.assertNotIn('000123',str(args))
        self.assertEqual(self.post('verify',dict(body,email='other@example.com')).status_code,422)
        self.assertEqual(self.post('verify',dict(body,code='12345')).status_code,422)
    def test_wrong_receipt_context_prevents_verification(self):
        self.store.enquiry_verification_context.return_value=None
        self.assertEqual(self.post('verify',{'request_id':self.identifier,'generation':1,'code':'123456'}).status_code,403)
        self.store.verify_enquiry.assert_not_called()
    def test_resend_last_generation_can_replay_without_generating_generation_four(self):
        self.store.enquiry_verification_context.return_value={'email':self.body['email'],'generation':3}
        self.store.resend_enquiry.return_value=dict(self.result,generation=3,sends_remaining=0)
        r=self.post('resend',{'request_id':self.identifier,'operation_id':str(uuid4())})
        self.assertEqual(r.status_code,200);self.assertEqual(self.store.resend_enquiry.call_args.args[3],3)
    def test_schema_error_hides_submitted_code(self):
        r=self.post('verify',{'request_id':self.identifier,'generation':1,'code':'private-invalid'})
        self.assertEqual(r.status_code,422);self.assertNotIn('private-invalid',r.text)
    def test_status_is_read_only_and_projection_minimal(self):
        self.store.enquiry_status.return_value=dict(self.result,payload=self.body,code_ciphertext='secret',code_digest='hash')
        r=self.post('status',{'request_id':self.identifier});self.assertEqual(r.status_code,200)
        self.assertNotIn('payload',r.json());self.assertNotIn('code_digest',r.json());self.wake.publish.assert_not_called()
    def test_changed_payload_fingerprint_changes(self):
        _,first=enquiry_payload(EnquiryInput(**self.body));_,second=enquiry_payload(EnquiryInput(**dict(self.body,message='Another enquiry.')))
        self.assertNotEqual(first,second)
    def test_incomplete_or_inconsistent_saved_result_is_not_success(self):
        for change in [{'generation':True},{'sends_remaining':0},{'request_id':'bad'},{'server_now':'bad'},{'resend_after':None}]:
            self.store.enquiry_status.return_value=dict(self.result,**change)
            self.assertEqual(self.post('status',{'request_id':self.identifier}).status_code,503)
        self.store.enquiry_status.return_value={'code':'ok','state':'received'}
        self.assertEqual(self.post('status',{'request_id':self.identifier}).status_code,503)
    def test_email_quota_uses_case_folded_address_without_changing_delivery_spelling(self):
        self.post('start')
        first=self.store.start_enquiry.call_args.args
        self.post('start',dict(self.body,email='casesensitive@example.com'))
        second=self.store.start_enquiry.call_args.args
        self.assertEqual(first[6],second[6]);self.assertNotEqual(first[3]['email'],second[3]['email'])
