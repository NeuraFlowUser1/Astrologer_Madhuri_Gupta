"""Website handlers and cookies against real purpose SQL; transport is test-only."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.company_auth import COOKIE
from appointment_system.configuration import installation
from appointment_system.errors import Rejected
from appointment_system.keys import KeyRing
from appointment_system.secret_configuration import booking_settings
from appointment_system.service_control import ControlDatabase,ControlError
from .sql_store import IsolatedStore
from .test_application import environment,protection,Reader
from .test_sql_company import CompanyFixture
from tools.checks.sql_target import literal


class Bridge(ControlDatabase):
    def __init__(self,target):self.store=IsolatedStore(target,'abs_company')
    def call(self,statement,parameters=(),*,resource_authority=None):
        try:return self.store._call(statement,parameters,resource_authority=resource_authority)
        except AssertionError as error:
            # This bridge replaces Unix-socket transport and SQLSTATE decoding only.
            if 'company session rejected' in str(error):raise ControlError('company_session_required',401) from None
            if 'business settings changed' in str(error):raise ControlError('company_state_changed',409) from None
            raise


class CompanyHTTP(CompanyFixture):
    def setUp(self):
        super().setUp();self.db.scalar("SELECT appointment_system.provision_login('appointment_system_web','web');")
        facts=installation()
        ring=KeyRing.parse(protection('company-session',11),purpose='company-session',
             installation_id=facts['installation_id'],environment=facts['environment'])
        settings=SimpleNamespace(digest=lambda purpose,value:ring.digest(purpose,value.encode()),google_client_id='synthetic-client')
        self.app=create_application(IsolatedStore(self.db,'appointment_system_web'),booking_settings(environment()),
             company_store=IsolatedStore(self.db,'abs_company'),company_settings=settings,company_database=Bridge(self.db),
             projection_reader=Reader(True),verified_client_address=lambda request:'127.0.0.1')
        self.client=TestClient(self.app,base_url=installation()['origin'])
        self.headers={'Origin':installation()['origin']}
        self.secret='Synthetic company password for tests'
        self.login()

    def login(self,password=None):
        response=self.client.post('/api/company/login',json={'username':'company.owner','password':password or self.secret},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(password or self.secret,response.text)
        status=self.client.get('/api/company/control/status');self.assertEqual(status.status_code,200,status.text)
        self.headers['X-Company-CSRF']=status.json()['csrf_token'];return response

    def test_login_is_private_and_cookie_has_host_only_strict_browser_protection(self):
        response=self.login();cookie=response.headers['set-cookie']
        self.assertIn(COOKIE+'=',cookie);self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=strict',cookie);self.assertNotIn('Domain=',cookie)
        self.assertIn('no-store',response.headers['cache-control'].split(', '))
        anonymous=TestClient(self.app,base_url=installation()['origin'])
        self.assertEqual(anonymous.get('/api/company/settings').status_code,401)

    def test_company_command_script_is_scoped_without_disclosing_credentials(self):
        page=self.client.get('/company/booking-control')
        self.assertLess(page.text.index('/api/company/assets/command-journal.js'),page.text.index('/api/company/assets/control.js'))
        result=self.client.get('/api/company/assets/command-journal.js')
        self.assertEqual(result.status_code,200)
        self.assertIn(installation()['installation_id'],result.text)
        self.assertNotIn('/*COMPANY_BROWSER_CONFIGURATION*/null',result.text)
        self.assertNotIn(self.secret,result.text)
        self.assertIn('no-store',result.headers['cache-control'])

    def test_private_business_change_checks_origin_csrf_and_revision_before_any_write(self):
        current=self.client.get('/api/company/settings').json();spec=deepcopy(current['settings']);spec['notice_minutes']=45
        body={'operation_id':str(uuid4()),'revision':current['revision'],'settings':spec,'reason':'Synthetic HTTP settings change'}
        for headers in ({'Origin':'https://foreign.example'},self.headers|{'X-Company-CSRF':'wrong'}):
            self.assertEqual(self.client.post('/api/company/settings',json=body,headers=headers).status_code,403)
        self.assertEqual(self.client.get('/api/company/settings').json()['revision'],current['revision'])
        first=self.client.post('/api/company/settings',json=body,headers=self.headers)
        self.assertEqual(first.status_code,200,first.text);self.assertTrue(first.json()['saved'])
        self.assertEqual(self.client.post('/api/company/settings',json=body,headers=self.headers).json(),first.json())
        body['operation_id']=str(uuid4())
        self.assertEqual(self.client.post('/api/company/settings',json=body,headers=self.headers).status_code,409)

    def test_password_confirmation_rotates_cookie_and_rejects_the_previous_cookie(self):
        previous=self.client.cookies.get(COOKIE)
        wrong=self.client.post('/api/company/reauthenticate',json={'password':'Wrong synthetic company password'},headers=self.headers)
        self.assertEqual(wrong.status_code,401)
        response=self.client.post('/api/company/reauthenticate',json={'password':self.secret},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);self.assertNotEqual(self.client.cookies.get(COOKIE),previous)
        self.assertEqual(self.client.get('/api/company/settings',headers={'Cookie':COOKIE+'='+previous}).status_code,401)
        self.assertEqual(self.client.get('/api/company/settings').status_code,200)

    def test_password_change_revokes_old_sessions_and_new_password_can_sign_in(self):
        previous=self.client.cookies.get(COOKIE);replacement='Replacement synthetic company password'
        before=int(self.db.scalar("SELECT count(*) FROM appointment_system.company_security_events WHERE purpose='password' AND success;"))
        response=self.client.post('/api/company/password',json={'password':self.secret,'new_password':replacement},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/company/settings',headers={'Cookie':COOKIE+'='+previous}).status_code,401)
        refused=self.client.post('/api/company/login',json={'username':'company.owner','password':self.secret},headers=self.headers)
        self.assertEqual(refused.status_code,401)
        self.login(replacement)
        self.assertEqual(int(self.db.scalar("SELECT count(*) FROM appointment_system.company_security_events WHERE purpose='password' AND success;")),before+1)

    def test_support_time_resolution_works_without_google_and_requires_company_csrf(self):
        path='/api/company/support/time-context'
        self.assertEqual(self.client.post(path,json={},headers={'Origin':installation()['origin']}).status_code,403)
        reply=self.client.post(path,json={},headers=self.headers)
        self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(reply.json()['timezone'],'Asia/Kolkata')
        value={'local':'2026-11-03T16:00','timezone':'Asia/Kolkata'}
        resolved=self.client.post('/api/company/support/resolve-time',json=value,headers=self.headers)
        self.assertEqual(resolved.status_code,200,resolved.text)
        self.assertEqual(resolved.json()['instant'],'2026-11-03T10:30:00+00:00')
        changed=self.client.post('/api/company/support/resolve-time',json=value|{'timezone':'UTC'},headers=self.headers)
        self.assertEqual(changed.status_code,409);self.assertEqual(changed.json()['code'],'timezone_changed')
        self.assertEqual(self.client.get('/api/company/staff-actions.js').status_code,200)
        self.client.cookies.clear();self.assertEqual(self.client.post(path,json={},headers=self.headers).status_code,401)
