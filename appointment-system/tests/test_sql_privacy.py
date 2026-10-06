"""Actual limited maintenance login, erasure/replay and OFF-only publication."""
import os
import unittest
from datetime import datetime,timezone
from uuid import uuid4
import psycopg
from psycopg.pq import TransactionStatus
from appointment_system.configuration import installation
from appointment_system.privacy_retention import PrivacyDatabase
from appointment_system.control_recovery import RecoveryDatabase
from appointment_system.service_control import ControlError
from appointment_system.privacy.engine import Retention
from appointment_system.privacy.ledger import Ledger,digest
from . import test_sql_restore as restore_fixture
from . import test_privacy_ledger as fixture
from tools.checks.sql_target import literal

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned native PostgreSQL required.')
class PrivacySQL(restore_fixture.RestoreSQL):
    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.control_privacy_policy_approvals CASCADE; TRUNCATE appointment_system.control_privacy_intents CASCADE; TRUNCATE appointment_system.operational_incidents;')
        self.db.scalar("SELECT appointment_system.provision_login('abs_staff','staff');")
        self.connection=psycopg.connect(host=self.db.native_socket(),dbname='postgres',user='abs_maintenance',autocommit=True)
        self.maintenance=PrivacyDatabase(self.connection)
        self.keys=fixture.synthetic_keys();self.store=fixture.MemoryStore(self.keys)
        native=self.connection
        for name in ('read_head','read_entry','create_entry','compare_and_swap_head'):
            original=getattr(self.store,name)
            def outside(*args,_original=original,**kwargs):
                self.assertEqual(native.info.transaction_status,TransactionStatus.IDLE,'Provider call cannot keep a SQL transaction open')
                return _original(*args,**kwargs)
            setattr(self.store,name,outside)
        self.ledger=Ledger(self.store,self.keys);self.engine=Retention(self.maintenance,self.ledger)
    def tearDown(self):
        if hasattr(self,'connection'):self.connection.close()
        super().tearDown()
    def old_incident(self):
        reference=str(uuid4())
        self.db.scalar("SELECT appointment_system.record_operation_incident("+literal(reference)+",'booking','request','unexpected_failure',1);",role='appointment_system_web')
        self.assertEqual(self.db.scalar('SELECT project FROM appointment_system.operational_incidents;'),installation()['project_id'])
        self.db.sql("UPDATE appointment_system.operational_incidents SET first_seen_at=clock_timestamp()-interval '35 days',last_seen_at=clock_timestamp()-interval '35 days';")
        return self.maintenance.inspect('routine-incidents-v1')['targets'][0]
    def approve(self):
        self.db.sql("INSERT INTO appointment_system.control_privacy_policy_approvals(policy_id,approved_by) VALUES('routine-incidents-v1','Synthetic owner approval');")
    def test_maintenance_is_registered_and_serving_logins_have_no_privacy_authority(self):
        result=self.maintenance.inspect('routine-incidents-v1')
        self.assertEqual(result['project'],installation()['project_id']);self.assertEqual(result['environment'],installation()['environment']);self.assertFalse(result['approved'])
        for role in ('appointment_system_web','abs_staff','abs_worker','abs_company'):
            with self.assertRaises(AssertionError):self.db.sql("SELECT appointment_system.control_privacy_candidates('routine-incidents-v1');",role=role)
            with psycopg.connect(host=self.db.native_socket(),dbname='postgres',user=role,autocommit=True) as connection:
                with self.assertRaises(ControlError):PrivacyDatabase(connection)
        with self.assertRaises(AssertionError):self.db.sql('DELETE FROM appointment_system.operational_incidents;',role='abs_maintenance')
    def test_durable_signed_intent_required_then_exact_old_incident_erased_and_retry_is_safe(self):
        target=self.old_incident();operation=str(uuid4())
        with self.assertRaises(psycopg.Error):self.maintenance.record(operation,'routine-incidents-v1',target['id'],target['target_hash'],0)
        self.approve();self.engine.record_intent(operation,'routine-incidents-v1',target['id'],target['target_hash'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.operational_incidents;'),'1')
        result=self.engine.apply(operation);self.assertTrue(result['erased']);self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.operational_incidents;'),'0')
        self.assertTrue(self.engine.apply(operation)['erased']);self.assertEqual(self.ledger.head()[0]['sequence'],2)
    def test_new_incident_activity_changes_eligibility_without_erasing_or_breaking_intent_history(self):
        target=self.old_incident();operation=str(uuid4());self.approve()
        self.engine.record_intent(operation,'routine-incidents-v1',target['id'],target['target_hash'])
        self.db.sql('UPDATE appointment_system.operational_incidents SET last_seen_at=clock_timestamp();')
        self.assertFalse(self.engine.apply(operation)['erased']);self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.operational_incidents;'),'1')
        self.assertEqual([entry['phase'] for entry,_ in self.ledger.walk(self.ledger.head()[0])],['cancelled','intent'])
    def test_restore_confirmation_needs_current_complete_privacy_replay_and_stays_off(self):
        result=self.restore();generation=result['snapshot']['restore_generation']
        with self.assertRaisesRegex(AssertionError,'isolated recovery completion required'):
            self.db.sql('SELECT appointment_system.api_enquiry_protection(gen_random_uuid());',role='appointment_system_web')
        with self.assertRaises(AssertionError):self.db.sql("SELECT appointment_system.record_operation_incident(gen_random_uuid(),'booking','request','unexpected_failure',1);",role='abs_worker')
        with self.assertRaises(psycopg.Error):self.maintenance.confirm(self.operation,result['snapshot'],{'sequence':0,'head_hash':'a'*64})
        proof=self.engine.replay(self.operation,generation)
        self.assertEqual(proof['project'],installation()['project_id']);self.assertEqual(proof['environment'],installation()['environment'])
        done=self.maintenance.confirm(self.operation,result['snapshot'],proof);self.assertTrue(done['verified']);self.assertTrue(self.maintenance.confirm(self.operation,result['snapshot'],proof)['replayed'])
        self.assertFalse(self.maintenance.current()['enabled'])
        self.assertIsNone(self.db.value('SELECT appointment_system.api_enquiry_protection(gen_random_uuid());',role='appointment_system_web'))
        with self.assertRaisesRegex(AssertionError,'booking disabled'):
            self.db.sql('SELECT appointment_system.public_policy();',role='appointment_system_web')
    def test_restoring_an_older_copy_replays_independent_erasure_before_completion(self):
        target=self.old_incident();old=self.db.value('SELECT to_jsonb(i) FROM appointment_system.operational_incidents i;')
        operation=str(uuid4());self.approve();self.engine.record_intent(operation,'routine-incidents-v1',target['id'],target['target_hash']);self.engine.apply(operation)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.operational_incidents;'),'0')
        # The owned isolated target simulates the older snapshot, while the
        # authenticated independent store retains the latest terminal history.
        self.db.sql('TRUNCATE appointment_system.control_privacy_intents CASCADE;')
        self.db.sql('INSERT INTO appointment_system.operational_incidents SELECT * FROM jsonb_populate_record(NULL::appointment_system.operational_incidents,'+literal(old)+'::jsonb);')
        result=self.restore();proof=self.engine.replay(self.operation,result['snapshot']['restore_generation'])
        self.assertEqual(proof['sequence'],2);self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.operational_incidents;'),'0')
        self.assertTrue(self.maintenance.confirm(self.operation,result['snapshot'],proof)['verified'])
    def test_restore_publication_can_only_publish_the_exact_current_off_generation(self):
        with self.assertRaises(psycopg.Error):self.maintenance.claim_publication()
        result=self.restore();job=self.maintenance.claim_publication();self.assertEqual(job['operation_id'],self.operation)
        with self.assertRaises(psycopg.Error):self.maintenance.finish_publication(dict(job,operation_id=str(uuid4())),result['snapshot'],None)
        self.assertTrue(self.maintenance.finish_publication(job,result['snapshot'],None))
        claimed=self.maintenance.claim_probe();self.assertEqual(claimed['snapshot'],result['snapshot']);self.assertTrue(self.maintenance.record_probe(claimed,result['snapshot']))
        self.assertFalse(self.maintenance.current()['enabled'])

    def test_complete_restore_resumes_lost_authority_reply_using_saved_sql_and_privacy_replay(self):
        import hashlib
        import httpx
        from appointment_system.control_recovery import RecoverySettings,RestoreReconciliation
        from appointment_system.configuration import worker_origin
        from appointment_system.projection import signature
        from appointment_system.serialization import canonical,decode
        from .test_projection import NOW
        keys=RecoverySettings(b'R'*32,b'C'*32,b'P'*32,worker_origin())
        remote=dict(self.external);lost=False;events=[]
        def provider(request):
            nonlocal remote,lost
            self.assertEqual(self.connection.info.transaction_status,TransactionStatus.IDLE)
            facts=installation();nonce=None;operation=None;pending=False
            if request.method=='GET':
                self.assertIn(str(request.url),(worker_origin()+'/service-state',facts['origin']+'/api/service-state/probe'))
                purpose='read';secret=keys.read_key;nonce=request.headers['X-Booking-State-Nonce']
            else:
                body=decode(request.content);purpose=body['purpose'];self.assertIn(purpose,('reconcile','publish'))
                secret=keys.reconcile_key if purpose=='reconcile' else keys.publish_key
                self.assertEqual(request.headers['X-Booking-Control-Signature'],signature(secret,purpose,body))
                self.assertEqual(str(request.url),worker_origin()+'/service-control/'+purpose)
                self.assertFalse(body['snapshot']['enabled']);remote=body['snapshot'];operation=body['operation_id']
                events.append(purpose)
                if purpose=='reconcile':
                    self.assertEqual(body['expected_generation'],self.external['restore_generation']);pending=True
                    if not lost:lost=True;raise httpx.ReadTimeout('Synthetic lost reply after accepted barrier')
                purpose+='-ack'
            value=dict(version=1,installation_id=facts['installation_id'],project=facts['project_id'],environment=facts['environment'],
                purpose=purpose,operation_id=operation,issued_at_ms=NOW,published_at_ms=NOW,snapshot=remote,
                snapshot_hash=hashlib.sha256(canonical(remote)).hexdigest(),reconcile_pending=pending)
            if nonce is not None:value['nonce']=nonce
            return httpx.Response(200,json=value|{'signature':signature(secret,purpose,value)})
        database=RecoveryDatabase(self.connection)
        restore=RestoreReconciliation(database,keys,self.engine.replay,transport=httpx.MockTransport(provider),clock=lambda:NOW)
        with self.assertRaisesRegex(ControlError,'restore_external_state_unavailable'):restore.run(self.operation)
        saved=database.saved(self.operation);self.assertEqual(saved['operation_id'],self.operation)
        self.assertFalse(saved['snapshot']['enabled']);self.assertEqual(remote['revision'],'0')
        with self.assertRaisesRegex(AssertionError,'isolated recovery completion required'):
            self.db.sql('SELECT appointment_system.api_enquiry_protection(gen_random_uuid());',role='appointment_system_web')
        self.assertEqual(restore.run(self.operation),{'operation_id':self.operation,'verified':True,'enabled':False})
        self.assertEqual(database.current(),saved['snapshot']);self.assertEqual(remote,saved['snapshot'])
        self.assertEqual(events,['reconcile','reconcile','publish'])
        self.assertIsNone(self.db.value('SELECT appointment_system.api_enquiry_protection(gen_random_uuid());',role='appointment_system_web'))
        with self.assertRaisesRegex(AssertionError,'booking disabled'):
            self.db.sql('SELECT appointment_system.public_policy();',role='appointment_system_web')

if __name__=='__main__':unittest.main()
