import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from appointment_system.connection import StorageUnavailable
from appointment_system.google_oauth import Access, Grant, GoogleFailure, OWNERS, scopes_for
from appointment_system.google_workspace import Workspace, WorkspaceFailure, PROJECT, TAB_ID, TAB, event_id
from appointment_system.google_records import prepare_owner_workbook, sheet_values
from appointment_system.google_delivery import run_google_delivery_once


class WorkspaceTests(unittest.TestCase):
    def test_missing_customer_email_keeps_meeting_creation_without_a_fake_attendee(self):
        body=Workspace(self.access).calendar_body(dict(self.booking,email=None))
        self.assertEqual(body['attendees'],[]);self.assertIn('conferenceData',body)
        self.assertNotIn('None',json.dumps(body));self.assertIn('hangoutsMeet',json.dumps(body))

    def setUp(self):
        self.grant = Grant('client','subject',OWNERS['client'],'synthetic-refresh',scopes_for('client'))
        self.access = Access('synthetic-access',datetime.now(timezone.utc)+timedelta(hours=1),self.grant)
        starts=datetime.now(timezone.utc)+timedelta(days=2)
        self.booking = dict(id=str(uuid4()), revision=1, state='confirmed',service_snapshot={'name':'Consultation'},
            starts_at=starts.isoformat(),ends_at=(starts+timedelta(minutes=30)).isoformat(),
            full_name='=formula',email='test@example.invalid',phone='+919876543210',amount_paise=250000,practice_timezone='Asia/Kolkata')
        self.intent = str(uuid4())
        self.file = dict(id='synthetic_sheet',mimeType='application/vnd.google-apps.spreadsheet',trashed=False,
            owners=[{'emailAddress':OWNERS['client']}],permissions=[{'type':'user','role':'owner','emailAddress':OWNERS['client']}],appProperties={'project':PROJECT,'role':'client','intent':self.intent})
        self.requests = []

    def workspace(self, responses):
        def handler(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'],'Bearer synthetic-access')
            result = responses.pop(0)
            if isinstance(result,Exception):
                raise result
            status, body = result
            return httpx.Response(status,json=body) if body is not None else httpx.Response(status)
        return Workspace(self.access,transport=httpx.MockTransport(handler))

    def event(self, state='success'):
        event = Workspace(self.access).calendar_body(self.booking)
        event.update(organizer={'email':OWNERS['client']},etag='"synthetic"')
        event['conferenceData']={'createRequest':{'status':{'statusCode':state}},
            'conferenceSolution':{'key':{'type':'hangoutsMeet'}},
            'entryPoints':[{'entryPointType':'video','uri':'https://meet.google.com/abc-defg-hij'}]}
        return event

    def test_create_meeting_invites_customer_once_and_retry_reuses_same_event(self):
        w=self.workspace([(404,None),(200,self.event()),(200,self.event())])
        self.assertEqual(w.ensure_meeting(self.booking)['state'],'ready')
        self.assertEqual(w.ensure_meeting(self.booking)['state'],'ready')
        self.assertEqual([r.method for r in self.requests],['GET','POST','GET'])
        body=json.loads(self.requests[1].content)
        self.assertEqual(body['attendees'],[{'email':self.booking['email']}])
        self.assertNotIn(self.booking['phone'],body['description'])
        self.assertNotIn(self.booking['full_name'],body['description'])
        self.assertEqual(self.requests[1].url.params['sendUpdates'],'all')
        self.assertEqual(body['id'],event_id(self.booking['id'],1))
        self.assertRegex(body['id'],r'^[a-v0-9]{5,1024}$')
        self.assertNotEqual(body['id'],event_id(self.booking['id'],2))

    def test_conflict_reconciles_existing_meeting_and_pending_is_not_ready(self):
        w=self.workspace([(404,None),(409,None),(200,self.event('pending'))])
        self.assertEqual(w.ensure_meeting(self.booking),{'state':'waiting','event_id':event_id(self.booking['id'],1),'meet_url':None})
        self.assertEqual(len(self.requests),3)

    def test_customer_is_not_repeated_as_the_calendar_owner_and_private_fields_stay_out(self):
        body=Workspace(self.access).calendar_body(dict(self.booking,email=OWNERS['client'],birth_details='private birth notes'))
        self.assertEqual(body['attendees'],[])
        self.assertNotIn('private birth',json.dumps(body))
        for field in ('guestsCanInviteOthers','guestsCanModify','guestsCanSeeOtherGuests'):
            self.assertIs(body[field],False)

    def test_wrong_owner_revision_time_and_meet_link_are_rejected(self):
        for mutation in ('owner','revision','time','link','malformed'):
            with self.subTest(mutation=mutation):
                event=self.event()
                if mutation=='owner': event['organizer']['email']=OWNERS['agency']
                if mutation=='revision': event['extendedProperties']['private']['revision']='2'
                if mutation=='time': event['start']['dateTime']='2026-10-05T06:00:00Z'
                if mutation=='link': event['conferenceData']['entryPoints'][0]['uri']='https://example.invalid/meeting'
                if mutation=='malformed': event['conferenceData']['entryPoints']=[None]
                with self.assertRaises(WorkspaceFailure): self.workspace([(200,event)]).ensure_meeting(self.booking)

    def test_ambiguous_post_is_not_repeated_inside_request(self):
        w=self.workspace([(404,None),httpx.ReadTimeout('synthetic')])
        with self.assertRaises(WorkspaceFailure) as error: w.ensure_meeting(self.booking)
        self.assertTrue(error.exception.uncertain)
        self.assertEqual(len(self.requests),2)

    def test_cancel_is_conditional_and_idempotent(self):
        w=self.workspace([(200,self.event()),(204,None),(404,None)])
        w.cancel_meeting(self.booking); w.cancel_meeting(self.booking)
        self.assertEqual(self.requests[1].headers['if-match'],'"synthetic"')
        self.assertEqual([r.method for r in self.requests],['GET','DELETE','GET'])

    def test_expired_appointment_does_not_create_a_meeting_on_delayed_retry(self):
        self.booking.update(starts_at='2020-01-01T04:30:00Z',ends_at='2020-01-01T05:00:00Z')
        with self.assertRaisesRegex(WorkspaceFailure,'google_appointment_ended'):
            self.workspace([]).ensure_meeting(self.booking)
        self.assertEqual(self.requests,[])

    def test_agency_cannot_use_client_calendar(self):
        self.access=Access('synthetic',self.access.expires_at,
            Grant('agency','agency-subject',OWNERS['agency'],'refresh',scopes_for('agency')))
        with self.assertRaises(WorkspaceFailure): self.workspace([]).ensure_meeting(self.booking)
        self.assertEqual(self.requests,[])

    def test_workbook_creation_owned_by_client_and_not_shared(self):
        w=self.workspace([(200,self.file)])
        self.assertEqual(w.create_workbook(self.intent),'synthetic_sheet')
        self.assertEqual(json.loads(self.requests[0].content)['appProperties']['role'],'client')
        wrong=copy.deepcopy(self.file); wrong['owners'][0]['emailAddress']=OWNERS['agency']
        with self.assertRaises(WorkspaceFailure): w.validate_workbook(wrong,self.intent)
        self.assertEqual(len(self.requests),1)

    def test_discovery_rejects_ambiguous_workbooks(self):
        for files in ([self.file,self.file],None):
            with self.assertRaises(WorkspaceFailure): self.workspace([(200,{'files':files})]).find_workbook(self.intent)
        self.assertIsNone(self.workspace([(200,{'files':[]})]).find_workbook(self.intent))

    def test_sheet_retry_uses_fixed_raw_row_and_does_not_overwrite_conflict(self):
        values=sheet_values({'id':str(uuid4()),'payload':self.booking},layout_version=1)
        w=self.workspace([(200,self.file),(200,{}),(200,{}),(200,{'values':[values]}),(200,self.file),(200,{'values':[values]})])
        w.write_booking_row('synthetic_sheet',self.intent,2,values)
        w.write_booking_row('synthetic_sheet',self.intent,2,values)
        writes=[r for r in self.requests if r.method=='PUT']
        self.assertEqual(len(writes),1)
        self.assertEqual(writes[0].url.params['valueInputOption'],'RAW')
        self.assertEqual(json.loads(writes[0].content)['values'][0][8],'=formula')
        with self.assertRaisesRegex(WorkspaceFailure,'google_row_conflict'):
            self.workspace([(200,self.file),(200,{'values':[['someone else']]})]).write_booking_row('synthetic_sheet',self.intent,2,values)

    def test_existing_tab_layout_is_checked(self):
        tab={'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':100,'columnCount':12}}
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):
            self.workspace([(200,self.file),(200,{'sheets':[{'properties':tab}]})]).prepare_workbook('synthetic_sheet',self.intent)

    def test_creation_intent_recovery_never_posts_again(self):
        store=Mock(); services=SimpleNamespace(google=SimpleNamespace(settings=SimpleNamespace(client_id='synthetic')))
        store.claim_google_workbook.return_value=dict(action='discover',subject='subject',intent=self.intent,lease=str(uuid4()))
        with patch('appointment_system.google_records.refresh_connection',return_value=self.access):
            with patch('appointment_system.google_records.Workspace') as factory:
                factory.return_value.find_workbook.return_value=None
                with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_creation_unresolved'):
                    prepare_owner_workbook(store,services,'client')
                factory.return_value.create_workbook.assert_not_called()
                store.finish_google_workbook.assert_not_called()

    def test_refresh_failure_does_not_consume_workbook_intent(self):
        store=Mock()
        with patch('appointment_system.google_records.refresh_connection',side_effect=GoogleFailure('google_request_failed')):
            with self.assertRaises(GoogleFailure): prepare_owner_workbook(store,Mock(),'client')
        store.claim_google_workbook.assert_not_called()

    def test_worker_saves_provider_failure_but_not_unknown_storage_completion(self):
        store=Mock(); store.claim_google_delivery.return_value={'id':str(uuid4()),'kind':'booking_calendar','recipient_role':'calendar','attempts':1,'payload':self.booking}
        store.finish_google_delivery.return_value=True
        with patch('appointment_system.google_delivery.refresh_connection',side_effect=GoogleFailure('google_request_failed')):
            self.assertEqual(run_google_delivery_once(store,Mock()),{'processed':1,'state':'failed'})
        self.assertEqual(store.finish_google_delivery.call_args.args[-2],'google_request_failed')
        store.finish_google_delivery.reset_mock()
        with patch('appointment_system.google_delivery.refresh_connection',side_effect=StorageUnavailable('uncertain')):
            with self.assertRaises(StorageUnavailable): run_google_delivery_once(store,Mock())
        store.finish_google_delivery.assert_not_called()

    def test_wrong_or_expired_owner_never_sends_a_google_request(self):
        for access in (None, Access('token', datetime.now(timezone.utc)-timedelta(seconds=1), self.grant)):
            with self.subTest(access_type=type(access).__name__), self.assertRaisesRegex(WorkspaceFailure,'google_access_unavailable'):
                Workspace(access)
        with self.assertRaisesRegex(GoogleFailure,'google_grant_invalid'):
            Grant('client','subject',OWNERS['agency'],'refresh',scopes_for('client'))
        w=self.workspace([])
        w.access=Access('token',datetime.now(timezone.utc)-timedelta(seconds=1),self.grant)
        with self.assertRaisesRegex(WorkspaceFailure,'google_access_unavailable'):
            w.find_workbook(self.intent)
        self.assertEqual(self.requests,[])

    def test_unexpected_google_responses_keep_write_uncertainty_without_retrying(self):
        from appointment_system.google_workspace import DRIVE
        for method in ('GET','POST'):
            for response in (httpx.Response(503,json={'private':'do not log'}),
                             httpx.Response(200,text='private response'),
                             httpx.Response(200,json=[]),
                             httpx.Response(200,content=b'{broken',headers={'content-type':'application/json'}),
                             httpx.Response(200,json={'oversized':'x'*262145})):
                calls=[]
                def serve(request):
                    calls.append(request)
                    return response
                with self.subTest(method=method,status=response.status_code), self.assertRaises(WorkspaceFailure) as error:
                    Workspace(self.access,transport=httpx.MockTransport(serve)).request(method,DRIVE)
                self.assertEqual(error.exception.uncertain,method!='GET')
                self.assertNotIn('private',str(error.exception))
                self.assertEqual(len(calls),1)

    def test_requests_reject_foreign_endpoints_and_unsupported_actions(self):
        from appointment_system.google_workspace import DRIVE
        for method,url in (('GET','http://www.googleapis.com/drive/v3/files'),
                           ('GET','https://www.googleapis.com.example.invalid/drive/v3/files'),
                           ('GET',DRIVE+'?token=secret'),('GET',DRIVE+'#fragment'),
                           ('PATCH',DRIVE),('GET','https://www.googleapis.com/unrelated')):
            with self.subTest(method=method,url=url), self.assertRaisesRegex(WorkspaceFailure,'google_endpoint_invalid'):
                self.workspace([]).request(method,url)
        self.assertEqual(self.requests,[])

    def test_failed_conference_and_missing_cancellation_version_are_controlled(self):
        for state in ('failure',None):
            with self.subTest(state=state), self.assertRaisesRegex(WorkspaceFailure,'google_meeting_unavailable'):
                self.workspace([(200,self.event(state))]).ensure_meeting(self.booking)
        event=self.event(); event.pop('etag')
        w=self.workspace([(200,event)])
        before=len(self.requests)
        with self.assertRaisesRegex(WorkspaceFailure,'google_event_mismatch'):
            w.cancel_meeting(self.booking)
        self.assertEqual(len(self.requests)-before,1)
        event['status']='cancelled'
        self.workspace([(200,event)]).cancel_meeting(self.booking)
        self.workspace([(410,None)]).cancel_meeting(self.booking)
        self.assertNotIn('DELETE',[r.method for r in self.requests])

    def test_workbook_volume_rejects_wrong_identity_and_invalid_layout_types(self):
        base=dict(role='client',volume_number=1,layout_version=1,generation=str(uuid4()),intent=self.intent)
        for change in ({'role':'agency'},{'volume_number':True},{'volume_number':0},
                       {'layout_version':True},{'layout_version':1.0},{'layout_version':5},
                       {'generation':'bad'},{'intent':'bad'},{'workbook_protocol':'unknown'},
                       {'workbook_protocol':'legacy-sarsa-workbook-v2'}):
            with self.subTest(change=change), self.assertRaisesRegex(WorkspaceFailure,'google_workbook_identity_invalid'):
                self.workspace([]).bind_volume(base|change)
        w=self.workspace([]);w.bind_volume(base)
        base['intent']=str(uuid4())
        self.assertEqual(w.workbook_markers(self.intent)['intent'],self.intent)
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_identity_invalid'):
            w.workbook_markers(base['intent'])
        self.assertEqual(self.requests,[])

    def test_capacity_requires_known_usage_and_room_for_next_workbook(self):
        for quota in (None,{}, {'usage':-1},{'usage':'unknown'}, {'usage':'10','limit':'unknown'},
                      {'usage':'100','limit':'100'}, {'usage':'0','limit':str(1048575)}):
            with self.subTest(quota=quota),self.assertRaisesRegex(WorkspaceFailure,'google_drive_capacity_required'):
                self.workspace([(200,{'storageQuota':quota})]).check_capacity()
        self.assertEqual(self.workspace([(200,{'storageQuota':{'usage':'20'}})]).check_capacity(),
                         {'used_bytes':20,'limit_bytes':None})
        self.assertEqual(self.workspace([(200,{'storageQuota':{'usage':'20','limit':str(20+1048576)}})]).check_capacity(),
                         {'used_bytes':20,'limit_bytes':20+1048576})

    def test_malformed_tab_dimensions_are_reported_without_writing(self):
        for grid in (None,[],{'rowCount':'many','columnCount':12},{'rowCount':10000,'columnCount':None}):
            tab={'sheetId':TAB_ID,'title':TAB,'gridProperties':grid}
            before=len(self.requests)
            with self.subTest(grid=grid),self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):
                self.workspace([(200,self.file),(200,{'sheets':[{'properties':tab}]})]).prepare_workbook('synthetic_sheet',self.intent)
            self.assertEqual([r.method for r in self.requests[before:]],['GET','GET'])

    def test_existing_workbook_headers_are_preserved_and_ambiguous_tabs_refused(self):
        from appointment_system.google_workspace import HEADERS
        tab={'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':12}}
        self.workspace([(200,self.file),(200,{'sheets':[{'properties':tab}]}),
                        (200,{'values':[HEADERS]})]).prepare_workbook('synthetic_sheet',self.intent)
        self.assertEqual([r.method for r in self.requests],['GET','GET','GET'])
        for sheets in ([{'properties':tab},{'properties':tab}], [{'properties':dict(tab,sheetId=7)}],
                       [{'properties':dict(tab,title='Someone else')}],[{}],[{'properties':None}],None):
            with self.subTest(sheets=sheets),self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):
                self.workspace([(200,self.file),(200,{'sheets':sheets})]).prepare_workbook('synthetic_sheet',self.intent)

    def test_new_tab_and_headers_use_fixed_addresses_and_raw_values(self):
        from appointment_system.google_workspace import HEADERS
        self.workspace([(200,self.file),(200,{}),(200,{}),(200,{}),(200,{})]).prepare_workbook('synthetic_sheet',self.intent)
        self.assertEqual([r.method for r in self.requests],['GET','GET','POST','GET','PUT'])
        request=self.requests[-1]
        self.assertEqual(request.url.params['valueInputOption'],'RAW')
        self.assertEqual(json.loads(request.content),{'values':[HEADERS]})

    def test_row_identity_and_readback_are_required_before_reporting_success(self):
        values=sheet_values({'id':str(uuid4()),'payload':self.booking},layout_version=1)
        for row,changed in ((True,values),(1,values),(10001,values),(2,values[:-1]),
                            (2,['wrong-project']+values[1:]),(2,values[:1]+['bad-id']+values[2:]),
                            (2,values[:8]+['x'*4001]+values[9:])):
            with self.subTest(row=row,fields=len(changed)),self.assertRaisesRegex(WorkspaceFailure,'google_row_invalid'):
                self.workspace([]).write_booking_row('synthetic_sheet',self.intent,row,changed)
        self.assertEqual(self.requests,[])
        with self.assertRaisesRegex(WorkspaceFailure,'google_sheet_readback_unresolved') as error:
            self.workspace([(200,self.file),(200,{}),(200,{}),(200,{})]).write_booking_row('synthetic_sheet',self.intent,2,values)
        self.assertTrue(error.exception.uncertain)
        self.assertEqual([r.method for r in self.requests],['GET','GET','PUT','GET'])


if __name__=='__main__': unittest.main()
