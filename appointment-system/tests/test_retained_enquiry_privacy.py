"""Actual retired source, narrow maintenance role and independent privacy replay."""
import os
import unittest
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from appointment_system.privacy_retention import PrivacyDatabase
from appointment_system.privacy.engine import Retention
from appointment_system.privacy.ledger import Ledger
from tools.checks.sql_target import SQLTarget
from . import test_native_sarsa_handover as native
from . import test_privacy_ledger as privacy


@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET')=='abs-implementation-pg18',
                    'Owned PG18 historical target required.')
class RetainedEnquiryPrivacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target=SQLTarget('abs-implementation-pg18');cls.target.check_owned()

    def setUp(self):
        native.NativeSarsaHandover.setUp(self)
        self.request=str(uuid4());self.job=str(uuid4())
        self.connection.execute('''INSERT INTO sarsa_booking.enquiries
            (request_id,email_key,receipt_digest,request_fingerprint,payload,code_digest,code_ciphertext,
             code_expires_at,resend_after,created_at,receipt_expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp()-interval '9 days',
             clock_timestamp()-interval '10 days',clock_timestamp()-interval '10 days',clock_timestamp()-interval '9 days')''',
            (self.request,'a'*64,'b'*64,'c'*64,Jsonb({'name':'Synthetic enquiry','email':'fixture@example.test',
              'message':'Private synthetic question'}),'d'*64,'e'*120))
        self.connection.execute('''INSERT INTO sarsa_booking.enquiry_delivery_jobs
            (id,request_id,kind,generation,state,deadline_at,destination,message_ciphertext,message_digest,first_attempt_at)
            VALUES(%s,%s,'verification',1,'done',clock_timestamp()-interval '9 days',
             'fixture@example.test',%s,%s,clock_timestamp()-interval '10 days')''',
             (self.job,self.request,'f'*120,'a'*64))
        self.original=self.rows()
        identifier=native.NativeSarsaHandover.start(self)
        result=self.handover.convert(identifier)
        self.handover.complete(identifier,result['target_digest'])
        self.maintenance_connection=psycopg.connect(host=self.socket,dbname=self.database,
            user='abs_maintenance',autocommit=True)
        self.addCleanup(self.maintenance_connection.close)
        self.database_api=PrivacyDatabase(self.maintenance_connection)
        keys=privacy.synthetic_keys();self.store=privacy.MemoryStore(keys)
        self.ledger=Ledger(self.store,keys);self.engine=Retention(self.database_api,self.ledger)

    def rows(self):
        return tuple(self.connection.execute(sql.SQL('SELECT to_jsonb(t) FROM sarsa_booking.{} t WHERE {}=%s').format(
            sql.Identifier(table),sql.Identifier(key)),(value,)).fetchone()[0]
            for table,key,value in [('enquiries','request_id',self.request),('enquiry_delivery_jobs','id',self.job)])

    def intent(self):
        self.connection.execute("INSERT INTO appointment_system.control_privacy_policy_approvals(policy_id,approved_by) "
            "VALUES('abandoned-enquiry-v1','Synthetic approved retention') ON CONFLICT DO NOTHING")
        target=next(row for row in self.engine.inspect('abandoned-enquiry-v1')['targets'] if row['id']==self.request)
        operation=str(uuid4());self.engine.record_intent(operation,'abandoned-enquiry-v1',self.request,target['target_hash'])
        return operation

    def assert_erased(self):
        enquiry,job=self.rows()
        self.assertEqual(enquiry['payload'],{});self.assertIsNone(enquiry['code_digest']);self.assertIsNone(enquiry['code_ciphertext'])
        self.assertIsNone(job['destination']);self.assertIsNone(job['message_ciphertext']);self.assertEqual(job['state'],'expired')
        for actual,old,erased in [(enquiry,self.original[0],{'payload','code_digest','code_ciphertext'}),
                                 (job,self.original[1],{'destination','message_ciphertext','state','lease_token','lease_expires_at'})]:
            self.assertEqual({k:v for k,v in actual.items() if k not in erased},{k:v for k,v in old.items() if k not in erased})
        self.assertEqual(self.connection.execute('SELECT payload,code_digest,code_ciphertext FROM appointment_system.enquiries WHERE request_id=%s',
            (self.request,)).fetchone(),({},None,None))
        self.assertEqual(self.connection.execute('SELECT state,amount_paise FROM appointment_system.bookings WHERE id=%s',
            (self.book,)).fetchone(),('confirmed',210000))

    def test_approved_erasure_clears_both_copies_keeps_evidence_and_is_repeatable(self):
        operation=self.intent();self.assertEqual(self.rows(),self.original)
        # The database's default timezone must not change the frozen comparison.
        self.maintenance_connection.execute("SET TimeZone='Asia/Kolkata'")
        self.assertTrue(self.engine.apply(operation)['erased']);self.assert_erased()
        self.assertTrue(self.engine.apply(operation)['erased']);self.assert_erased()
        self.assertEqual(self.ledger.head()[0]['sequence'],2)

    def test_retired_writer_and_maintenance_cannot_change_or_delete_source_directly(self):
        for role in ('sarsa_booking_web','abs_maintenance','appointment_system_web','abs_company'):
            with psycopg.connect(host=self.socket,dbname=self.database,user=role,autocommit=True) as connection:
                for query in ("UPDATE sarsa_booking.enquiries SET payload='{}'",'DELETE FROM sarsa_booking.enquiries',
                              'DELETE FROM appointment_system.conversion_retained_enquiries'):
                    with self.subTest(role=role,query=query),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        connection.execute(query)
        with self.connection.transaction():
            self.connection.execute('SET LOCAL ROLE appointment_system_owner')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.connection.execute("UPDATE sarsa_booking.enquiries SET payload='{}'")
        self.assertEqual(self.rows(),self.original)

    def test_changed_retained_copy_rolls_back_canonical_erase_and_completion(self):
        operation=self.intent()
        # Fault injection by the isolated database administrator represents a
        # damaged retained copy; no serving or maintenance role has this power.
        with self.connection.transaction():
            self.connection.execute('ALTER TABLE sarsa_booking.enquiry_delivery_jobs DISABLE TRIGGER retained_source_guard')
            self.connection.execute('UPDATE sarsa_booking.enquiry_delivery_jobs SET attempts=attempts+1 WHERE id=%s',(self.job,))
            self.connection.execute('ALTER TABLE sarsa_booking.enquiry_delivery_jobs ENABLE TRIGGER retained_source_guard')
        with self.assertRaisesRegex(psycopg.Error,'retained source changed'):self.engine.apply(operation)
        self.assertEqual(self.connection.execute('SELECT payload FROM appointment_system.enquiries WHERE request_id=%s',
            (self.request,)).fetchone()[0],self.original[0]['payload'])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.control_privacy_completions').fetchone()[0],0)
        self.assertEqual(self.ledger.head()[0]['sequence'],1)

    def test_completion_does_not_permit_rewriting_retained_identity_or_recreating_content(self):
        operation=self.intent();self.engine.apply(operation)
        for query in ("UPDATE sarsa_booking.enquiries SET payload='{\"message\":\"recreated\"}'",
                      "UPDATE sarsa_booking.enquiries SET email_key=repeat('f',64)",
                      "UPDATE sarsa_booking.enquiry_delivery_jobs SET provider_id='changed'",
                      "UPDATE sarsa_booking.enquiry_delivery_jobs SET destination='someone@example.test'",
                      "DELETE FROM sarsa_booking.enquiries"):
            with self.subTest(query=query),self.assertRaises(psycopg.Error),self.connection.transaction():
                self.connection.execute('SET LOCAL ROLE appointment_system_owner')
                self.connection.execute(query)
        self.assert_erased()

    def test_new_canonical_activity_cancels_erasure_and_keeps_both_copies(self):
        operation=self.intent()
        self.connection.execute('UPDATE appointment_system.enquiries SET verified_at=clock_timestamp() WHERE request_id=%s',
            (self.request,))
        self.assertFalse(self.engine.apply(operation)['erased']);self.assertEqual(self.rows(),self.original)
        self.assertEqual(self.connection.execute('SELECT payload FROM appointment_system.enquiries WHERE request_id=%s',
            (self.request,)).fetchone()[0],self.original[0]['payload'])

    def test_independent_replay_erases_restored_old_personal_data_before_release(self):
        operation=self.intent()
        saved=self.connection.execute('SELECT to_jsonb(e) FROM appointment_system.enquiries e WHERE request_id=%s',(self.request,)).fetchone()[0]
        self.engine.apply(operation)
        # Recreate exactly the earlier synthetic snapshot while retaining the
        # independent signed outcome. This is test-only administrator authority.
        self.connection.execute('TRUNCATE appointment_system.control_privacy_intents CASCADE')
        for schema,table,old,key in [('sarsa_booking','enquiries',self.original[0],'request_id'),
                                     ('sarsa_booking','enquiry_delivery_jobs',self.original[1],'id'),
                                     ('appointment_system','enquiries',saved,'request_id')]:
            relation=sql.Identifier(schema,table)
            with self.connection.transaction():
                self.connection.execute(sql.SQL('ALTER TABLE {} DISABLE TRIGGER USER').format(relation))
                fields=[name for name in old if name!=key]
                query=sql.SQL('UPDATE {} t SET ({})=(SELECT {} FROM jsonb_populate_record(NULL::{},%s)) WHERE {}=%s').format(
                    relation,sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(map(sql.Identifier,fields)),
                    relation,sql.Identifier(key))
                self.connection.execute(query,(Jsonb(old),old[key]))
                self.connection.execute(sql.SQL('ALTER TABLE {} ENABLE TRIGGER USER').format(relation))
        restore=str(uuid4());barrier=self.database_api.barrier(restore,self.database_api.current())
        proof=self.engine.replay(restore,barrier['snapshot']['restore_generation'])
        self.assertEqual(proof['sequence'],2);self.assert_erased()
        self.assertFalse(self.database_api.current()['enabled'])

    def test_canonical_only_archive_needs_no_obsolete_source_and_partial_source_is_rejected(self):
        operation=self.intent()
        self.connection.execute('ALTER TABLE sarsa_booking.enquiry_delivery_jobs RENAME TO isolated_hidden_jobs')
        with self.assertRaisesRegex(psycopg.Error,'retained source incomplete'):self.engine.apply(operation)
        self.connection.execute('ALTER TABLE sarsa_booking.enquiries RENAME TO isolated_hidden_enquiries')
        with self.assertRaisesRegex(psycopg.Error,'absence requires restored generation'):self.engine.apply(operation)
        self.database_api.barrier(str(uuid4()),self.database_api.current())
        self.assertTrue(self.engine.apply(operation)['erased'])
        self.assertEqual(self.connection.execute('SELECT payload FROM appointment_system.enquiries WHERE request_id=%s',
            (self.request,)).fetchone()[0],{})
