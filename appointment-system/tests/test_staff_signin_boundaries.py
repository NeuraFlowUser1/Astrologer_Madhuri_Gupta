"""Staff HTTP failures use real cookies/ciphers and a synthetic signed Google reply.

The storage port is deliberately controlled here. Native one-use transaction
behavior is covered separately by test_sql_staff_enquiries.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from appointment_system.connection import StorageUnavailable
from appointment_system.google_oauth import GrantCipher, OAuthSettings
from appointment_system.secret_configuration import booking_settings
from appointment_system.studio import StudioServices, SESSION_COOKIE
from .test_application import PublicStore, Reader, environment
from .test_keys import ring
from . import test_google_oauth as google_fixture


class StaffSigninBoundaries(TestCase):
    @classmethod
    def setUpClass(cls):
        google_fixture.GoogleOAuthTests.setUpClass()

    def setUp(self):
        self.google = google_fixture.GoogleOAuthTests()
        self.google.setUp()
        self.google.settings = OAuthSettings(google_fixture.CLIENT, 'synthetic-secret', installation()['origin'])
        self.google.claims['sub'] = '123456789'
        self.services = StudioServices(self.google.provider(),
            GrantCipher(google_fixture.CLIENT, ring(purpose='google-grant')), ring(purpose='staff-session'))
        self.store = Mock(spec_set=['require_booking_admission', 'start_google_attempt',
            'consume_google_attempt', 'finish_google_signin', 'studio_session', 'studio_logout', '_call'])
        self.store.start_google_attempt.return_value = True
        self.store.finish_google_signin.return_value = True
        self.store.studio_session.return_value = {'role': 'client'}
        self.reader = Reader(True)
        self.app = create_application(PublicStore(), booking_settings(environment()),
            verified_client_address=lambda request: '127.0.0.1', projection_reader=self.reader,
            staff_store=self.store, studio_services=self.services)
        self.client = TestClient(self.app, base_url=installation()['origin'])
        self.addCleanup(self.client.close)
        self.headers = {'Origin': installation()['origin']}

    def start(self, portal='booking'):
        route = 'studio' if portal == 'booking' else 'enquiry-studio'
        response = self.client.post('/api/' + route + '/sign-in/start', json={'role': 'client'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        args = self.store.start_google_attempt.call_args.args
        self.store.consume_google_attempt.return_value = {'role': 'client', 'portal': portal,
            'encrypted_attempt': args[4]}
        query = parse_qs(urlsplit(response.json()['authorization_url']).query)
        self.google.claims['nonce'] = query['nonce'][0]
        return query['state'][0]

    def callback(self, params):
        return self.client.get('/api/studio/sign-in/callback', params=params, follow_redirects=False)

    def test_unknown_start_commit_never_releases_authorization_url_or_cookie(self):
        for result in (False, None, 1):
            self.store.start_google_attempt.return_value = result
            response = self.client.post('/api/studio/sign-in/start', json={'role': 'client'}, headers=self.headers)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('authorization_url', response.text)
            self.assertNotIn('set-cookie', response.headers)
        self.assertEqual(self.google.calls, [])

    def test_ambiguous_callback_is_rejected_before_consuming_attempt_or_contacting_google(self):
        state = self.start()
        for params in ([('state', state), ('state', state), ('code', 'synthetic')],
                       [('state', state), ('code', 'one'), ('code', 'two')],
                       {'state': state, 'code': 'synthetic', 'error': 'access_denied'},
                       {'state': state, 'code': 'x' * 8192}):
            response = self.callback(params)
            self.assertEqual(response.headers['location'], '/studio?connection=failed')
        self.store.consume_google_attempt.assert_not_called()
        self.assertEqual(self.google.calls, [])

    def test_cancelled_missing_and_unknown_attempts_never_create_a_session(self):
        for params in ({'error': 'access_denied'}, {}):
            state = self.start('enquiry')
            response = self.callback({'state': state} | params)
            self.assertEqual(response.headers['location'], '/enquiries-studio?connection=failed')
            self.assertNotIn(SESSION_COOKIE + '=', response.headers.get('set-cookie', ''))
        state = self.start()
        self.store.consume_google_attempt.return_value = None
        self.assertEqual(self.callback({'state': state, 'code': 'synthetic'}).headers['location'], '/studio?connection=failed')
        self.store.finish_google_signin.assert_not_called()
        self.assertEqual(self.google.calls, [])

    def test_uncertain_final_commit_requests_status_check_without_issuing_a_session(self):
        for result in (False, None, StorageUnavailable('synthetic lost commit response')):
            state = self.start('enquiry')
            self.store.finish_google_signin.reset_mock(side_effect=True)
            if isinstance(result, Exception):
                self.store.finish_google_signin.side_effect = result
            else:
                self.store.finish_google_signin.return_value = result
            response = self.callback({'state': state, 'code': 'synthetic-code'})
            expected = 'check' if isinstance(result, Exception) else 'failed'
            self.assertEqual(response.headers['location'], '/enquiries-studio?connection=' + expected)
            self.assertNotIn(SESSION_COOKIE + '=', response.headers.get('set-cookie', ''))
            self.store.finish_google_signin.assert_called_once()
        self.store.consume_google_attempt.side_effect = StorageUnavailable('synthetic read unavailable')
        state = self.start()
        self.assertEqual(self.callback({'state': state, 'code': 'synthetic'}).headers['location'], '/studio?connection=check')

    def test_staff_status_never_accepts_agency_or_missing_identity_as_client(self):
        self.client.cookies.set(SESSION_COOKIE, self.services.issue('session'))
        for saved in (None, {'role': 'agency'}, {'role': 'unknown'}):
            self.store.studio_session.return_value = saved
            self.assertEqual(self.client.get('/api/studio/status').status_code, 401)
        self.store.require_booking_admission.assert_not_called()
        self.store.studio_session.return_value = {'role': 'client'}
        response = self.client.get('/api/studio/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['resources'], [])
        self.assertFalse(response.json()['authorization_saved'])
        self.assertIsNone(response.json()['workbook_url'])
        self.store._call.assert_not_called()

    def test_connected_status_uses_exact_resource_and_workbook_failure_is_not_success(self):
        services = StudioServices(self.services.google, self.services.cipher, self.services.signing_key, SimpleNamespace())
        app = create_application(PublicStore(), booking_settings(environment()),
            verified_client_address=lambda request: '127.0.0.1', projection_reader=self.reader,
            staff_store=self.store, studio_services=services)
        with TestClient(app, base_url=installation()['origin']) as client:
            client.cookies.set(SESSION_COOKIE, services.issue('session'))
            self.store._call.return_value = [{'resource': 'agency_sheet', 'connected': True, 'spreadsheet_id': 'foreign-sheet'}]
            response = client.get('/api/studio/status')
            self.assertFalse(response.json()['authorization_saved'])
            self.assertIsNone(response.json()['workbook_url'])
            self.store._call.return_value += [{'resource': 'client_sheet', 'connected': True,
                'reconnect_required': False, 'spreadsheet_id': 'synthetic-client-sheet'}]
            response = client.get('/api/studio/status')
            self.assertEqual(response.json()['workbook_url'], 'https://docs.google.com/spreadsheets/d/synthetic-client-sheet')
            from appointment_system.google_workspace import WorkspaceFailure
            with patch('appointment_system.studio.prepare_owner_workbook', side_effect=WorkspaceFailure('google_workbook_save_uncertain')):
                response = client.post('/api/studio/workbook/prepare', json={}, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['code'], 'workbook_not_ready')
            self.assertNotIn('workbook_url', response.json())

    def test_off_hides_booking_logout_but_enquiry_logout_still_revokes_the_same_session(self):
        token = self.services.issue('session')
        self.client.cookies.set(SESSION_COOKIE, token)
        self.reader.enabled = False
        response = self.client.post('/api/studio/logout', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.store.studio_logout.assert_not_called()
        response = self.client.post('/api/enquiry-studio/logout', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.store.studio_logout.assert_called_once_with(self.services.digest('session', token),
            google_fixture.CLIENT, installation()['origin'])
        self.store.require_booking_admission.assert_not_called()
        self.assertIn('Max-Age=0', response.headers['set-cookie'])
