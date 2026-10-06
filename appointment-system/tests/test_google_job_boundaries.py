"""Google orchestration preserves ownership, retry identity and uncertain results.

Provider/database ports are synthetic here; transport and native transaction
proofs remain in the existing workspace and SQL resource suites.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from appointment_system.connection import StorageUnavailable
from appointment_system.google_delivery import run_google_delivery_once
from appointment_system.google_oauth import GoogleFailure
from appointment_system.google_records import prepare_owner_workbook, workspace_for_record, copy_booking_record
from appointment_system.google_workspace import WorkspaceFailure


class GoogleJobBoundaries(TestCase):
    def setUp(self):
        self.store = Mock(spec_set=['claim_google_delivery', 'finish_google_delivery', 'claim_google_workbook',
            'begin_google_workbook_create', 'finish_google_workbook', 'mapped_google_row', 'assign_sheet_row'])
        self.store.finish_google_delivery.return_value = True
        self.workspace = Mock(spec_set=['cancel_meeting', 'ensure_meeting', 'bind_volume', 'check_capacity',
            'create_workbook', 'find_workbook', 'prepare_workbook', 'write_booking_row', 'workbook_project'])
        self.workspace.workbook_project.return_value = 'synthetic-project'
        self.services = SimpleNamespace(google=SimpleNamespace(settings=SimpleNamespace(client_id='new-google-client')))
        self.access = SimpleNamespace(client_id='retained-google-client', grant=SimpleNamespace(subject='saved-owner'))
        self.job = {'id': str(uuid4()), 'kind': 'booking_calendar', 'recipient_role': 'calendar', 'attempts': 2,
                    'payload': {'synthetic': 'booking'}}
        self.store.claim_google_delivery.return_value = self.job
        self.saved = {'subject': 'saved-owner', 'lease': str(uuid4()), 'intent': str(uuid4()),
                      'action': 'create', 'spreadsheet_id': 'synthetic-sheet'}
        self.store.claim_google_workbook.return_value = self.saved

    def test_empty_resource_queue_does_no_provider_work_and_lost_finish_is_not_done(self):
        self.store.claim_google_delivery.return_value = None
        self.assertEqual(run_google_delivery_once(self.store, self.services, resource='client_sheet'), {'processed': 0})
        self.store.claim_google_delivery.assert_called_once_with('client_sheet')
        self.store.finish_google_delivery.assert_not_called()
        self.store.claim_google_delivery.return_value = self.job | {'kind': 'sheet_booking'}
        with patch('appointment_system.google_delivery.copy_booking_record', return_value='synthetic-sheet'):
            for result in (False, None, 1):
                self.store.finish_google_delivery.return_value = result
                self.assertEqual(run_google_delivery_once(self.store, self.services), {'processed': 0, 'retry': True})
        self.assertEqual(self.store.finish_google_delivery.call_args.args[1:5], ('done', 'synthetic-sheet', None, None))

    def test_calendar_waiting_completion_and_obsolete_work_keep_distinct_outcomes(self):
        with patch('appointment_system.google_delivery.refresh_connection', return_value=self.access) as refresh, \
                patch('appointment_system.google_delivery.Workspace', return_value=self.workspace):
            for state in ('waiting', 'ready'):
                self.workspace.ensure_meeting.return_value = {'event_id': 'synthetic-event', 'meet_url': None if state == 'waiting' else 'https://meet.google.com/abc-defg-hij', 'state': state}
                result = run_google_delivery_once(self.store, self.services)
                self.assertEqual(result, {'processed': 1, 'state': 'waiting' if state == 'waiting' else 'done'})
                if state == 'waiting':
                    self.assertEqual(self.store.finish_google_delivery.call_args.args[-1], 15)
            refresh.assert_called_with(self.store, self.services, 'client', resource='calendar')
            self.workspace.reset_mock()
            self.store.claim_google_delivery.return_value = self.job | {'obsolete': True}
            self.assertEqual(run_google_delivery_once(self.store, self.services), {'processed': 1, 'state': 'obsolete'})
            self.workspace.cancel_meeting.assert_called_once_with(self.job['payload'])
            self.workspace.ensure_meeting.assert_not_called()
            self.store.claim_google_delivery.return_value = self.job | {'kind': 'booking_cancelled'}
            self.assertEqual(run_google_delivery_once(self.store, self.services), {'processed': 1, 'state': 'done'})
            self.assertEqual(self.workspace.cancel_meeting.call_count, 2)

    def test_provider_identity_conflicts_require_attention_and_storage_failure_keeps_lease_unfinished(self):
        with patch('appointment_system.google_delivery.refresh_connection', return_value=self.access), \
                patch('appointment_system.google_delivery.Workspace', return_value=self.workspace):
            for failure, state in [(WorkspaceFailure('google_event_mismatch'), 'attention'),
                                    (WorkspaceFailure('google_workbook_sharing_mismatch'), 'attention'),
                                    (GoogleFailure('google_reconnect_required'), 'failed')]:
                self.workspace.ensure_meeting.side_effect = failure
                self.assertEqual(run_google_delivery_once(self.store, self.services), {'processed': 1, 'state': state})
                self.assertEqual(self.store.finish_google_delivery.call_args.args[4], str(failure))
            self.store.finish_google_delivery.reset_mock()
            self.workspace.ensure_meeting.side_effect = StorageUnavailable('synthetic unknown commit')
            with self.assertRaises(StorageUnavailable):
                run_google_delivery_once(self.store, self.services)
            self.store.finish_google_delivery.assert_not_called()
        self.store.claim_google_delivery.return_value = self.job | {'kind': 'booking_cancelled', 'recipient_role': 'agency_sheet'}
        self.assertEqual(run_google_delivery_once(self.store, self.services), {'processed': 1, 'state': 'failed'})
        self.assertEqual(self.store.finish_google_delivery.call_args.args[4], 'google_record_job_invalid')

    def test_workbook_creation_requires_saved_intent_and_uses_retained_google_client(self):
        self.store.begin_google_workbook_create.return_value = True
        self.store.finish_google_workbook.return_value = True
        self.workspace.create_workbook.return_value = 'synthetic-created-sheet'
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access), \
                patch('appointment_system.google_records.Workspace', return_value=self.workspace):
            _, saved = prepare_owner_workbook(self.store, self.services, 'client')
            self.assertEqual(saved['spreadsheet_id'], 'synthetic-created-sheet')
            self.store.claim_google_workbook.assert_called_once_with('client', 'retained-google-client')
            self.workspace.prepare_workbook.assert_called_once_with('synthetic-created-sheet', self.saved['intent'])
            self.workspace.reset_mock()
            self.store.begin_google_workbook_create.return_value = False
            with self.assertRaisesRegex(WorkspaceFailure, 'creation_unresolved'):
                prepare_owner_workbook(self.store, self.services, 'client')
            self.workspace.create_workbook.assert_not_called()
            self.workspace.prepare_workbook.assert_not_called()

    def test_discovery_never_creates_a_second_workbook_or_claims_an_unknown_save_succeeded(self):
        self.saved['action'] = 'discover'
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access), \
                patch('appointment_system.google_records.Workspace', return_value=self.workspace):
            self.workspace.find_workbook.return_value = None
            with self.assertRaisesRegex(WorkspaceFailure, 'creation_unresolved'):
                prepare_owner_workbook(self.store, self.services, 'client')
            self.workspace.prepare_workbook.assert_not_called()
            self.workspace.find_workbook.return_value = 'synthetic-existing-sheet'
            self.store.finish_google_workbook.return_value = False
            with self.assertRaisesRegex(WorkspaceFailure, 'save_uncertain'):
                prepare_owner_workbook(self.store, self.services, 'client')
            self.store.finish_google_workbook.return_value = True
            self.assertEqual(prepare_owner_workbook(self.store, self.services, 'client')[1]['spreadsheet_id'], 'synthetic-existing-sheet')
        self.workspace.create_workbook.assert_not_called()
        self.store.begin_google_workbook_create.assert_not_called()

    def test_unavailable_foreign_or_review_workbook_is_not_prepared(self):
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access), \
                patch('appointment_system.google_records.Workspace', return_value=self.workspace):
            for saved, code in [(None, 'google_workbook_unavailable'),
                                (self.saved | {'subject': 'foreign'}, 'google_workbook_owner_mismatch'),
                                (self.saved | {'action': 'review', 'code': 'saved-review-reason'}, 'saved-review-reason'),
                                (self.saved | {'action': 'unknown'}, 'google_workbook_unavailable')]:
                self.store.claim_google_workbook.return_value = saved
                with self.assertRaisesRegex(WorkspaceFailure, code):
                    prepare_owner_workbook(self.store, self.services, 'client')
            self.store.claim_google_workbook.return_value = self.saved | {'action': 'ready'}
            self.assertEqual(prepare_owner_workbook(self.store, self.services, 'client')[1]['spreadsheet_id'], 'synthetic-sheet')
        self.workspace.check_capacity.assert_not_called()
        self.workspace.prepare_workbook.assert_not_called()

    def test_pinned_record_cannot_move_owner_client_workbook_or_intent(self):
        mapped = self.saved | {'client_id': 'retained-google-client', 'grant_id': str(uuid4()), 'values': ['saved-history']}
        with patch('appointment_system.google_records.refresh_connection', return_value=self.access) as refresh, \
                patch('appointment_system.google_records.Workspace', return_value=self.workspace):
            for changed in ({'subject': 'foreign'}, {'client_id': 'new-google-client'}):
                self.store.mapped_google_row.return_value = mapped | changed
                with self.assertRaisesRegex(WorkspaceFailure, 'owner_mismatch'):
                    workspace_for_record(self.store, self.services, 'client', self.job['id'], 'booking')
            self.store.mapped_google_row.return_value = mapped
            workspace, saved = workspace_for_record(self.store, self.services, 'client', self.job['id'], 'booking')
            refresh.assert_called_with(self.store, self.services, 'client', grant_id=mapped['grant_id'])
            self.assertIs(workspace, self.workspace)
            self.assertEqual(saved, mapped)
        job = self.job | {'kind': 'sheet_booking', 'recipient_role': 'client_sheet'}
        with patch('appointment_system.google_records.workspace_for_record', return_value=(self.workspace, mapped)):
            for assigned in (None, mapped | {'spreadsheet_id': 'foreign-sheet'}, mapped | {'intent': str(uuid4())}):
                self.store.assign_sheet_row.return_value = assigned
                with self.assertRaisesRegex(WorkspaceFailure, 'assignment_unavailable'):
                    copy_booking_record(self.store, self.services, job)
            self.workspace.write_booking_row.assert_not_called()
            self.store.assign_sheet_row.return_value = mapped | {'row': 2}
            self.assertEqual(copy_booking_record(self.store, self.services, job), 'synthetic-sheet')
            self.workspace.write_booking_row.assert_called_once_with('synthetic-sheet', mapped['intent'], 2, ['saved-history'])
        for changed in ({'kind': 'unknown'}, {'recipient_role': 'calendar'}):
            with self.assertRaisesRegex(WorkspaceFailure, 'job_invalid'):
                copy_booking_record(self.store, self.services, job | changed)
