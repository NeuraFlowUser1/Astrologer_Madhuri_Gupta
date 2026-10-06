"""Real SQL reclaims, stale releases, exact attempts and permanent review limits."""
import json
from uuid import uuid4
from appointment_system.configuration import installation
from appointment_system.email_configuration import connection
from appointment_system.job_authority import JobClaim
from .test_sql_booking import BookingFixture
from .test_mail_contracts import document
from . import test_sql_mail as mail_fixture
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal

class JobClaimsSQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")

    def setUp(self):
        super().setUp()
        self.declared=connection(json.dumps(document()))
        metadata={'account_id':self.declared.account_id,'active_key_id':self.declared.active_key_id,
          'retained_keys':list(self.declared.keys),'legacy_identities':document()['legacy_identities']}
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal(metadata)+'::jsonb,20,600);')
        self.worker=IsolatedStore(self.db,'abs_worker')
        self.booking_saved=mail_fixture.MailSQL.confirmed(self)

    def claim(self):
        self.db.sql("UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '1 hour' WHERE recipient_role<>'customer';")
        job=self.worker.claim_email_delivery();self.assertIsNotNone(job);return job

    def check(self,claim):
        return self.worker._call('SELECT true',job_authority=claim)

    def test_claim_stamps_actual_installation_release_restore_and_saved_attempt(self):
        job=self.claim();claim=JobClaim.saved('booking',job)
        self.assertEqual(job['claim_installation'],installation()['installation_id'])
        self.assertEqual(job['claim_release'],'a'*64);self.assertEqual(job['claim_contract'],1)
        self.assertEqual(job['claim_generation'],self.db.scalar('SELECT restore_generation FROM appointment_system.control_product_state;'))
        self.assertTrue(self.check(claim));self.assertEqual(job['state'],'processing')

    def test_wrong_attempt_generation_release_or_lease_has_no_write_authority(self):
        job=self.claim()
        for fields in ({'attempts':job['attempts']+1},{'claim_generation':str(uuid4())},
                       {'claim_release':'b'*64},{'lease_token':str(uuid4())}):
            with self.subTest(fields=fields),self.assertRaisesRegex(AssertionError,'job claim changed'):
                self.check(JobClaim.saved('booking',dict(job,**fields)))
        self.assertTrue(self.check(JobClaim.saved('booking',job)))
        self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.delivery_jobs WHERE id='+literal(job['id'])+';'),'processing')

    def test_replacement_attempt_revokes_original_claim_without_changing_payload(self):
        old=self.claim();old_claim=JobClaim.saved('booking',old)
        self.db.sql('UPDATE appointment_system.delivery_jobs SET lease_expires_at=clock_timestamp()-interval \'1 second\' WHERE id='+literal(old['id'])+';')
        new=self.worker.claim_email_delivery();self.assertEqual(new['id'],old['id']);self.assertNotEqual(new['lease_token'],old['lease_token'])
        self.assertEqual(new['attempts'],old['attempts']+1);self.assertEqual(new['payload'],old['payload'])
        with self.assertRaisesRegex(AssertionError,'job claim changed'):self.check(old_claim)
        self.assertTrue(self.check(JobClaim.saved('booking',new)))

    def test_release_replacement_invalidates_live_job_and_direct_unfenced_completion(self):
        job=self.claim();claim=JobClaim.saved('booking',job)
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'b'*64+"');")
        with self.assertRaisesRegex(AssertionError,'job claim changed'):self.check(claim)
        direct='SELECT appointment_system.finish_email_delivery('+','.join(literal(value) for value in (job['id'],job['lease_token'],None,'synthetic_error',False,30))+');'
        self.assertEqual(self.db.scalar(direct),'f')
        self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.delivery_jobs WHERE id='+literal(job['id'])+';'),'processing')

    def test_old_record_assignment_entry_cannot_be_used_by_registered_worker(self):
        job=self.worker.claim_google_delivery('client_sheet');self.assertIsNotNone(job)
        for name in ('assign_sheet_row','assign_enquiry_row'):
            with self.assertRaisesRegex(AssertionError,'permission denied'):
                self.db.sql('SELECT appointment_system.'+name+"('client',"+literal(job['id'])+",'[]'::jsonb);",role='abs_worker')
        with self.assertRaisesRegex(AssertionError,'job claim changed'):
            self.worker.assign_sheet_row('client',dict(job,lease_token=str(uuid4())),[])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_rows WHERE job_id='+literal(job['id'])+';'),'0')

    def test_exhausted_google_job_becomes_private_review_and_stops_normal_due_selection(self):
        self.db.sql("UPDATE appointment_system.delivery_jobs SET attempts=20 WHERE kind='booking_calendar';")
        self.assertIsNone(self.worker.claim_google_delivery('calendar'))
        self.assertEqual(self.db.scalar("SELECT state FROM appointment_system.delivery_jobs WHERE kind='booking_calendar';"),'needs_review')
        self.assertEqual(self.db.scalar("SELECT last_error_code FROM appointment_system.delivery_jobs WHERE kind='booking_calendar';"),'job_attempt_limit')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.recovery_due_work WHERE lane='booking_records' AND resource='calendar';"),'0')

if __name__=='__main__':
    import unittest
    unittest.main()
