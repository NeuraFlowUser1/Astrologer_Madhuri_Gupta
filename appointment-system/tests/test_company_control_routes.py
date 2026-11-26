"""Company sign-in, credential, page, asset and business-settings routes, with a scripted database (no SQL)."""
import hashlib
import hmac
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.company_auth import COOKIE, password_hash
from appointment_system.company_control import router, PRIVATE_HEADERS
from appointment_system.configuration import origin
from appointment_system.service_control import ControlError
from .fixtures import business

SECRET = 'Synthetic company password'
NEW_SECRET = 'Another synthetic password'


class CompanyControlRoutes(TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(digest=lambda purpose, value:
            hmac.new(b'C' * 32, (purpose + ':' + value).encode(), hashlib.sha256).hexdigest())
        self.calls = []
        self.accept = True
        self.wait = False
        self.database = SimpleNamespace(call=self.call, status=lambda token: {'progress': 'effective'})
        self.token = 'x' * 43
        self.csrf = self.settings.digest('csrf', self.token)
        self.headers = {'origin': origin(), 'x-company-csrf': self.csrf}
        self.address = lambda request: '192.0.2.10'
        self.client = self.make_client()
        self.addCleanup(self.client.close)

    def call(self, statement, args=()):
        self.calls.append((statement, args))
        if 'company_session_touch' in statement:
            return True
        if 'company_login_begin' in statement or 'company_credential_begin' in statement:
            if self.wait:
                return {'code': 'please_wait'}
            return {'attempt_id': str(uuid4()), 'credential_revision': '1', 'password_hash': password_hash(SECRET)}
        if 'company_login_finish' in statement or 'company_credential_finish' in statement:
            return self.accept
        if 'company_business_settings' in statement:
            return {'revision': '1', 'settings': business()}
        if 'company_save_business_settings' in statement:
            return {'saved': True, 'revision': '2'}
        return {'saved': True}

    def make_client(self):
        app = FastAPI()
        app.include_router(router(self.settings, database=self.database, address=lambda request: self.address(request)))
        @app.exception_handler(ControlError)
        async def control_error(request, error):
            return JSONResponse({'code': error.code}, error.status)
        client = TestClient(app, base_url=origin())
        client.cookies.set(COOKIE, self.token)
        return client

    def risk(self):
        statement, args = next(item for item in reversed(self.calls) if 'begin' in item[0])
        return args[1] if 'company_login_begin' in statement else args[2]

    def test_sign_in_issues_a_strict_host_cookie_and_hashes_the_network_source(self):
        response = self.client.post('/api/company/sign-in/start', json={'username': 'synthetic.owner', 'password': SECRET},
                                    headers={'origin': origin()})
        self.assertEqual((response.status_code, response.json()), (200, {'signed_in': True}))
        cookie = response.headers['set-cookie']
        for part in ('HttpOnly', 'Secure', 'SameSite=strict', 'Path=/', 'Max-Age=28800'):
            self.assertIn(part.lower(), cookie.lower())
        self.assertEqual(response.headers['cache-control'], PRIVATE_HEADERS['Cache-Control'])
        self.assertEqual(self.risk(), self.settings.digest('login-risk', '192.0.2.10'))
        # IPv6 sources are grouped by /64, mapped IPv4 is unwrapped, and anything unreadable is one shared source.
        for address, expected in (('2001:db8::1', '2001:db8::/64'), ('::ffff:192.0.2.7', '192.0.2.7'),
                                  ('not an address', 'unverified-shared-source'), (None, 'unverified-shared-source')):
            with self.subTest(address=address):
                self.address = lambda request, address=address: address
                self.client.post('/api/company/login', json={'username': 'synthetic.owner', 'password': SECRET},
                                 headers={'origin': origin()})
                self.assertEqual(self.risk(), self.settings.digest('login-risk', expected))

    def test_sign_in_refusals_keep_their_status_and_never_set_a_cookie(self):
        body = {'username': 'synthetic.owner', 'password': SECRET}
        self.accept = False
        response = self.client.post('/api/company/sign-in/start', json=body, headers={'origin': origin()})
        self.assertEqual((response.status_code, response.json()['code']), (401, 'company_login_failed'))
        self.assertNotIn('set-cookie', response.headers)
        self.wait = True
        self.assertEqual(self.client.post('/api/company/sign-in/start', json=body, headers={'origin': origin()}).status_code, 429)
        for headers in ({'origin': 'https://other.example.test'}, {'origin': origin(), 'content-encoding': 'gzip'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post('/api/company/sign-in/start', json=body, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/company/sign-in/start', content='x', headers={'origin': origin(),
                         'content-type': 'text/plain'}).status_code, 422)

    def test_reauthentication_and_password_change_need_the_page_token_and_rotate_the_session(self):
        for path, body, expected in (('/api/company/reauthenticate', {'password': SECRET}, {'confirmed': True}),
                                     ('/api/company/password', {'password': SECRET, 'new_password': NEW_SECRET}, {'changed': True})):
            with self.subTest(path=path):
                response = self.client.post(path, json=body, headers=self.headers)
                self.assertEqual((response.status_code, response.json()), (200, expected))
                self.assertIn(COOKIE, response.headers['set-cookie'])
                self.assertNotIn(self.token, response.headers['set-cookie'])
                statement, args = next(item for item in reversed(self.calls) if 'company_credential_finish' in item[0])
                self.assertEqual(args[5], 'password' if 'new_password' in body else 'reauthenticate')
                self.assertEqual(args[6] is not None, 'new_password' in body)
                # Keep using the original synthetic session for the refusals below.
                self.client.cookies.clear(); self.client.cookies.set(COOKIE, self.token)
                self.assertEqual(self.client.post(path, json=body, headers=self.headers | {'x-company-csrf': 'a' * 64}).status_code, 403)
                self.assertEqual(self.client.post(path, json=body, headers=self.headers | {'x-company-csrf': 'short'}).status_code, 403)
                self.accept = False
                self.assertEqual(self.client.post(path, json=body, headers=self.headers).status_code, 401)
                self.accept = True; self.wait = True
                self.assertEqual(self.client.post(path, json=body, headers=self.headers).status_code, 429)
                self.wait = False

    def test_page_and_assets_are_private_and_only_named_files_are_served(self):
        page = self.client.get('/company/booking-control')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('CALENDAR_RESOURCE_BUTTONS', page.text); self.assertNotIn('CLIENT_NAME', page.text)
        self.assertIn("default-src 'none'", page.headers['content-security-policy'])
        for name, kind in (('control.js', 'text/javascript'), ('control.css', 'text/css'), ('command-journal.js', 'text/javascript')):
            with self.subTest(name=name):
                response = self.client.get('/api/company/assets/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers['content-type'].startswith(kind))
                self.assertEqual(response.headers['cache-control'], PRIVATE_HEADERS['Cache-Control'])
        journal = self.client.get('/api/company/assets/command-journal.js').text
        self.assertNotIn('/*COMPANY_BROWSER_CONFIGURATION*/null', journal)
        self.assertIn('891d05ec-8ab2-4a87-b537-1c30f2b694b6', journal)
        for name in ('control.html', '..%2Fcompany_control.py', 'other.js'):
            self.assertEqual(self.client.get('/api/company/assets/' + name).status_code, 404)

    def test_business_settings_read_and_save_bind_the_exact_operation_and_parsed_document(self):
        response = self.client.get('/api/company/settings')
        self.assertEqual((response.status_code, response.json()['revision']), (200, '1'))
        operation = str(uuid4())
        saved = self.client.post('/api/company/settings', json={'operation_id': operation, 'revision': '1',
                                 'settings': business(), 'reason': ' Reviewed business setting '}, headers=self.headers)
        self.assertEqual((saved.status_code, saved.json()), (200, {'saved': True, 'revision': '2'}))
        statement, args = self.calls[-1]
        self.assertIn('company_save_business_settings', statement)
        self.assertEqual((str(args[2]), args[3], args[5]), (operation, 1, 'Reviewed business setting'))
        self.assertEqual(args[4].obj['timezone'], 'Asia/Kolkata')
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/company/settings').status_code, 401)
