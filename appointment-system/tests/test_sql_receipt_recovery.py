"""Support receipt replacement, key rotation and permission boundaries on native SQL."""
from dataclasses import replace
import hashlib
import hmac
from uuid import UUID,uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from appointment_system.credentials import ReceiptKeys
from appointment_system.keys import KeyRing,encode
from appointment_system.receipt_recovery import recovery_code,code_digest,support_key
from appointment_system.secret_configuration import booking_settings
from appointment_system.security import receipt_digest
from tools.checks.sql_target import literal
from .test_sql_staff import StaffFixture,CLIENT,ORIGIN
from .test_application import Reader,environment,protection
from .sql_store import IsolatedStore


class ReceiptRecoveryFixture(StaffFixture):
    def setUp(self):
        super().setUp()
        spec=protection('receipt',1);spec['keys']={'old':encode(b'A'*32),'new':encode(b'B'*32)};spec['active']='old'
        self.old=ReceiptKeys(KeyRing.parse(spec,installation_id=spec['installation_id'],environment=spec['environment'],purpose='receipt'))
        self.new=ReceiptKeys(replace(self.old.ring,active='new'))
        self.public=IsolatedStore(self.db,'appointment_system_web');self.reader=Reader(True)
        self.settings=replace(booking_settings(environment()),receipt_key=self.new)
        self.client=TestClient(create_application(self.public,self.settings,verified_client_address=lambda request:'127.0.0.1',projection_reader=self.reader),base_url=installation()['origin'])
        self.addCleanup(self.client.close);self.headers={'Origin':installation()['origin']}

    def issue(self,booking,key=None,operation=None):
        key=key or self.old;operation=operation or uuid4();reference=UUID(booking['request'])
        key_id=support_key(key,self.staff,reference,operation,new=True);code=recovery_code(key,operation,reference,key_id=key_id)
        result=self.staff.studio_support_change(self.session,CLIENT,ORIGIN,operation,reference,1,'receipt_recovery',
            'Synthetic authorized access replacement','pay_synthetic',None,None,code_digest(key,reference,code,key_id=key_id),key_id)
        self.assertEqual(result['code'],'support_saved',result)
        return operation,code,result

    def redeem(self,booking,code,secret):
        return self.client.post('/api/checkout/recover-receipt',json={'request_id':booking['request'],'code':code,'secret':secret},headers=self.headers)

class ReceiptRecoverySQL(ReceiptRecoveryFixture):
    def correction(self,booking,operation=None):
        operation=operation or uuid4();reference=UUID(booking['request'])
        key_id=support_key(self.old,self.staff,reference,operation,new=True)
        code=recovery_code(self.old,operation,reference,key_id=key_id)
        return self.staff.studio_support_change(self.session,CLIENT,ORIGIN,operation,reference,1,'contact_correction',
            'Synthetic approved contact correction','pay_synthetic','corrected@example.com','+919123456789',
            code_digest(self.old,reference,code,key_id=key_id),key_id)

    def test_contact_correction_preserves_full_records_and_the_accepted_meeting_choice(self):
        booking=self.confirmed(notes='Saved preparation',birth_place='Saved city')
        self.spec['meeting']='internal';self.set_policy(self.spec)
        operation=uuid4();result=self.correction(booking,operation)
        self.assertEqual(result['code'],'support_saved');self.assertEqual(self.correction(booking,operation),result)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='booking_cancelled';"),'1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND kind='booking_calendar';"),'1')
        rows=self.db.value("SELECT jsonb_agg(payload) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND kind='sheet_booking';")
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(row['request_id'],booking['request']);self.assertEqual(row['currency'],'INR')
            self.assertEqual(row['preparation']['notes'],'Saved preparation');self.assertEqual(row['payment_reference'],'pay_synthetic')
            self.assertEqual(row['email'],'corrected@example.com');self.assertEqual(row['revision'],2)
        previous=self.db.value("SELECT payload FROM appointment_system.delivery_jobs WHERE kind='booking_cancelled';")
        self.assertEqual(previous['revision'],1);self.assertNotEqual(previous['email'],'corrected@example.com')

    def test_internal_meeting_contact_correction_never_queues_google_even_if_current_choice_changes(self):
        self.spec['meeting']='internal';self.set_policy(self.spec);booking=self.confirmed()
        self.spec['meeting']='google_meet';self.set_policy(self.spec)
        self.assertEqual(self.correction(booking)['code'],'support_saved')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE recipient_role='calendar';"),'0')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2;"),'4')

    def test_rotated_code_replays_unchanged_and_new_receipt_metadata_is_installed_atomically(self):
        booking=self.confirmed();operation,code,result=self.issue(booking)
        _,again,replayed=self.issue(booking,self.new,operation);self.assertEqual(code,again);self.assertEqual(result,replayed)
        secret=self.new.issue();response=self.redeem(booking,code,secret)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['code'],'receipt_restored')
        self.assertEqual(self.redeem(booking,code,secret).status_code,200,'Same receipt retry after a lost response must work')
        status=self.client.post('/api/checkout/status',json={'request_id':booking['request']},headers=self.headers|{'X-Booking-Receipt':secret})
        self.assertEqual(status.status_code,200,status.text);self.assertEqual(status.json()['appointment_state'],'confirmed')
        saved=self.db.value("SELECT jsonb_build_object('format',b.receipt_format,'key',b.receipt_key_id,'digest',a.receipt_digest) FROM appointment_system.bookings b JOIN appointment_system.checkout_admissions a USING(request_id) WHERE b.request_id="+literal(booking['request'])+';')
        self.assertEqual(saved,{'format':'v1','key':'new','digest':receipt_digest(booking['request'],secret,self.new)})
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.receipt_recoveries;'),'1')

    def test_wrong_codes_are_bounded_and_never_replace_the_receipt(self):
        booking=self.confirmed();_,code,_=self.issue(booking);secret=self.new.issue();wrong='00000000' if code!='00000000' else '11111111'
        for _ in range(5):self.assertEqual(self.redeem(booking,wrong,secret).status_code,403)
        self.assertEqual(self.redeem(booking,code,secret).status_code,403)
        self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.receipt_recoveries;'),'5')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.receipt_recoveries WHERE redeemed_at IS NOT NULL;'),'0')

    def test_replaced_access_cannot_be_redeemed_into_another_secret_and_off_denies_all_public_recovery(self):
        booking=self.confirmed();_,code,_=self.issue(booking);secret=self.new.issue()
        self.assertEqual(self.redeem(booking,code,secret).status_code,200)
        self.assertEqual(self.redeem(booking,code,self.new.issue()).status_code,403)
        self.reader.enabled=False;self.assertEqual(self.redeem(booking,code,secret).status_code,404)

    def test_retired_database_overloads_are_no_longer_callable_by_application_roles(self):
        self.assertEqual(self.db.scalar("SELECT has_function_privilege('appointment_system_web','appointment_system.redeem_receipt_recovery(uuid,text,text)','EXECUTE');"),'f')
        self.assertEqual(self.db.scalar("SELECT has_function_privilege('abs_staff','appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text)','EXECUTE');"),'f')
        self.assertEqual(self.db.scalar("SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='appointment_system.redeem_receipt_recovery(uuid,text,text,text)'::regprocedure;"),'appointment_system_owner')


