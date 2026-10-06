"""Actual enquiry queue and protected mail protocol with a synthetic provider."""
import json,re
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from uuid import uuid4
import httpx
from appointment_system.contact_delivery import run_contact_email_once
from appointment_system.email_configuration import connection
from appointment_system.resend_email import ResendSender
from tools.checks.sql_target import literal
from .test_sql_enquiry_flow import EnquiryFixture
from .test_mail_contracts import document


class EnquiryDeliverySQL(EnquiryFixture):
    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.email_reservations;TRUNCATE appointment_system.email_allowance_baselines;')
        self.declared=connection(json.dumps(document()))
        metadata=dict(account_id=self.declared.account_id,active_key_id=self.declared.active_key_id,
                      retained_keys=list(self.declared.keys),legacy_identities=document()['legacy_identities'])
        self.db.scalar('SELECT appointment_system.configure_mail_connection('+literal(metadata)+'::jsonb,20,600);')
        self.requests=[]

    def send(self,handler=None,kind='verification'):
        def provider(request):
            self.requests.append(request)
            return handler(request) if handler else httpx.Response(200,json={'id':str(uuid4())})
        sender=ResendSender(self.declared.pinned('k2'),httpx.MockTransport(provider),self.declared)
        return run_contact_email_once(self.worker,sender,self.keys,kind=kind)

    def test_full_enquiry_delivery_commits_private_snapshot_before_send_and_does_not_repeat(self):
        self.start()
        def provider(request):
            row=self.db.value("SELECT jsonb_build_object('encrypted',message_ciphertext IS NOT NULL,"
                "'attempted',first_attempt_at IS NOT NULL,'account',mail_account_id) FROM appointment_system.enquiry_delivery_jobs WHERE kind='verification';")
            self.assertEqual(row,dict(encrypted=True,attempted=True,account='synthetic-team'))
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'1')
            return httpx.Response(200,json={'id':str(uuid4())})
        self.assertEqual(self.send(provider)['processed'],1)
        body=json.loads(self.requests[0].content);code=re.search(r'\b[0-9]{6}\b',body['text']).group()
        self.assertEqual(self.verify(code).json()['state'],'received')
        for _ in range(2):self.assertEqual(self.send(kind='notification')['processed'],1)
        self.assertEqual(self.send(kind='notification')['processed'],0)
        self.assertEqual(len(self.requests),3)
        recipients=[json.loads(request.content)['to'][0] for request in self.requests]
        self.assertEqual(recipients.count('customer@example.com'),2)
        self.assertEqual(recipients.count('practice@example.test'),1)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE state='completed';"),'3')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'3')

    def test_lost_send_reply_retries_same_protected_body_and_identity_with_one_budget_reservation(self):
        self.start()
        def lost(request):raise httpx.ReadTimeout('Synthetic lost reply')
        self.assertEqual(self.send(lost)['processed'],1)
        self.assertEqual(self.db.scalar("SELECT state FROM appointment_system.enquiry_delivery_jobs WHERE kind='verification';"),'delivery_unknown')
        self.db.sql("UPDATE appointment_system.enquiry_delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.send()['processed'],1)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(self.requests[0].content,self.requests[1].content)
        self.assertEqual(self.requests[0].headers['idempotency-key'],self.requests[1].headers['idempotency-key'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'1')

    def test_expired_unsent_code_is_suppressed_without_spending_mail_budget(self):
        self.start()
        self.db.sql("UPDATE appointment_system.enquiries SET code_expires_at=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.send()['processed'],0)
        self.assertEqual(self.requests,[])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'0')
        self.assertEqual(self.db.scalar("SELECT state FROM appointment_system.enquiry_delivery_jobs WHERE kind='verification';"),'suppressed')

    def test_quota_refusal_keeps_verified_enquiry_and_records_retry_instead_of_delivery(self):
        self.start();self.send()
        code=re.search(r'\b[0-9]{6}\b',json.loads(self.requests[0].content)['text']).group()
        self.assertEqual(self.verify(code).json()['state'],'received')
        def quota(request):return httpx.Response(429,json={'name':'daily_quota_exceeded'},headers={'Retry-After':'90'})
        self.assertEqual(self.send(quota,kind='notification')['processed'],1)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(self.db.scalar('SELECT verified_at IS NOT NULL FROM appointment_system.enquiries;'),'t')
        row=self.db.value("SELECT jsonb_build_object('state',state,'error',last_error_code,'wait',next_attempt_at>clock_timestamp()+interval '23 hours') "
                          "FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification' AND last_error_code='daily_quota_exceeded';")
        self.assertEqual(row,dict(state='pending',error='daily_quota_exceeded',wait=True))
        # A definite quota rejection has not delivered anything. Its later
        # allowed retry must keep the frozen contents and original job identity.
        self.db.sql("UPDATE appointment_system.enquiry_delivery_jobs SET next_attempt_at=clock_timestamp()+interval '1 hour' WHERE last_error_code IS NULL;"
                    "UPDATE appointment_system.enquiry_delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE last_error_code='daily_quota_exceeded';")
        deadline=self.db.scalar("SELECT deadline_at FROM appointment_system.enquiry_delivery_jobs WHERE last_error_code='daily_quota_exceeded';")
        # Advance only the application's deadline check. The saved deadline is
        # immutable; do not disable its trigger or rewrite protected identity.
        later=datetime.fromisoformat(deadline).astimezone(timezone.utc)+timedelta(seconds=1)
        with patch('appointment_system.contact_delivery.datetime') as clock:
            clock.now.return_value=later
            self.assertEqual(self.send(kind='notification')['processed'],1)
        self.assertEqual(self.requests[1].content,self.requests[2].content)
        self.assertEqual(self.requests[1].headers['idempotency-key'],self.requests[2].headers['idempotency-key'])
