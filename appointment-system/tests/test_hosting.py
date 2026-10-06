"""Actual composed routes, fault isolation and exact host/worker authority."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.configuration import installation
from appointment_system.hosting import create_hosted_application
from appointment_system.keys import encode
from appointment_system.worker_access import WorkerKey
from appointment_system.studio import StudioServices
from appointment_system.google_access import refresh_connection
from appointment_system.google_oauth import GoogleFailure
from .test_application import PublicStore,Reader,environment,protection
from appointment_system.serialization import canonical

class WorkerStore(PublicStore):
    def begin_recovery_run(self,run,release,scheduled):
        self.calls.append(('plan',release));return {'run_id':run,'release_digest':release,'empty':True}

class Hosting(unittest.TestCase):
    def setUp(self):
        self.facts=installation()|{'environment':'production'};self.store=WorkerStore()
        self.keys={name:encode(bytes([byte])*32) for name,byte in [('RECOVERY',21),('EMAIL',22),('GOOGLE',23)]}
        self.env=environment()|{'VERCEL':'1','VERCEL_ENV':'production'}|{'BOOKING_'+name+'_WORKER_KEY':value for name,value in self.keys.items()}
        self.patches=[patch('appointment_system.hosting.installation',return_value=self.facts),
            patch('appointment_system.hosting.purpose_store',return_value=self.store),
            patch('appointment_system.projection.ProjectionReader',return_value=Reader(False))]
        self.env['BOOKING_CONTROL_READ_KEY']=encode(b'R'*32)
        for item in self.patches:item.start();self.addCleanup(item.stop)
        self.client=TestClient(create_hosted_application(self.env,release_digest='a'*64),base_url=installation()['origin'])

    def test_composed_process_enquiries_and_private_diagnostics_do_not_collapse_with_missing_payments(self):
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertEqual(self.client.get('/booking').status_code,404)
        self.assertEqual(self.client.post('/api/contact/start',json={},headers={'Origin':installation()['origin']}).status_code,422)
        path='/api/internal/recovery/configuration'
        self.assertEqual(self.client.post(path,json={}).status_code,401)
        reply=self.client.post(path,json={},headers={'Authorization':'Bearer '+self.keys['RECOVERY']})
        self.assertEqual(reply.status_code,200,reply.text);value=reply.json()
        self.assertEqual(value['release_digest'],'a'*64);self.assertEqual(value['provider_acceptance'],'not_checked')
        self.assertFalse(value['configured']['payment_accounts']);self.assertTrue(value['configured']['recovery_contract'])
        for secret in self.keys.values():self.assertNotIn(secret,reply.text)

    def test_composed_worker_contract_gets_verified_release_and_only_matching_credentials(self):
        body={'run_id':str(uuid4()),'release_digest':'a'*64,'scheduled_at':1};path='/api/internal/worker/plan'
        self.assertEqual(self.client.post(path,json=body).status_code,401)
        headers={'Authorization':'Bearer '+self.keys['RECOVERY']}
        self.assertEqual(self.client.post(path,json=body|{'release_digest':'b'*64},headers=headers).status_code,409)
        reply=self.client.post(path,json=body,headers=headers)
        self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(self.store.calls,[('plan','a'*64)])
        for old in ('google/run','email/run','recovery/plan','contact/email'):
            self.assertEqual(self.client.post('/api/internal/'+old,json={},headers=headers).status_code,404)

    def test_alternate_or_duplicate_host_headers_are_denied_before_business_calls(self):
        self.assertEqual(self.client.get('/api/health',headers={'Host':'foreign.example.test'}).status_code,421)
        self.assertEqual(self.client.get('/api/health',headers=[('Host','practice.example.test'),('Host','practice.example.test')]).status_code,421)
        self.assertEqual(self.store.calls,[])

    def test_missing_worker_duty_does_not_borrow_another_secret_or_break_process(self):
        env=dict(self.env);del env['BOOKING_RECOVERY_WORKER_KEY']
        client=TestClient(create_hosted_application(env,release_digest='a'*64),base_url=installation()['origin'])
        self.assertEqual(client.get('/api/health').status_code,200)
        self.assertEqual(client.post('/api/internal/worker/plan',json={'run_id':str(uuid4()),'release_digest':'a'*64,'scheduled_at':1},
            headers={'Authorization':'Bearer '+self.keys['EMAIL']}).status_code,503)
        env['BOOKING_RECOVERY_WORKER_KEY']=self.keys['EMAIL']
        client=TestClient(create_hosted_application(env,release_digest='a'*64),base_url=installation()['origin'])
        self.assertEqual(client.get('/api/health').status_code,503)

class StaffComposition(unittest.TestCase):
    def env(self):
        return {'BOOKING_GOOGLE_CLIENT_ID':'123456789012-synthetic.apps.googleusercontent.com',
            'BOOKING_GOOGLE_CLIENT_SECRET':'GOCSPX-synthetic-test-secret',
            'BOOKING_GOOGLE_TOKEN_KEYS':canonical(protection('google-grant',31)),
            'BOOKING_STAFF_SESSION_KEYS':canonical(protection('staff-session',32)),
            'BOOKING_GOOGLE_RESOURCE_KEYS':canonical(protection('google-resource-grant',33))}

    def test_missing_or_malformed_resource_connection_does_not_disable_staff_signin(self):
        for value in (None,'malformed', '{}'):
            env=self.env()
            if value is not None:env['BOOKING_GOOGLE_RESOURCES']=value
            with self.subTest(value=value):
                services=StudioServices.from_environment(env)
                self.assertIsNone(services.resources);self.assertTrue(services.issue('session').startswith('s1.'))

    def test_missing_resource_cannot_fall_back_to_the_retired_google_connection_writer(self):
        services=StudioServices.from_environment(self.env())
        class Refuse:
            def __getattr__(self,name):raise AssertionError('Retired writer reached')
        with self.assertRaisesRegex(GoogleFailure,'google_connection_unavailable'):
            refresh_connection(Refuse(),services,'client')

    def test_worker_key_requires_canonical_padded_encoding_and_rejects_duplicate_headers(self):
        from starlette.datastructures import Headers
        value=encode(b'X'*32);key=WorkerKey(value)
        self.assertTrue(key.accepts(Headers({'authorization':'Bearer '+value})))
        self.assertFalse(key.accepts(Headers(raw=[(b'authorization',('Bearer '+value).encode())]*2)))
        for invalid in (value[:-1],value[:-2]+'Z=',False):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):WorkerKey(invalid)
