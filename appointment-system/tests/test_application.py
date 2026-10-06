"""Real HTTP boundary checks with explicit non-network database/provider ports."""
from copy import deepcopy
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import Settings,create_application
from appointment_system.credentials import ReceiptKeys,ContextKeys
from appointment_system.keys import KeyRing,encode
from appointment_system.secret_configuration import historical,booking_settings
from appointment_system.serialization import canonical
from appointment_system.configuration import installation
from appointment_system.errors import Rejected
from appointment_system.storage import UnavailableStore
from .fixtures import business


def protection(purpose,byte):
    facts=installation()
    return {'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
            'purpose':purpose,'active':'current','keys':{'current':encode(bytes([byte])*32)}}


def environment():
    return {'BOOKING_RECEIPT_KEYS':canonical(protection('receipt',1)),
            'BOOKING_CONTEXT_KEYS':canonical(protection('context',2)),
            'BOOKING_RISK_KEYS':canonical(protection('risk',3))}


class Reader:
    def __init__(self,enabled):self.enabled=enabled;self.calls=0
    async def read(self):
        self.calls+=1
        return {'enabled':self.enabled,'activation_epoch':'546d4db9-b5ce-42e9-84ce-85aa356be8a8'}


class PublicStore:
    _expected_host='localhost'
    def __init__(self):self.calls=[];self.contexts={}
    def consume_limit(self,scope,identity,*,booking=False):
        self.calls.append(('limit',scope));return {'allowed':True,'retry_after':0}
    def require_booking_admission(self):return '546d4db9-b5ce-42e9-84ce-85aa356be8a8'
    def public_policy(self):
        self.calls.append(('policy',));return {'policy':business(),'quote_version':'x','schedule_browsing_open':True}
    def context_snapshot(self,identifier):
        return {'server_now':'2026-10-02T18:00:00Z','context':self.contexts.get(str(identifier))}
    def create_context(self,identifier,digest,metadata):
        self.calls.append(('context',str(identifier),metadata['format'],metadata['key_id']))
        self.contexts[str(identifier)]={'credential_digest':digest,'credential_format':metadata['format'],
          'credential_key_id':metadata['key_id'],'activation_epoch':self.require_booking_admission(),
          'expires_at':'2030-01-01T00:00:00Z'}


