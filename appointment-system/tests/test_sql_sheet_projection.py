"""Current rows on a fresh owned database, including draft migration review.

Uses only the two disconnected proof containers. Never selects a customer DSN.
"""
import os
from unittest.mock import patch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
from psycopg import sql

from tools.checks.sql_target import SQLTarget, command, literal
from appointment_system.google_records import sheet_values
from appointment_system.sheet_projection import values_for
from appointment_system.serialization import fingerprint
from appointment_system.settings import BusinessSettings
from .fixtures import installation, business
from .test_sql_booking import BookingFixture
from .sql_store import IsolatedStore


class ProjectionTarget(SQLTarget):
    def sql(self, statement, *, role='postgres', check=True):
        if role not in ('postgres','appointment_system_web','abs_worker','abs_staff','abs_company','abs_backup'):
            raise ValueError('Invalid proof role')
        result=command(['exec','-i','--user','postgres',self.name,'psql','-X','-U',role,
            '-d',self.database,'-v','ON_ERROR_STOP=1','-Atq'],body=statement)
        if result.returncode and check:raise AssertionError(result.stderr[:1600])
        return result


class CurrentSheetSQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        cls.db=ProjectionTarget(os.environ['BOOKING_SQL_TEST_TARGET']);cls.db.check_owned()
        cls.db.database='abs_projection_'+uuid4().hex[:12]
        with psycopg.connect(host=cls.db.native_socket(),dbname='postgres',user='postgres',autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.db.database)))
        def cleanup():
            with psycopg.connect(host=cls.db.native_socket(),dbname='postgres',user='postgres',autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(cls.db.database)))
        cls.addClassCleanup(cleanup)
        root=Path(__file__).resolve().parents[1]
        for path in sorted((root/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql')):
            cls.db.sql('BEGIN;'+path.read_text()+'COMMIT;')
        profile=installation()
        for target in profile['database_targets'].values():target['database']=cls.db.database
        cls.db.value('SELECT appointment_system.configure_installation('+literal(profile)+'::jsonb,'+
            literal(BusinessSettings.parse(business()).document)+'::jsonb,true);')
        for role,purpose in [('appointment_system_web','web'),('abs_worker','worker'),('abs_staff','staff')]:
            cls.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_workbook_volumes CASCADE;'
            'TRUNCATE appointment_system.enquiries CASCADE;'
            'UPDATE appointment_system.sheet_projection_turns SET last_was_current=false;')
        self.worker=IsolatedStore(self.db,'abs_worker')
        self.db.sql("INSERT INTO appointment_system.google_workbooks(role,subject,client_id,spreadsheet_id,state,connection_revision,layout_version) "
            "VALUES('client','synthetic-subject','synthetic-client','synthetic_sheet','ready',1,3);")

    def mapped(self,layout=3):
        if layout!=3:
            self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_workbook_volumes CASCADE;'
                "INSERT INTO appointment_system.google_workbooks(role,subject,client_id,spreadsheet_id,state,connection_revision,layout_version) "
                "VALUES('client','synthetic-subject','synthetic-client','synthetic_sheet','ready',1,"+str(layout)+');')
        booking=self.booking()
        self.assertEqual(self.start_order(booking),'t');self.assertEqual(self.record_order(booking),'ready')
        self.assertEqual(self.capture(booking),'confirmed')
        job=self.worker.claim_google_delivery('client_sheet')
        self.assertIsNotNone(job)
        assigned=self.worker.assign_sheet_row('client',job,sheet_values(job,layout))
        self.assertIsNotNone(assigned)
        return booking,job,assigned

    def claim(self):return self.worker.claim_sheet_projection('booking','client')

    def approve(self,job,observed=None):
        values=values_for(job);digest=fingerprint(values)
        return self.worker.approve_sheet_projection(job,values,digest,observed),digest

    def make_due(self):
        self.db.sql("UPDATE appointment_system.sheet_current_records SET due_at=clock_timestamp()-interval '1 second';")

    def test_first_history_address_maps_one_current_row_and_finished_work_stays_scheduled(self):
        booking,history,address=self.mapped();job=self.claim()
        self.assertEqual(job['row_number'],address['row'])
        self.assertEqual(job['snapshot']['id'],booking['booking'])
        self.assertEqual(job['snapshot']['revision'],1)
        result,digest=self.approve(job);self.assertEqual(result,'ok')
        self.assertTrue(self.worker.finish_sheet_projection(job,digest,None,False))
        self.assertIsNone(self.claim())
        due=self.db.value("SELECT jsonb_build_object('later',due_at>clock_timestamp()+interval '23 hours','seen',verified_at IS NOT NULL) FROM appointment_system.sheet_current_records;")
        self.assertEqual(due,{'later':True,'seen':True})
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.recovery_due_work WHERE lane='booking_records' AND resource='client_sheet';"),'2')

    def test_new_revision_invalidates_old_write_permission_and_old_completion_cannot_clear_new_work(self):
        booking,_,_=self.mapped();old=self.claim();result,digest=self.approve(old);self.assertEqual(result,'ok')
        self.db.sql('UPDATE appointment_system.bookings SET revision=revision+1 WHERE id='+literal(booking['booking'])+';')
        self.assertEqual(self.approve(old)[0],'changed')
        self.assertTrue(self.worker.finish_sheet_projection(old,digest,None,False))
        new=self.claim();self.assertEqual(new['snapshot']['revision'],2)
        self.assertGreater(new['sequence'],old['sequence'])

    def test_known_old_remote_digest_is_repairable_but_unknown_rows_and_wrong_hash_are_refused(self):
        self.mapped();job=self.claim()
        result,digest=self.approve(job);self.assertEqual(result,'ok')
        self.assertTrue(self.worker.finish_sheet_projection(job,digest,None,False));self.make_due()
        next_job=self.claim()
        self.assertEqual(self.approve(next_job,digest)[0],'ok')
        self.assertEqual(self.approve(next_job,'b'*64)[0],'conflict')
        self.assertEqual(self.worker.approve_sheet_projection(next_job,values_for(next_job),'c'*64,None),'invalid')
        self.assertFalse(self.worker.finish_sheet_projection(next_job,'c'*64,None,False))

    def test_concurrent_claims_have_one_winner_and_history_gets_its_turn(self):
        self.mapped()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.claim(),range(2)))
        selected=[r for r in results if r is not None];self.assertEqual(len(selected),1)
        self.worker.finish_sheet_projection(selected[0],None,'google_service_unavailable',False)
        self.make_due()
        self.db.sql("UPDATE appointment_system.delivery_jobs SET state='pending',lease_token=NULL,lease_expires_at=NULL WHERE recipient_role='client_sheet';")
        self.assertIsNone(self.claim())
        self.assertIsNotNone(self.claim())

    def test_restore_release_expiry_and_other_accounts_cannot_borrow_a_claim(self):
        self.mapped();job=self.claim()
        for changed in (dict(job,role='agency'),dict(job,lease=str(uuid4())),dict(job,record_id=str(uuid4()))):
            self.assertEqual(self.approve(changed)[0],'changed')
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'b'*64+"');")
        self.assertEqual(self.approve(job)[0],'changed')
        self.assertFalse(self.worker.finish_sheet_projection(job,None,'google_service_unavailable',False))
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'a'*64+"');")
        self.db.sql("UPDATE appointment_system.sheet_current_records SET lease_until=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.approve(job)[0],'changed')
        self.assertIsNotNone(self.claim())

    def test_conflict_is_visible_without_deleting_history_or_sending_more_mail(self):
        _,_,_=self.mapped();before=self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs;')
        job=self.claim();self.assertTrue(self.worker.finish_sheet_projection(job,None,'google_row_conflict',True))
        self.assertIsNone(self.claim())
        self.assertEqual(self.db.scalar('SELECT appointment_system.recovery_attention();'),'t')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_rows;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs;'),before)

    def test_only_worker_can_claim_and_backups_can_only_read_the_new_relations(self):
        self.mapped()
        for role in ('appointment_system_web','abs_staff'):
            self.assertNotEqual(self.db.sql("SELECT appointment_system.claim_sheet_projection('booking','client');",role=role,check=False).returncode,0)
        for table in ('sheet_current_records','sheet_current_digests','sheet_projection_turns','company_sheet_reviews'):
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('appointment_system_web','appointment_system."+table+"','SELECT');"),'f')
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('appointment_system_backup_access','appointment_system."+table+"','SELECT');"),'t')
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('appointment_system_backup_access','appointment_system."+table+"','UPDATE');"),'f')

    def test_new_history_layout_stores_full_hash_and_maps_current_without_touching_legacy_format(self):
        booking,job,assigned=self.mapped(4)
        self.assertEqual(assigned['layout_version'],4)
        self.assertEqual(len(assigned['values']),36)
        self.assertEqual(assigned['values'][-1],fingerprint(assigned['values'][:-1]))
        current=self.claim();self.assertEqual(current['layout_version'],4)
        result,digest=self.approve(current);self.assertEqual(result,'ok')
        self.assertTrue(self.worker.finish_sheet_projection(current,digest,None,False))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_rows;'),'1')

    def test_new_history_cannot_allocate_a_bad_hash_or_a_second_current_record(self):
        booking,job,first=self.mapped(4)
        self.db.sql("INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key,payload) "
            "SELECT gen_random_uuid(),booking_id,kind,recipient_role,booking_revision,'meeting-ready',payload "
            'FROM appointment_system.delivery_jobs WHERE id='+literal(job['id'])+';')
        next_job=self.worker.claim_google_delivery('client_sheet');values=sheet_values(next_job,4)
        self.assertIsNone(self.worker.assign_sheet_row('client',next_job,values[:-1]+['a'*64]))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_rows;'),'1')
        second=self.worker.assign_sheet_row('client',next_job,values)
        self.assertNotEqual(first['row'],second['row'])
        current=self.claim();self.assertEqual(current['row_number'],first['row'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_current_records;'),'1')

    def test_enquiry_current_row_is_independent_of_booking_off_and_keeps_saved_context(self):
        from appointment_system.contact_records import enquiry_values
        reference=str(uuid4());payload=dict(name='Synthetic enquiry',email='person@example.invalid',phone='+919876543210',
            subject='Help',message='Please call.',source='services',service_interest='consultation',kind='contact',dob='',location='Delhi')
        self.db.sql("UPDATE appointment_system.control_product_state SET enabled=false;"
            'INSERT INTO appointment_system.enquiries(request_id,email_key,receipt_digest,request_fingerprint,payload,code_expires_at,resend_after,verified_at) VALUES ('+
            ','.join(literal(v) for v in (reference,'d'*64,'e'*64,'f'*64,payload))+"::jsonb,clock_timestamp(),clock_timestamp(),clock_timestamp());"
            'INSERT INTO appointment_system.enquiry_delivery_jobs(request_id,kind,generation,deadline_at) VALUES ('+literal(reference)+",'client_sheet',0,clock_timestamp()+interval '1 day');")
        job=self.worker.claim_enquiry_delivery('client_sheet');self.assertIsNotNone(job)
        assigned=self.worker.assign_enquiry_row('client',job,enquiry_values(job,3));self.assertIsNotNone(assigned)
        current=self.worker.claim_sheet_projection('enquiry','client');self.assertEqual(current['record_id'],reference)
        values=values_for(current);self.assertEqual(values[2:4],['services','contact']);self.assertEqual(values[11],'consultation')
        digest=fingerprint(values)
        self.assertEqual(self.worker.approve_sheet_projection(current,values,digest,None),'ok')
        self.assertTrue(self.worker.finish_sheet_projection(current,digest,None,False))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'0')

    def test_new_workbook_is_layout_four_and_existing_ready_workbook_is_not_replaced_for_layout_alone(self):
        from . import test_sql_google_resources as resources
        from .test_google_resources import WEB
        from appointment_system.google_oauth import RESOURCE_SCOPES
        metadata={name:dict(owner_email='agency@example.test' if name=='agency_sheet' else 'practice@example.test',
            active_client=WEB,retained_clients=[WEB]) for name in RESOURCE_SCOPES}
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_workbook_volumes,appointment_system.google_resource_grants CASCADE;')
        self.assertTrue(resources.ResourceSQL.configure(self,metadata))
        self.assertTrue(resources.ResourceSQL.install(self,'client_sheet')[1])
        saved=self.worker.claim_google_workbook('client',WEB);self.assertEqual(saved['layout_version'],4)
        self.assertTrue(self.worker.begin_google_workbook_create('client',saved['lease'],saved['intent']))
        self.assertTrue(self.worker.finish_google_workbook('client',saved['lease'],'new_owned_sheet'))
        again=self.worker.claim_google_workbook('client',WEB);self.assertEqual(again['action'],'ready')
        self.assertEqual(again['spreadsheet_id'],'new_owned_sheet');self.assertEqual(again['grant_id'],saved['grant_id'])
        self.db.sql("UPDATE appointment_system.google_workbooks SET next_row=9000;")
        next_volume=self.worker.claim_google_workbook('client',WEB)
        self.assertEqual((next_volume['action'],next_volume['volume_number'],next_volume['layout_version']),('create',2,4))
        self.assertEqual(self.db.scalar("SELECT spreadsheet_id FROM appointment_system.google_workbook_volumes WHERE volume_number=1;"),'new_owned_sheet')
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_workbook_volumes CASCADE;'
            "INSERT INTO appointment_system.google_workbooks(role,subject,client_id,spreadsheet_id,state,connection_revision,layout_version) "
            "VALUES('client','123456789',"+literal(WEB)+",'retained_layout_three','ready',1,3);")
        retained=self.worker.claim_google_workbook('client',WEB)
        self.assertEqual((retained['action'],retained['spreadsheet_id'],retained['layout_version']),('ready','retained_layout_three',3))

    def test_actual_worker_lane_recovers_a_lost_reply_and_late_old_remote_write(self):
        from . import test_sheet_projection as remote
        from appointment_system.sheet_projection import run_projection_once
        booking,_,address=self.mapped()
        fake=remote.CurrentSheets();fake.setUp()
        fake.job.update({k:address[k] for k in ('volume_number','layout_version','intent','generation','subject','client_id')})
        fake.file['appProperties'].update(intent=address['intent'],generation=address['generation'])
        def run():
            with patch('appointment_system.sheet_projection.refresh_connection',return_value=fake.access):
                return run_projection_once(self.worker,fake.services,'booking','client_sheet',transport=fake.transport())
        fake.lost=True;self.assertTrue(run()['processed'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_current_digests;'),'1')
        old=list(fake.cells[0]);self.make_due();self.assertTrue(run()['processed'])
        self.assertEqual(sum(r.method=='PUT' for r in fake.requests),1)
        self.db.sql('UPDATE appointment_system.bookings SET revision=revision+1,email=\'changed@example.invalid\' WHERE id='+literal(booking['booking'])+';')
        self.assertTrue(run()['processed']);new=list(fake.cells[0]);self.assertNotEqual(old,new)
        fake.cells=[old];self.make_due();self.assertTrue(run()['processed'])
        self.assertEqual(fake.cells,[new])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.sheet_current_digests;'),'2')

    def test_company_can_review_and_requeue_without_bypassing_conflicts_or_creating_another_booking(self):
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from appointment_system.application import create_application
        from appointment_system.company_auth import password_hash
        from appointment_system.keys import KeyRing
        from appointment_system.secret_configuration import booking_settings
        from .test_application import environment,protection,Reader
        from .test_sql_company_http import Bridge
        self.mapped();job=self.claim()
        self.assertTrue(self.worker.finish_sheet_projection(job,None,'google_row_conflict',True))
        password='Synthetic company password for tests'
        self.db.scalar("SELECT appointment_system.provision_login('abs_company','company');")
        self.db.scalar("SELECT appointment_system.provision_company_password('company.owner',"+literal(password_hash(password))+');')
        facts=installation();ring=KeyRing.parse(protection('company-session',11),purpose='company-session',
            installation_id=facts['installation_id'],environment=facts['environment'])
        settings=SimpleNamespace(digest=lambda purpose,value:ring.digest(purpose,value.encode()),google_client_id='synthetic-client')
        app=create_application(IsolatedStore(self.db,'appointment_system_web'),booking_settings(environment()),
            company_store=IsolatedStore(self.db,'abs_company'),company_settings=settings,company_database=Bridge(self.db),
            projection_reader=Reader(False),verified_client_address=lambda request:'127.0.0.1')
        with TestClient(app,base_url=facts['origin']) as client:
            self.assertEqual(client.get('/api/company/records/status').status_code,401)
            headers={'Origin':facts['origin']}
            login=client.post('/api/company/login',json={'username':'company.owner','password':password},headers=headers)
            self.assertEqual(login.status_code,200,login.text)
            headers['X-Company-CSRF']=client.get('/api/company/control/status').json()['csrf_token']
            response=client.get('/api/company/records/status');self.assertEqual(response.status_code,200,response.text)
            self.assertIn('no-store',response.headers['cache-control'])
            item=response.json()['records'][0]
            self.assertEqual(item['last_error_code'],'google_row_conflict')
            body={key:item[key] for key in ('role','record_kind','record_id','sequence')}
            body.update(operation_id=str(uuid4()),reason='Requested another protected spreadsheet check.')
            self.assertEqual(client.post('/api/company/records/recheck',json=body,headers={'Origin':facts['origin']}).status_code,403)
            self.assertEqual(client.post('/api/company/records/recheck',json=body,headers=headers|{'Origin':'https://foreign.example'}).status_code,403)
            for _ in range(2):
                response=client.post('/api/company/records/recheck',json=body,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['code'],'check_queued')
            self.assertEqual(client.get('/api/company/records/status').json()['total'],0)
            self.assertEqual(client.post('/api/company/records/recheck',json=body|{'reason':'Another reason'},headers=headers).json()['code'],'request_conflict')
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.company_sheet_reviews;'),'1')
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'1')
            next_job=self.claim();self.assertEqual(self.approve(next_job,'c'*64)[0],'conflict')
            self.assertEqual(client.post('/api/company/sign-out',json={},headers=headers).status_code,200)
            self.assertEqual(client.get('/api/company/records/status').status_code,401)

    def test_current_address_cannot_be_moved_and_provider_failure_retries_are_bounded(self):
        self.mapped();job=self.claim()
        with self.assertRaisesRegex(AssertionError,'immutable current row address'):
            self.db.sql('UPDATE appointment_system.sheet_current_records SET row_number=row_number+1;')
        self.assertTrue(self.worker.finish_sheet_projection(job,None,'google_service_unavailable',False))
        self.assertEqual(self.db.scalar('SELECT failures FROM appointment_system.sheet_current_records;'),'1')
        for failures in (1,7,9999):
            self.make_due();self.db.sql('UPDATE appointment_system.sheet_current_records SET failures='+str(failures)+';')
            again=self.claim();self.assertTrue(self.worker.finish_sheet_projection(again,None,'google_service_unavailable',False))
            self.assertEqual(self.db.scalar("SELECT due_at<=clock_timestamp()+interval '1 day' AND due_at>=clock_timestamp()+interval '29 minutes' FROM appointment_system.sheet_current_records;"),'t')

    def test_volume_access_defaults_private_and_travels_with_history_and_current_jobs(self):
        _,_,assigned=self.mapped()
        self.assertEqual(assigned['approved_permissions'],[])
        self.assertEqual(self.claim()['approved_permissions'],[])
        for role in ('appointment_system_web','abs_worker','abs_staff','abs_company'):
            with self.subTest(role=role),self.assertRaises(AssertionError):
                self.db.sql("UPDATE appointment_system.google_workbook_volumes SET approved_permissions='[]';",role=role)

    def test_saved_named_access_is_immutable_and_invalid_approvals_are_rejected(self):
        named=dict(type='user',role='writer',emailAddress='retained-writer@example.test')
        for value in ({},[{}],[None],[named]*2,[named]*17,[named|{'role':'owner'}],
                      [named|{'type':'anyone'}],[named|{'emailAddress':'invalid'}],
                      [named|{'extra':True}], [named|{'role':None}]):
            with self.subTest(value=value):
                self.assertEqual(self.db.scalar('SELECT appointment_system.valid_workbook_permissions('+literal(value)+'::jsonb);'),'f')
        self.assertEqual(self.db.scalar('SELECT appointment_system.valid_workbook_permissions('+literal([named])+'::jsonb);'),'t')
        self.db.sql("INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,state,approved_permissions) "
                    "VALUES('client',2,4,gen_random_uuid(),'subject','client','creating',"+literal([named])+"::jsonb);")
        self.assertEqual(self.db.value('SELECT approved_permissions FROM appointment_system.google_workbook_volumes WHERE volume_number=2;'),[named])
        with self.assertRaisesRegex(AssertionError,'immutable workbook identity'):
            self.db.sql("UPDATE appointment_system.google_workbook_volumes SET approved_permissions='[]' WHERE volume_number=2;")
        with self.assertRaises(AssertionError):
            self.db.sql("INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,state,approved_permissions) "
                        "VALUES('client',3,4,gen_random_uuid(),'subject','client','creating','[{\"type\":\"anyone\",\"role\":\"reader\"}]');")
