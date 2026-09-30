import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend.booking_engine.application import Settings, create_application
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.google_oauth import Attempt, GoogleOAuth, GrantCipher, Grant, Access, OAuthSettings, scopes_for
from backend.booking_engine.studio import StudioServices, SESSION_COOKIE, SIGNIN_COOKIE, CONNECT_COOKIE

ORIGIN = 'https://sarsa.example'
CLIENT = '123-synthetic.apps.googleusercontent.com'


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.consume_limit.return_value = {'allowed': True, 'retry_after': 1}
        self.settings = Settings(ORIGIN, b'a'*32, b'b'*32, b'c'*32)
        self.google = Mock(wraps=GoogleOAuth(OAuthSettings(CLIENT, 'synthetic-secret', ORIGIN)))
        self.google.settings = OAuthSettings(CLIENT, 'synthetic-secret', ORIGIN)
        self.cipher = GrantCipher(CLIENT, [Fernet.generate_key()])
        self.services = StudioServices(self.google, self.cipher, b'd'*32)
        self.app = create_application(self.store, self.settings, verified_client_address=lambda _: '192.0.2.1', studio_services=self.services)
        self.client = TestClient(self.app, base_url=ORIGIN, raise_server_exceptions=False)
        self.headers = {'Origin': ORIGIN}

    def prepare(self, purpose='signin', role='client'):
        attempt = Attempt.new(role)
        cookie = 'b'*43
        self.client.cookies.set(SIGNIN_COOKIE if purpose=='signin' else CONNECT_COOKIE, cookie)
        self.store.consume_google_attempt.return_value = dict(role=role, encrypted_attempt=self.cipher.seal_attempt(attempt, purpose),
            subject='synthetic-subject' if purpose=='connect' else None, server_now=datetime.now(timezone.utc).isoformat())
        return attempt

    def callback(self, attempt, purpose='signin', **extra):
        path='/api/studio/sign-in/callback' if purpose=='signin' else '/api/studio/google/callback'
        return self.client.get(path, params=dict(state=attempt.state, code='synthetic-code', **extra), follow_redirects=False)

    def test_start_requires_origin_and_exact_owner_role(self):
        self.store.start_google_attempt.return_value=True
        response=self.client.post('/api/studio/sign-in/start', json={'role':'client'})
        self.assertEqual(response.status_code,403)
        self.store.start_google_attempt.assert_not_called()
        response=self.client.post('/api/studio/sign-in/start', json={'role':'other'},headers=self.headers)
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/studio/sign-in/start', json={'role':'client'},headers=self.headers)
        self.assertEqual(response.status_code,200)
        query=parse_qs(urlsplit(response.json()['authorization_url']).query)
        self.assertEqual(query['scope'],['openid email'])
        self.assertEqual(query['access_type'],['online'])
        self.assertEqual(query['redirect_uri'],[ORIGIN+'/api/studio/sign-in/callback'])
        for flag in ('Secure','HttpOnly','SameSite=lax','Max-Age=600','Path=/'):
            self.assertIn(flag,response.headers['set-cookie'])
        self.assertNotIn(query['state'][0], self.store.start_google_attempt.call_args.args[0])

    def test_start_commit_uncertainty_never_issues_cookie_or_redirect(self):
        self.store.start_google_attempt.side_effect=StorageUnavailable('synthetic detail')
        response=self.client.post('/api/studio/sign-in/start',json={'role':'agency'},headers=self.headers)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('set-cookie',response.headers)
        self.assertNotIn('authorization_url',response.text)

    def test_signin_consumes_before_exchange_and_issues_cookie_only_after_commit(self):
        attempt=self.prepare()
        sequence=[]
        self.store.consume_google_attempt.side_effect=lambda *args: (sequence.append('consume') or dict(role='client', encrypted_attempt=self.cipher.seal_attempt(attempt,'signin')))
        self.google.sign_in.side_effect=lambda *args: (sequence.append('exchange') or 'synthetic-subject')
        self.store.finish_google_signin.side_effect=lambda *args: (sequence.append('commit') or True)
        response=self.callback(attempt)
        self.assertEqual(sequence,['consume','exchange','commit'])
        self.assertEqual(response.headers['location'],'/studio?connection=signed-in')
        for flag in ('Secure','HttpOnly','SameSite=strict','Max-Age=3600'):
            self.assertIn(flag,','.join(response.headers.get_list('set-cookie')))
        self.assertNotIn('synthetic-code',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_consumed_expired_wrong_browser_or_missing_cookie_prevents_exchange(self):
        attempt=self.prepare()
        self.store.consume_google_attempt.return_value=None
        self.assertEqual(self.callback(attempt).headers['location'],'/studio?connection=failed')
        self.google.sign_in.assert_not_called()
        self.client.cookies.clear()
        self.store.consume_google_attempt.reset_mock()
        self.callback(attempt)
        self.store.consume_google_attempt.assert_not_called()

    def test_denial_duplicate_state_and_code_error_conflict_are_not_exchanged(self):
        attempt=self.prepare()
        response=self.client.get('/api/studio/sign-in/callback',params={'state':attempt.state,'error':'access_denied'},follow_redirects=False)
        self.assertEqual(response.headers['location'],'/studio?connection=failed')
        self.google.sign_in.assert_not_called()
        self.prepare()
        self.client.get('/api/studio/sign-in/callback?state='+attempt.state+'&state='+attempt.state+'&code=code',follow_redirects=False)
        self.google.sign_in.assert_not_called()
        self.callback(attempt,error='access_denied')
        self.google.sign_in.assert_not_called()

    def test_uncertain_finish_never_issues_session_cookie(self):
        attempt=self.prepare()
        self.google.sign_in.return_value='synthetic-subject'
        self.store.finish_google_signin.side_effect=StorageUnavailable('uncertain secret')
        response=self.callback(attempt)
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['location'],'/studio?connection=check')
        self.assertNotIn(SESSION_COOKIE,','.join(response.headers.get_list('set-cookie')))
        self.assertNotIn('uncertain secret',response.text)

    def test_connect_start_uses_session_role_not_request_body(self):
        self.client.cookies.set(SESSION_COOKIE,'s'*43)
        self.store.studio_session.return_value={'role':'agency','subject':'agency-subject'}
        self.store.start_google_attempt.return_value=True
        response=self.client.post('/api/studio/google/start',json={'role':'client'},headers=self.headers)
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/studio/google/start',json={},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.store.start_google_attempt.call_args.args[3],'agency')
        self.assertNotIn('calendar',response.json()['authorization_url'])

    def test_connection_encrypts_before_commit_and_failed_revision_stays_failed(self):
        attempt=self.prepare('connect')
        grant=Grant('client','synthetic-subject','sarsajyotish@gmail.com','synthetic-refresh',scopes_for('client'))
        self.google.exchange.return_value=Access('synthetic-access',datetime.now(timezone.utc),grant)
        self.store.finish_google_connection.return_value=True
        response=self.callback(attempt,'connect')
        self.assertEqual(response.headers['location'],'/studio?connection=saved')
        args=self.store.finish_google_connection.call_args.args
        self.assertNotIn('synthetic-refresh',args[2])
        self.assertEqual(self.google.exchange.call_args.kwargs['previous_subject'],'synthetic-subject')
        attempt=self.prepare('connect')
        self.store.finish_google_connection.return_value=False
        self.assertEqual(self.callback(attempt,'connect').headers['location'],'/studio?connection=failed')

    def test_private_status_and_logout_do_not_expose_session_or_grant(self):
        self.assertEqual(self.client.get('/api/studio/status').status_code,401)
        self.client.cookies.set(SESSION_COOKIE,'s'*43)
        self.store.studio_session.return_value={'role':'client','subject':'synthetic-subject'}
        self.store.studio_connection_status.return_value={'authorization_saved':True,'reconnect_required':False}
        response=self.client.get('/api/studio/status')
        self.assertEqual(response.json()['email'],'sarsajyotish@gmail.com')
        self.assertNotIn('synthetic-subject',response.text)
        self.assertEqual(self.client.post('/api/studio/logout',json={}).status_code,403)
        response=self.client.post('/api/studio/logout',json={},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.store.studio_logout.assert_called_once()
        self.assertIn('Max-Age=0',response.headers['set-cookie'])

    def test_workbook_preparation_requires_session_origin_and_own_role(self):
        with patch('backend.booking_engine.studio.prepare_owner_workbook') as prepare:
            self.assertEqual(self.client.post('/api/studio/workbook/prepare',json={}).status_code,403)
            self.assertEqual(self.client.post('/api/studio/workbook/prepare',json={},headers=self.headers).status_code,403)
            prepare.assert_not_called()
            self.client.cookies.set(SESSION_COOKIE,'s'*43)
            self.store.studio_session.return_value={'role':'agency','subject':'synthetic-subject'}
            self.assertEqual(self.client.post('/api/studio/workbook/prepare',json={'role':'client'},headers=self.headers).status_code,422)
            prepare.return_value=(Mock(),{'spreadsheet_id':'synthetic_sheet'})
            response=self.client.post('/api/studio/workbook/prepare',json={},headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(prepare.call_args.args[2],'agency')
            self.assertEqual(response.json(),{'workbook_url':'https://docs.google.com/spreadsheets/d/synthetic_sheet'})
            prepare.side_effect=StorageUnavailable('private details')
            response=self.client.post('/api/studio/workbook/prepare',json={},headers=self.headers)
            self.assertEqual(response.status_code,503)
            self.assertNotIn('private details',response.text)

    def test_private_page_security_and_disabled_configuration(self):
        response=self.client.get('/studio')
        self.assertEqual(response.status_code,200)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
        self.assertEqual(response.headers['x-robots-tag'],'noindex, nofollow')
        self.assertEqual(self.client.get('/api/studio/interface.js').status_code,200)
        bare=create_application(self.store,self.settings,verified_client_address=lambda _:'192.0.2.1')
        self.assertEqual(TestClient(bare).get('/studio').status_code,503)

    def test_private_configuration_requires_explicit_protected_keys(self):
        import json
        values=dict(SARSA_GOOGLE_CLIENT_ID=CLIENT,SARSA_GOOGLE_CLIENT_SECRET='synthetic-secret',
                    SARSA_PUBLIC_ORIGIN=ORIGIN,SARSA_GOOGLE_TOKEN_KEYS=json.dumps([Fernet.generate_key().decode()]),
                    SARSA_STUDIO_SIGNING_KEY=Fernet.generate_key().decode())
        services=StudioServices.from_environment(values)
        self.assertEqual(services.google.settings.client_id,CLIENT)
        for changed in ({'SARSA_STUDIO_SIGNING_KEY':'short'}, {'SARSA_GOOGLE_TOKEN_KEYS':'[]'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                StudioServices.from_environment(dict(values,**changed))


if __name__=='__main__':
    unittest.main()
