"""A saved Google consent finish rings the worker; a refused one leaves it asleep."""
import hashlib
import hmac
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.company_auth import COOKIE
from appointment_system.configuration import origin
from appointment_system.resource_consent import router
from appointment_system.service_control import ControlError
from appointment_system.studio import SESSION_COOKIE


class ResourceConsentFinish(TestCase):
    def setUp(self):
        self.token = 'x' * 43
        self.settings = SimpleNamespace(digest=lambda purpose, value:
            hmac.new(b'C' * 32, (purpose + ':' + value).encode(), hashlib.sha256).hexdigest())
        self.studio = SimpleNamespace(resources=object(), digest=lambda purpose, value: purpose + ':' + str(value))
        self.company = Mock(spec=['call']); self.company.call.side_effect = self.company_call
        self.staff = Mock(spec=['_call']); self.staff._call.return_value = {'installed': True}
        self.wake = Mock(spec=['publish']); self.wake.publish.return_value = True
        self.headers = {'origin': origin(), 'x-company-csrf': self.settings.digest('csrf', self.token)}

    def company_call(self, statement, args=()):
        return True if 'company_session_touch' in statement else {'installed': True}

    def client(self, wake):
        app = FastAPI()
        app.include_router(router(self.studio, self.settings, self.company, self.staff, None, wake=wake))
        @app.exception_handler(ControlError)
        async def control_error(request, error):
            return JSONResponse({'code': error.code}, error.status)
        client = TestClient(app, base_url=origin())
        client.cookies.set(COOKIE, self.token); client.cookies.set(SESSION_COOKIE, 'staff-session')
        self.addCleanup(client.close)
        return client

    def test_successful_finish_rings_once_for_company_and_staff_without_changing_the_reply(self):
        client = self.client(self.wake)
        for path, store in (('/api/company/resources/finish', self.company.call), ('/api/studio/resources/finish', self.staff._call)):
            for ring in (Mock(return_value=True), Mock(return_value=False), Mock(side_effect=RuntimeError('ring failed'))):
                with self.subTest(path=path, ring=ring):
                    self.wake.publish.reset_mock(); self.wake.publish.side_effect = ring
                    response = client.post(path, json={'attempt_id': str(uuid4())}, headers=self.headers)
                    self.assertEqual((response.status_code, response.json()), (200, {'installed': True}))
                    self.assertIn('no-store', response.headers['cache-control'])
                    self.wake.publish.assert_called_once_with()
                    self.assertIn('finish_resource_consent', store.call_args[0][0])
        response = self.client(None).post('/api/studio/resources/finish', json={'attempt_id': str(uuid4())}, headers=self.headers)
        self.assertEqual((response.status_code, response.json()), (200, {'installed': True}))

    def test_refused_or_invalid_finish_does_not_ring(self):
        client = self.client(self.wake)
        self.staff._call.side_effect = ControlError('google_consent_unavailable', 409)
        response = client.post('/api/studio/resources/finish', json={'attempt_id': str(uuid4())}, headers=self.headers)
        self.assertEqual((response.status_code, response.json()), (409, {'code': 'google_consent_unavailable'}))
        response = client.post('/api/studio/resources/finish', json={'attempt_id': '00000000-0000-0000-0000-000000000000'}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        response = client.post('/api/company/resources/finish', json={'attempt_id': str(uuid4())}, headers=self.headers | {'origin': 'https://foreign.example.test'})
        self.assertEqual(response.status_code, 403)
        self.wake.publish.assert_not_called()
