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

    def make_client(self, configured=True, publish=True, worker=True, wake=None):
        app = FastAPI()
        app.include_router(router(self.settings if configured else None,
            database=self.database if configured else None, publisher=self.publisher if publish else None,
            worker_key=self.worker if worker else None, wake=wake))
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

    def test_every_accepted_switch_change_rings_the_worker_even_when_already_effective(self):
        wake = Mock(spec=['publish']); wake.publish.return_value = True
        with self.make_client(wake=wake) as client:
            result = client.post('/api/company/control/change', json=self.command(), headers=self.headers)
            self.assertEqual((result.status_code, result.json()), (200, self.published))
            wake.publish.assert_called_once_with()
            for outcome, ring in (('declined', Mock(return_value=False)), ('raised', Mock(side_effect=RuntimeError('ring failed')))):
                with self.subTest(ring=outcome):
                    self.published = {'progress': 'applying'}; wake.publish.reset_mock(); wake.publish.side_effect = ring
                    result = client.post('/api/company/control/change', json=self.command(), headers=self.headers)
                    self.assertEqual((result.status_code, result.json()), (202, {'progress': 'applying'}))
                    wake.publish.assert_called_once_with()
        with self.make_client(publish=False, wake=wake) as client:
            wake.publish.reset_mock(); wake.publish.side_effect = None
            result = client.post('/api/company/control/change', json=self.command(), headers=self.headers)
            self.assertEqual((result.status_code, result.json()), (202, {'progress': 'applying'}))
            wake.publish.assert_called_once_with()
        self.database.command.side_effect = ControlError('company_request_rejected', 403); wake.publish.reset_mock()
        with self.make_client(wake=wake) as client:
            self.assertEqual(client.post('/api/company/control/change', json=self.command(), headers=self.headers).status_code, 403)
        wake.publish.assert_not_called()

    def test_status_rings_on_every_read_and_republishes_only_a_change_still_on_its_way(self):
        wake = Mock(spec=['publish']); wake.publish.return_value = True
        with self.make_client(wake=wake) as client:
            for progress in ('initializing', 'accepted', 'publishing', 'published', 'effective', 'superseded', 'needs_review'):
                with self.subTest(progress=progress):
                    wake.publish.reset_mock(); self.publisher.reset_mock(); self.database.status.reset_mock()
                    reads = [{'progress': progress, 'enabled': True}, {'progress': 'effective', 'enabled': True}]
                    self.database.status.side_effect = lambda token, reads=reads: dict(reads.pop(0))
                    result = client.get('/api/company/control/status')
                    self.assertEqual(result.status_code, 200)
                    wake.publish.assert_called_once_with()
                    pending = progress in ('accepted', 'publishing', 'published')
                    self.assertEqual(self.publisher.call_count, 1 if pending else 0)
                    self.assertEqual(self.database.status.call_count, 2 if pending else 1)
                    # The page sees the state after the republication.
                    self.assertEqual(result.json()['progress'], 'effective' if pending else progress)
                    self.assertEqual(result.json()['csrf_token'], self.headers['x-company-csrf'])
        self.database.status.side_effect = None
        with self.make_client(publish=False, wake=wake) as client:
            self.database.status.return_value = {'progress': 'accepted'}
            self.assertEqual(client.get('/api/company/control/status').json()['progress'], 'accepted')

    def test_status_keeps_its_answer_when_publication_and_ring_both_fail_and_a_later_read_publishes(self):
        from appointment_system.request_budget import BudgetExpired
        wake = Mock(spec=['publish'])
        for failure in (ControlError('publication_unconfirmed'), BudgetExpired()):
            with self.subTest(failure=type(failure).__name__), self.make_client(wake=wake) as client:
                self.publisher.reset_mock(); self.publisher.side_effect = failure
                wake.publish.side_effect = RuntimeError('ring failed')
                self.database.status.side_effect = None; self.database.status.return_value = {'progress': 'accepted', 'enabled': True}
                result = client.get('/api/company/control/status')
                self.assertEqual((result.status_code, result.json()['progress']), (200, 'accepted'))
                # The worker comes back: the next read publishes and the page sees the change take effect.
                self.publisher.assert_called_once_with()
                self.publisher.reset_mock(); self.publisher.side_effect = None; wake.publish.side_effect = None
                reads = [{'progress': 'accepted'}, {'progress': 'effective'}]
                self.database.status.side_effect = lambda token: dict(reads.pop(0))
                self.assertEqual(client.get('/api/company/control/status').json()['progress'], 'effective')
                self.publisher.assert_called_once_with()
        # A re-read that fails after a publication keeps the first answer rather than failing the page.
        with self.make_client(wake=wake) as client:
            reads = iter([{'progress': 'published'}])
            def status(token):
                try: return dict(next(reads))
                except StopIteration: raise ControlError('company_tools_unavailable') from None
            self.database.status.side_effect = status
            self.assertEqual(client.get('/api/company/control/status').json()['progress'], 'published')
        self.database.status.side_effect = None

    def test_automatic_rechecks_ring_only_when_the_change_has_just_taken_effect_and_never_without_a_session(self):
        wake = Mock(spec=['publish']); wake.publish.return_value = True
        automatic = {'x-company-recheck': '1'}
        with self.make_client(wake=wake) as client:
            for reads, rings in (([{'progress': 'effective'}], 0), ([{'progress': 'published'}, {'progress': 'published'}], 0),
                                 ([{'progress': 'accepted'}, {'progress': 'effective'}], 1), ([{'progress': 'initializing'}], 0)):
                with self.subTest(reads=reads):
                    wake.publish.reset_mock(); pending = list(reads)
                    self.database.status.side_effect = lambda token: dict(pending.pop(0))
                    self.assertEqual(client.get('/api/company/control/status', headers=automatic).status_code, 200)
                    self.assertEqual(wake.publish.call_count, rings)
            # An unconfirmed or failed republication skips the ring: the same worker would not answer it either.
            self.database.status.side_effect = None; self.database.status.return_value = {'progress': 'accepted'}
            for outcome in ({'processed': 1, 'retry': True}, ControlError('company_tools_unavailable')):
                wake.publish.reset_mock()
                if isinstance(outcome, dict): self.publisher.return_value = outcome
                else: self.publisher.side_effect = outcome
                self.assertEqual(client.get('/api/company/control/status').json()['progress'], 'accepted')
                wake.publish.assert_not_called()
            self.publisher.side_effect = None; self.publisher.return_value = {'processed': 1, 'retry': False}
            wake.publish.reset_mock(); client.get('/api/company/control/status'); wake.publish.assert_called_once_with()
            self.publisher.return_value = {'published': True}
            # Without a valid session nothing is published and nothing rings.
            self.publisher.reset_mock(); wake.publish.reset_mock(); client.cookies.clear()
            self.assertEqual(client.get('/api/company/control/status').status_code, 401)
            client.cookies.set(COOKIE, 'short')
            self.assertEqual(client.get('/api/company/control/status').status_code, 401)
            self.publisher.assert_not_called(); wake.publish.assert_not_called()
        self.database.status.side_effect = None

    def test_the_real_publisher_reports_an_unanswered_worker_as_a_retry_and_the_status_read_skips_the_ring(self):
        from unittest.mock import AsyncMock, patch
        from appointment_system.control_publication import Publisher, PublicationSettings
        from appointment_system.configuration import worker_origin
        database = Mock(spec_set=['claim_publication', 'claim_probe', 'record_probe', 'probe_retry'])
        database.claim_publication.return_value = None
        database.claim_probe.return_value = {'operation_id': 'synthetic-operation'}
        reader = Mock(spec_set=['attestation'])
        reader.attestation = AsyncMock(side_effect=ControlError('projection_unavailable'))
        real = Publisher(database, PublicationSettings(b'P' * 32, b'R' * 32, worker_origin()))
        wake = Mock(spec=['publish']); wake.publish.return_value = True
        self.database.status.return_value = {'progress': 'published'}
        app = FastAPI()
        app.include_router(router(self.settings, database=self.database, publisher=real, worker_key=self.worker, wake=wake))
        with patch('appointment_system.control_publication.ProjectionReader', return_value=reader), \
             TestClient(app, base_url=origin()) as client:
            client.cookies.set(COOKIE, self.token)
            self.assertEqual(client.get('/api/company/control/status').json()['progress'], 'published')
        database.probe_retry.assert_called_once_with({'operation_id': 'synthetic-operation'}, 'projection_unavailable')
        wake.publish.assert_not_called()

    def test_a_spent_request_budget_during_a_switch_change_tries_the_ring_and_answers_as_before(self):
        from appointment_system.request_budget import BudgetExpired
        wake = Mock(spec=['publish']); wake.publish.return_value = True
        app = FastAPI()
        app.include_router(router(self.settings, database=self.database, publisher=self.publisher, worker_key=self.worker, wake=wake))
        @app.exception_handler(BudgetExpired)
        async def spent(request, error):
            return JSONResponse({'code': 'request_pending'}, 503)
        with TestClient(app, base_url=origin()) as client:
            client.cookies.set(COOKIE, self.token)
            self.publisher.side_effect = BudgetExpired()
            result = client.post('/api/company/control/change', json=self.command(), headers=self.headers)
            self.assertEqual((result.status_code, result.json()), (503, {'code': 'request_pending'}))
            wake.publish.assert_called_once_with()
            self.publisher.side_effect = None; wake.publish.reset_mock()
            original = self.database.call.side_effect
            def call(statement, args=()):
                if 'control_command_result' in statement: raise BudgetExpired()
                return original(statement, args)
            self.database.call.side_effect = call
            result = client.post('/api/company/control/change', json=self.command(), headers=self.headers)
            self.assertEqual(result.status_code, 503); wake.publish.assert_called_once_with()
            self.database.call.side_effect = original

    def test_records_recheck_rings_after_saving_and_a_failed_ring_changes_nothing(self):
        review = dict(operation_id=str(uuid4()), record_id=str(uuid4()), role='agency', record_kind='enquiry',
                      sequence='3', reason='Reviewed record conflict')
        for ring in (Mock(return_value=True), Mock(return_value=False), Mock(side_effect=RuntimeError('ring failed'))):
            wake = Mock(spec=['publish']); wake.publish.side_effect = ring
            with self.make_client(wake=wake) as client:
                response = client.post('/api/company/records/recheck', json=review, headers=self.headers)
                self.assertEqual((response.status_code, response.json()), (200, {'saved': True}))
                wake.publish.assert_called_once_with()
        wake = Mock(spec=['publish'])
        with self.make_client(wake=wake) as client:
            self.assertEqual(client.post('/api/company/records/recheck', json=review | {'sequence': '9223372036854775807'},
                                         headers=self.headers).status_code, 422)
        wake.publish.assert_not_called()

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
