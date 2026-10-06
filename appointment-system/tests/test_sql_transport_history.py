"""Committed attempts remain distinct across retries and exact privacy erasure."""
from uuid import uuid4
import psycopg
from . import test_sql_booking as booking_fixture
from . import test_sql_privacy as privacy_fixture
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal

class TransportHistorySQL(booking_fixture.BookingFixture):
    def setUp(self):
        super().setUp();self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        self.worker=IsolatedStore(self.db,'abs_worker')
        item=self.booking();self.assertEqual(self.start_order(item),'t');self.assertEqual(self.record_order(item),'ready')
        self.assertEqual(self.capture(item),'confirmed')

    def test_each_retry_keeps_prior_claim_result_and_exact_writer_identity(self):
        first=self.worker.claim_google_delivery('calendar');self.assertIsNotNone(first)
        self.assertTrue(self.worker.finish_google_delivery(first,'failed',error='google_request_failed',delay=30))
        self.db.sql('UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp() WHERE id='+literal(first['id'])+';')
        second=self.worker.claim_google_delivery('calendar');self.assertEqual(second['id'],first['id'])
        self.assertNotEqual(second['lease_token'],first['lease_token'])
        event=self.db.scalar('SELECT appointment_system.calendar_event_identity(id,revision,calendar_protocol) FROM appointment_system.bookings WHERE id='+literal(second['booking_id'])+';')
        self.assertTrue(self.worker.finish_google_delivery(second,'done',provider=event,meet='https://meet.google.com/abc-defg-hij'))
        rows=self.db.value('SELECT jsonb_agg(to_jsonb(e) ORDER BY occurred_at,id) FROM appointment_system.transport_attempt_events e WHERE job_id='+literal(first['id'])+';')
        self.assertEqual([row['phase'] for row in rows],['claimed','result','claimed','result'])
        self.assertEqual([row['state'] for row in rows],['processing','retry_wait','processing','completed'])
        self.assertEqual([row['attempt'] for row in rows],[1,1,2,2])
        for row in rows:
            self.assertEqual(row['installation_id'],first['claim_installation']);self.assertEqual(row['release_digest'],'a'*64)
            self.assertFalse(set(row)&{'payload','destination','provider_id','email','phone','booking_id','message_snapshot'})
        for role in ('appointment_system_web','abs_worker'):
            with self.assertRaisesRegex(AssertionError,'permission denied'):
                self.db.sql('UPDATE appointment_system.transport_attempt_events SET state=\'completed\';',role=role)

    def test_reclaimed_expired_attempt_records_unknown_before_new_claim(self):
        first=self.worker.claim_google_delivery('calendar')
        self.db.sql('UPDATE appointment_system.delivery_jobs SET lease_expires_at=clock_timestamp()-interval \'1 second\' WHERE id='+literal(first['id'])+';')
        second=self.worker.claim_google_delivery('calendar');self.assertNotEqual(second['lease_token'],first['lease_token'])
        rows=self.db.value('SELECT jsonb_agg(state ORDER BY occurred_at,id) FROM appointment_system.transport_attempt_events WHERE job_id='+literal(first['id'])+';')
        self.assertEqual(rows,['processing','delivery_unknown','processing'])
        with self.assertRaises(AssertionError):self.worker.finish_google_delivery(first,'done')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.transport_attempt_events WHERE job_id='+literal(first['id'])+';'),'3')

class TransportRetentionSQL(privacy_fixture.PrivacySQL):
    def old_transport(self):
        identifier=str(uuid4())
        self.db.sql("INSERT INTO appointment_system.transport_attempt_events(id,installation_id,job_kind,job_id,attempt,lease_token,generation,release_digest,contract,phase,state,occurred_at) SELECT "+literal(identifier)+",installation_id,'booking',gen_random_uuid(),1,gen_random_uuid(),gen_random_uuid(),'"+'a'*64+"',1,'result','completed',clock_timestamp()-interval '100 days' FROM appointment_system.installation;")
        self.db.sql("INSERT INTO appointment_system.control_privacy_policy_approvals(policy_id,approved_by) VALUES('resolved-transport-v1','Synthetic owner approval');")
        targets=self.maintenance.inspect('resolved-transport-v1')['targets'];return next(row for row in targets if row['id']==identifier)

    def test_only_proved_mature_resolved_attempt_is_erased_and_replay_does_not_restore_it(self):
        target=self.old_transport();old=self.db.value('SELECT to_jsonb(e) FROM appointment_system.transport_attempt_events e WHERE id='+literal(target['id'])+';')
        operation=str(uuid4());self.engine.record_intent(operation,'resolved-transport-v1',target['id'],target['target_hash'])
        self.assertTrue(self.engine.apply(operation)['erased']);self.assertTrue(self.engine.apply(operation)['erased'])
        self.db.sql('TRUNCATE appointment_system.control_privacy_intents CASCADE; INSERT INTO appointment_system.transport_attempt_events SELECT * FROM jsonb_populate_record(NULL::appointment_system.transport_attempt_events,'+literal(old)+'::jsonb);')
        result=self.restore();proof=self.engine.replay(self.operation,result['snapshot']['restore_generation'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.transport_attempt_events WHERE id='+literal(target['id'])+';'),'0')
        self.assertTrue(self.maintenance.confirm(self.operation,result['snapshot'],proof)['verified'])

    def test_newer_attempt_evidence_cancels_erasure_without_deleting_audit_records(self):
        target=self.old_transport();operation=str(uuid4());self.engine.record_intent(operation,'resolved-transport-v1',target['id'],target['target_hash'])
        self.db.sql('UPDATE appointment_system.transport_attempt_events SET occurred_at=clock_timestamp() WHERE id='+literal(target['id'])+';')
        self.assertFalse(self.engine.apply(operation)['erased'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.transport_attempt_events WHERE id='+literal(target['id'])+';'),'1')
