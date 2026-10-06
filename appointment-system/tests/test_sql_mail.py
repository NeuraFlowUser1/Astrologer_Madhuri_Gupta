"""Committed mail sends/callbacks/quota races in disconnected PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json
from uuid import uuid4
import httpx
from .test_sql_booking import BookingFixture
from .test_mail_contracts import document
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal
from appointment_system.email_configuration import connection
from appointment_system.email_delivery import run_email_delivery_once
from appointment_system.email_messages import message_hash,render_message
from appointment_system.resend_email import ResendSender


class MailSQL(BookingFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.email_reservations;TRUNCATE appointment_system.enquiries CASCADE;')
        self.db.sql('TRUNCATE appointment_system.email_allowance_baselines;')
        self.declared=connection(json.dumps(document()))
        metadata={'account_id':self.declared.account_id,'active_key_id':self.declared.active_key_id,
          'retained_keys':list(self.declared.keys),'legacy_identities':document()['legacy_identities']}
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal(metadata)+'::jsonb,20,600);')
        self.worker=IsolatedStore(self.db,'abs_worker')

    def confirmed(self):
        saved=self.booking();self.start_order(saved);self.record_order(saved)
        self.assertEqual(self.capture(saved),'confirmed');return saved

    def sender(self,handler):
        return ResendSender(self.declared.pinned('k2'),httpx.MockTransport(handler),self.declared)

    def test_send_commits_frozen_content_account_key_and_budget_before_network(self):
        self.confirmed();requests=[]
        def handler(request):
            job_id=json.loads(request.content)['tags'][3]['value']
            row=self.db.value('SELECT jsonb_build_object(\'frozen\',message_snapshot IS NOT NULL,\'attempted\',first_attempt_at IS NOT NULL,\'account\',mail_account_id,\'reserved\',(SELECT count(*) FROM appointment_system.email_reservations WHERE job_id='+literal(job_id)+')) FROM appointment_system.delivery_jobs WHERE id='+literal(job_id)+';')
            self.assertEqual(row,{'frozen':True,'attempted':True,'account':'synthetic-team','reserved':1})
            requests.append(request);return httpx.Response(200,json={'id':str(uuid4())})
        result=run_email_delivery_once(self.worker,self.sender(handler))
        self.assertEqual(result['processed'],1);self.assertEqual(len(requests),1)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE state='completed';"),'1')

    def test_uncertain_retry_reuses_original_bytes_key_and_one_reservation(self):
        self.confirmed();requests=[]
        def handler(request):requests.append(request);raise httpx.ReadTimeout('Synthetic lost reply.')
        first=run_email_delivery_once(self.worker,self.sender(handler));self.assertEqual(first['processed'],1)
        self.db.sql("UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE first_attempt_at IS NOT NULL;")
        self.db.sql("UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '1 hour' WHERE first_attempt_at IS NULL;")
        run_email_delivery_once(self.worker,self.sender(handler))
        self.assertEqual(len(requests),2);self.assertEqual(requests[0].content,requests[1].content)
        self.assertEqual(requests[0].headers['idempotency-key'],requests[1].headers['idempotency-key'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'1')

    def test_account_or_key_mutation_is_rejected_and_frozen_binding_is_immutable(self):
        self.confirmed();job=self.worker.claim_email_delivery();body=render_message(job)
        sender=self.sender(lambda request:self.fail('No provider call expected.'));binding=sender.binding(job,body)
        self.assertIsNone(self.worker.begin_email_send(job,body,message_hash(body),binding=binding|{'account_id':'foreign'}))
        self.assertIsNone(self.worker.begin_email_send(job,body,message_hash(body),binding=binding|{'credential_version':'unregistered'}))
        begun=self.worker.begin_email_send(job,body,message_hash(body),binding=binding);self.assertIsNotNone(begun)
        result=self.db.sql("UPDATE appointment_system.delivery_jobs SET mail_idempotency_key='replacement' WHERE id="+literal(job['id'])+';',check=False)
        self.assertNotEqual(result.returncode,0);self.assertIn('cannot change',result.stderr)
        self.assertIsNone(self.worker.begin_email_send(job,body|{'text':'Changed'},message_hash(body|{'text':'Changed'}),binding=binding))

    def test_notification_evidence_uses_saved_account_and_does_not_complete_other_message(self):
        self.confirmed();job=self.worker.claim_email_delivery();body=render_message(job)
        sender=self.sender(lambda request:self.fail('No send needed.'));binding=sender.binding(job,body)
        begun=self.worker.begin_email_send(job,body,message_hash(body),binding=binding)
        provider=str(uuid4());event={'event':'email.delivered','email_id':provider,'job_id':job['id'],
          'occurred_at':datetime.now(timezone.utc).isoformat(),'binding_version':2,'mail_format':'resend-v1',
          'recipient_hash':hashlib.sha256(job['destination'].lower().encode()).hexdigest(),
          'message_version':str(job['template_version'])}
        self.worker.save_provider_event('resend','foreign-team','live','synthetic-foreign','a'*64,event)
        self.assertFalse(self.worker.reconcile_email_event())
        self.worker.save_provider_event('resend','synthetic-team','live','synthetic-owned','b'*64,event)
        self.assertTrue(self.worker.reconcile_email_event())
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_observations;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.mail_acceptance_claims WHERE job_id='+literal(job['id'])+';'),'1')
        # An authenticated early callback is evidence, not permission to finish
        # the lease currently owned by a sender.
        self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.delivery_jobs WHERE id='+literal(job['id'])+';'),'processing')
        self.assertIsNotNone(begun)

    def test_shared_atomic_budget_reserves_verification_capacity_and_counts_once(self):
        saved=self.confirmed();identifiers=[]
        for revision in range(20,40):
            identifier=str(uuid4());identifiers.append(identifier)
            self.db.sql("INSERT INTO appointment_system.delivery_jobs(id,booking_id,booking_revision,kind,recipient_role) VALUES("+literal(identifier)+','+literal(saved['booking'])+','+str(revision)+",'booking_ack','customer');")
        def reserve(identifier):return self.db.scalar('SELECT appointment_system.reserve_mail_budget('+literal(identifier)+',NULL,false);')
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,identifiers))
        self.assertEqual(results.count(''),12);self.assertEqual(results.count('email_budget_exhausted'),8)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'12')
        admitted=identifiers[results.index('')]
        self.assertEqual(reserve(admitted),'');self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'12')

    def test_registered_web_cannot_configure_budget_or_call_mail_sender(self):
        for statement in ["SELECT appointment_system.configure_mail_connection('{}'::jsonb,100,3000);",
          "SELECT appointment_system.begin_scoped_mail('booking',gen_random_uuid(),gen_random_uuid(),'{}'::jsonb,'x','{}'::jsonb);",
          "SELECT * FROM appointment_system.mail_connection;"]:
            result=self.db.sql(statement,role='appointment_system_web',check=False)
            self.assertNotEqual(result.returncode,0)
