"""Real read-only snapshot, concurrent write, age export and offline PG restore."""
from datetime import datetime,timezone
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
import psycopg
from appointment_system.backup.database import export_connection,validate_archive,migration_hashes,IsolatedPostgres
from appointment_system.backup.snapshot import capture
from appointment_system.backup.protocol import Identity,BackupError
from appointment_system.backup.age_stream import hashed
from .test_sql_booking import BookingFixture
from .sql_store import IsolatedStore
from appointment_system.google_records import sheet_values
from appointment_system.sheet_projection import values_for
from appointment_system.serialization import fingerprint
from appointment_system.company_auth import password_hash
from . import test_backup_protocol as backup_tests
from tools.checks.sql_target import literal
from tools.conversion import verification
from .test_mail_contracts import document
from appointment_system.email_configuration import connection as mail_connection
from .test_sql_receipt_copy import ReceiptCopySQL

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET') and os.environ.get('BOOKING_AGE_BINARY'),
    'Owned native PostgreSQL socket and pinned native age tool are both required.')
class BackupSQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        BookingFixture.setUpClass.__func__(cls);backup_tests.NativeAge.setUpClass.__func__(cls)

    def setUp(self):
        super().setUp()
        self.db.scalar("SELECT appointment_system.provision_login('abs_backup','backup');")
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'a'*64+"');")
        self.ledger=migration_hashes(Path(__file__).resolve().parents[1]/'engine/appointment_system/migrations')
        self.tables=json.loads((Path(__file__).resolve().parents[1]/'database/relations.json').read_text())
        actual=self.db.value("SELECT jsonb_agg(n.nspname||'.'||c.relname ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='appointment_system' AND c.relkind IN ('r','p') AND NOT c.relispartition;")
        self.assertEqual(sorted(self.tables),actual,'The shipped backup allowlist must include every installed relation.')
        row=self.db.value("SELECT jsonb_build_object('installation',installation_id,'project',project_id,'environment',environment) FROM appointment_system.installation WHERE singleton;")
        self.scope=Identity(row['installation'],row['project'],row['environment'],'practice@example.test','a'*64)
        self.socket=self.db.native_socket()

    def connection(self):return psycopg.connect(host=self.socket,dbname='postgres',user='abs_backup')

    def dump(self,snapshot):
        self.assertIn(snapshot['postgres_major'],(16,18))
        return subprocess.Popen(['docker','exec','--user','postgres',self.db.name,'pg_dump','-U','abs_backup','-d','postgres',
            '--format=custom','--schema=appointment_system','--no-owner','--no-privileges','--snapshot='+snapshot['snapshot']],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)

    def test_native_snapshot_remains_consistent_during_write_and_restores_exactly(self):
        self.db.sql('TRUNCATE appointment_system.company_password_recoveries;')
        self.addCleanup(self.db.sql,'TRUNCATE appointment_system.company_password_recoveries;')
        with psycopg.connect(host=self.socket,dbname='postgres',user='postgres',autocommit=True) as native:
            subject=native.execute('SELECT appointment_system.provision_company_password(%s,%s)',
                ('backup.proof',password_hash('Synthetic recovery snapshot credential'))).fetchone()[0]
            revision=native.execute('SELECT credential_revision FROM appointment_system.company_credentials WHERE subject=%s',(subject,)).fetchone()[0]
            native.execute('SELECT appointment_system.provision_company_password(%s,%s)',
                ('backup.proof',password_hash('Synthetic recovered snapshot credential')))
            native.execute('INSERT INTO appointment_system.company_password_recoveries(operation_id,subject,previous_revision,resulting_revision,operator_role,reason,body_hash) VALUES(%s,%s,%s,%s,session_user,%s,%s)',
                (str(uuid4()),subject,revision,revision+1,'Synthetic snapshot recovery evidence','a'*64))
        self.db.sql('TRUNCATE appointment_system.conversion_retained_enquiries,appointment_system.conversion_handover CASCADE;')
        retained=str(uuid4());handover=str(uuid4())
        self.addCleanup(self.db.sql,'TRUNCATE appointment_system.conversion_retained_enquiries,appointment_system.conversion_handover CASCADE;'
            'DELETE FROM appointment_system.enquiries WHERE request_id='+literal(retained)+';')
        self.db.sql('INSERT INTO appointment_system.enquiries(request_id,email_key,receipt_digest,request_fingerprint,payload,code_expires_at,resend_after) VALUES ('+
            literal(retained)+','+literal('a'*64)+','+literal('b'*64)+','+literal('c'*64)+",'{}',clock_timestamp(),clock_timestamp());")
        with psycopg.connect(host=self.socket,dbname='postgres',user='postgres',autocommit=True) as native:
            row=native.execute('SELECT to_jsonb(e) FROM appointment_system.enquiries e WHERE request_id=%s',(retained,)).fetchone()[0]
            manifest=verification.capture(native,{'enquiries':[row]});verified=verification.verify(native,manifest)
        self.db.sql('INSERT INTO appointment_system.conversion_handover(id,installation_id,source_layout,source_digest,phase,writer_roles,provider_accounts,source_counts,release_digest,completed_at,verification_manifest,verified_target_digest) SELECT '+
            literal(handover)+",installation_id,'legacy-004-31',"+literal('d'*64)+",'complete',ARRAY['synthetic_retired'],'[]','{}',"+
            literal('e'*64)+',clock_timestamp(),'+literal(manifest)+'::jsonb,'+literal(verified)+
            ' FROM appointment_system.installation WHERE singleton;')
        self.db.sql('INSERT INTO appointment_system.conversion_retained_enquiries VALUES ('+literal(handover)+','+
            literal(retained)+",'synthetic_retired',"+literal('f'*64)+",'{}');")
        booking=self.booking(email=None,normalization_version=3);self.assertEqual(self.start_order(booking),'t');self.assertEqual(self.record_order(booking),'ready')
        self.assertEqual(self.capture(booking),'confirmed')
        declared=mail_connection(json.dumps(document()))
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal({
            'account_id':declared.account_id,'active_key_id':declared.active_key_id,
            'retained_keys':list(declared.keys),'legacy_identities':document()['legacy_identities']})+'::jsonb,20,600);')
        accepted=ReceiptCopySQL.copy(self,booking)
        self.assertEqual(accepted['code'],'receipt_copy_accepted')
        ReceiptCopySQL.history(self,booking,age=120,state='suppressed')
        copy_query="SELECT jsonb_agg(to_jsonb(j) ORDER BY id) FROM appointment_system.delivery_jobs j WHERE kind='booking_receipt';"
        expected_copies=self.db.value(copy_query)
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_workbook_volumes CASCADE;'
            "UPDATE appointment_system.sheet_projection_turns SET last_was_current=false;"
            "INSERT INTO appointment_system.google_workbooks(role,subject,client_id,spreadsheet_id,state,connection_revision,layout_version) "
            "VALUES('client','synthetic-subject','synthetic-client','synthetic_sheet','ready',1,4);")
        self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        worker=IsolatedStore(self.db,'abs_worker');job=worker.claim_google_delivery('client_sheet')
        self.assertIsNotNone(worker.assign_sheet_row('client',job,sheet_values(job,4)))
        current=worker.claim_sheet_projection('booking','client');values=values_for(current)
        self.assertEqual(worker.approve_sheet_projection(current,values,fingerprint(values),None),'ok')
        self.db.sql('INSERT INTO appointment_system.company_sheet_reviews(operation_id,role,record_kind,record_id,sequence,actor,reason) VALUES ('+
            literal(str(uuid4()))+",'client','booking',"+literal(booking['booking'])+","+literal(current['sequence'])+
            ",'company:synthetic','Synthetic backup review');")
        operation=str(uuid4())
        self.db.sql('INSERT INTO appointment_system.historical_staff_operations VALUES('+literal(operation)+','+
            literal(booking['booking'])+",'receipt_recovery','client:synthetic',"+literal('e'*64)+",1,1,'{}'::jsonb,clock_timestamp());")
        self.db.sql('INSERT INTO appointment_system.historical_staff_appointment_history VALUES('+literal(operation)+
            ",clock_timestamp(),clock_timestamp(),86400,false,'Synthetic retained history');")
        challenge=str(uuid4());provider=str(uuid4());event='evt_backup_'+uuid4().hex
        self.db.sql('INSERT INTO appointment_system.historical_verification_receipts VALUES('+literal(challenge)+','+
            literal(provider)+",'synthetic-team','contact',clock_timestamp());")
        self.db.sql('INSERT INTO appointment_system.historical_email_observations VALUES('+literal(event)+','+
            literal(provider)+",'synthetic-team','verification',"+literal(challenge)+",'email.delivered',clock_timestamp(),clock_timestamp());")
        self.addCleanup(self.db.sql,'DELETE FROM appointment_system.historical_verification_receipts WHERE challenge_id='+literal(challenge)+';')
        self.addCleanup(self.db.sql,'DELETE FROM appointment_system.historical_email_observations WHERE event_id='+literal(event)+';')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive.age'
            def concurrent_dump(snapshot):
                self.db.scalar("SELECT appointment_system.consume_request_limit('availability','"+'d'*64+"');",role='appointment_system_web')
                self.assertGreater(int(self.db.scalar('SELECT count(*) FROM appointment_system.request_limits;')),snapshot['table_counts']['appointment_system.request_limits'])
                return self.dump(snapshot)
            with self.connection() as connection:
                with connection.transaction():
                    facts=export_connection(connection,self.scope,self.ledger,self.tables,path,self.recipient,self.binary,dump_factory=concurrent_dump)
            self.assertGreaterEqual(facts['table_counts']['appointment_system.historical_verification_receipts'],1)
            self.assertGreaterEqual(facts['table_counts']['appointment_system.historical_email_observations'],1)
            self.assertEqual(facts['table_counts']['appointment_system.conversion_retained_enquiries'],1)
            self.assertEqual(facts['table_counts']['appointment_system.historical_staff_operations'],1)
            self.assertEqual(facts['table_counts']['appointment_system.historical_staff_appointment_history'],1)
            self.assertEqual(facts['table_counts']['appointment_system.sheet_current_records'],1)
            self.assertEqual(facts['table_counts']['appointment_system.sheet_current_digests'],1)
            self.assertEqual(facts['table_counts']['appointment_system.company_sheet_reviews'],1)
            self.assertEqual(facts['table_counts']['appointment_system.company_password_recoveries'],1)
            self.assertEqual(facts['table_counts']['appointment_system.sheet_projection_turns'],4)
            sha,size=hashed(path)
            manifest=dict(version=1,purpose='database-export',**self.scope.fields(),source_commit='b'*40,source_run='12345',source_attempt='1',
                archive_name='appointment-'+self.scope.installation_id+'-12345-1.dump.age',archive_sha256=sha,archive_bytes=size,
                created_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),schemas=['appointment_system'],database_contract=1,
                **{key:value for key,value in facts.items() if key!='snapshot'})
            restored_facts=[];original_query=IsolatedPostgres.query
            def query_with_copy_proof(target,query):
                result=original_query(target,query)
                if 'jsonb_object_agg(version,sha256)' in query:
                    self.assertEqual(original_query(target,'SELECT count(*) FROM appointment_system.bookings WHERE email IS NULL;'),'1')
                    self.assertEqual(json.loads(original_query(target,copy_query)),expected_copies)
                    restored_facts.append(True)
                return result
            with patch.object(IsolatedPostgres,'query',query_with_copy_proof):
                proof=validate_archive(path,self.scope,manifest,self.identity,self.binary,self.ledger)
            self.assertEqual(restored_facts,[True],'The independent restored database must preserve NULL contacts and both queued and settled immutable copy rows.')
            self.assertEqual(proof['migration_count'],len(self.ledger));self.assertEqual(proof['restored_authority'],'off_new_generation')
            self.assertEqual(len(proof['invariants_digest']),64)

    def test_backup_login_is_readonly_and_release_and_relation_allowlist_are_checked(self):
        with self.connection() as connection:
            with connection.transaction():
                saved=capture(connection,self.scope,self.ledger,self.tables)
                self.assertEqual(saved['migrations'],self.ledger)
                with self.assertRaises(psycopg.Error):connection.execute("UPDATE appointment_system.intake_settings SET public_open=false;")
        wrong=Identity(self.scope.installation_id,self.scope.project,self.scope.environment,self.scope.owner_email,'b'*64)
        with self.assertRaises(BackupError),self.connection() as connection:
            with connection.transaction():capture(connection,wrong,self.ledger,self.tables)
        self.db.sql('CREATE TABLE appointment_system.unreleased_table(id integer);')
        try:
            with self.assertRaises(BackupError),self.connection() as connection:
                with connection.transaction():capture(connection,self.scope,self.ledger,self.tables)
        finally:self.db.sql('DROP TABLE appointment_system.unreleased_table;')
