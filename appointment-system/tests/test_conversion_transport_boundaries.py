"""Historical jobs retain ownership, exact retry identity and uncertain outcomes."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from uuid import uuid4
from tools.conversion.transport import TransportTransfer,job_state
from tools.conversion.source import catalogue,ConversionError
from .test_conversion_records import bindings


class TransportBoundaries(unittest.TestCase):
    def setUp(self):
        self.layout=next(v for v in catalogue() if v.identifier=='legacy-003-16')
        self.transfer=TransportTransfer(bindings())

    def job(self,**changes):
        return dict(id=str(uuid4()),state='pending',kind='booking_confirmed',recipient_role='customer',record_id=str(uuid4()),
            attempts=0,next_attempt_at='2031-04-04T10:00:00Z',first_attempt_at=None,provider_id=None,last_error_code=None,
            message_version=1,send_uncertain=False,message_payload=None,created_at='2031-04-04T10:00:00Z',accepted_at='2031-04-04T10:00:00Z')|changes

    def test_only_known_states_translate_and_unknown_sends_never_become_completed(self):
        for state,uncertain,error,want in [('sent',False,None,'completed'),('sent',False,'superseded_by_cancellation','suppressed'),
            ('processing',False,None,'retry_wait'),('processing',True,None,'delivery_unknown'),('failed',False,None,'needs_review'),
            ('failed',True,None,'delivery_unknown'),('pending',False,None,'pending'),('pending',True,None,'delivery_unknown')]:
            with self.subTest(state=state,uncertain=uncertain):self.assertEqual(job_state({'state':state,'send_uncertain':uncertain,'last_error_code':error}),want)
        with self.assertRaises(ConversionError):job_state({'state':'invented'})
        for bad in (None,object()):
            with self.assertRaises(ConversionError):TransportTransfer(bad)
        with self.assertRaises(ConversionError):TransportTransfer(bindings(),mail=object())
        for layout,source in [(SimpleNamespace(project='004'),{}),(self.layout,None)]:
            with self.assertRaises(ConversionError):self.transfer(layout,'delivery_jobs',[],source)
        with self.assertRaises(ConversionError):self.transfer(self.layout,'unknown',[{}],{})

    def test_saved_payment_case_keeps_resolution_and_requires_its_original_account(self):
        row=dict(id=str(uuid4()),booking_id=str(uuid4()),key_id='rzp_test_legacy',state='open',external_reference='fixture',kind='review',created_at='2031-04-04T10:00:00Z')
        self.assertIsNone(self.transfer(self.layout,'payment_cases',[row],{})['payment_cases'][0]['resolved_at'])
        with self.assertRaisesRegex(ConversionError,'resolution_missing'):self.transfer(self.layout,'payment_cases',[row|{'state':'closed'}],{})
        closed=row|dict(state='closed',handled_at='2031-04-04T11:00:00Z',handled_by='Synthetic staff',note='',resolution='')
        result=self.transfer(self.layout,'payment_cases',[closed],{})['payment_cases'][0]
        self.assertEqual(result['resolution_note'],'Historical staff resolution');self.assertEqual(result['resolution_actor'],'Synthetic staff')
        with self.assertRaisesRegex(ConversionError,'payment_binding_unresolved'):self.transfer(self.layout,'payment_cases',[row|{'key_id':'foreign'}],{})

    def test_payment_notification_preserves_verified_facts_but_refuses_foreign_merchant(self):
        row=dict(key_id='rzp_test_legacy',account_id='merchant123',kind='payment.captured',payment_id='pay_synthetic',order_id='order_synthetic',
            record_id=str(uuid4()),event_id='event-synthetic',payload_hash='a'*64,received_at='2031-04-04T10:00:00Z',processed_at=None,
            next_attempt_at='2031-04-04T10:00:00Z',attempts=0,last_error=None,resource_fact={'amount':100})
        result=self.transfer(self.layout,'payment_events',[row],{})['provider_inbox'][0]
        self.assertEqual(result['account_id'],'merchant123');self.assertEqual(result['payload']['resource_fact'],{'amount':100});self.assertIsNone(result['lease_token'])
        with self.assertRaisesRegex(ConversionError,'ownership_conflict'):self.transfer(self.layout,'payment_events',[row|{'account_id':'foreign'}],{})
        job=self.job(kind='payment_event',record_id=row['record_id'])
        for events in ([],[row,row]):
            with self.assertRaisesRegex(ConversionError,'identity_missing'):self.transfer.jobs(self.layout,[job],{'public.payment_events':events})
        self.assertEqual(self.transfer.jobs(self.layout,[job],{'public.payment_events':[row]})['provider_inbox'][0],result)

    def test_missing_parents_and_unbound_previously_sent_mail_stop_conversion(self):
        enquiry={'id':str(uuid4()),'request_id':str(uuid4()),'email':'synthetic@example.test'}
        for job,source,code in [(self.job(),{},'booking_job_identity_missing'),
            (self.job(kind='inquiry_received'),{},'enquiry_job_identity_missing'),
            (self.job(kind='sheet_inquiry',recipient_role='customer',record_id=enquiry['id']),{'public.inquiries':[enquiry]},'enquiry_job_identity_missing'),
            (self.job(kind='inquiry_received',record_id=enquiry['id'],first_attempt_at='2031-04-04T10:00:00Z'),{'public.inquiries':[enquiry]},'mail_binding_unresolved')]:
            with self.subTest(code=code),self.assertRaisesRegex(ConversionError,code):self.transfer.jobs(self.layout,[job],source)
        job=self.job(kind='inquiry_received',recipient_role='client',record_id=enquiry['id']);before=deepcopy(job)
        result=self.transfer.jobs(self.layout,[job],{'public.inquiries':[enquiry]})['enquiry_delivery_jobs'][0]
        self.assertEqual(result['kind'],'practice_notice');self.assertEqual(result['destination'],self.transfer.bindings.installation.document['owners']['client_email']);self.assertEqual(job,before)
        self.assertNotIn('message_snapshot',result)

    def test_uncertain_spreadsheet_attempt_requires_review_but_completed_copy_is_not_repeated(self):
        job=self.job(kind='sheet_inquiry',recipient_role='client_sheet',first_attempt_at='2031-04-04T10:00:00Z')
        for state,want in [('delivery_unknown','needs_review'),('completed','completed'),('suppressed','suppressed')]:
            common={'state':state};self.transfer.sheet_continuation(common,job,self.layout,{})
            self.assertEqual(common['state'],want)
        common={'state':'retry_wait'};self.transfer.sheet_continuation(common,job,self.layout,{'public.sheet_history_rows':[{'job_id':job['id'],'role':'client_sheet'}]})
        self.assertEqual(common,{'state':'retry_wait'})
        with self.assertRaisesRegex(ConversionError,'snapshot_incomplete'):self.transfer.snapshot({})
