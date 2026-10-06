"""HTTP → context → encrypted code → send → proof → SQL reservation, without money."""
from copy import deepcopy
import json,re
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from .test_sql_booking import BookingFixture
from .test_application import environment,protection,Reader
from .test_mail_contracts import document
from .fixtures import business
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal
from appointment_system.application import create_application
from appointment_system.booking_verification import VerificationSecrets
from appointment_system.configuration import installation
from appointment_system.email_configuration import connection
from appointment_system.resend_email import ResendSender
from appointment_system.secret_configuration import booking_settings
from appointment_system.serialization import canonical


class BookingCodeFixture(BookingFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")

    def setUp(self):
        super().setUp();self.spec=business(booking_otp=True);self.set_policy(self.spec)
        self.db.sql('TRUNCATE appointment_system.email_reservations;TRUNCATE appointment_system.enquiries CASCADE;TRUNCATE appointment_system.request_limits;')
        self.public=IsolatedStore(self.db,'appointment_system_web');self.worker=IsolatedStore(self.db,'abs_worker')
        env=environment()|{'BOOKING_VERIFICATION_DIGEST_KEYS':canonical(protection('booking-verification-digest',11)),
           'BOOKING_VERIFICATION_ENCRYPTION_KEYS':canonical(protection('booking-verification-encryption',12))}
        self.settings=booking_settings(env);self.keys=VerificationSecrets.from_environment(env);self.requests=[]
        declared=connection(json.dumps(document()))
        metadata={'account_id':declared.account_id,'active_key_id':declared.active_key_id,'retained_keys':list(declared.keys),'legacy_identities':document()['legacy_identities']}
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal(metadata)+'::jsonb,20,600);')
        def send(request):self.requests.append(request);return httpx.Response(200,json={'id':str(uuid4())})
        self.sender=ResendSender(declared.pinned('k2'),httpx.MockTransport(send),declared)
        self.reader=Reader(True)
        app=create_application(self.public,self.settings,verified_client_address=lambda request:'127.0.0.1',
            projection_reader=self.reader,worker_store=self.worker,email_sender=self.sender,booking_verification_keys=self.keys)
        self.client=TestClient(app,base_url=installation()['origin']);self.headers={'Origin':installation()['origin']}
        response=self.client.post('/api/checkout-context',headers=self.headers,json={})
        self.assertEqual(response.status_code,200,response.text)
        self.context=self.db.scalar('SELECT id FROM appointment_system.checkout_contexts;');self.email='Customer@example.com'

    def start(self,*,email=None,operation=None):
        self.operation=operation or str(uuid4())
        response=self.client.post('/api/booking-verification/start',headers=self.headers,
            json={'operation_id':self.operation,'email':email or self.email})
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def code(self):
        body=json.loads(self.requests[-1].content)
        self.assertEqual(body['to'],[self.email]);return re.search(r'code is: ([0-9]{6})',body['text'])[1]

    def verify(self,started,code,*,operation=None,email=None):
        return self.client.post('/api/booking-verification/verify',headers=self.headers,json={
          'operation_id':operation or str(uuid4()),'email':email or self.email,
          'challenge_id':started['challenge_id'],'generation':started['generation'],'code':code})

    def reservation(self,token,request=None):
        draft=self.draft(context=self.context);body=draft['payload']|{'email':self.email,'verification_grant':token}
        if request:body['request_id']=request
        secret=self.settings.receipt_key.issue()
        return self.public.reserve(self.context,body,secret,self.settings.receipt_key,self.account,verification_keys=self.keys),body,secret

