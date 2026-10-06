"""Old delivery reports retain their exact parent and cannot become fresh sends."""
from copy import deepcopy
from datetime import timedelta
import unittest
from uuid import uuid4

from appointment_system.email_messages import message_hash
from tools.conversion.mail import MailTransfer
from tools.conversion.mail_events import MailEventTransfer
from tools.conversion.source import catalogue, ConversionError
from tools.conversion.transport import TransportTransfer
from .test_conversion_records import bindings
from .test_conversion_mail import declared, message, job
from .test_contact_protection import keys


class HistoricalMailEvents(unittest.TestCase):
    def setUp(self):
        self.layout=next(value for value in catalogue() if value.identifier=='legacy-003-16')
        self.bound=bindings();self.row=job();self.provider=str(uuid4());self.body=message(self.row,'003')
        self.book=dict(id=self.row['booking_id'],service_id='consultation',service_name='Saved service',
            amount_paise=210000,currency='INR',starts_at='2031-04-04T10:30:00Z',duration_minutes=30,
            full_name='Synthetic customer',email=self.row['destination'],phone='+919999999999',state='confirmed')
        self.original=dict(id=self.row['id'],record_id=self.book['id'],kind='booking_confirmed',
            recipient_role='customer',state='processing',attempts=1,send_uncertain=True,
            first_attempt_at=self.row['first_attempt_at'],next_attempt_at=self.row['first_attempt_at'],
            created_at=self.row['first_attempt_at'],provider_id=self.provider,last_error_code=None,
            message_version=2,message_payload=self.body,accepted_at=None)
        self.source={'public.delivery_jobs':[self.original],'public.bookings':[self.book]}
        self.event=dict(event_id='evt_saved_report',provider_id=self.provider,event_type='email.delivered',
            occurred_at=self.row['first_attempt_at'],received_at=self.row['first_attempt_at'])
        self.transfer=MailEventTransfer(TransportTransfer(self.bound,MailTransfer(declared('003'),{'003':'k1'},contact=keys())))

    def test_multiple_reports_retain_times_and_one_acceptance_for_the_saved_message(self):
        later=dict(self.event,event_id='evt_later',event_type='email.bounced',
            received_at=(self.bound.now+timedelta(minutes=2)).isoformat())
        result=self.transfer(self.layout,'email_events',[later,self.event],self.source)
        self.assertEqual(len(result['email_observations']),2)
        self.assertEqual([row['event_id'] for row in result['email_observations']],['evt_later','evt_saved_report'])
        for row in result['email_observations']:
            self.assertEqual((row['job_id'],row['provider_id']),(self.original['id'],self.provider))
        claims=result['mail_acceptance_claims'];self.assertEqual(len(claims),1)
        self.assertEqual((claims[0]['kind'],claims[0]['message_hash'],claims[0]['result'],claims[0]['observed_at']),
            ('booking',message_hash(self.body),'accepted',self.event['received_at']))
        self.assertEqual(result,self.transfer(self.layout,'email_events',[later,self.event],self.source))

    def test_enquiry_report_stays_with_enquiry_mail_and_its_protected_message(self):
        enquiry=str(uuid4());request=str(uuid4())
        self.original.update(kind='inquiry_received',record_id=enquiry)
        self.source['public.inquiries']=[dict(id=enquiry,request_id=request,email=self.row['destination'])]
        result=self.transfer(self.layout,'email_events',[self.event],self.source)
        self.assertNotIn('email_observations',result)
        observation=result['enquiry_email_observations'][0]
        self.assertEqual((observation['job_id'],observation['provider_id']),(self.original['id'],self.provider))
        converted=self.transfer.transport.jobs(self.layout,[self.original],self.source)['enquiry_delivery_jobs'][0]
        self.assertEqual(converted['request_id'],request)
        claim=result['mail_acceptance_claims'][0]
        self.assertEqual((claim['kind'],claim['message_hash']),('contact',converted['message_digest']))

    def test_unbound_mail_connection_and_wrong_table_are_refused(self):
        with self.assertRaises(ConversionError):MailEventTransfer(TransportTransfer(self.bound))
        with self.assertRaises(ConversionError):self.transfer(self.layout,'unknown_table',[self.event],self.source)

    def test_duplicate_wrong_purpose_and_conflicting_owners_cannot_be_guessed(self):
        for change in ('duplicate','role','verification','registry','attempt'):
            with self.subTest(change=change):
                source=deepcopy(self.source)
                if change=='duplicate':source['public.delivery_jobs'].append(dict(self.original,id=str(uuid4())))
                if change=='role':source['public.delivery_jobs'][0]['recipient_role']='calendar'
                if change=='verification':source['public.verification_emails']=[dict(provider_id=self.provider)]
                if change=='registry':source['public.mail_provider_ownership']=[dict(provider_id=self.provider,purpose='delivery',intent_id=str(uuid4()))]
                if change=='attempt':source['public.delivery_jobs'][0]['first_attempt_at']=None
                with self.assertRaises(ConversionError):self.transfer(self.layout,'email_events',[self.event],source)

    def test_bad_event_or_changed_frozen_message_cannot_become_an_acceptance_fact(self):
        for change in ({'event_id':'bad report'}, {'event_type':'unknown'}, {'provider_id':'invalid'}, {'received_at':'yesterday'}):
            with self.subTest(change=change),self.assertRaises(ConversionError):
                self.transfer(self.layout,'email_events',[self.event|change],self.source)
        # The historical frozen recipient can legitimately differ from a
        # customer's later contact details. Its declared sender cannot drift
        # into another account's identity.
        self.source['public.delivery_jobs'][0]['message_payload']['from']='Foreign Practice <foreign@example.test>'
        with self.assertRaises(ConversionError):self.transfer(self.layout,'email_events',[self.event],self.source)

    def test_missing_erased_message_is_not_invented_to_create_an_acceptance_digest(self):
        self.original['message_payload']=None
        result=self.transfer(self.layout,'email_events',[self.event],self.source)
        self.assertEqual(len(result['email_observations']),1)
        self.assertNotIn('mail_acceptance_claims',result)
        translated=self.transfer.transport.jobs(self.layout,[self.original],self.source)['delivery_jobs'][0]
        self.assertEqual(translated['state'],'needs_review')
        self.assertEqual(translated['last_error_code'],'legacy_mail_snapshot_unavailable')

    def test_unmatched_report_is_preserved_without_inventing_a_job_or_acceptance(self):
        self.source['public.delivery_jobs']=[]
        result=self.transfer(self.layout,'email_events',[self.event],self.source)
        self.assertEqual(set(result),{'historical_email_observations'})
        saved=result['historical_email_observations'][0]
        self.assertEqual((saved['classification'],saved['challenge_id'],saved['provider_id']),('unmatched',None,self.provider))
        self.assertEqual(saved['recorded_at'],self.event['received_at'])
        self.assertEqual(saved['mail_account_id'],'synthetic-team')

    def test_verification_receipt_and_report_remain_retired_not_current_codes(self):
        receipt=dict(challenge_id=str(uuid4()),provider_id=self.provider,purpose='contact',accepted_at=self.event['received_at'])
        self.source['public.delivery_jobs']=[];self.source['public.verification_emails']=[receipt]
        result=self.transfer(self.layout,'verification_emails',[receipt],self.source)
        self.assertEqual(result,{'historical_verification_receipts':[receipt|{'mail_account_id':'synthetic-team'}]})
        result=self.transfer(self.layout,'email_events',[self.event],self.source)
        self.assertEqual(set(result),{'historical_email_observations'})
        observation=result['historical_email_observations'][0]
        self.assertEqual((observation['classification'],observation['challenge_id']),('verification',receipt['challenge_id']))
        for changes in ({'purpose':'admin'},{'accepted_at':'invalid'},{'challenge_id':'invalid'}):
            with self.subTest(changes=changes),self.assertRaises(ConversionError):
                self.transfer(self.layout,'verification_emails',[receipt|changes],self.source)
        with self.assertRaises(ConversionError):self.transfer(self.layout,'verification_emails',[receipt,receipt],self.source)
