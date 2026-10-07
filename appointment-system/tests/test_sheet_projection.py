"""Remote write disorder and failure contracts, without live Google calls."""
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from appointment_system.configuration import installation
from appointment_system.google_oauth import Access, Grant, OWNERS, scopes_for
from appointment_system.google_workspace import PROJECT, WorkspaceFailure
from appointment_system.serialization import fingerprint
from appointment_system.sheet_projection import (
    BOOKING_HEADERS, ENQUIRY_HEADERS, definition, normalized, values_for, synchronize, run_projection_once)


class CurrentSheets(unittest.TestCase):
    def test_missing_booking_email_is_a_blank_cell_in_both_supported_current_layouts(self):
        self.job['snapshot']['email']=None
        for layout in (3,4):
            self.job['layout_version']=layout;values=values_for(self.job)
            self.assertEqual(values[4],'');self.assertEqual(len(values),len(BOOKING_HEADERS))
            self.assertTrue(all(type(value) is str for value in values));self.assertIn('+919876543210',values)

    def setUp(self):
        grant = Grant('client', 'synthetic-subject', OWNERS['client'], 'synthetic-refresh', scopes_for('client'))
        self.access = Access('synthetic-access', datetime.now(timezone.utc)+timedelta(hours=1), grant)
        self.services = SimpleNamespace(google=SimpleNamespace(settings=SimpleNamespace(client_id='synthetic-client')))
        self.job = dict(role='client', record_kind='booking', record_id=str(uuid4()), lease=str(uuid4()), sequence=1,
            grant_id=str(uuid4()), subject=grant.subject, client_id='synthetic-client', volume_number=1,
            layout_version=3, generation=str(uuid4()), intent=str(uuid4()), row_number=24, spreadsheet_id='synthetic_sheet',
            snapshot=dict(request_id=str(uuid4()), state='confirmed', revision=1, created_at='2026-10-01T12:00:00Z',
                full_name='=A1', email='person@example.invalid', phone='+919876543210',
                service_snapshot={'name': 'Consultation'}, starts_at='2026-10-06T10:30:00Z',
                questions=1, amount_paise=100, currency='INR', practice_timezone='Asia/Kolkata',
                preparation={'notes': 'Private note'}, meet_url=None, payment_reference='pay_synthetic'))
        self.file = dict(id='synthetic_sheet', trashed=False, mimeType='application/vnd.google-apps.spreadsheet',
            owners=[{'emailAddress': OWNERS['client']}], permissions=[{'type': 'user', 'role': 'owner', 'emailAddress': OWNERS['client']}],
            appProperties=dict(project=PROJECT, role='client', intent=self.job['intent'],
                generation=self.job['generation'], volume='1', layout='3', installation=installation()['installation_id']))
        self.store = Mock()
        self.store.claim_sheet_projection.return_value = self.job
        self.store.approve_sheet_projection.return_value = 'ok'
        self.store.finish_sheet_projection.return_value = True
        self.cells = []; self.requests = []; self.read_count = 0
        self.lost = False; self.late = None; self.changed_after_put = False

    def transport(self):
        def response(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic-access')
            title, tab, headers = definition(self.job['record_kind'], self.job['layout_version'])
            if request.url.path.startswith('/drive/'):
                return httpx.Response(200, json=self.file)
            if request.url.path.endswith('/synthetic_sheet'):
                return httpx.Response(200, json={'sheets': [{'properties': {'sheetId': tab, 'title': title,
                    'gridProperties': {'rowCount': 10000, 'columnCount': len(headers)}}}]})
            if '!A1:' in request.url.path:
                return httpx.Response(200, json={'values': [headers]})
            if request.method == 'PUT':
                self.assertEqual(request.url.params['valueInputOption'], 'RAW')
                self.cells = copy.deepcopy(json.loads(request.content)['values'])
                if self.changed_after_put:
                    self.cells[0][1] = 'outdated'
                if self.lost:
                    self.lost = False
                    raise httpx.ReadTimeout('synthetic lost reply')
                return httpx.Response(200, json={})
            self.read_count += 1
            if self.late is not None and self.read_count == 2:
                self.cells = [self.late]
            return httpx.Response(200, json={'values': copy.deepcopy(self.cells)})
        return httpx.MockTransport(response)

    def run_once(self):
        with patch('appointment_system.sheet_projection.refresh_connection', return_value=self.access):
            return run_projection_once(self.store, self.services, self.job['record_kind'], 'client_sheet', transport=self.transport())

    def test_unapproved_sharing_stops_current_record_work_for_private_review(self):
        self.file['permissions'].append(dict(type='user',role='reader',emailAddress='foreign@example.test'))
        self.assertTrue(self.run_once()['attention'])
        self.assertEqual(self.store.finish_sheet_projection.call_args.args[1:],
                         (None,'google_workbook_sharing_mismatch',True))
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.requests[0].method,'GET')

    def test_values_keep_contact_preparation_currency_and_local_time_without_formula_evaluation(self):
        values = values_for(self.job)
        self.assertEqual(len(values), len(BOOKING_HEADERS))
        self.assertEqual(values[3], '=A1')
        self.assertEqual(values[8:13], ['1', 'INR', '2026-10-06', '16:00', 'Asia/Kolkata'])
        self.assertEqual(values[16:19], ['Private note', '', 'pay_synthetic'])
        self.run_once()
        self.assertEqual(self.cells, [values])
        self.assertEqual(self.store.finish_sheet_projection.call_args.args[1], fingerprint(values))

    def test_lost_successful_reply_is_read_back_without_another_write(self):
        self.lost = True
        self.run_once(); self.run_once()
        self.assertEqual(sum(r.method == 'PUT' for r in self.requests), 1)
        self.assertIsNotNone(self.store.finish_sheet_projection.call_args_list[0].args[2])
        self.assertIsNone(self.store.finish_sheet_projection.call_args_list[1].args[2])

    def test_delayed_old_write_is_repaired_on_the_persisted_follow_up(self):
        old = values_for(self.job)
        self.run_once()
        self.job['snapshot']['revision'] = 2
        self.job['snapshot']['starts_at'] = '2026-10-06T11:30:00Z'
        self.job['sequence'] = 2
        self.run_once()
        # An already-sent old request arrives after the successful new readback.
        self.cells = [old]
        self.run_once()
        self.assertEqual(self.cells, [values_for(self.job)])
        self.assertEqual(self.store.approve_sheet_projection.call_args.args[3], fingerprint(old))

    def test_unrecognized_occupied_row_is_attention_and_never_overwritten(self):
        self.cells = [['Foreign record']]
        self.store.approve_sheet_projection.return_value = 'conflict'
        result = self.run_once()
        self.assertTrue(result['attention'])
        self.assertFalse(any(r.method == 'PUT' for r in self.requests))

    def test_changed_revision_after_read_stops_write_and_leaves_follow_up(self):
        self.store.approve_sheet_projection.return_value = 'changed'
        result = self.run_once()
        self.assertFalse(result['attention'])
        self.assertFalse(any(r.method == 'PUT' for r in self.requests))
        self.assertEqual(self.store.finish_sheet_projection.call_args.args[2], 'google_sheet_revision_changed')

    def test_readback_mismatch_never_marks_delivery_successful(self):
        self.changed_after_put = True
        self.run_once()
        self.assertIsNone(self.store.finish_sheet_projection.call_args.args[1])
        self.assertEqual(self.store.finish_sheet_projection.call_args.args[2], 'google_sheet_readback_unresolved')

    def test_uncertain_database_approval_never_calls_remote_write(self):
        self.store.approve_sheet_projection.side_effect = RuntimeError('synthetic lost commit')
        with self.assertRaisesRegex(RuntimeError, 'lost commit'): self.run_once()
        self.assertFalse(any(r.method == 'PUT' for r in self.requests))
        self.store.finish_sheet_projection.assert_not_called()

    def test_saved_grant_owner_is_required_before_any_remote_write(self):
        for field in ('subject', 'client_id'):
            with self.subTest(field=field):
                original = self.job[field]; self.job[field] = 'wrong'
                self.run_once(); self.job[field] = original
        self.assertEqual(self.requests, [])
        self.file['owners'] = [{'emailAddress': OWNERS['agency']}]
        self.run_once()
        self.assertFalse(any(r.method != 'GET' for r in self.requests))

    def test_older_enquiry_history_tab_is_preserved_and_new_layout_uses_standard_name(self):
        self.job.update(record_kind='enquiry', snapshot=dict(request_id=str(uuid4()), verified_at='2026-10-01T12:00:00Z',
            payload=dict(name='Synthetic', email='person@example.invalid', phone='+919876543210', subject='Help',
                message='Please call.', kind='contact', source='services', service_interest='consultation', dob='', location='')))
        values = values_for(self.job)
        self.assertEqual(len(values), len(ENQUIRY_HEADERS))
        self.run_once()
        self.assertTrue(any('Enquiry current' in r.url.path for r in self.requests))
        self.assertEqual(definition('enquiry', 4)[0], 'Enquiries')

    def test_missing_turn_or_non_sheet_resource_does_not_touch_google(self):
        self.assertIsNone(run_projection_once(self.store, self.services, 'booking', 'calendar'))
        self.store.claim_sheet_projection.return_value = None
        self.assertIsNone(self.run_once())
        self.assertEqual(self.requests, [])

    def test_trailing_blank_cells_are_normalized_but_wrong_types_and_extra_cells_are_rejected(self):
        self.assertEqual(normalized([['a']], 3), ['a', '', ''])
        for rows in ([['a', 'b']], [[1]], ['bad'], [['a'], ['b']], {}):
            with self.subTest(rows=rows), self.assertRaises(WorkspaceFailure): normalized(rows, 1)
        self.assertIsNone(normalized([], 3))