class BookingCodeSQL(BookingCodeFixture):
    def test_email_code_is_protected_before_send_and_is_not_booking_or_payment(self):
        started=self.start();self.assertEqual(len(self.requests),1)
        row=self.db.value('SELECT to_jsonb(j) FROM appointment_system.booking_verification_mail j;')
        self.assertEqual(row['state'],'completed');self.assertEqual(row['mail_account_id'],'synthetic-team')
        self.assertTrue(row['message_ciphertext'].startswith('e1.'));self.assertNotIn(self.code(),json.dumps(row))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations WHERE verification;'),'1')
        self.assertIn('does not confirm',json.loads(self.requests[0].content)['text'])
        self.assertEqual(started['state'],'awaiting_verification')

    def test_verification_retry_returns_same_grant_and_reservation_consumes_once(self):
        started=self.start();operation=str(uuid4());code=self.code()
        verified=self.verify(started,code,operation=operation);self.assertEqual(verified.status_code,200,verified.text)
        repeat=self.verify(started,code,operation=operation);self.assertEqual(repeat.json(),verified.json())
        result,body,secret=self.reservation(verified.json()['verification_grant']);self.assertEqual(result['code'],'reserved')
        retry=self.public.reserve(self.context,body,secret,self.settings.receipt_key,self.account,verification_keys=self.keys)
        self.assertEqual(retry,{'code':'existing','booking_id':result['booking_id']})
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.booking_verification_grants WHERE consumed_request IS NOT NULL;'),'1')

    def test_wrong_guesses_stop_at_five_and_wrong_operation_replay_does_not_add_guesses(self):
        started=self.start();code=self.code();wrong='000000' if code!='000000' else '111111';operation=str(uuid4())
        first=self.verify(started,wrong,operation=operation);repeat=self.verify(started,wrong,operation=operation)
        self.assertEqual(first.status_code,422);self.assertEqual(repeat.status_code,422)
        for _ in range(4):self.assertEqual(self.verify(started,wrong).status_code,422)
        self.assertEqual(self.verify(started,code).status_code,429)
        self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.booking_verification_challenges;'),'5')

    def test_expired_code_cannot_issue_proof_and_wrong_context_cannot_use_it(self):
        started=self.start();code=self.code()
        self.db.sql("UPDATE appointment_system.booking_verification_challenges SET expires_at=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.verify(started,code).status_code,410)
        self.client.cookies.clear();self.assertEqual(self.verify(started,code).status_code,403)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.booking_verification_grants;'),'0')

    def test_price_change_keeps_proof_but_email_change_revokes_it(self):
        started=self.start();verified=self.verify(started,self.code());self.assertEqual(verified.status_code,200,verified.text)
        token=verified.json()['verification_grant'];changed=deepcopy(self.spec);changed['services'][0]['pricing']['amount_paise']=100
        self.set_policy(changed)
        result,_,_=self.reservation(token);self.assertEqual(result['code'],'reserved')

    def test_changed_email_revokes_old_unconsumed_proof(self):
        started=self.start();verified=self.verify(started,self.code());self.assertEqual(verified.status_code,200,verified.text)
        self.start(email='Different@example.com')
        result,_,_=self.reservation(verified.json()['verification_grant']);self.assertEqual(result['code'],'verification_required')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.booking_verification_grants WHERE revoked_at IS NOT NULL;'),'1')

    def test_start_retry_does_not_send_again_and_changed_body_conflicts(self):
        first=self.start();repeat=self.start(operation=self.operation)
        self.assertEqual(first,repeat);self.assertEqual(len(self.requests),1)
        response=self.client.post('/api/booking-verification/start',headers=self.headers,
            json={'operation_id':self.operation,'email':'Different@example.com'})
        self.assertEqual(response.status_code,409)

    def test_resend_wait_replay_generation_and_shared_recipient_limit(self):
        started=self.start();body={'operation_id':str(uuid4()),'email':self.email,'challenge_id':started['challenge_id'],'generation':1}
        result=self.client.post('/api/booking-verification/resend',headers=self.headers,json=body)
        self.assertEqual(result.status_code,429)
        self.db.sql("UPDATE appointment_system.booking_verification_challenges SET last_code_at=clock_timestamp()-interval '61 seconds';")
        result=self.client.post('/api/booking-verification/resend',headers=self.headers,json=body)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['generation'],2)
        self.assertEqual(len(self.requests),2)
        repeat=self.client.post('/api/booking-verification/resend',headers=self.headers,json=body)
        self.assertEqual(repeat.json(),result.json());self.assertEqual(len(self.requests),2)
        self.assertEqual(self.verify(started,'111111').status_code,409)

    def test_off_and_booking_otp_disabled_prevent_new_challenges(self):
        self.reader.enabled=False
        self.assertEqual(self.client.post('/api/booking-verification/start',headers=self.headers,json={'operation_id':str(uuid4()),'email':self.email}).status_code,404)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.booking_verification_challenges;'),'0')
        self.reader.enabled=True;self.set_policy(business(booking_otp=False))
        response=self.client.post('/api/booking-verification/start',headers=self.headers,json={'operation_id':str(uuid4()),'email':self.email})
        self.assertEqual(response.status_code,409);self.assertEqual(response.json()['code'],'verification_not_required')
