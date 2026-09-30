import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.google_oauth import Access, Grant, GoogleFailure, OWNERS, scopes_for
from backend.booking_engine.google_workspace import Workspace, WorkspaceFailure, PROJECT, TAB_ID, TAB, event_id
from backend.booking_engine.google_records import prepare_owner_workbook, sheet_values
from backend.booking_engine.google_delivery import run_google_delivery_once


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.grant = Grant('client','subject',OWNERS['client'],'synthetic-refresh',scopes_for('client'))
        self.access = Access('synthetic-access',datetime.now(timezone.utc)+timedelta(hours=1),self.grant)
        starts=datetime.now(timezone.utc)+timedelta(days=2)
        self.booking = dict(id=str(uuid4()), revision=1, state='confirmed',service_snapshot={'name':'Consultation'},
            starts_at=starts.isoformat(),ends_at=(starts+timedelta(minutes=30)).isoformat(),
            full_name='=formula',email='test@example.invalid',phone='+919876543210',amount_paise=250000)
        self.intent = str(uuid4())
        self.file = dict(id='synthetic_sheet',mimeType='application/vnd.google-apps.spreadsheet',trashed=False,
            owners=[{'emailAddress':OWNERS['client']}],appProperties={'project':PROJECT,'role':'client','intent':self.intent})
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

    def test_create_meeting_and_retry_reuses_same_event_without_inviting_customer(self):
        w=self.workspace([(404,None),(200,self.event()),(200,self.event())])
        self.assertEqual(w.ensure_meeting(self.booking)['state'],'ready')
        self.assertEqual(w.ensure_meeting(self.booking)['state'],'ready')
        self.assertEqual([r.method for r in self.requests],['GET','POST','GET'])
        body=json.loads(self.requests[1].content)
        self.assertNotIn('attendees',body)
        self.assertEqual(self.requests[1].url.params['sendUpdates'],'none')
        self.assertEqual(body['id'],event_id(self.booking['id'],1))
        self.assertRegex(body['id'],r'^[a-v0-9]{5,1024}$')
        self.assertNotEqual(body['id'],event_id(self.booking['id'],2))

    def test_conflict_reconciles_existing_meeting_and_pending_is_not_ready(self):
        w=self.workspace([(404,None),(409,None),(200,self.event('pending'))])
        self.assertEqual(w.ensure_meeting(self.booking),{'state':'waiting','event_id':event_id(self.booking['id'],1),'meet_url':None})
        self.assertEqual(len(self.requests),3)

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
        values=sheet_values({'id':str(uuid4()),'payload':self.booking})
        w=self.workspace([(200,self.file),(200,{}),(200,{}),(200,self.file),(200,{'values':[values]})])
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
        with patch('backend.booking_engine.google_records.refresh_connection',return_value=self.access):
            with patch('backend.booking_engine.google_records.Workspace') as factory:
                factory.return_value.find_workbook.return_value=None
                with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_creation_unresolved'):
                    prepare_owner_workbook(store,services,'client')
                factory.return_value.create_workbook.assert_not_called()
                store.finish_google_workbook.assert_not_called()

    def test_refresh_failure_does_not_consume_workbook_intent(self):
        store=Mock()
        with patch('backend.booking_engine.google_records.refresh_connection',side_effect=GoogleFailure('google_request_failed')):
            with self.assertRaises(GoogleFailure): prepare_owner_workbook(store,Mock(),'client')
        store.claim_google_workbook.assert_not_called()

    def test_worker_saves_provider_failure_but_not_unknown_storage_completion(self):
        store=Mock(); store.claim_google_delivery.return_value={'id':str(uuid4()),'kind':'booking_calendar','attempts':1,'payload':self.booking}
        store.finish_google_delivery.return_value=True
        with patch('backend.booking_engine.google_delivery.refresh_connection',side_effect=GoogleFailure('google_request_failed')):
            self.assertEqual(run_google_delivery_once(store,Mock()),{'processed':1,'state':'failed'})
        self.assertEqual(store.finish_google_delivery.call_args.args[-2],'google_request_failed')
        store.finish_google_delivery.reset_mock()
        with patch('backend.booking_engine.google_delivery.refresh_connection',side_effect=StorageUnavailable('uncertain')):
            with self.assertRaises(StorageUnavailable): run_google_delivery_once(store,Mock())
        store.finish_google_delivery.assert_not_called()


if __name__=='__main__': unittest.main()
