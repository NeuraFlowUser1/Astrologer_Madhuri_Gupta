"""Company control replies distinguish saved intent from effective publication."""
import hashlib
import hmac
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.company_control import router
from appointment_system.company_auth import COOKIE
from appointment_system.configuration import origin
from appointment_system.service_control import ControlError
from .fixtures import business


class CompanyControlBoundaries(TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(digest=lambda purpose, value:
            hmac.new(b'C' * 32, (purpose + ':' + value).encode(), hashlib.sha256).hexdigest())
        self.database = Mock(spec=['call', 'status', 'command', 'incidents'])
        self.database.call.side_effect = self.call
        self.database.status.return_value = {'enabled': False}
        self.database.command.return_value = {'progress': 'applying'}
        self.database.incidents.return_value = {'items': []}
        self.saved_calls = []
        self.published = {'progress': 'effective', 'enabled': False}
        self.publisher = Mock(return_value={'published': True})
        self.worker = Mock(spec=['accepts']); self.worker.accepts.return_value = True
        self.token = 'x' * 43
        self.headers = {'origin': origin(), 'x-company-csrf': self.settings.digest('csrf', self.token)}
        self.client = self.make_client()
        self.addCleanup(self.client.close)

    def call(self, statement, args=()):
        self.saved_calls.append((statement, args))
        if 'company_session_touch' in statement:
            return True
        if 'control_command_result' in statement:
            return self.published
        return {'saved': True}

    def make_client(self, configured=True, publish=True, worker=True):
        app = FastAPI()
        app.include_router(router(self.settings if configured else None,
            database=self.database if configured else None, publisher=self.publisher if publish else None,
            worker_key=self.worker if worker else None))
        @app.exception_handler(ControlError)
        async def control_error(request, error):
            return JSONResponse({'code': error.code}, error.status)
        client = TestClient(app, base_url=origin())
        client.cookies.set(COOKIE, self.token)
        return client

    def command(self):
        return dict(operation_id=str(uuid4()), generation=str(uuid4()), revision='1', enabled=False, reason='Reviewed service pause')

    def test_mode_change_reports_effective_only_from_saved_publication_result(self):
        command = self.command()
        result = self.client.post('/api/company/control/change', json=command, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), self.published)
        self.database.command.assert_called_once()
        self.publisher.assert_called_once_with()
        self.assertIn('control_command_result', self.saved_calls[-1][0])
        self.published = {'progress': 'applying'}
        self.publisher.side_effect = ControlError('publication_configuration')
        result = self.client.post('/api/company/control/change', json=command, headers=self.headers)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.json(), {'progress': 'applying'})
        self.assertIn('no-store', result.headers['cache-control'])
        with self.make_client(publish=False) as client:
            result = client.post('/api/company/control/change', json=command, headers=self.headers)
            self.assertEqual(result.status_code, 202)

    def test_invalid_command_id_version_and_boolean_are_rejected_before_any_mode_write(self):
        for changed in ({'revision': '9223372036854775808'}, {'operation_id': '00000000-0000-0000-0000-000000000000'},
                        {'generation': '00000000-0000-0000-0000-000000000000'}, {'enabled': 1}):
            result = self.client.post('/api/company/control/change', json=self.command() | changed, headers=self.headers)
            self.assertEqual(result.status_code, 422)
        self.database.command.assert_not_called(); self.publisher.assert_not_called()

    def test_private_status_records_and_incidents_recheck_session_and_do_not_cache(self):
        for path in ('/api/company/control/status', '/api/company/records/status', '/api/company/operations/incidents'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(self.client.get('/api/company/control/status').json()['csrf_token'], self.headers['x-company-csrf'])
        self.assertGreaterEqual(sum('company_session_touch' in stmt for stmt, _ in self.saved_calls), 4)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/company/records/status').status_code, 401)
        with self.make_client(configured=False) as client:
            self.assertEqual(client.get('/api/company/control/status').status_code, 503)

    def test_settings_and_record_review_reject_invalid_revisions_and_bind_exact_operation(self):
        body = dict(operation_id=str(uuid4()), revision='1', settings=business(), reason='Reviewed business setting')
        for changed in ({'revision': '9223372036854775807'}, {'operation_id': '00000000-0000-0000-0000-000000000000'},
                        {'settings': {}}, {'settings': business() | {'unsupported': True}}):
            response = self.client.post('/api/company/settings', json=body | changed, headers=self.headers)
            self.assertEqual(response.status_code, 422)
        self.assertFalse(any('company_save_business_settings' in stmt for stmt, _ in self.saved_calls))
        review = dict(operation_id=str(uuid4()), record_id=str(uuid4()), role='client', record_kind='booking',
                      sequence='2', reason='Reviewed record conflict')
        response = self.client.post('/api/company/records/recheck', json=review, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        stmt, args = self.saved_calls[-1]
        self.assertIn('company_sheet_recheck', stmt)
        self.assertEqual(args[3:5], ('client', 'booking'))
        self.assertEqual(args[6:], (2, 'Reviewed record conflict'))
        for changed in ({'operation_id': '00000000-0000-0000-0000-000000000000'},
                        {'record_id': '00000000-0000-0000-0000-000000000000'}, {'sequence': '9223372036854775807'}):
            response = self.client.post('/api/company/records/recheck', json=review | changed, headers=self.headers)
            self.assertEqual(response.status_code, 422)

    def test_logout_ends_saved_session_and_clears_host_cookie(self):
        response = self.client.post('/api/company/logout', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'signed_out': True})
        self.assertIn('control_session_end', self.saved_calls[-1][0])
        self.assertEqual(self.saved_calls[-1][1], (self.settings.digest('session', self.token),))
        for fragment in ('Max-Age=0', 'HttpOnly', 'Secure', 'SameSite=strict'):
            self.assertIn(fragment, response.headers['set-cookie'])

    def test_internal_publication_requires_exact_worker_authority_and_complete_configuration(self):
        route = '/api/internal/service-control/publish'
        for value in (False, None, 1):
            self.worker.accepts.return_value = value
            self.assertEqual(self.client.post(route, json={}).status_code, 401)
        self.publisher.assert_not_called()
        self.worker.accepts.return_value = True
        with self.make_client(publish=False) as client:
            self.assertEqual(client.post(route, json={}).status_code, 503)
        with self.make_client(worker=False) as client:
            self.assertEqual(client.post(route, json={}).status_code, 401)
        response = self.client.post(route, json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['published'])
        self.publisher.assert_called_once()

    def test_unlisted_company_assets_are_not_arbitrary_file_reads(self):
        for name in ('unknown.js', 'company_auth.py', 'control.html'):
            self.assertEqual(self.client.get('/api/company/assets/' + name).status_code, 404)
