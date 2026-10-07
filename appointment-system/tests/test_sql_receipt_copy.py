"""Owned receipts, durable copy identity and worker delivery in disconnected SQL."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from uuid import uuid4
import httpx
from .test_sql_booking import BookingFixture
from .test_mail_contracts import document
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal
from appointment_system.email_configuration import connection
from appointment_system.email_delivery import run_email_delivery_once
from appointment_system.resend_email import ResendSender

class ReceiptCopySQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.email_reservations;TRUNCATE appointment_system.email_allowance_baselines;')
        self.declared=connection(json.dumps(document()))
        metadata={'account_id':self.declared.account_id,'active_key_id':self.declared.active_key_id,
            'retained_keys':list(self.declared.keys),'legacy_identities':document()['legacy_identities']}
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal(metadata)+'::jsonb,20,600);')
        self.worker=IsolatedStore(self.db,'abs_worker')

    def confirmed(self,*,email=None,meeting='internal'):
        spec=deepcopy(self.spec);spec['meeting']=meeting;self.set_policy(spec)
        saved=self.booking(email=email,normalization_version=3);self.start_order(saved);self.record_order(saved)
        self.assertEqual(self.capture(saved),'confirmed');return saved

    def copy(self,saved,*,operation=None,revision=1,email='copy@example.test',ready=True,receipt=None):
        operation=operation or str(uuid4())
        result=self.db.value('SELECT appointment_system.request_receipt_copy('+','.join([
            literal(saved['request']),literal(receipt or saved['receipt']),literal(operation),str(revision),
            literal({'email':email,'sending_ready':ready})+'::jsonb'])+');',role='appointment_system_web')
        return result

    def job(self,saved):
        return self.db.value('SELECT to_jsonb(j) FROM appointment_system.delivery_jobs j WHERE booking_id='+literal(saved['booking'])+" AND kind='booking_receipt';")

    def only_copy_due(self,saved):
        self.db.sql("UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '2 hours' WHERE kind<>'booking_receipt';")

    def history(self,saved,*,age=120,state='suppressed',uncertain=False):
        """A valid historical fixture at insertion; never edits immutable identity."""
        operation=str(uuid4());accepted=datetime.now(timezone.utc)-timedelta(seconds=age)
        metadata=dict(version=1,operation_id=operation,expected_revision=1,input_fingerprint='f'*64,
            accepted_at=accepted.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
        self.db.sql('INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key,destination,send_deadline_at,receipt_copy_request,state,send_uncertain,first_attempt_at) VALUES('+','.join([
            literal(str(uuid4())),literal(saved['booking']),"'booking_receipt'","'customer'",'1',literal('receipt:'+operation),
            "'copy@example.test'",literal((accepted+timedelta(hours=23)).isoformat()),literal(metadata)+'::jsonb',literal(state),literal(uncertain),literal(accepted.isoformat()) if uncertain else 'NULL'])+');')
        return operation

    def test_optional_copy_destination_is_not_booking_contact_and_exact_replay_is_one_job(self):
        b=self.confirmed();op=str(uuid4());first=self.copy(b,operation=op)
        self.assertEqual(first['code'],'receipt_copy_accepted');self.assertEqual(first['operation_id'],op)
        job=self.job(b);self.assertEqual(job['destination'],'copy@example.test')
        self.assertFalse(first['email_copy']['has_booking_email']);self.assertEqual(first['email_copy']['target_hint'],'c***@example.test')
        self.assertEqual(self.db.scalar('SELECT email IS NULL FROM appointment_system.bookings;'),'t')
        again=self.copy(b,operation=op,ready=False);self.assertTrue(again['replayed'])
        self.assertEqual(self.job(b)['id'],job['id'])
        self.assertEqual(self.copy(b,operation=op,email='other@example.test')['code'],'request_conflict')
        self.assertEqual(self.copy(b)['code'],'copy_pending')

    def test_canonical_booking_email_is_used_and_different_address_cannot_redirect_it(self):
        b=self.confirmed(email='saved@example.test')
        self.assertEqual(self.copy(b,email='different@example.test')['code'],'email_destination_conflict')
        self.assertEqual(self.copy(b,email=None)['code'],'receipt_copy_accepted')
        self.assertEqual(self.job(b)['destination'],'saved@example.test')

    def test_new_revision_and_confirmation_checks_do_not_break_an_accepted_replay(self):
        b=self.confirmed();op=str(uuid4());first=self.copy(b,operation=op)
        self.db.sql("UPDATE appointment_system.bookings SET revision=revision+1 WHERE id="+literal(b['booking'])+';')
        replay=self.copy(b,operation=op)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['booking_revision'],1)
        self.assertEqual(replay['email_copy']['state'],'superseded')
        self.assertEqual(self.copy(b)['code'],'revision_changed')
        self.db.sql("UPDATE appointment_system.bookings SET state='cancelled',cancelled_at=clock_timestamp() WHERE id="+literal(b['booking'])+';')
        self.assertTrue(self.copy(b,operation=op)['replayed'])
        self.assertEqual(self.copy(b,revision=2)['code'],'booking_not_confirmed')

    def test_invalid_access_off_and_missing_resources_insert_nothing(self):
        b=self.confirmed()
        self.assertEqual(self.copy(b,receipt='f'*64)['code'],'access_unavailable')
        self.assertEqual(self.copy(b,ready=False)['code'],'copy_unavailable')
        self.assertEqual(self.copy(b,email=None)['code'],'invalid_request')
        self.assertIsNone(self.job(b))
        self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false;')
        with self.assertRaises(AssertionError):self.copy(b)
        self.assertIsNone(self.job(b))

    def test_concurrent_operations_accept_one_and_same_operation_replays(self):
        b=self.confirmed();operations=[str(uuid4()) for _ in range(5)]
        with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(lambda op:self.copy(b,operation=op),operations))
        self.assertEqual(sum(r['code']=='receipt_copy_accepted' for r in results),1)
        winner=operations[next(i for i,r in enumerate(results) if r['code']=='receipt_copy_accepted')]
        with ThreadPoolExecutor(max_workers=4) as pool:replays=list(pool.map(lambda _:self.copy(b,operation=winner),range(4)))
        self.assertTrue(all(r['replayed'] for r in replays))
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='booking_receipt';"),'1')

    def test_accepted_identity_destination_and_deadline_are_immutable_before_send(self):
        b=self.confirmed();self.copy(b);job=self.job(b)
        for change in ["destination='other@example.test'","send_deadline_at=send_deadline_at+interval '1 hour'",
            'booking_revision=booking_revision+1',"receipt_copy_request=jsonb_set(receipt_copy_request,'{input_fingerprint}',to_jsonb(repeat('f',64)))"]:
            result=self.db.sql('UPDATE appointment_system.delivery_jobs SET '+change+' WHERE id='+literal(job['id'])+';',check=False)
            self.assertNotEqual(result.returncode,0)
        deadline=datetime.fromisoformat(job['send_deadline_at']);accepted=datetime.fromisoformat(job['receipt_copy_request']['accepted_at'].replace('Z','+00:00'))
        self.assertLessEqual(deadline-accepted,timedelta(hours=23))

    def test_pending_google_link_waits_without_a_provider_attempt_and_never_after_deadline(self):
        b=self.confirmed(meeting='google_meet');self.copy(b);self.only_copy_due(b)
        self.assertIsNone(self.worker.claim_email_delivery());job=self.job(b)
        self.assertEqual(job['attempts'],0);self.assertIsNone(job['first_attempt_at'])
        self.assertLessEqual(datetime.fromisoformat(job['next_attempt_at']),datetime.now(timezone.utc)+timedelta(seconds=31))
        self.db.sql("UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='google_connection_failed' WHERE kind='booking_calendar';"
            "UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE kind='booking_receipt';")
        self.assertIsNone(self.worker.claim_email_delivery());self.assertEqual(self.job(b)['last_error_code'],'email_meeting_unavailable')

    def test_copy_uses_existing_official_sender_and_frozen_idempotency(self):
        b=self.confirmed();self.copy(b);self.only_copy_due(b);sent=[]
        def handler(request):sent.append(request);return httpx.Response(200,json={'id':str(uuid4())})
        sender=ResendSender(self.declared.pinned('k2'),httpx.MockTransport(handler),self.declared)
        result=run_email_delivery_once(self.worker,sender)
        self.assertEqual(result['processed'],1);self.assertEqual(len(sent),1)
        payload=json.loads(sent[0].content);self.assertEqual(payload['to'],['copy@example.test'])
        self.assertIn('Your appointment details',payload['subject']);self.assertNotIn('Synthetic Customer',payload['text'])
        self.assertEqual(self.copy(b,operation=self.job(b)['receipt_copy_request']['operation_id'])['email_copy']['state'],'provider_accepted')

    def test_direct_helpers_and_worker_copy_admission_are_denied(self):
        for role,statement in [('appointment_system_web',"SELECT appointment_system.receipt_copy_state(gen_random_uuid());"),
            ('appointment_system_web',"SELECT appointment_system.entry_request_receipt_copy(gen_random_uuid(),'x',gen_random_uuid(),1,'{}');"),
            ('abs_worker',"SELECT appointment_system.request_receipt_copy(gen_random_uuid(),'x',gen_random_uuid(),1,'{}');")]:
            self.assertNotEqual(self.db.sql(statement,role=role,check=False).returncode,0)

    def test_three_accepted_operations_limit_and_rolling_window_are_database_owned(self):
        b=self.confirmed()
        for age in (180,120,90):self.history(b,age=age)
        result=self.copy(b);self.assertEqual(result['code'],'copy_limit')
        self.assertEqual(result['email_copy']['remaining_requests'],0);self.assertGreater(result['retry_after'],86000)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='booking_receipt';"),'3')

    def test_terminal_failure_frees_delivery_but_does_not_skip_cooldown(self):
        b=self.confirmed();self.history(b,age=10,state='failed')
        result=self.copy(b);self.assertEqual(result['code'],'copy_cooldown');self.assertTrue(1<=result['retry_after']<=60)
        self.assertEqual(result['email_copy']['state'],'needs_attention')

    def test_unknown_send_blocks_forever_even_after_quota_window_and_deadline(self):
        b=self.confirmed();self.history(b,age=25*3600,state='needs_review',uncertain=True)
        result=self.copy(b);self.assertEqual(result['code'],'copy_pending')
        self.assertEqual(result['email_copy']['blocked_reason'],'delivery_unknown');self.assertEqual(result['email_copy']['remaining_requests'],3)

    def test_expired_unattempted_copy_is_not_sent_and_new_deliberate_copy_is_allowed(self):
        b=self.confirmed();self.history(b,age=24*3600+60,state='pending');self.only_copy_due(b)
        self.assertIsNone(self.worker.claim_email_delivery());job=self.job(b)
        self.assertEqual(job['attempts'],0);self.assertEqual(job['last_error_code'],'email_deadline_passed')
        current=self.db.value('SELECT appointment_system.receipt_copy_state('+literal(b['booking'])+');')
        self.assertEqual(current['state'],'needs_attention');self.assertTrue(current['can_request'])
        self.assertEqual(self.copy(b)['code'],'receipt_copy_accepted')

    def test_saved_connection_is_required_and_invalid_metadata_cannot_enter_restore(self):
        b=self.confirmed();self.db.sql('DELETE FROM appointment_system.mail_connection;')
        self.assertEqual(self.copy(b)['code'],'copy_unavailable');self.assertIsNone(self.job(b))
        bad=self.db.sql("INSERT INTO appointment_system.delivery_jobs(booking_id,kind,recipient_role,booking_revision,event_key,destination,send_deadline_at,receipt_copy_request) VALUES ("+
            literal(b['booking'])+",'booking_receipt','customer',1,'receipt:"+str(uuid4())+"','copy@example.test',clock_timestamp()+interval '23 hours','{}');",check=False)
        self.assertNotEqual(bad.returncode,0)
