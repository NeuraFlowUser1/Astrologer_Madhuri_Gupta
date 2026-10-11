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



class ReceiptRecoverySQL(ReceiptRecoveryFixture):
    def correction(self,booking,operation=None,*,email='corrected@example.com'):
        operation=operation or uuid4();reference=UUID(booking['request'])
        return self.staff.studio_support_change(self.session,CLIENT,ORIGIN,operation,reference,1,'contact_correction',
            'Synthetic approved contact correction','pay_synthetic',email,'+919123456789')

    def test_contact_correction_uses_the_booking_frozen_email_rule_when_current_otp_is_on(self):
        booking=self.confirmed(email=None,normalization_version=3)
        self.spec['booking_verification']['email']=True;self.spec['required_contacts']=['email','phone'];self.set_policy(self.spec)
        result=self.correction(booking,email=None);self.assertEqual(result['code'],'contact_corrected')
        self.assertEqual(self.db.scalar('SELECT email IS NULL FROM appointment_system.bookings;'),'t')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND recipient_role='customer';"),'0')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND kind='sheet_booking';"),'2')

    def test_contact_correction_preserves_full_records_and_the_accepted_meeting_choice(self):
        booking=self.confirmed(notes='Saved preparation',birth_place='Saved city')
        self.spec['meeting']='internal';self.set_policy(self.spec)
        operation=uuid4();result=self.correction(booking,operation)
        self.assertEqual(result['code'],'contact_corrected');self.assertEqual(self.correction(booking,operation),result)
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
        self.assertEqual(self.correction(booking)['code'],'contact_corrected')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE recipient_role='calendar';"),'0')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2;"),'4')





    def test_retired_database_overloads_are_absent(self):
        for signature in ('redeem_receipt_recovery(uuid,text,text)','redeem_receipt_recovery(uuid,text,text,text)',
          'recovery_protection(uuid,uuid)','studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text)'):
            self.assertEqual(self.db.scalar("SELECT to_regprocedure('appointment_system."+signature+"') IS NULL;"),'t')