class HistoricalReceiptRecoverySQL(ReceiptRecoveryFixture):
    def historical(self,prefix='sarsa:004:'):
        booking=self.confirmed();operation,_,_=self.issue(booking)
        material=b'Synthetic historical recovery protection only'
        # Compute with the original system's algorithm independently of the reader.
        raw=hmac.new(material,f'{prefix}support-code:v1:{operation}:{booking["request"]}'.encode(),hashlib.sha256).digest()
        code=str(int.from_bytes(raw,'big')%100000000).zfill(8)
        digest=hmac.new(material,f'{prefix}support-code-digest:v1:{booking["request"]}:{code}'.encode(),hashlib.sha256).hexdigest()
        keys=replace(self.new,legacy_keys=(('prior',material),),recovery_readers={'prior-support':{
            'key_id':'prior','code_audience':prefix+'support-code:v1:','digest_audience':prefix+'support-code-digest:v1:'}})
        self.db.sql('UPDATE appointment_system.receipt_recoveries SET code_format=\'prior-support\',code_key_id=\'prior\',code_digest='+literal(digest)+' WHERE operation_id='+literal(str(operation))+';')
        self.client.close()
        self.client=TestClient(create_application(self.public,replace(self.settings,receipt_key=keys),verified_client_address=lambda request:'127.0.0.1',projection_reader=self.reader),base_url=installation()['origin'])
        self.addCleanup(self.client.close)
        return booking,code,operation

    def assert_historical_redemption(self,prefix):
        booking,code,operation=self.historical(prefix);secret=self.new.issue()
        response=self.redeem(booking,code,secret)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.redeem(booking,code,secret).status_code,200)
        self.assertEqual(self.redeem(booking,code,self.new.issue()).status_code,403)
        status=self.client.post('/api/checkout/status',json={'request_id':booking['request']},headers=self.headers|{'X-Booking-Receipt':secret})
        self.assertEqual(status.status_code,200,status.text)
        self.assertEqual(self.db.value("SELECT jsonb_build_object('format',receipt_format,'key',receipt_key_id) FROM appointment_system.bookings WHERE request_id="+literal(booking['request'])+';'),{'format':'v1','key':'new'})
        self.assertEqual(self.db.value("SELECT jsonb_build_object('format',code_format,'key',code_key_id,'redeemed',redeemed_at IS NOT NULL) FROM appointment_system.receipt_recoveries WHERE operation_id="+literal(str(operation))+';'),{'format':'prior-support','key':'prior','redeemed':True})

    def test_sarsa_code_remains_redeemable_without_changing_the_original_code_or_key(self):
        self.assert_historical_redemption('sarsa:004:')

    def test_astroadvice_code_remains_redeemable_without_changing_the_original_code_or_key(self):
        self.assert_historical_redemption('astro:003:')

    def test_historical_codes_keep_attempt_limits_and_the_off_fence(self):
        booking,code,_=self.historical();secret=self.new.issue()
        self.reader.enabled=False
        self.assertEqual(self.redeem(booking,code,secret).status_code,404)
        self.reader.enabled=True
        wrong='00000000' if code!='00000000' else '11111111'
        for _ in range(5):self.assertEqual(self.redeem(booking,wrong,secret).status_code,403)
        self.assertEqual(self.redeem(booking,code,secret).status_code,403)
        self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.receipt_recoveries;'),'5')

    def test_expired_historical_code_cannot_be_revived_by_the_new_reader(self):
        booking,code,_=self.historical()
        self.db.sql("UPDATE appointment_system.receipt_recoveries SET created_at=clock_timestamp()-interval '1 hour',expires_at=clock_timestamp()-interval '1 minute';")
        self.assertEqual(self.redeem(booking,code,self.new.issue()).status_code,403)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.receipt_recoveries WHERE redeemed_at IS NOT NULL;'),'0')
