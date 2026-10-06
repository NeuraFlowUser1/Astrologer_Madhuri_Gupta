"""Real role-separated worker transactions, release/restore fencing and fairness."""
import time
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from appointment_system.worker_access import WorkerKey
from appointment_system.keys import encode
from appointment_system.recovery_contract import LANES,ACK_FIELDS,RecoveryRuntime
from appointment_system.secret_configuration import booking_settings
from appointment_system.serialization import canonical
from .test_sql_booking import BookingFixture
from .test_application import environment,Reader
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal

RELEASE='a'*64

class RecoverySQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.enquiries CASCADE;TRUNCATE appointment_system.google_attempts CASCADE;'
          'TRUNCATE appointment_system.studio_sessions CASCADE;TRUNCATE appointment_system.request_limits;'
          'TRUNCATE appointment_system.worker_runs CASCADE;TRUNCATE appointment_system.control_publications;'
          'UPDATE appointment_system.worker_lane_turns SET next_resource=0;')
        self.db.scalar('SELECT appointment_system.configure_worker_release('+literal(RELEASE)+');')
        self.db.sql('UPDATE appointment_system.worker_release SET next_cursor=0;')
        self.worker=IsolatedStore(self.db,'abs_worker')

    def plan(self,*,run=None,release=RELEASE,scheduled=None):
        return self.worker.begin_recovery_run(run or str(uuid4()),release,scheduled or int(time.time()*1000))

    def confirmed(self):
        item=self.booking();self.assertEqual(self.start_order(item),'t');self.assertEqual(self.record_order(item),'ready')
        self.assertEqual(self.capture(item),'confirmed');return item

    def choose(self,plan,lane):
        return self.worker.claim_recovery_turn(plan['run_id'],lane,plan['generation'],plan['release_digest'])

    def test_idle_plan_has_nine_evaluated_counts_and_no_lane_calls_or_live_lease(self):
        plan=self.plan();self.assertEqual(set(plan['lanes']),set(LANES));self.assertFalse(plan['attention'])
        self.assertTrue(all(row['remaining_due']==0 for row in plan['lanes'].values()))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.worker_lane_evaluations;'),'0')
        self.assertIsNone(self.db.value('SELECT active_run FROM appointment_system.worker_release;'))
        self.assertEqual(self.plan()['cursor'],1)

    def test_busy_run_replay_and_foreign_release_are_not_new_authority(self):
        self.booking();run=str(uuid4());stamp=int(time.time()*1000);first=self.plan(run=run,scheduled=stamp)
        self.assertEqual(self.plan(run=run,scheduled=stamp),first)
        self.assertEqual(self.plan()['code'],'run_busy')
        self.assertEqual(self.plan(release='b'*64)['code'],'release_mismatch')
        self.assertEqual(self.plan(run=run,scheduled=stamp-1)['code'],'run_conflict')

    def test_each_calendar_and_workbook_resource_gets_a_saved_turn(self):
        self.confirmed();selected=[]
        for _ in range(4):
            plan=self.plan();turn=self.choose(plan,'booking_records');self.assertEqual(turn['code'],'ok')
            selected.append(turn['resource'])
            ack=self.worker.complete_recovery_turn(plan['run_id'],'booking_records',turn['lease_token'],
                plan['generation'],RELEASE,0,False,False)
            self.assertEqual(set(ack),ACK_FIELDS);self.assertEqual(ack['code'],'evaluated-empty')
            self.assertGreaterEqual(ack['remaining_due'],3)
            self.assertTrue(self.worker.end_recovery_run(plan['run_id'],RELEASE)['completed'])
        self.assertEqual(selected,['calendar','client_sheet','agency_sheet','calendar'])

    def test_selected_google_claim_cannot_take_the_other_workbook(self):
        self.confirmed();job=self.worker.claim_google_delivery('agency_sheet')
        self.assertEqual((job['kind'],job['recipient_role']),('sheet_booking','agency_sheet'))
        self.assertIsNone(self.worker.claim_google_delivery('not-a-resource'))
        self.assertIsNone(self.worker.claim_google_delivery('agency_sheet'))
        other=self.worker.claim_google_delivery('client_sheet');self.assertEqual(other['recipient_role'],'client_sheet')

    def test_repeat_turn_and_foreign_lease_cannot_manufacture_completion(self):
        self.booking();plan=self.plan();turn=self.choose(plan,'payment')
        self.assertEqual(self.choose(plan,'payment')['code'],'turn_repeated')
        result=self.worker.complete_recovery_turn(plan['run_id'],'payment',str(uuid4()),plan['generation'],RELEASE,1,False,False)
        self.assertEqual(result['code'],'turn_conflict')
        self.assertIsNone(self.db.value('SELECT completed_at FROM appointment_system.worker_lane_evaluations;'))

    def test_old_run_cannot_complete_after_restore_or_release_replacement(self):
        self.booking();plan=self.plan();turn=self.choose(plan,'payment')
        self.db.sql('UPDATE appointment_system.control_product_state SET restore_generation='+literal(str(uuid4()))+';')
        result=self.worker.complete_recovery_turn(plan['run_id'],'payment',turn['lease_token'],plan['generation'],RELEASE,1,False,False)
        self.assertEqual(result['code'],'generation_mismatch')
        self.assertFalse(self.worker.end_recovery_run(plan['run_id'],RELEASE)['completed'])
        self.db.scalar('SELECT appointment_system.configure_worker_release('+literal('b'*64)+');')
        self.assertEqual(self.choose(plan,'payment')['code'],'generation_mismatch')

    def test_public_login_cannot_plan_read_history_or_replace_release(self):
        statements=('SELECT appointment_system.begin_recovery_run('+literal(str(uuid4()))+','+literal(RELEASE)+','+str(int(time.time()*1000))+');',
                    'SELECT count(*) FROM appointment_system.worker_runs;',
                    'SELECT appointment_system.configure_worker_release('+literal('b'*64)+');')
        for statement in statements:
            with self.assertRaisesRegex(AssertionError,'permission denied'):self.db.scalar(statement,role='appointment_system_web')

    def test_every_lane_sql_call_checks_restore_release_lease_and_completion(self):
        from appointment_system.worker_authority import admitted,Turn,current
        for change in ('restore','release','lease','completed','expired'):
            self.setUp();self.confirmed();plan=self.plan();turn=self.choose(plan,'booking_records')
            authority=Turn(plan['run_id'],'booking_records',plan['generation'],RELEASE,turn['lease_token'])
            with admitted(authority):
                job=self.worker.claim_google_delivery('calendar');self.assertIsNotNone(job)
            if change=='restore':self.db.sql('UPDATE appointment_system.control_product_state SET restore_generation='+literal(str(uuid4()))+';')
            elif change=='release':self.db.scalar('SELECT appointment_system.configure_worker_release('+literal('b'*64)+');')
            elif change=='lease':authority=Turn(plan['run_id'],'booking_records',plan['generation'],RELEASE,str(uuid4()))
            elif change=='completed':self.worker.complete_recovery_turn(plan['run_id'],'booking_records',turn['lease_token'],plan['generation'],RELEASE,0,False,False)
            else:self.db.sql("UPDATE appointment_system.worker_release SET active_until=clock_timestamp()-interval '1 second';")
            with admitted(authority):
                with self.assertRaisesRegex(AssertionError,'worker .* changed'):
                    self.worker.finish_google_delivery(job,'failed',None,None,'google_request_failed',30)
            self.assertIsNone(current())
            self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.delivery_jobs WHERE id='+literal(job['id'])+';'),'processing')

    def test_real_http_contract_uses_matching_key_and_bounded_canonical_response(self):
        keys={name:WorkerKey(encode(bytes([n])*32)) for name,n in (('recovery',21),('email',22),('google',23))}
        app=create_application(IsolatedStore(self.db,'appointment_system_web'),booking_settings(environment()),
          verified_client_address=lambda request:'127.0.0.1',worker_store=self.worker,projection_reader=Reader(False),
          recovery_worker_key=keys['recovery'],email_worker_key=keys['email'],worker_key=keys['google'],recovery_release=RecoveryRuntime(RELEASE))
        client=TestClient(app,base_url=installation()['origin']);run=str(uuid4())
        body={'run_id':run,'release_digest':RELEASE,'scheduled_at':int(time.time()*1000)}
        headers={'Authorization':'Bearer '+keys['recovery'].value}
        self.assertEqual(client.post('/api/internal/worker/plan',json=body).status_code,401)
        malformed=body|{'scheduled_at':True};self.assertEqual(client.post('/api/internal/worker/plan',json=malformed,headers=headers).status_code,422)
        self.booking();response=client.post('/api/internal/worker/plan',json=body,headers=headers)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.content,canonical(response.json()))
        plan=response.json();request={'run_id':run,'release_digest':RELEASE,'generation':plan['generation']}
        response=client.post('/api/internal/worker/email_events',json=request,headers=headers)
        self.assertEqual(response.status_code,401)
        response=client.post('/api/internal/worker/email_events',json=request,headers={'Authorization':'Bearer '+keys['email'].value})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(set(response.json()),ACK_FIELDS)
        self.assertEqual(response.json()['code'],'evaluated-empty')
        self.assertEqual(client.post('/api/internal/worker/email_events',json=request,
          headers={'Authorization':'Bearer '+keys['email'].value}).status_code,409)
