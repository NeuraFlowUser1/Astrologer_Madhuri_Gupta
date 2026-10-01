"""Owner-bound records, broken provider responses and retry fencing.

All provider traffic is captured. Failure assertions check that a saved lease
cannot be reported complete, shared with another owner, or blindly recreated.
"""
import copy
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock,patch
from uuid import uuid4

import httpx

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.google_oauth import GoogleFailure
from backend.booking_engine.google_workspace import Workspace,WorkspaceFailure,DRIVE,TAB,TAB_ID,resource_id,event_id
from backend.booking_engine.google_records import prepare_owner_workbook,copy_booking_record,sheet_values
from backend.booking_engine.google_delivery import run_google_delivery_once
from backend.booking_engine.tests import test_google_workspace as fixtures


class WorkbookLeaseTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock();self.services=SimpleNamespace(google=SimpleNamespace(settings=SimpleNamespace(client_id='synthetic')))
        self.access=SimpleNamespace(grant=SimpleNamespace(subject='client-subject'))
        self.saved={'subject':'client-subject','action':'create','intent':str(uuid4()),'lease':str(uuid4())}
        self.store.claim_google_workbook.return_value=self.saved
        self.store.finish_google_workbook.return_value=True

    def call(self):
        return prepare_owner_workbook(self.store,self.services,'client')

    def test_missing_or_different_owner_never_creates_a_sheet(self):
        for saved,code in [(None,'google_workbook_unavailable'),({**self.saved,'subject':'another-owner'},'google_workbook_owner_mismatch')]:
            self.store.claim_google_workbook.return_value=saved
            with patch('backend.booking_engine.google_records.refresh_connection',return_value=self.access),patch('backend.booking_engine.google_records.Workspace') as workspace:
                with self.assertRaisesRegex(WorkspaceFailure,code):self.call()
                workspace.return_value.create_workbook.assert_not_called()
                self.store.finish_google_workbook.assert_not_called()

    def test_ready_record_returns_same_owned_sheet_without_a_write(self):
        self.saved.update(action='ready',spreadsheet_id='existing-sheet')
        with patch('backend.booking_engine.google_records.refresh_connection',return_value=self.access),patch('backend.booking_engine.google_records.Workspace') as workspace:
            self.assertEqual(self.call(),(workspace.return_value,self.saved))
            workspace.return_value.create_workbook.assert_not_called();workspace.return_value.prepare_workbook.assert_not_called()

    def test_discovery_reconciles_the_same_intent_and_fences_commit(self):
        self.saved['action']='discover'
        with patch('backend.booking_engine.google_records.refresh_connection',return_value=self.access),patch('backend.booking_engine.google_records.Workspace') as workspace:
            workspace.return_value.find_workbook.return_value='recovered-sheet'
            _,saved=self.call()
            self.assertEqual(saved['spreadsheet_id'],'recovered-sheet')
            workspace.return_value.find_workbook.assert_called_once_with(self.saved['intent'])
            workspace.return_value.create_workbook.assert_not_called()
            self.assertEqual(str(self.store.finish_google_workbook.call_args.args[1]),self.saved['lease'])

    def test_missing_discovery_unknown_action_and_lost_save_retain_uncertainty(self):
        for action,identifier,committed,code in [('discover',None,True,'google_workbook_creation_unresolved'),('unknown','sheet',True,'google_workbook_unavailable'),('create','sheet',False,'google_workbook_save_uncertain')]:
            self.saved['action']=action;self.store.finish_google_workbook.return_value=committed
            with patch('backend.booking_engine.google_records.refresh_connection',return_value=self.access),patch('backend.booking_engine.google_records.Workspace') as workspace:
                workspace.return_value.find_workbook.return_value=identifier;workspace.return_value.create_workbook.return_value=identifier
                with self.assertRaisesRegex(WorkspaceFailure,code) as error:self.call()
                if action!='unknown':self.assertTrue(error.exception.uncertain)

    def test_record_assignment_is_bound_to_owned_sheet_before_writing(self):
        job={'kind':'sheet_booking','recipient_role':'client_sheet','id':str(uuid4()),'payload':{'id':str(uuid4()),'revision':1,'state':'confirmed','service_snapshot':{'name':'Synthetic'},'starts_at':'2035-01-02T04:30:00Z','ends_at':'2035-01-02T05:00:00Z','full_name':'Synthetic','email':'test@example.invalid','phone':'+919876543210','amount_paise':100}}
        values=sheet_values(job);workspace=Mock()
        for assigned in [None,{'spreadsheet_id':'foreign-sheet'},dict(spreadsheet_id='owned-sheet',intent='fixed-intent',row=2,values=values)]:
            self.store.assign_sheet_row.return_value=assigned;workspace.reset_mock()
            with patch('backend.booking_engine.google_records.prepare_owner_workbook',return_value=(workspace,{'spreadsheet_id':'owned-sheet'})):
                if not assigned or assigned['spreadsheet_id']!='owned-sheet':
                    with self.assertRaisesRegex(WorkspaceFailure,'google_record_assignment_unavailable'):copy_booking_record(self.store,self.services,job)
                    workspace.write_booking_row.assert_not_called()
                else:
                    self.assertEqual(copy_booking_record(self.store,self.services,job),'owned-sheet')
                    workspace.write_booking_row.assert_called_once_with('owned-sheet','fixed-intent',2,values)
        for invalid in [{**job,'kind':'unknown'},{**job,'recipient_role':'calendar'}]:
            with self.assertRaisesRegex(WorkspaceFailure,'google_record_job_invalid'):copy_booking_record(self.store,self.services,invalid)


