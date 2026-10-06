"""Real HTTP → purpose SQL → encrypted challenge → verify/save flows."""
import os,unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.secret_configuration import booking_settings
from appointment_system.configuration import installation as current_installation
from appointment_system.settings import BusinessSettings
from appointment_system.receipt_view import timestamp
from tools.checks.sql_target import SQLTarget,literal
from .fixtures import installation,business
from .test_application import environment,Reader
from .test_contact_protection import keys
from .sql_store import IsolatedStore

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned isolated SQL target required.')
class EnquiryFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET']);cls.db.check_owned()
        cls.db.value('SELECT appointment_system.configure_installation('+literal(installation())+'::jsonb,'+
            literal(BusinessSettings.parse(business()).document)+'::jsonb,true);')
        for role,purpose in [('appointment_system_web','web'),('abs_worker','worker')]:
            cls.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')

    def setUp(self):
        self.db.sql('TRUNCATE appointment_system.enquiries CASCADE;TRUNCATE appointment_system.request_limits;'
            'UPDATE appointment_system.contact_intake SET public_open=true;'
            'UPDATE appointment_system.control_product_state SET enabled=false;')
        self.keys=keys();self.reference=str(uuid4());self.credential=self.keys.receipt_keys.issue()
        self.public=IsolatedStore(self.db,'appointment_system_web');self.worker=IsolatedStore(self.db,'abs_worker')
        self.client=self.make_client()
        self.headers={'Origin':current_installation()['origin'],'x-enquiry-receipt':self.credential}
        self.body={'request_id':self.reference,'name':'Synthetic Customer','email':'customer@example.com',
                   'phone':'','subject':'Synthetic enquiry','message':'A synthetic enquiry for isolated tests.'}

    def make_client(self,ready=True):
        app=create_application(self.public,booking_settings(environment()),
            verified_client_address=lambda request:'127.0.0.1',worker_store=self.worker,
            contact_secrets=self.keys,contact_delivery_ready=ready,projection_reader=Reader(False))
        return TestClient(app,base_url=current_installation()['origin'])

    def start(self,body=None):
        response=self.client.post('/api/contact/start',json=body or self.body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['code'],'ok')
        return response.json()

    def code(self):
        job=self.worker.claim_enquiry_delivery('email');self.assertEqual(job['kind'],'verification')
        code=self.keys.open_code(job['code_ciphertext'],self.reference,self.body['email'],job['generation'],
            timestamp(job['code_expires_at']),format=job['code_format'])
        return code,job

    def verify(self,code,generation=1,client=None):
        return (client or self.client).post('/api/contact/verify',headers=self.headers,
            json={'request_id':self.reference,'generation':generation,'code':code})

class EnquiryFlowSQL(EnquiryFixture):
    def test_off_does_not_disable_enquiry_and_verification_atomically_saves_four_obligations(self):
        self.assertEqual(self.client.get('/api/booking-policy').status_code,404)
        self.assertEqual(self.start()['state'],'awaiting_verification');code,_=self.code()
        self.assertEqual(self.verify(code).json()['state'],'received')
        self.assertEqual(self.verify(code).json()['state'],'received')
        row=self.db.value("SELECT jsonb_build_object('verified',verified_at IS NOT NULL,'code_erased',code_ciphertext IS NULL,"
            "'format',receipt_format,'key_id',receipt_key_id) FROM appointment_system.enquiries WHERE request_id="+literal(self.reference)+';')
        self.assertEqual(row,{'verified':True,'code_erased':True,'format':'v1','key_id':'k2'})
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification';"),'4')

    def test_saved_retry_keeps_original_challenge_and_changed_content_is_rejected(self):
        self.start();original=self.db.scalar('SELECT code_ciphertext FROM appointment_system.enquiries;')
        self.start();self.assertEqual(self.db.scalar('SELECT code_ciphertext FROM appointment_system.enquiries;'),original)
        changed=self.client.post('/api/contact/start',json=self.body|{'message':'Different saved content.'},headers=self.headers)
        self.assertEqual(changed.status_code,409);self.assertEqual(changed.json()['code'],'request_conflict')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiry_delivery_jobs;'),'1')

    def test_wrong_credential_cannot_read_or_verify_a_saved_enquiry(self):
        self.start();code,_=self.code();self.headers['x-enquiry-receipt']=self.keys.receipt_keys.issue()
        response=self.verify(code);self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.scalar('SELECT verified_at IS NOT NULL FROM appointment_system.enquiries;'),'f')

    def test_wrong_codes_are_persistently_bounded_and_expired_codes_cannot_save(self):
        self.start();code,_=self.code();wrong='000000' if code!='000000' else '111111'
        for _ in range(5):self.assertNotEqual(self.verify(wrong).status_code,200)
        self.assertNotEqual(self.verify(code).status_code,200)
        self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.enquiries;'),'5')
        self.assertEqual(self.db.scalar('SELECT verified_at IS NOT NULL FROM appointment_system.enquiries;'),'f')

    def test_resend_cooldown_then_same_operation_preserves_one_new_generation(self):
        self.start();operation=str(uuid4());body={'request_id':self.reference,'operation_id':operation}
        response=self.client.post('/api/contact/resend',headers=self.headers,json=body)
        self.assertEqual(response.status_code,429)
        self.db.sql("UPDATE appointment_system.enquiries SET resend_after=clock_timestamp()-interval '1 second';")
        first=self.client.post('/api/contact/resend',headers=self.headers,json=body)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['generation'],2)
        frozen=self.db.scalar('SELECT code_ciphertext FROM appointment_system.enquiries;')
        replay=self.client.post('/api/contact/resend',headers=self.headers,json=body)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(self.db.scalar('SELECT code_ciphertext FROM appointment_system.enquiries;'),frozen)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiry_delivery_jobs;'),'2')
        code,_=self.code();self.assertEqual(self.verify(code,2).json()['state'],'received')

    def test_saved_enquiry_can_be_verified_when_delivery_setup_later_becomes_unavailable(self):
        self.start();code,_=self.code()
        response=self.verify(code,client=self.make_client(ready=False))
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['state'],'received')
