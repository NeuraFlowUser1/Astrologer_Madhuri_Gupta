import json
import unittest
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
from backend.booking_engine.tests import test_contact as contact_fixture
ORIGIN=contact_fixture.ORIGIN
from backend.booking_engine.contact_messages import render_contact_message,seal_message,open_message
from backend.booking_engine.contact_delivery import run_contact_email_once,run_contact_google_once
from backend.booking_engine.contact_records import enquiry_values,copy_enquiry_record,prepare_enquiry_tab,write_enquiry_row,HEADERS
from backend.booking_engine.resend_email import EmailFailure
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.google_workspace import WorkspaceFailure,PROJECT
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.google_worker import WorkerKey
from backend.booking_engine.tests.test_hosting import key


class ContactDeliveryTests(unittest.TestCase):
    def setUp(self):
        fixture=contact_fixture.ContactTests();fixture.setUp();self.keys=fixture.keys
        self.now=datetime.now(timezone.utc)
        self.job={'id':str(uuid4()),'request_id':str(uuid4()),'kind':'verification','generation':1,
            'destination':'case@example.com','payload':{'email':'case@example.com','name':'Synthetic','phone':'','subject':'<script>','message':'=1+1'},
            'attempts':1,'lease_token':str(uuid4()),'deadline_at':(self.now+timedelta(minutes=5)).isoformat(),
            'code_expires_at':(self.now+timedelta(minutes=5)).isoformat(),'verified_at':self.now.isoformat()}
        _,self.job['code_ciphertext']=self.keys.challenge(self.job['request_id'],'case@example.com',1)
        self.store=Mock();self.store.claim_enquiry_delivery.return_value=self.job
        self.store.finish_enquiry_delivery.return_value=True
        self.store.begin_enquiry_send.side_effect=lambda job,cipher,digest:dict(job,message_ciphertext=cipher,message_digest=digest,first_attempt_at=self.now.isoformat())
        self.sender=Mock();self.sender.send.return_value=str(uuid4())

    def test_code_is_not_in_subject_or_plaintext_persistence(self):
        message=render_contact_message(self.job,self.keys)
        code=self.keys.open_code(self.job['code_ciphertext'],self.job['request_id'],'case@example.com',1,self.now+timedelta(minutes=5))
        self.assertIn(code,message['text']);self.assertNotIn(code,message['subject'])
        encrypted,digest=seal_message(self.keys,self.job,message)
        self.assertNotIn(message['text'],encrypted)
        self.assertEqual(open_message(self.keys,dict(self.job,message_ciphertext=encrypted,message_digest=digest)),message)
        self.assertNotEqual(digest,self.keys.digest('code',self.job['request_id'],1,'case@example.com',code))

    def test_snapshot_bound_to_job_destination_and_key(self):
        message=render_contact_message(self.job,self.keys);encrypted,digest=seal_message(self.keys,self.job,message)
        saved=dict(self.job,message_ciphertext=encrypted,message_digest=digest)
        for change in [{'id':str(uuid4())},{'destination':'else@example.com'},{'message_digest':'a'*64},{'message_ciphertext':'corrupted'}]:
            with self.assertRaises(EmailFailure):open_message(self.keys,dict(saved,**change))

    def test_saved_admission_precedes_provider_and_finish(self):
        order=[]
        def begin(job,cipher,digest):
            order.append('committed');return dict(job,message_ciphertext=cipher,message_digest=digest,first_attempt_at=self.now.isoformat())
        self.store.begin_enquiry_send.side_effect=begin
        self.sender.send.side_effect=lambda *args:order.append('provider') or str(uuid4())
        self.store.finish_enquiry_delivery.side_effect=lambda *args:order.append('finish') or True
        self.assertEqual(run_contact_email_once(self.store,self.sender,self.keys)['processed'],1)
        self.assertEqual(order,['committed','provider','finish']);self.store.expire_enquiry_codes.assert_called_once()
        self.assertEqual(self.sender.send.call_args.args[1],self.job['id'])

    def test_unknown_commit_never_calls_provider(self):
        self.store.begin_enquiry_send.side_effect=StorageUnavailable()
        with self.assertRaises(StorageUnavailable):run_contact_email_once(self.store,self.sender,self.keys)
        self.sender.send.assert_not_called();self.store.finish_enquiry_delivery.assert_not_called()

    def test_budget_or_generation_deferral_never_calls_provider(self):
        self.store.begin_enquiry_send.side_effect=None;self.store.begin_enquiry_send.return_value=None
        self.assertTrue(run_contact_email_once(self.store,self.sender,self.keys)['deferred'])
        self.sender.send.assert_not_called();self.store.finish_enquiry_delivery.assert_not_called()

    def test_retry_uses_frozen_message_without_rendering(self):
        encrypted,digest=seal_message(self.keys,self.job,render_contact_message(self.job,self.keys))
        self.job.update(message_ciphertext=encrypted,message_digest=digest)
        with patch('backend.booking_engine.contact_delivery.render_contact_message',side_effect=AssertionError('Must reuse snapshot')):
            run_contact_email_once(self.store,self.sender,self.keys)
        self.assertEqual(self.store.begin_enquiry_send.call_args.args[1:],(encrypted,digest))

    def test_timeout_is_saved_as_uncertain_with_same_identity(self):
        self.sender.send.side_effect=EmailFailure('email_send_unconfirmed')
        run_contact_email_once(self.store,self.sender,self.keys)
        args=self.store.finish_enquiry_delivery.call_args.args
        self.assertIsNone(args[1]);self.assertEqual(args[2],'email_send_unconfirmed');self.assertFalse(args[3])

    def test_lost_lease_not_reported_as_success(self):
        self.store.finish_enquiry_delivery.return_value=False
        self.assertEqual(run_contact_email_once(self.store,self.sender,self.keys),{'processed':0,'retry':True})

    def test_expired_code_or_send_deadline_never_sent(self):
        self.job['code_expires_at']=(self.now-timedelta(seconds=1)).isoformat()
        run_contact_email_once(self.store,self.sender,self.keys);self.sender.send.assert_not_called()
        self.assertTrue(self.store.finish_enquiry_delivery.call_args.args[3])

    def test_acknowledgement_and_practice_notice_do_not_confirm_booking(self):
        for kind,destination in [('acknowledgement','case@example.com'),('practice_notice','sarsajyotish@gmail.com')]:
            message=render_contact_message(dict(self.job,kind=kind,destination=destination),self.keys)
            self.assertIn('not an appointment',message['text']);self.assertNotIn('=1+1',message['text'])
            self.assertEqual(message['to'],[destination]);self.assertEqual(message['reply_to'],'sarsajyotish@gmail.com')

    def test_google_copy_is_fixed_row_and_owner_specific(self):
        job=dict(self.job,kind='client_sheet');workspace=Mock()
        saved={'spreadsheet_id':'synthetic-file','intent':str(uuid4())}
        assigned=dict(saved,row=2,values=enquiry_values(job));self.store.assign_enquiry_row.return_value=assigned
        with patch('backend.booking_engine.contact_records.prepare_owner_workbook',return_value=(workspace,saved)) as prepare,patch('backend.booking_engine.contact_records.prepare_enquiry_tab'),patch('backend.booking_engine.contact_records.write_enquiry_row') as write:
            self.assertEqual(copy_enquiry_record(self.store,Mock(),job),'synthetic-file')
        self.assertEqual(prepare.call_args.args[2],'client');write.assert_called_once_with(workspace,assigned)
        self.assertEqual(assigned['values'][0],PROJECT);self.assertEqual(assigned['values'][8],'=1+1')

    def test_google_wrong_saved_workbook_fails_before_remote_write(self):
        self.store.assign_enquiry_row.return_value={'spreadsheet_id':'wrong','intent':'wrong'}
        with patch('backend.booking_engine.contact_records.prepare_owner_workbook',return_value=(Mock(),{'spreadsheet_id':'correct','intent':'correct'})),patch('backend.booking_engine.contact_records.prepare_enquiry_tab') as prepare:
            with self.assertRaises(WorkspaceFailure):copy_enquiry_record(self.store,Mock(),dict(self.job,kind='agency_sheet'))
        prepare.assert_not_called()

    def test_row_write_uses_raw_values_and_never_overwrites_different_content(self):
        values=enquiry_values(self.job);assigned={'spreadsheet_id':'synthetic','intent':str(uuid4()),'row':2,'values':values}
        workspace=Mock();workspace.request.return_value=(200,{'values':[]})
        with patch('backend.booking_engine.contact_records.verify_owner'):
            write_enquiry_row(workspace,assigned)
        self.assertEqual(workspace.request.call_args.kwargs['params'],{'valueInputOption':'RAW'})
        workspace.reset_mock();workspace.request.return_value=(200,{'values':[['changed']]})
        with patch('backend.booking_engine.contact_records.verify_owner'):
            with self.assertRaises(WorkspaceFailure):write_enquiry_row(workspace,assigned)
        self.assertEqual(workspace.request.call_count,1)

    def test_existing_row_and_header_are_idempotent_and_mismatches_stop(self):
        values=enquiry_values(self.job);workspace=Mock();workspace.request.return_value=(200,{'values':[values]})
        with patch('backend.booking_engine.contact_records.verify_owner'):
            write_enquiry_row(workspace,{'spreadsheet_id':'synthetic','intent':str(uuid4()),'row':2,'values':values})
        self.assertEqual(workspace.request.call_count,1)
        for headers in ([HEADERS],[['changed']]):
            workspace.reset_mock();workspace.request.side_effect=[(200,{'sheets':[{'properties':{'sheetId':4005,'title':'Enquiries','gridProperties':{'rowCount':10000,'columnCount':10}}}]}),(200,{'values':headers})]
            with patch('backend.booking_engine.contact_records.verify_owner'):
                if headers==[HEADERS]:prepare_enquiry_tab(workspace,'synthetic',str(uuid4()))
                else:
                    with self.assertRaises(WorkspaceFailure):prepare_enquiry_tab(workspace,'synthetic',str(uuid4()))
            self.assertEqual(workspace.request.call_count,2)

    def test_google_worker_surfaces_uncertain_completion(self):
        self.store.claim_enquiry_delivery.return_value=dict(self.job,kind='agency_sheet')
        self.store.finish_enquiry_delivery.return_value=False
        with patch('backend.booking_engine.contact_records.copy_enquiry_record',return_value='synthetic-file'):
            self.assertEqual(run_contact_google_once(self.store,Mock()),{'processed':0,'retry':True})

    def test_private_worker_rejects_browser_and_selected_recipient(self):
        secret=key(b'w')
        app=create_application(self.store,Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32),verified_client_address=lambda _:'192.0.2.1',
            email_worker_key=WorkerKey(secret),email_sender=self.sender,contact_secrets=self.keys)
        client=TestClient(app,base_url=ORIGIN)
        self.assertEqual(client.post('/api/internal/contact/email',json={}).status_code,401)
        self.assertEqual(client.post('/api/internal/contact/email',json={'recipient':'other@example.com'},headers={'authorization':'Bearer '+secret}).status_code,422)
        self.assertEqual(client.post('/api/internal/contact/google',json={}).status_code,503)
        self.store.claim_enquiry_delivery.assert_not_called()