class HTTPApplication(unittest.TestCase):
    def setUp(self):
        self.settings=booking_settings(environment());self.store=PublicStore();self.reader=Reader(True)
        app=create_application(self.store,self.settings,verified_client_address=lambda request:'127.0.0.1',projection_reader=self.reader)
        self.client=TestClient(app,base_url=installation()['origin'])
        self.headers={'Origin':installation()['origin']}

    def test_policy_exposes_only_public_receipt_key_id_and_creates_versioned_context(self):
        result=self.client.get('/api/booking-policy')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['receipt_access'],{'version':1,'key_id':'current'})
        self.assertNotIn(encode(b'\1'*32),result.text)
        created=self.client.post('/api/checkout-context',json={},headers=self.headers)
        self.assertEqual(created.status_code,200)
        cookie=created.headers['set-cookie']
        self.assertIn('__Host-appointment-checkout=c1.current.',cookie)
        self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=strict',cookie)
        self.assertEqual(self.client.post('/api/checkout-context',json={},headers=self.headers).status_code,200)
        self.assertEqual(len([call for call in self.store.calls if call[0]=='context']),1)

    def test_off_routes_cannot_reach_database_but_enquiries_health_and_company_survive(self):
        self.reader.enabled=False
        for path in ('/booking','/receipt','/studio','/api/booking-policy','/api/checkout/status','/Booking','/studio//appointments'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,404,path)
        self.assertEqual(self.store.calls,[])
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertEqual(self.client.post('/api/contact/start',json={},headers=self.headers).status_code,422)
        self.assertEqual(self.client.get('/company/booking-control').status_code,200)

    def test_off_or_new_activation_during_request_cannot_return_booking_content(self):
        original=self.store.public_policy
        def off():
            self.reader.enabled=False
            return original()
        self.store.public_policy=off
        response=self.client.get('/api/booking-policy')
        self.assertEqual(response.status_code,404)
        self.assertNotIn('quote_version',response.text)
        self.assertEqual(self.reader.calls,2)
        self.reader.enabled=True
        async def changed():
            self.reader.calls+=1
            return {'enabled':True,'activation_epoch':str(uuid4())}
        self.reader.read=changed
        self.store.public_policy=original
        self.assertEqual(self.client.get('/api/booking-policy').status_code,404)

    def test_projection_failure_before_response_hides_content_without_repeating_business_work(self):
        from appointment_system.service_control import ControlError
        async def unavailable():
            self.reader.calls+=1
            if self.reader.calls==2:raise ControlError('projection_configuration')
            return {'enabled':True,'activation_epoch':'546d4db9-b5ce-42e9-84ce-85aa356be8a8'}
        self.reader.read=unavailable
        response=self.client.get('/api/booking-policy')
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.store.calls.count(('policy',)),1)
        self.assertEqual(response.headers['cache-control'],'private, no-store')

    def test_public_state_and_origin_checks_do_not_borrow_staff_credentials(self):
        self.assertEqual(self.client.get('/api/service-state').json()['enabled'],True)
        self.assertEqual(self.store.calls,[])
        response=self.client.post('/api/checkout-context',json={},headers={'Origin':'https://foreign.example.test'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.store.calls,[])
        response=self.client.post('/api/checkout-context',content='{}',headers=self.headers)
        self.assertEqual(response.status_code,415)
        self.assertEqual(self.store.calls,[])

    def test_missing_purpose_never_falls_back_to_public_store(self):
        missing=UnavailableStore()
        from appointment_system.connection import StorageUnavailable
        with self.assertRaises(StorageUnavailable):missing.studio_session('opaque','client','origin')
        self.assertEqual(self.store.calls,[])

    def test_retired_worker_consumers_cannot_bypass_common_turn_authority(self):
        for path in ('/api/internal/google/run','/api/internal/email/run','/api/internal/email/events',
                     '/api/internal/contact/email','/api/internal/contact/google',
                     '/api/internal/recovery/plan','/api/internal/recovery/payment',
                     '/api/internal/recovery/payment-events','/api/internal/recovery/maintenance'):
            response=self.client.post(path,json={},headers={'Authorization':'Bearer old-worker-key'})
            self.assertEqual(response.status_code,404,path)
        self.assertEqual(self.store.calls,[])

    def test_ambiguous_or_oversized_json_is_rejected_before_storage(self):
        headers=self.headers|{'Content-Type':'application/json'}
        for body in ('{"request_id":"one","request_id":"two"}',
                     '{"value":1.5}', '{"value":NaN}', '['*34+'0'+']'*34):
            response=self.client.post('/api/checkout-context',content=body,headers=headers)
            self.assertEqual(response.status_code,422)
            self.assertNotIn(body,response.text)
        self.assertEqual(self.client.post('/api/checkout-context',content='"'+'x'*16384+'"',headers=headers).status_code,413)
        self.assertEqual(self.store.calls,[])


class ProtectedConfiguration(unittest.TestCase):
    def test_required_rings_have_exact_installation_and_distinct_material(self):
        good=environment();self.assertIsInstance(booking_settings(good),Settings)
        for name in good:
            wrong=dict(good);value=deepcopy(protection('risk' if name.endswith('RISK_KEYS') else 'receipt',1))
            value['installation_id']=str(uuid4());wrong[name]=canonical(value)
            with self.assertRaises(Rejected):booking_settings(wrong)
        wrong=environment();wrong['BOOKING_CONTEXT_KEYS']=canonical(protection('context',1))
        with self.assertRaises(Rejected):booking_settings(wrong)

    def test_legacy_transport_keeps_original_text_bytes_without_guessing_format(self):
        facts=installation();original=b'Original printed context key, at least 32 bytes'
        value={'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
               'readers':{'receipt':{},'context':{}},'materials':{'old-context':encode(original)}}
        self.assertEqual(historical({'BOOKING_LEGACY_PROTECTION':canonical(value)})[1],(('old-context',original),))
        for mutation in ({'installation_id':str(uuid4())},{'environment':'production'},{'version':True},
                         {'materials':{'old-context':'bad'}}):
            with self.assertRaises(Rejected):historical({'BOOKING_LEGACY_PROTECTION':canonical(value|mutation)})

    def test_legacy_reader_metadata_is_immutable_and_shape_cannot_change_after_validation(self):
        value={'old':{'algorithm':'json-sha256','audience':'','purpose':'booking','key_id':None,'encoding':'hex64'}}
        parsed=booking_settings(environment())
        keys=ReceiptKeys(parsed.receipt_key.ring,value)
        value['old']['purpose']='context'
        self.assertEqual(keys.legacy['old']['purpose'],'booking')
        with self.assertRaises(TypeError):keys.legacy['old']['purpose']='context'
