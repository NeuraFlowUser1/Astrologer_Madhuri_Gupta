"""Owned enquiry rows, lost replies and changed Google data; no provider traffic."""
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from appointment_system.configuration import installation
from appointment_system.connection import StorageUnavailable
from appointment_system.contact_delivery import run_contact_google_once
from appointment_system.contact_records import (
    FULL_HEADERS, HEADERS, CONTEXT_HEADERS, TAB_ID, copy_enquiry_record,
    enquiry_values, prepare_enquiry_tab, write_enquiry_row,
)
from appointment_system.google_oauth import Access, Grant, OWNERS, scopes_for
from appointment_system.google_workspace import PROJECT, Workspace, WorkspaceFailure


class EnquiryRecords(unittest.TestCase):
    def setUp(self):
        self.job = dict(id=str(uuid4()), request_id=str(uuid4()), kind='client_sheet', attempts=1,
            verified_at='2026-10-01T12:00:00Z', payload=dict(name='=literal name',
                email='enquiry@example.invalid', phone='+919876543210', subject='Consultation',
                message='Please call about a consultation.', source='contact', service_interest='',
                kind='contact', dob='', location=''))
        self.grant = Grant('client', 'synthetic-subject', OWNERS['client'], 'synthetic-refresh', scopes_for('client'))
        self.access = Access('synthetic-access', datetime.now(timezone.utc)+timedelta(hours=1), self.grant)
        self.saved = dict(role='client', subject=self.grant.subject, client_id='synthetic-client',
            intent=str(uuid4()), generation=str(uuid4()), volume_number=1, layout_version=3,
            grant_id=str(uuid4()), spreadsheet_id='synthetic_sheet', action='ready', row=24)
        self.values = enquiry_values(self.job, 3)
        self.file = dict(id='synthetic_sheet', mimeType='application/vnd.google-apps.spreadsheet',
            trashed=False, owners=[dict(emailAddress=OWNERS['client'])], permissions=[dict(type='user', role='owner', emailAddress=OWNERS['client'])],
            appProperties=dict(project=PROJECT, role='client', intent=self.saved['intent'],
                generation=self.saved['generation'], volume='1', layout='3', installation=installation()['installation_id']))
        self.tab = dict(sheetId=TAB_ID, title='Enquiries', gridProperties=dict(rowCount=10000, columnCount=15))
        self.services = SimpleNamespace(google=SimpleNamespace(settings=SimpleNamespace(client_id='synthetic-client')))
        self.store = Mock()
        self.store.mapped_google_row.return_value = self.saved
        self.store.assign_enquiry_row.return_value = dict(self.saved, values=self.values)
        self.store.claim_enquiry_delivery.return_value = self.job
        self.store.finish_enquiry_delivery.return_value = True
        self.requests = []

    def transport(self, replies):
        def handler(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic-access')
            result = replies.pop(0)
            if isinstance(result, Exception):
                raise result
            return httpx.Response(result[0], json=result[1])
        return httpx.MockTransport(handler)

    def workspace(self, replies):
        workspace = Workspace(self.access, transport=self.transport(replies))
        workspace.bind_volume(self.saved)
        return workspace

    def prepared(self, values=None):
        return [(200, self.file), (200, dict(sheets=[dict(properties=self.tab)])),
            (200, dict(values=[FULL_HEADERS])), (200, self.file), (200, dict(values=values or []))]

    def test_saved_owner_row_and_payload_are_reused_after_a_lost_write_reply(self):
        # The first PUT reached Sheets; its response was lost. The next delivery
        # observes that exact fixed row and completes without a second write.
        replies = self.prepared()+[httpx.ReadTimeout('synthetic lost reply')]+self.prepared([self.values[:-2]])
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access):
            first = run_contact_google_once(self.store, self.services, transport=self.transport(replies), resource='client_sheet')
            second = run_contact_google_once(self.store, self.services, transport=self.transport(replies), resource='client_sheet')
        self.assertEqual(first, dict(processed=1, retry=False))
        self.assertEqual(second, dict(processed=1, retry=False))
        self.assertEqual(len(replies), 0)
        writes = [r for r in self.requests if r.method == 'PUT']
        self.assertEqual(len(writes), 1)
        self.assertIn('A24:O24', writes[0].url.path)
        self.assertEqual(writes[0].url.params['valueInputOption'], 'RAW')
        self.assertEqual(json.loads(writes[0].content)['values'], [self.values])
        completions = self.store.finish_enquiry_delivery.call_args_list
        self.assertIsNone(completions[0].args[1])
        self.assertIsNotNone(completions[0].args[2])
        self.assertEqual(completions[1].args[1:4], ('synthetic_sheet', None, False))

    def test_existing_frozen_values_win_over_later_job_changes(self):
        self.saved['values'] = self.values
        self.job['payload']['name'] = 'Changed later'
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access) as refresh:
            self.assertEqual(copy_enquiry_record(self.store, self.services, self.job,
                transport=self.transport(self.prepared([self.values]))), 'synthetic_sheet')
        self.assertEqual(self.store.assign_enquiry_row.call_args.args[2], self.values)
        self.assertEqual(refresh.call_args.kwargs['grant_id'], self.saved['grant_id'])
        self.assertFalse(any(r.method != 'GET' for r in self.requests))

    def test_different_owner_or_saved_subject_never_writes_or_creates_a_replacement(self):
        for mismatch in ('owner', 'subject', 'client'):
            with self.subTest(mismatch=mismatch):
                self.setUp()
                if mismatch == 'owner': self.file['owners'][0]['emailAddress'] = OWNERS['agency']
                if mismatch == 'subject': self.saved['subject'] = 'another-subject'
                if mismatch == 'client': self.saved['client_id'] = 'another-client'
                with patch('appointment_system.google_records.refresh_connection', return_value=self.access):
                    with self.assertRaisesRegex(WorkspaceFailure, 'google_workbook_owner_mismatch'):
                        copy_enquiry_record(self.store, self.services, self.job, transport=self.transport([(200, self.file)]))
                self.assertFalse(any(r.method != 'GET' for r in self.requests))
                self.store.claim_google_workbook.assert_not_called()

    def test_changed_row_requires_attention_without_overwriting_customer_data(self):
        changed = list(self.values); changed[8] = 'Staff has changed this cell'
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access):
            result = run_contact_google_once(self.store, self.services, transport=self.transport(self.prepared([changed])))
        self.assertEqual(result, dict(processed=1, retry=False))
        self.assertEqual(self.store.finish_enquiry_delivery.call_args.args[1:4], (None, 'google_row_conflict', True))
        self.assertFalse(any(r.method != 'GET' for r in self.requests))

    def test_unapproved_sharing_stops_enquiry_history_work_for_private_review(self):
        self.file['permissions'].append(dict(type='group',role='reader',emailAddress='foreign@example.test'))
        with patch('appointment_system.google_records.refresh_connection',return_value=self.access):
            result=run_contact_google_once(self.store,self.services,transport=self.transport([(200,self.file)]))
        self.assertEqual(result,dict(processed=1,retry=False))
        self.assertEqual(self.store.finish_enquiry_delivery.call_args.args[1:4],
                         (None,'google_workbook_sharing_mismatch',True))
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.requests[0].method,'GET')

    def test_missing_tab_is_created_once_with_raw_headers_before_the_assigned_row(self):
        replies = [(200, self.file), (200, dict(sheets=[])), (200, {}), (200, {}), (200, {})]
        prepare_enquiry_tab(self.workspace(replies), 'synthetic_sheet', self.saved['intent'], 3)
        create = json.loads(self.requests[2].content)['requests'][0]['addSheet']['properties']
        self.assertEqual(create['sheetId'], TAB_ID)
        self.assertEqual(create['gridProperties'], dict(rowCount=10000, columnCount=15, frozenRowCount=1))
        self.assertEqual(json.loads(self.requests[4].content)['values'], [FULL_HEADERS])
        self.assertEqual(self.requests[4].url.params['valueInputOption'], 'RAW')

    def test_changed_tab_or_headers_are_not_repaired_over_existing_data(self):
        for mutation in ('id', 'title', 'rows', 'columns', 'duplicate', 'malformed', 'header'):
            with self.subTest(mutation=mutation):
                tab = copy.deepcopy(self.tab); tabs = [dict(properties=tab)]
                if mutation == 'id': tab['sheetId'] += 1
                if mutation == 'title': tab['title'] = 'Different tab'
                if mutation == 'rows': tab['gridProperties']['rowCount'] = 99
                if mutation == 'columns': tab['gridProperties']['columnCount'] = 10
                if mutation == 'duplicate': tabs *= 2
                if mutation == 'malformed': tabs = [None]
                replies = [(200, self.file), (200, dict(sheets=tabs)), (200, dict(values=[['Changed header']]))]
                with self.assertRaisesRegex(WorkspaceFailure, 'google_workbook_layout_changed'):
                    prepare_enquiry_tab(self.workspace(replies), 'synthetic_sheet', self.saved['intent'], 3)
                self.assertFalse(any(r.method != 'GET' for r in self.requests))
        with self.assertRaisesRegex(WorkspaceFailure, 'google_workbook_layout_changed'):
            prepare_enquiry_tab(self.workspace([]), 'synthetic_sheet', self.saved['intent'], 99)

    def test_invalid_assignment_cannot_select_another_file_or_row(self):
        for mutation in ('absent', 'file', 'intent'):
            with self.subTest(mutation=mutation):
                assigned = dict(self.saved, values=self.values)
                if mutation == 'absent': assigned = None
                if mutation == 'file': assigned['spreadsheet_id'] = 'another_sheet'
                if mutation == 'intent': assigned['intent'] = str(uuid4())
                self.store.assign_enquiry_row.return_value = assigned
                with patch('appointment_system.google_records.refresh_connection', return_value=self.access):
                    with self.assertRaisesRegex(WorkspaceFailure, 'google_record_assignment_unavailable'):
                        copy_enquiry_record(self.store, self.services, self.job, transport=self.transport([]))
        for row in (True, 1, 10001, '24'):
            with self.assertRaisesRegex(WorkspaceFailure, 'google_row_invalid'):
                write_enquiry_row(self.workspace([]), dict(self.saved, row=row, values=self.values))
        for changed in ([*self.values[:1], 'not-a-uuid', *self.values[2:]], ['another-project', *self.values[1:]],
                        [*self.values[:8], 'x'*4001, *self.values[9:]], self.values[:-1]):
            with self.assertRaisesRegex(WorkspaceFailure, 'google_row_invalid'):
                write_enquiry_row(self.workspace([]), dict(self.saved, values=changed))
        self.assertEqual(self.requests, [])

    def test_old_layouts_preserve_their_exact_width_and_invalid_job_is_bounded(self):
        for layout, headers in ((1, HEADERS), (2, CONTEXT_HEADERS), (3, FULL_HEADERS)):
            self.assertEqual(len(enquiry_values(self.job, layout)), len(headers))
        for job, layout in (({}, 1), (dict(self.job, id='not-a-uuid'), 1), (self.job, 99)):
            with self.assertRaisesRegex(WorkspaceFailure, 'google_row_invalid'): enquiry_values(job, layout)
        with self.assertRaisesRegex(WorkspaceFailure, 'google_record_job_invalid'):
            copy_enquiry_record(self.store, self.services, dict(self.job, kind='calendar'))

    def test_empty_lane_and_unknown_database_completion_do_not_forge_success(self):
        self.store.claim_enquiry_delivery.return_value = None
        self.assertEqual(run_contact_google_once(self.store, self.services), dict(processed=0))
        with self.assertRaisesRegex(ValueError, 'contact_lane_invalid'):
            run_contact_google_once(self.store, self.services, resource='calendar')
        self.store.claim_enquiry_delivery.return_value = self.job
        self.store.finish_enquiry_delivery.return_value = False
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access):
            self.assertEqual(run_contact_google_once(self.store, self.services,
                transport=self.transport(self.prepared([self.values]))), dict(processed=0, retry=True))
        self.store.finish_enquiry_delivery.reset_mock()
        with patch('appointment_system.google_records.refresh_connection', side_effect=StorageUnavailable('synthetic')):
            with self.assertRaises(StorageUnavailable): run_contact_google_once(self.store, self.services)
        self.store.finish_enquiry_delivery.assert_not_called()
