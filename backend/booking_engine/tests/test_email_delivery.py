import copy
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock
from uuid import uuid4

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.email_delivery import run_email_delivery_once
from backend.booking_engine.email_messages import render_message,message_hash
from backend.booking_engine.resend_email import EmailFailure


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.job={'send_deadline_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'id':str(uuid4()),'lease_token':str(uuid4()),'attempts':1,'kind':'booking_ack',
            'recipient_role':'customer','destination':'person@example.com','payload':{
                'reference':str(uuid4()),'service':'Kundli Prediction','starts_at':datetime.now(timezone.utc).isoformat(),
                'amount_paise':250000,'currency':'INR','meet_url':'https://meet.google.com/abc-defg-hij',
                'notes':'PRIVATE_NOTES','phone':'PRIVATE_PHONE','birth_date':'PRIVATE_BIRTH'}}
        self.store=Mock()
        self.store.claim_email_delivery.return_value=self.job
        self.store.begin_email_send.side_effect=lambda job,payload,digest:dict(job,message_snapshot=payload,
            first_attempt_at=datetime.now(timezone.utc).isoformat())
        self.store.finish_email_delivery.return_value=True
        self.sender=Mock();self.sender.send.return_value=str(uuid4())

    def test_rescheduled_message_does_not_request_another_payment(self):
        self.job['payload']['change_kind']='rescheduled'
        message=render_message(self.job)
        self.assertIn('Appointment rescheduled',message['subject'])
        self.assertIn('does not request another payment',message['text'])
        self.assertNotIn('PRIVATE_PHONE',message['text'])

    def test_minimal_message_and_escape(self):
        self.job['payload']['service']='<script>unsafe & text</script>'
        message=render_message(self.job)
        self.assertIn('&lt;script&gt;',message['html'])
        self.assertNotIn('<script>',message['html'])
        for private in ('PRIVATE_NOTES','PRIVATE_PHONE','PRIVATE_BIRTH'):
            self.assertNotIn(private,str(message))
        self.assertIn('INR 2,500.00',message['text'])
        self.assertIn('India time',message['text'])

    def test_details_require_valid_meeting_and_client_cannot_receive_customer_kind(self):
        self.job['kind']='booking_details'
        self.assertIn('https://meet.google.com/',render_message(self.job)['text'])
        for link in ('https://evil.example/','javascript:alert(1)',None):
            self.job['payload']['meet_url']=link
            with self.assertRaises(EmailFailure):render_message(self.job)
        self.job['recipient_role']='client'
        with self.assertRaises(EmailFailure):render_message(self.job)

    def test_commit_precedes_send_and_finish(self):
        calls=[]
        def begin(job,payload,digest):
            calls.append('commit')
            return dict(job,message_snapshot=payload,first_attempt_at=datetime.now(timezone.utc))
        self.store.begin_email_send.side_effect=begin
        self.sender.send.side_effect=lambda *args:(calls.append('send') or str(uuid4()))
        self.store.finish_email_delivery.side_effect=lambda *args:(calls.append('finish') or True)
        self.assertEqual(run_email_delivery_once(self.store,self.sender)['processed'],1)
        self.assertEqual(calls,['commit','send','finish'])

    def test_unknown_commit_and_budget_deferral_never_send(self):
        self.store.begin_email_send.side_effect=StorageUnavailable()
        with self.assertRaises(StorageUnavailable):run_email_delivery_once(self.store,self.sender)
        self.sender.send.assert_not_called();self.store.finish_email_delivery.assert_not_called()
        self.store.begin_email_send.side_effect=None;self.store.begin_email_send.return_value=None
        self.assertTrue(run_email_delivery_once(self.store,self.sender)['deferred'])
        self.sender.send.assert_not_called()

    def test_frozen_message_survives_template_or_booking_changes(self):
        frozen=render_message(self.job)
        self.job.update(message_snapshot=copy.deepcopy(frozen),message_hash=message_hash(frozen))
        self.job['payload']['service']='Changed service'
        run_email_delivery_once(self.store,self.sender)
        self.assertEqual(self.sender.send.call_args.args[0],frozen)
        self.job['message_snapshot']['text']='tampered'
        self.sender.reset_mock()
        run_email_delivery_once(self.store,self.sender)
        self.sender.send.assert_not_called()
        self.assertEqual(self.store.finish_email_delivery.call_args.args[2],'email_snapshot_conflict')

    def test_timeout_keeps_uncertain_and_configuration_fault_stops_retry(self):
        for code,attention in [('email_send_unconfirmed',False),('email_configuration_rejected',True),('email_retry_window_closed',True)]:
            self.sender.send.side_effect=EmailFailure(code)
            run_email_delivery_once(self.store,self.sender)
            args=self.store.finish_email_delivery.call_args.args
            self.assertEqual(args[2:4],(code,attention))
            self.assertTrue(15<=args[4]<=900)

    def test_deadline_rechecked_after_begin_commit(self):
        self.job['send_deadline_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        run_email_delivery_once(self.store,self.sender)
        self.sender.send.assert_not_called()
        self.assertEqual(self.store.finish_email_delivery.call_args.args[2],'email_deadline_passed')

    def test_unknown_completion_is_not_masked(self):
        self.store.finish_email_delivery.side_effect=StorageUnavailable()
        with self.assertRaises(StorageUnavailable):run_email_delivery_once(self.store,self.sender)
        self.sender.send.assert_called_once()

    def test_cancellation_never_promises_refund(self):
        self.job['kind']='booking_cancelled'
        self.assertIn('does not confirm a refund',render_message(self.job)['text'])
        self.job.update(kind='payment_review',recipient_role='client',destination='sarsajyotish@gmail.com')
        self.assertIn('not an appointment confirmation',render_message(self.job)['text'])
        self.job['kind']='unknown'
        with self.assertRaises(EmailFailure):render_message(self.job)
