"""Real purpose SQL and real signed Google callback, synthetic transport only."""
import hashlib,time,json
from unittest.mock import patch
from types import SimpleNamespace
from uuid import UUID,uuid4
from urllib.parse import parse_qs,urlsplit
import httpx
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.company_auth import COOKIE
from appointment_system.configuration import installation
from appointment_system.google_oauth import GoogleOAuth,OAuthSettings,GrantCipher,RESOURCE_SCOPES,TOKEN,CERTS,USERINFO
from appointment_system.google_resources import Resources,ResourceCipher
from appointment_system.keys import KeyRing
from appointment_system.secret_configuration import booking_settings
from appointment_system.studio import StudioServices
from .test_sql_company import CompanyFixture
from .test_sql_company_http import Bridge
from .test_sql_booking import BookingFixture
from .sql_store import IsolatedStore
from .test_application import environment,protection,Reader
from .test_google_resources import spec,WEB
from . import test_google_oauth as signed_provider
from tools.checks.sql_target import literal

class ResourceHTTP(CompanyFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();signed_provider.GoogleOAuthTests.setUpClass()

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_resources,appointment_system.google_resource_grants CASCADE;')
        for role,purpose in [('appointment_system_web','web'),('abs_staff','staff')]:
            self.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')
        self.expected=None;self.calls=[];self.provider_error=False
        def provider(request):
            self.calls.append(request)
            if str(request.url)==CERTS:return httpx.Response(200,json={'synthetic':signed_provider.GoogleOAuthTests.cert})
            if str(request.url)==USERINFO:return httpx.Response(200,json={'sub':'123456789','email':'practice@example.test','email_verified':True})
            if str(request.url)==TOKEN:
                if self.provider_error:return httpx.Response(400,json={'error':'invalid_grant'})
                helper=signed_provider.GoogleOAuthTests();claims=dict(iss='https://accounts.google.com',aud=WEB,sub='123456789',
                    email='practice@example.test',email_verified=True,nonce=self.expected['nonce'][0],iat=int(time.time())-1,exp=int(time.time())+3600)
                return httpx.Response(200,json=dict(id_token=helper.signed(claims),access_token='synthetic-access',refresh_token='synthetic-refresh',
                    token_type='Bearer',expires_in=3600,scope=' '.join(sorted(RESOURCE_SCOPES[self.resource]))))
            self.fail('Undeclared synthetic provider destination')
        def key(purpose,byte):
            return KeyRing.parse(protection(purpose,byte),installation_id=installation()['installation_id'],environment='test',purpose=purpose)
        registry=Resources(spec(),ResourceCipher(key('google-resource-grant',13)),transport=httpx.MockTransport(provider))
        self.assertEqual(self.db.scalar('SELECT appointment_system.configure_google_resources('+literal(registry.metadata())+'::jsonb);'),'t')
        studio=StudioServices(GoogleOAuth(OAuthSettings(WEB,'synthetic-secret',installation()['origin'])),
            GrantCipher(WEB,key('google-grant',6)),key('staff-session',9),registry)
        company_key=key('company-session',11)
        company_settings=SimpleNamespace(digest=lambda purpose,value:company_key.digest(purpose,value.encode()),google_client_id=WEB)
        app=create_application(IsolatedStore(self.db,'appointment_system_web'),booking_settings(environment()),
            staff_store=IsolatedStore(self.db,'abs_staff'),company_store=IsolatedStore(self.db,'abs_company'),
            company_settings=company_settings,company_database=Bridge(self.db),studio_services=studio,
            projection_reader=Reader(True),verified_client_address=lambda request:'127.0.0.1')
        self.client=TestClient(app,base_url=installation()['origin']);self.headers={'Origin':installation()['origin']}
        response=self.client.post('/api/company/login',json={'username':'company.owner','password':'Synthetic company password for tests'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.headers['X-Company-CSRF']=self.client.get('/api/company/control/status').json()['csrf_token']

    def begin_resource(self,resource='calendar'):
        self.resource=resource
        response=self.client.post('/api/company/resources/start',json={'resource':resource},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.expected=parse_qs(urlsplit(response.json()['authorization_url']).query)
        self.assertEqual(self.expected['scope'][0].split(),sorted(RESOURCE_SCOPES[resource]))
        return response

    def callback(self):
        # Provider return has only the Lax correlation cookie, not company authority.
        cookie=self.client.cookies.get(COOKIE);self.client.cookies.delete(COOKIE)
        result=self.client.get('/api/company/resources/callback',params={'state':self.expected['state'][0],'code':'synthetic-code'},follow_redirects=False)
        self.assertEqual(result.status_code,303,result.text)
        self.assertNotIn(COOKIE+'=',result.headers.get('set-cookie',''))
        self.client.cookies.set(COOKIE,cookie)
        return result

    def test_callback_only_stages_and_original_company_tab_explicitly_finishes(self):
        self.begin_resource();response=self.callback();self.assertIn('.pending',response.headers['location'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')
        pending=self.client.get('/api/company/resources/status').json()['pending'];self.assertEqual(len(pending),1)
        attempt=pending[0]['attempt_id']
        result=self.client.post('/api/company/resources/finish',json={'attempt_id':attempt},headers=self.headers)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['code'],'saved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'1')
        self.assertEqual(len(self.calls),2)

    def test_origin_csrf_duplicate_query_and_callback_replay_cannot_install(self):
        for headers in ({'Origin':'https://foreign.example.test'},self.headers|{'X-Company-CSRF':'bad'}):
            response=self.client.post('/api/company/resources/start',json={'resource':'calendar'},headers=headers)
            self.assertEqual(response.status_code,403)
        self.begin_resource();state=self.expected['state'][0]
        self.assertEqual(self.client.get('/api/company/resources/callback?state='+state+'&state='+state+'&code=synthetic').status_code,401)
        self.assertEqual(len(self.calls),0);self.callback()
        self.assertEqual(self.client.get('/api/company/resources/callback',params={'state':state,'code':'synthetic'},follow_redirects=False).status_code,401)
        self.assertEqual(len(self.calls),2)

    def test_owner_link_completes_permission_without_sharing_password_or_creating_login(self):
        fixture=BookingFixture();fixture.db=self.db;fixture.setUp();booking=fixture.booking()
        fixture.start_order(booking);fixture.record_order(booking);self.assertEqual(fixture.capture(booking),'confirmed')
        result=self.client.post('/api/company/resources/owner-link',json=dict(operation_id=str(uuid4()),resource='calendar',
            reference=booking['request'],reason='Synthetic owner permission repair'),headers=self.headers)
        self.assertEqual(result.status_code,200,result.text)
        link=result.json()['owner_link'];identifier,secret=urlsplit(link).fragment.removeprefix('link=').split('.')
        self.resource='calendar'
        owner=TestClient(self.client.app,base_url=installation()['origin'])
        start=owner.post('/api/company/resources/owner-start',json={'operation_id':identifier,'secret':secret},headers={'Origin':installation()['origin']})
        self.assertEqual(start.status_code,200,start.text);self.expected=parse_qs(urlsplit(start.json()['authorization_url']).query)
        response=owner.get('/api/company/resources/callback',params={'state':self.expected['state'][0],'code':'synthetic-code'},follow_redirects=False)
        self.assertEqual(response.status_code,303,response.text);self.assertEqual(response.headers['location'],'/company/google-repair#approved=pending')
        self.assertEqual(owner.get('/api/company/resources/status').status_code,401)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')
        pending=self.client.get('/api/company/resources/status').json()['pending']
        saved=self.client.post('/api/company/resources/finish',json={'attempt_id':pending[0]['attempt_id']},headers=self.headers)
        self.assertEqual(saved.json()['code'],'saved');self.assertNotIn('Synthetic company password',link)

    def test_invalid_owner_links_and_zero_identifiers_cannot_request_google_access(self):
        body=dict(operation_id=str(uuid4()),resource='calendar',reference=str(uuid4()),reason='Synthetic owner repair')
        response=self.client.post('/api/company/resources/owner-link',json=body,headers=self.headers)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['code'],'existing_obligation_required')
        for field in ('operation_id','reference'):
            with self.subTest(field=field):
                response=self.client.post('/api/company/resources/owner-link',json=body|{field:str(UUID(int=0))},headers=self.headers)
                self.assertEqual(response.status_code,422,response.text)
        for headers,status in (({'Origin':'https://foreign.example.test'},403),(self.headers,401)):
            response=self.client.post('/api/company/resources/owner-start',json={'operation_id':str(uuid4()),'secret':'a'*64},headers=headers)
            self.assertEqual(response.status_code,status,response.text)
        result=self.client.post('/api/company/resources/finish',json={'attempt_id':str(UUID(int=0))},headers=self.headers)
        self.assertEqual(result.status_code,422,result.text)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')

    def test_cancelled_or_failed_reconnection_preserves_the_installed_permission(self):
        self.begin_resource();self.callback()
        pending=self.client.get('/api/company/resources/status').json()['pending']
        response=self.client.post('/api/company/resources/finish',json={'attempt_id':pending[0]['attempt_id']},headers=self.headers)
        self.assertEqual(response.json()['code'],'saved')
        original=self.db.scalar('SELECT md5(string_agg(row_to_json(g)::text,\'\' ORDER BY id)) FROM appointment_system.google_resource_grants g;')
        for failure in ('cancelled','provider'):
            with self.subTest(failure=failure):
                self.begin_resource();self.provider_error=failure=='provider'
                params={'state':self.expected['state'][0]}
                params.update({'error':'access_denied'} if failure=='cancelled' else {'code':'synthetic-invalid-code'})
                response=self.client.get('/api/company/resources/callback',params=params,follow_redirects=False)
                self.assertEqual(response.status_code,303,response.text)
                self.assertTrue(response.headers['location'].endswith('.failed'))
                self.assertEqual(self.client.get('/api/company/resources/status').json()['pending'],[])
                self.assertEqual(self.db.scalar('SELECT md5(string_agg(row_to_json(g)::text,\'\' ORDER BY id)) FROM appointment_system.google_resource_grants g;'),original)

    def test_malformed_callback_and_unrelated_browser_cannot_consume_permission(self):
        self.begin_resource();state=self.expected['state'][0]
        stranger=TestClient(self.client.app,base_url=installation()['origin'])
        response=stranger.get('/api/company/resources/callback',params={'state':state,'code':'synthetic-code'},follow_redirects=False)
        self.assertEqual(response.status_code,401,response.text)
        for params in ({'state':state,'code':'x','error':'access_denied'},
                       {'state':state,'code':'x'*4097},{'state':state,'extra':'untrusted'},
                       {'state':'malformed','code':'x'}):
            with self.subTest(keys=tuple(params)):
                response=self.client.get('/api/company/resources/callback',params=params,follow_redirects=False)
                self.assertEqual(response.status_code,401,response.text)
        self.assertEqual(self.calls,[])
        self.callback()
        self.assertEqual(len(self.client.get('/api/company/resources/status').json()['pending']),1)

    def test_calendar_cannot_be_used_as_a_workbook_and_repair_page_is_private(self):
        response=self.client.post('/api/company/resources/workbook',json={'resource':'calendar'},headers=self.headers)
        self.assertEqual(response.status_code,422,response.text)
        for path in ('/company/google-repair','/api/company/google-repair.js'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('no-store',response.headers['cache-control'])
            self.assertNotIn('synthetic-secret',response.text)
        self.assertEqual(self.calls,[])

    def test_company_prepares_the_approved_owners_workbook_once_through_actual_permissions(self):
        from appointment_system.google_workspace import Workspace,DRIVE,DRIVE_ABOUT
        from .test_sheet_layout import FourTabWorkbook
        self.begin_resource('client_sheet');self.callback()
        pending=self.client.get('/api/company/resources/status').json()['pending']
        saved=self.client.post('/api/company/resources/finish',json={'attempt_id':pending[0]['attempt_id']},headers=self.headers)
        self.assertEqual(saved.json()['code'],'saved')
        google=FourTabWorkbook();google.setUp();creations=[]
        def provider(request):
            if str(request.url).split('?')[0]==DRIVE_ABOUT:
                google.requests.append(request)
                return httpx.Response(200,json={'storageQuota':{'usage':'0','limit':'100000000'}})
            if str(request.url).split('?')[0]==DRIVE and request.method=='POST':
                google.requests.append(request);body=json.loads(request.content);creations.append(body)
                google.file['appProperties']=body['appProperties']
                return httpx.Response(200,json=google.file)
            return google.handle(request)
        def workspace(access,**kwargs):return Workspace(access,transport=httpx.MockTransport(provider))
        with patch('appointment_system.google_records.Workspace',side_effect=workspace):
            first=self.client.post('/api/company/resources/workbook',json={'resource':'client_sheet'},headers=self.headers)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json(),{'workbook_url':'https://docs.google.com/spreadsheets/d/synthetic_sheet'})
            repeated=self.client.post('/api/company/resources/workbook',json={'resource':'client_sheet'},headers=self.headers)
            self.assertEqual(repeated.status_code,200,repeated.text)
            self.assertEqual(repeated.json(),first.json())
        self.assertEqual(len(creations),1)
        self.assertEqual(len(google.tabs),4)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_workbooks;'),'1')
