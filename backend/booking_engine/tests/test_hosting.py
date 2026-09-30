import base64
import json
import unittest
from unittest.mock import Mock, patch

import certifi
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.requests import Request
from psycopg.conninfo import conninfo_to_dict

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.hosting import (
    DATABASE_HOST, ORIGIN, booking_keys, create_hosted_application, vercel_client_address,
)


def key(letter):
    return base64.urlsafe_b64encode(letter * 32).decode()


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            'VERCEL': '1', 'VERCEL_ENV': 'production', 'SARSA_PUBLIC_ORIGIN': ORIGIN,
            'SARSA_DATABASE_URL': f'postgresql://sarsa_booking_web:synthetic-password@{DATABASE_HOST}/neondb?sslmode=verify-full',
            'SARSA_BOOKING_KEYS': json.dumps(dict(receipt=key(b'a'), context=key(b'b'), risk=key(b'c'))),
            'SARSA_GOOGLE_CLIENT_ID': '123-synthetic.apps.googleusercontent.com',
            'SARSA_GOOGLE_CLIENT_SECRET': 'synthetic-secret',
            'SARSA_GOOGLE_TOKEN_KEYS': json.dumps([Fernet.generate_key().decode()]),
            'SARSA_STUDIO_SIGNING_KEY': key(b'd'),
        }

    def test_no_network_or_legacy_import_during_composition(self):
        with patch('psycopg.connect', side_effect=AssertionError('Unexpected database connection')):
            app = create_hosted_application(self.environment)
        paths = {route.path for route in app.routes}
        self.assertIn('/studio', paths)
        self.assertIn('/api/checkout/status', paths)
        self.assertNotIn('/api/contact', paths)

    def test_worker_key_is_optional_but_must_be_distinct_when_configured(self):
        for value,valid in [(key(b'w'),True),(key(b'd'),False),(key(b'a'),False),('invalid',False)]:
            environment=dict(self.environment,SARSA_GOOGLE_WORKER_KEY=value)
            with patch('psycopg.connect') as connect:
                app=create_hosted_application(environment)
                response=TestClient(app,base_url=ORIGIN).post('/api/internal/google/run',json={})
            self.assertEqual(response.status_code,401 if valid else 503)
            connect.assert_not_called()

    def test_missing_or_wrong_environment_is_closed_without_leaking_values(self):
        changes = [{name: None} for name in self.environment]
        changes += [{'VERCEL_ENV': 'preview'}, {'SARSA_PUBLIC_ORIGIN': 'https://other.example'},
                    {'SARSA_DATABASE_URL': self.environment['SARSA_DATABASE_URL'].replace('sarsa_booking_web', 'neondb_owner')},
                    {'SARSA_DATABASE_URL': self.environment['SARSA_DATABASE_URL'].replace(DATABASE_HOST, 'other.example')},
                    {'SARSA_DATABASE_URL': self.environment['SARSA_DATABASE_URL'].replace('verify-full', 'disable')},
                    {'SARSA_DATABASE_URL': self.environment['SARSA_DATABASE_URL'] + '&sslkeylogfile=/tmp/forbidden'},
                    {'SARSA_DATABASE_URL': self.environment['SARSA_DATABASE_URL'] + '&sslrootcert=/tmp/untrusted'},
                    {'SARSA_STUDIO_SIGNING_KEY': key(b'a')}]
        for change in changes:
            with self.subTest(change=list(change)):
                environment = dict(self.environment, **change)
                environment = {k: v for k, v in environment.items() if v is not None}
                with patch('psycopg.connect') as connect:
                    response = TestClient(create_hosted_application(environment),base_url=ORIGIN).get('/studio')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn('synthetic', response.text)
                connect.assert_not_called()

    def test_console_url_uses_packaged_certificate_bundle_and_hostname_verification(self):
        environment = dict(self.environment,
            SARSA_DATABASE_URL=self.environment['SARSA_DATABASE_URL'].replace('verify-full', 'require') + '&channel_binding=require')
        with patch('backend.booking_engine.hosting.Store') as store:
            app = create_hosted_application(environment)
        self.assertIn('/studio', {route.path for route in app.routes})
        configured = conninfo_to_dict(store.call_args.args[0])
        self.assertEqual(configured['sslmode'], 'verify-full')
        self.assertEqual(configured['sslrootcert'], certifi.where())
        self.assertEqual(configured['channel_binding'], 'require')
        self.assertEqual(configured['host'], DATABASE_HOST)

    def test_wrong_host_rejected_before_database_or_callback_redirect(self):
        app = create_hosted_application(self.environment)
        with patch('psycopg.connect') as connect:
            response = TestClient(app).get('/api/studio/sign-in/callback?code=synthetic', follow_redirects=False)
        self.assertEqual(response.status_code, 421)
        self.assertNotIn('location', response.headers)
        self.assertNotIn('synthetic', response.text)
        connect.assert_not_called()

    def test_provider_header_contract_and_spoofed_fallback(self):
        for value in ['203.0.113.5', '2001:db8::5']:
            request = Request({'type': 'http', 'headers': [(b'x-vercel-forwarded-for', value.encode())]})
            self.assertEqual(vercel_client_address(request), value)
        for headers in [[], [(b'x-forwarded-for', b'203.0.113.5')],
                        [(b'x-vercel-forwarded-for', b'1.1.1.1, 2.2.2.2')],
                        [(b'x-vercel-forwarded-for', b'fe80::1%eth0')],
                        [(b'x-vercel-forwarded-for', b'1.1.1.1')] * 2]:
            with self.assertRaises(StorageUnavailable):
                vercel_client_address(Request({'type': 'http', 'headers': headers}))

    def test_address_failure_prevents_database_work_and_valid_request_uses_quota(self):
        store = Mock()
        store.consume_limit.return_value = {'allowed': True}
        with patch('backend.booking_engine.hosting.Store', return_value=store):
            app = create_hosted_application(self.environment)
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.assertEqual(client.get('/api/booking-policy').status_code, 503)
        store.consume_limit.assert_not_called()
        response = client.get('/api/booking-policy', headers={'x-vercel-forwarded-for': '203.0.113.5'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertNotIn('203.0.113.5', str(store.consume_limit.call_args))
        self.assertEqual(client.post('/api/webhooks/razorpay', json={}).status_code, 503)

    def test_bad_or_reused_keys_rejected(self):
        for value in ['[]', '{}', '{"receipt":"a","receipt":"b"}',
                      json.dumps(dict(receipt=key(b'a'), context=key(b'a'), risk=key(b'c'))),
                      json.dumps(dict(receipt='not-a-key', context=key(b'b'), risk=key(b'c')))]:
            with self.assertRaises(ValueError):
                booking_keys(value)

    def test_optional_google_failure_does_not_disable_payment_or_receipt_routes(self):
        for changes in [{'SARSA_GOOGLE_TOKEN_KEYS':'invalid'}, {'SARSA_GOOGLE_CLIENT_SECRET':''},
                        {'SARSA_GOOGLE_WORKER_KEY':'invalid'}, {'SARSA_STUDIO_SIGNING_KEY':key(b'a')}]:
            environment = dict(self.environment, **changes)
            with patch('backend.booking_engine.hosting.Store') as store:
                store.return_value.consume_limit.return_value = {'allowed':True}
                app = create_hosted_application(environment)
                paths = {route.path for route in app.routes}
                self.assertIn('/api/checkout/verify-payment', paths)
                self.assertIn('/api/checkout/status', paths)
                response = TestClient(app,base_url=ORIGIN).get('/api/booking-policy',
                    headers={'x-vercel-forwarded-for':'192.0.2.1'})
                self.assertEqual(response.status_code,200)

    def test_contact_configuration_is_independent_and_cannot_open_unfinished_delivery(self):
        for digest,valid in [(key(b'z'),True),(key(b'a'),False),(key(b'd'),False)]:
            env=dict(self.environment,SARSA_CONTACT_KEYS=json.dumps({'digest':digest,'encryption':[Fernet.generate_key().decode()]}))
            with patch('backend.booking_engine.hosting.Store'),patch('backend.booking_engine.hosting.create_application') as compose:
                create_hosted_application(env)
            self.assertEqual(compose.call_args.kwargs['contact_secrets'] is not None,valid)
            self.assertFalse(compose.call_args.kwargs.get('contact_delivery_ready',False))
        with patch('backend.booking_engine.hosting.Store') as store:
            store.return_value.consume_limit.return_value={'allowed':True}
            app=create_hosted_application(dict(self.environment,SARSA_CONTACT_KEYS='invalid'))
            response=TestClient(app,base_url=ORIGIN).get('/api/booking-policy',headers={'x-vercel-forwarded-for':'192.0.2.1'})
        self.assertEqual(response.status_code,200)

    def test_contact_activation_requires_explicit_switch_and_all_consumers(self):
        env=dict(self.environment,SARSA_CONTACT_KEYS=json.dumps({'digest':key(b'k'),'encryption':[Fernet.generate_key().decode()]}),
            SARSA_GOOGLE_WORKER_KEY=key(b'g'),SARSA_EMAIL_WORKER_KEY=key(b'e'),SARSA_RECOVERY_WORKER_KEY=key(b'r'),SARSA_WAKE_KEY=key(b'w'),
            SARSA_RESEND_API_KEY='re_'+'a'*24,SARSA_RESEND_WEBHOOK_SECRET='whsec_'+base64.b64encode(b'z'*32).decode())
        for enabled,expected in [('true',True),('false',False),('TRUE',False),('1',False),('',False)]:
            with patch('backend.booking_engine.hosting.Store'),patch('backend.booking_engine.hosting.create_application') as compose:
                create_hosted_application(dict(env,SARSA_CONTACT_DELIVERY_ENABLED=enabled))
            self.assertEqual(compose.call_args.kwargs['contact_delivery_ready'],expected)
        for missing in ['SARSA_CONTACT_KEYS','SARSA_GOOGLE_WORKER_KEY','SARSA_EMAIL_WORKER_KEY','SARSA_RECOVERY_WORKER_KEY','SARSA_WAKE_KEY','SARSA_RESEND_API_KEY','SARSA_RESEND_WEBHOOK_SECRET','SARSA_GOOGLE_CLIENT_SECRET']:
            with patch('backend.booking_engine.hosting.Store'),patch('backend.booking_engine.hosting.create_application') as compose:
                create_hosted_application(dict(env,SARSA_CONTACT_DELIVERY_ENABLED='true',**{missing:''}))
            self.assertFalse(compose.call_args.kwargs['contact_delivery_ready'])


if __name__ == '__main__':
    unittest.main()
