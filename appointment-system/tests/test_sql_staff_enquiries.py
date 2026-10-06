"""Real staff SQL login and enquiry-only HTTP when the booking product is OFF."""
from urllib.parse import parse_qs,urlsplit
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from appointment_system.google_oauth import OAuthSettings,GrantCipher
from appointment_system.studio import StudioServices,SESSION_COOKIE
from appointment_system.keys import encode
from tools.checks.sql_target import literal
from . import test_sql_enquiry_flow as enquiry_tests,test_google_oauth as oauth_tests
from .test_application import Reader,environment
from appointment_system.secret_configuration import booking_settings
from .test_keys import ring,document
from .sql_store import IsolatedStore

class StaffEnquiriesSQL(enquiry_tests.EnquiryFlowSQL):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();oauth_tests.GoogleOAuthTests.setUpClass()

    def setUp(self):
        super().setUp()
        self.db.sql("TRUNCATE appointment_system.studio_identities,appointment_system.google_attempts,appointment_system.staff_reviews CASCADE;UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false;")
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'a'*64+"');")
        self.db.scalar("SELECT appointment_system.provision_login('abs_staff','staff');")
        self.staff=IsolatedStore(self.db,'abs_staff')
        self.google=oauth_tests.GoogleOAuthTests();self.google.setUp();self.google.settings=OAuthSettings(oauth_tests.CLIENT,'synthetic-secret',installation()['origin'])
        self.google.claims['sub']='123456789'
        keys=document(purpose='staff-session');keys['keys']={'k1':encode(b'S'*32),'k2':encode(b'T'*32)}
        self.services=StudioServices(self.google.provider(),GrantCipher(oauth_tests.CLIENT,ring(purpose='google-grant')),ring(keys,purpose='staff-session'))
        self.reader=Reader(False);self.settings=booking_settings(environment())
        app=create_application(self.public,self.settings,verified_client_address=lambda request:'127.0.0.1',projection_reader=self.reader,
            contact_secrets=self.keys,contact_delivery_ready=True,worker_store=self.worker,staff_store=self.staff,studio_services=self.services)
        self.client=TestClient(app,base_url=installation()['origin']);self.reader.enabled=False

    def sign_in(self,portal='enquiry',complete=True):
        response=self.client.post('/api/'+('enquiry-studio' if portal=='enquiry' else 'studio')+'/sign-in/start',json={'role':'client'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        query=parse_qs(urlsplit(response.json()['authorization_url']).query);self.google.claims['nonce']=query['nonce'][0]
        if not complete:return query
        callback=self.client.get('/api/studio/sign-in/callback',params={'state':query['state'][0],'code':'synthetic-once-code'},follow_redirects=False)
        self.assertEqual(callback.status_code,303,callback.text);return callback

    def test_google_signin_native_staff_role_works_off_without_creating_resource_or_company_grant(self):
        callback=self.sign_in();self.assertEqual(callback.headers['location'],'/enquiries-studio?connection=signed-in')
        self.assertIn(SESSION_COOKIE,callback.headers['set-cookie'])
        status=self.client.get('/api/enquiry-studio/status');self.assertEqual(status.json(),{'signed_in':True,'email':'practice@example.test'})
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_connections;'),'0')
        self.assertEqual(self.client.get('/studio').status_code,404)
        self.assertEqual(self.client.get('/api/studio/status').status_code,404)
        self.assertEqual(self.client.get('/enquiries-studio').status_code,200)
        self.assertNotIn('NeuraFlow',self.client.get('/enquiries-studio').text)
        self.assertEqual(self.client.get('/api/enquiry-studio/interface.js').status_code,200)

    def test_signed_in_staff_can_list_open_and_review_verified_enquiry_off_but_cannot_read_payment(self):
        self.start();code,_=self.code();self.assertEqual(self.verify(code).status_code,200)
        self.sign_in();self.headers.pop('x-enquiry-receipt',None)
        page=self.client.post('/api/enquiry-studio/inbox/list',json={'view':'enquiries'},headers=self.headers)
        self.assertEqual(page.status_code,200,page.text);self.assertEqual(len(page.json()['items']),1)
        key=page.json()['items'][0]['item_key'];detail=self.client.post('/api/enquiry-studio/inbox/detail',json={'item_key':key},headers=self.headers)
        self.assertEqual(detail.status_code,200,detail.text);self.assertEqual(detail.json()['item']['enquiry']['message'],self.body['message'])
        body={'item_key':key,'operation_id':str(uuid4()),'expected_revision':0,'note':'Called the customer and replied.'}
        for _ in range(2):
            result=self.client.post('/api/enquiry-studio/inbox/review',json=body,headers=self.headers);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.staff_reviews;'),'1')
        saved=self.client.post('/api/enquiry-studio/inbox/action-result',json={'operation_id':body['operation_id']},headers=self.headers)
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json(),{'code':'review_saved','revision':1,'operation_id':body['operation_id']})
        self.assertEqual(self.client.get('/api/enquiry-studio/staff-actions.js').status_code,200)
        for action in ('detail','review','retry'):
            payload={'item_key':'payment:'+str(uuid4())} if action=='detail' else body|{'item_key':'payment:'+str(uuid4())}
            self.assertEqual(self.client.post('/api/enquiry-studio/inbox/'+action,json=payload,headers=self.headers).status_code,403)

    def test_signin_requires_same_browser_one_time_return_and_wrong_google_owner_cannot_login(self):
        query=self.sign_in(complete=False);self.client.cookies.clear()
        result=self.client.get('/api/studio/sign-in/callback',params={'state':query['state'][0],'code':'synthetic-code'},follow_redirects=False)
        self.assertNotIn('signed-in',result.headers['location']);self.assertEqual(len(self.google.calls),0)
        query=self.sign_in(complete=False);self.google.claims['email']='foreign@example.test'
        for _ in range(2):
            result=self.client.get('/api/studio/sign-in/callback',params={'state':query['state'][0],'code':'synthetic-code'},follow_redirects=False)
            self.assertNotIn('signed-in',result.headers['location'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.studio_sessions;'),'0')
        self.assertEqual(len([r for r in self.google.calls if str(r.url).endswith('/token')]),1)

    def test_booking_signin_is_fenced_after_off_but_enquiry_signout_revokes_existing_access(self):
        self.reader.enabled=True;self.db.sql('UPDATE appointment_system.control_product_state SET enabled=true,requested_enabled=true;')
        query=self.sign_in('booking',complete=False)
        self.reader.enabled=False;self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false;')
        result=self.client.get('/api/studio/sign-in/callback',params={'state':query['state'][0],'code':'synthetic-code'},follow_redirects=False)
        self.assertNotIn('signed-in',result.headers['location']);self.assertEqual(len(self.google.calls),0)
        self.sign_in();cookie=self.client.cookies.get(SESSION_COOKIE)
        result=self.client.post('/api/enquiry-studio/logout',json={},headers=self.headers);self.assertEqual(result.status_code,200,result.text)
        self.client.cookies.set(SESSION_COOKIE,cookie,domain='practice.example.test',path='/')
        self.assertEqual(self.client.get('/api/enquiry-studio/status').status_code,401)

    def failed_delivery_setup(self):
        self.start();code,_=self.code();self.assertEqual(self.verify(code).status_code,200)
        self.db.sql("UPDATE appointment_system.enquiry_delivery_jobs SET state='needs_review',last_error_code='synthetic_failure' WHERE kind<>'verification';")
        self.sign_in();self.headers.pop('x-enquiry-receipt',None)
        return self.db.value("SELECT jsonb_agg('enquiry-delivery:'||id ORDER BY ('enquiry-delivery:'||id)) FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification';")

    def test_off_enquiry_issue_view_returns_all_four_failed_delivery_obligations(self):
        expected=self.failed_delivery_setup()
        result=self.client.post('/api/enquiry-studio/inbox/list',json={'view':'issues'},headers=self.headers)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['view'],'enquiry-issues')
        self.assertEqual([row['item_key'] for row in result.json()['items']],expected)
        self.assertEqual(sorted(row['category'] for row in result.json()['items']),
            ['agency_records','client_records','enquiry_email','enquiry_email'])
        self.assertIsNone(result.json()['next_cursor'])
        self.assertEqual(self.client.get('/studio').status_code,404)
        self.assertEqual(self.client.get('/api/booking-policy').status_code,404)

    def test_enquiry_issue_cursor_keeps_only_remaining_enquiry_delivery_items(self):
        expected=self.failed_delivery_setup()
        result=self.client.post('/api/enquiry-studio/inbox/list',json={'view':'issues','after':expected[1]},headers=self.headers)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([row['item_key'] for row in result.json()['items']],expected[2:])
        self.assertIsNone(result.json()['next_cursor'])

    def test_enquiry_issue_view_does_not_treat_unverified_work_as_a_failure(self):
        self.start()
        self.db.sql("UPDATE appointment_system.enquiry_delivery_jobs SET state='needs_review',last_error_code='synthetic_failure';")
        self.sign_in();self.headers.pop('x-enquiry-receipt',None)
        result=self.client.post('/api/enquiry-studio/inbox/list',json={'view':'issues'},headers=self.headers)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['items'],[])

    def test_visible_enquiry_delivery_issue_accepts_one_replayed_review_without_changing_delivery(self):
        expected=self.failed_delivery_setup();key=expected[0]
        detail=self.client.post('/api/enquiry-studio/inbox/detail',json={'item_key':key},headers=self.headers)
        self.assertEqual(detail.status_code,200,detail.text);self.assertEqual(detail.json()['item']['item_key'],key)
        payload={'item_key':key,'operation_id':str(uuid4()),'expected_revision':0,'note':'Checked the saved enquiry delivery.'}
        for _ in range(2):
            result=self.client.post('/api/enquiry-studio/inbox/review',json=payload,headers=self.headers)
            self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['code'],'review_saved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.staff_reviews;'),'1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification' AND state='needs_review';"),'4')
        result=self.client.post('/api/enquiry-studio/inbox/list',json={'view':'issues'},headers=self.headers)
        self.assertEqual(len(result.json()['items']),4)
        self.assertEqual(next(row for row in result.json()['items'] if row['item_key']==key)['review_revision'],1)