class DeliveryFencingTests(unittest.TestCase):
    def test_empty_queue_and_lost_completion_do_not_claim_delivery(self):
        store=Mock();store.claim_google_delivery.return_value=None
        self.assertEqual(run_google_delivery_once(store,Mock()),{'processed':0});store.finish_google_delivery.assert_not_called()
        store.claim_google_delivery.return_value={'kind':'sheet_booking','attempts':1}
        store.finish_google_delivery.return_value=False
        with patch('backend.booking_engine.google_delivery.copy_booking_record',return_value='same-sheet'):
            self.assertEqual(run_google_delivery_once(store,Mock()),{'processed':0,'retry':True})

    def test_calendar_waiting_preserves_short_retry_and_final_meeting_identity(self):
        for state,url,delay in [('waiting',None,15),('ready','https://meet.google.com/abc-defg-hij',15)]:
            store=Mock();job={'kind':'booking_calendar','attempts':1,'payload':{'id':'synthetic'}}
            store.claim_google_delivery.return_value=job;store.finish_google_delivery.return_value=True
            with patch('backend.booking_engine.google_delivery.refresh_connection'),patch('backend.booking_engine.google_delivery.Workspace') as workspace:
                workspace.return_value.ensure_meeting.return_value={'state':state,'event_id':'fixed-event','meet_url':url}
                result=run_google_delivery_once(store,Mock())
            self.assertEqual(result['processed'],1)
            self.assertEqual(store.finish_google_delivery.call_args.args[2:4],('fixed-event',url))
            if state=='waiting':self.assertEqual(store.finish_google_delivery.call_args.args[-1],delay)

    def test_cancellation_has_no_replacement_meeting_or_customer_invitation(self):
        store=Mock();job={'kind':'booking_cancelled','recipient_role':'calendar','attempts':2,'payload':{'id':'synthetic'}}
        store.claim_google_delivery.return_value=job;store.finish_google_delivery.return_value=True
        with patch('backend.booking_engine.google_delivery.refresh_connection'),patch('backend.booking_engine.google_delivery.Workspace') as workspace:
            self.assertEqual(run_google_delivery_once(store,Mock()),{'processed':1,'state':'done'})
            workspace.return_value.cancel_meeting.assert_called_once_with(job['payload']);workspace.return_value.ensure_meeting.assert_not_called()

    def test_failure_states_and_unknown_jobs_are_recorded_without_private_payload(self):
        for failure,state in [(WorkspaceFailure('google_row_conflict'),'attention'),(GoogleFailure('google_connection_unavailable'),'failed')]:
            store=Mock();job={'kind':'sheet_booking','attempts':3,'payload':{'email':'private@example.invalid'}}
            store.claim_google_delivery.return_value=job;store.finish_google_delivery.return_value=True
            with patch('backend.booking_engine.google_delivery.copy_booking_record',side_effect=failure):result=run_google_delivery_once(store,Mock())
            self.assertEqual(result,{'processed':1,'state':state});self.assertNotIn('private',str(result))
            self.assertEqual(store.finish_google_delivery.call_args.args[4],str(failure))
        store.claim_google_delivery.return_value={'kind':'unknown','attempts':1}
        self.assertEqual(run_google_delivery_once(store,Mock())['state'],'failed')

    def test_unknown_database_commit_propagates_without_false_success(self):
        store=Mock();store.claim_google_delivery.return_value={'kind':'sheet_booking','attempts':1}
        with patch('backend.booking_engine.google_delivery.copy_booking_record',side_effect=StorageUnavailable('unknown')):
            with self.assertRaises(StorageUnavailable):run_google_delivery_once(store,Mock())
        store.finish_google_delivery.assert_not_called()


class WorkspaceBoundaryTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    workspace=fixtures.WorkspaceTests.workspace
    event=fixtures.WorkspaceTests.event

    def test_endpoint_and_identifier_rejections_precede_authorization_forwarding(self):
        workspace=self.workspace([])
        for url in ['http://www.googleapis.com/drive/v3/files','https://evil.invalid/drive/v3/files',DRIVE+'?secret=x',DRIVE+'#x','https://www.googleapis.com/unknown']:
            with self.assertRaisesRegex(WorkspaceFailure,'google_endpoint_invalid'):workspace.request('GET',url)
        with self.assertRaises(WorkspaceFailure):workspace.request('PATCH',DRIVE)
        for value in [None,'','../sheet','x'*201]:
            with self.assertRaises(WorkspaceFailure):resource_id(value)
        for revision in [True,0,-1,'1']:
            with self.assertRaises(WorkspaceFailure):event_id(self.booking['id'],revision)
        self.assertEqual(self.requests,[])

    def test_response_bounds_and_bad_json_cannot_become_accepted_write(self):
        cases=[httpx.Response(503,json={'private':'do not disclose'}),httpx.Response(200,text='HTML'),httpx.Response(200,json=[]),httpx.Response(200,content=b'x'*262145,headers={'content-type':'application/json'}),httpx.Response(200,content=b'{bad',headers={'content-type':'application/json'})]
        for response in cases:
            requests=[]
            workspace=Workspace(self.access,transport=httpx.MockTransport(lambda request:(requests.append(request) or response)))
            with self.assertRaises(WorkspaceFailure) as error:workspace.request('POST',DRIVE,body={})
            self.assertTrue(error.exception.uncertain);self.assertEqual(len(requests),1)
            self.assertNotIn('private',str(error.exception))

    def test_expired_access_is_rejected_at_construction_and_again_before_call(self):
        from backend.booking_engine.google_oauth import Access
        stale=Access('synthetic',datetime.now(timezone.utc)-timedelta(seconds=1),self.grant)
        with self.assertRaisesRegex(WorkspaceFailure,'google_access_unavailable'):Workspace(stale)
        workspace=self.workspace([]);workspace.access=stale
        with self.assertRaisesRegex(WorkspaceFailure,'google_access_unavailable'):workspace.request('GET',DRIVE)
        self.assertEqual(self.requests,[])

    def test_meeting_failure_and_conditional_cancel_require_valid_provider_identity(self):
        event=self.event('failure')
        with self.assertRaisesRegex(WorkspaceFailure,'google_meeting_unavailable'):self.workspace([(200,event)]).ensure_meeting(self.booking)
        event=self.event();event.pop('etag')
        with self.assertRaisesRegex(WorkspaceFailure,'google_event_mismatch'):self.workspace([(200,event)]).cancel_meeting(self.booking)
        self.assertTrue(all(request.method!='DELETE' for request in self.requests))

    def test_workbook_layout_is_checked_before_any_header_rewrite(self):
        invalid=[{'sheets':[None]},{'sheets':[{'properties':None}]},{'sheets':[{'properties':{'sheetId':TAB_ID,'title':'Different'}}]},
          {'sheets':[{'properties':{'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':2,'columnCount':12}}}]}]
        for layout in invalid:
            self.requests=[]
            with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):
                self.workspace([(200,self.file),(200,layout)]).prepare_workbook('synthetic_sheet',self.intent)
            self.assertTrue(all(request.method=='GET' for request in self.requests))
        valid={'sheets':[{'properties':{'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':12}}}]}
        self.workspace([(200,self.file),(200,valid),(200,{})]).prepare_workbook('synthetic_sheet',self.intent)

    def test_invalid_rows_never_touch_remote_workbook(self):
        values=sheet_values({'id':str(uuid4()),'payload':self.booking})
        for row,content in [(True,values),(1,values),(10001,values),(2,[]),(2,[0]*12),(2,['wrong-project']+values[1:]),(2,[values[0],'bad-id']+values[2:])]:
            with self.assertRaisesRegex(WorkspaceFailure,'google_row_invalid'):self.workspace([]).write_booking_row('synthetic_sheet',self.intent,row,content)
        self.assertEqual(self.requests,[])

    def test_changed_file_identity_cannot_redirect_preparation_or_write(self):
        changed=copy.deepcopy(self.file);changed['id']='other-sheet'
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_owner_mismatch'):
            self.workspace([(200,changed)]).prepare_workbook('synthetic_sheet',self.intent)
        values=sheet_values({'id':str(uuid4()),'payload':self.booking})
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_owner_mismatch'):
            self.workspace([(200,changed)]).write_booking_row('synthetic_sheet',self.intent,2,values)
