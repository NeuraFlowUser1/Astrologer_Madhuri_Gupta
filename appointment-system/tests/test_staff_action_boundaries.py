"""Staff route contracts keep booking, enquiry and agency permissions separate."""
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.access import AccessDenied
from appointment_system.connection import StorageUnavailable
from appointment_system.credentials import ReceiptKeys
from appointment_system.receipt_recovery import recovery_code
from appointment_system.studio_appointments import add_appointment_routes
from appointment_system.studio_calendar import add_calendar_routes
from appointment_system.studio_inbox import add_inbox_routes
from .test_keys import ring


class StaffActionBoundaries(TestCase):
    def setUp(self):
        self.methods = ['studio_action_result', 'studio_appointment_detail', 'studio_appointment_cancel',
            'studio_appointment_reschedule', 'studio_booking_lookup', 'recovery_protection',
            'studio_time_context', 'studio_resolve_time', 'studio_pending_result', 'studio_calendar_list',
            'studio_calendar_month', 'studio_calendar_close', 'studio_calendar_reopen', 'studio_inbox_list',
            'studio_inbox_detail', 'studio_inbox_review', 'studio_inbox_retry',
            'studio_inbox_refund_verified', 'studio_inbox_resource_reviewed']
        self.store = Mock(spec=self.methods)
        for method in self.methods:
            getattr(self.store, method).return_value = {'code': 'ok'}
        self.actor = Mock(return_value=('staff-session', {'role': 'client'}))
        self.browser, self.limit = Mock(), Mock()
        self.wake = Mock(spec=['publish'])
        self.key = ReceiptKeys(ring())
        self.operation, self.claim, self.reference = uuid4(), uuid4(), uuid4()
        self.base = dict(operation_id=str(self.operation), reason='Synthetic reviewed change')
        self.appointment = self.base | {'claim_id': str(self.claim), 'expected_revision': 1}
        self.item = 'payment:' + str(self.reference)
        self.review = dict(operation_id=str(self.operation), item_key=self.item, expected_revision=1, note='Synthetic review')
        self.client = self.make_client()
        self.addCleanup(self.client.close)

    def make_client(self, with_key=True):
        app = FastAPI()
        @app.exception_handler(AccessDenied)
        async def denied(request, error):
            return JSONResponse({'code': 'access_unavailable'}, 403)
        @app.exception_handler(StorageUnavailable)
        async def unavailable(request, error):
            return JSONResponse({'code': 'temporarily_unavailable'}, 503)
        arguments = (app, self.store, 'synthetic-client', 'https://practice.example.test', self.actor, self.browser, self.limit)
        add_appointment_routes(*arguments, wake=self.wake, receipt_key=self.key if with_key else None)
        add_calendar_routes(*arguments)
        add_inbox_routes(*arguments, wake=self.wake)
        return TestClient(app)

    def post(self, path, body):
        return self.client.post('/api/' + path, json=body)

    def test_appointment_success_keeps_operation_revision_and_saved_result_despite_failed_wake(self):
        self.wake.publish.side_effect = RuntimeError('synthetic lost acknowledgement')
        for name, success in [('cancel', 'cancelled'), ('reschedule', 'rescheduled')]:
            body = self.appointment | ({'starts_at': '2026-10-09T10:00:00+05:30'} if name == 'reschedule' else {})
            target = getattr(self.store, 'studio_appointment_' + name)
            target.return_value = {'code': success}
            response = self.post('studio/appointments/' + name, body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'code': success})
            self.assertEqual(target.call_args.args[:7], ('staff-session', 'synthetic-client',
                'https://practice.example.test', self.operation, self.claim, 1, self.base['reason']))
            if name == 'reschedule':
                self.assertEqual(target.call_args.args[7], datetime.fromisoformat(body['starts_at']))
        self.assertEqual(self.wake.publish.call_count, 2)
        self.assertEqual(self.limit.call_args.args[1], 'studio')

    def test_appointment_conflicts_unknown_results_and_nonclient_actor_never_look_successful(self):
        self.actor.return_value = ('staff-session', {'role': 'agency'})
        self.assertEqual(self.post('studio/appointments/detail', {'claim_id': str(self.claim)}).status_code, 403)
        self.store.studio_appointment_detail.assert_not_called()
        self.actor.return_value = ('staff-session', {'role': 'client'})
        for code in ('booking_unavailable', 'appointment_unavailable', 'revision_changed', 'request_conflict',
                     'invalid_change', 'time_unavailable', 'time_already_reserved', 'late_reschedule_used'):
            self.store.studio_appointment_cancel.return_value = {'code': code}
            response = self.post('studio/appointments/cancel', self.appointment)
            self.assertEqual(response.status_code, 422 if code == 'invalid_change' else 409)
            self.assertEqual(response.json(), {'code': code})
        for value, status in [(None, 503), ({'code': 'access_unavailable'}, 403), ({'code': 'unknown'}, 503)]:
            self.store.studio_appointment_cancel.return_value = value
            self.assertEqual(self.post('studio/appointments/cancel', self.appointment).status_code, status)
        self.wake.publish.assert_not_called()

    def test_lookup_is_not_receipt_access_and_invalid_change_is_rejected_before_storage(self):
        self.store.studio_booking_lookup.return_value = {'code': 'ok', 'reference': str(self.reference)}
        response = self.post('studio/appointments/lookup', {'reference': str(self.reference)})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('receipt', response.json())
        self.assertEqual(self.limit.call_args.args[1], 'studio_status')
        for changed in ({'starts_at': '2026-10-09T10:00:00'}, {'starts_at': '2026-10-09T10:00:01Z'},
                        {'starts_at': '2026-10-09T10:00:00.000001Z'}, {'expected_revision': True}, {'reason': 'bad\nreason'}):
            body = self.appointment | {'starts_at': '2026-10-09T10:00:00Z'} | changed
            self.assertEqual(self.post('studio/appointments/reschedule', body).status_code, 422)
        self.store.studio_appointment_reschedule.assert_not_called()

    def test_retried_support_action_uses_saved_code_key_and_never_fabricates_access(self):
        body = {'operation_id': str(self.operation)}
        self.store.recovery_protection.return_value = {'format': 'v1', 'key_id': 'k1'}
        self.store.studio_action_result.return_value = {'code': 'support_saved', 'active': True, 'reference': str(self.reference)}
        response = self.post('studio/appointments/action-result', body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['activation_code'], recovery_code(self.key, self.operation, self.reference, key_id='k1'))
        with self.make_client(with_key=False) as client:
            self.assertEqual(client.post('/api/studio/appointments/action-result', json=body).status_code, 503)
        self.store.studio_action_result.return_value = {'code': 'support_saved', 'active': False}
        self.assertNotIn('activation_code', self.post('studio/appointments/action-result', body).json())
        for value, status in [(None, 503), ({'code': 'access_unavailable'}, 403), ({'code': 'unexpected'}, 503),
                              ({'code': 'operation_not_found'}, 200)]:
            self.store.studio_action_result.return_value = value
            self.assertEqual(self.post('studio/appointments/action-result', body).status_code, status)

    def test_calendar_writes_use_bounded_zoned_intervals_and_client_authority(self):
        body = self.base | {'starts_at': '2026-10-09T10:00:00Z', 'ends_at': '2026-10-09T10:20:00Z'}
        self.store.studio_calendar_close.return_value = {'code': 'closed'}
        self.store.studio_calendar_reopen.return_value = {'code': 'reopened'}
        self.assertEqual(self.post('studio/calendar/close', body).status_code, 200)
        self.assertEqual(self.post('studio/calendar/reopen', self.base | {'claim_id': str(self.claim)}).status_code, 200)
        self.store.studio_calendar_close.reset_mock()
        for change in ({'ends_at': body['starts_at']}, {'ends_at': '2026-11-10T10:00:00Z'},
                       {'starts_at': '2026-10-09T10:00:00'}, {'starts_at': '2026-10-09T10:00:01Z'}):
            self.assertEqual(self.post('studio/calendar/close', body | change).status_code, 422)
        self.store.studio_calendar_close.assert_not_called()
        self.actor.return_value = ('staff-session', {'role': 'agency'})
        self.assertEqual(self.post('studio/calendar/month', {'month': '2026-10-01'}).status_code, 403)
        self.store.studio_calendar_month.assert_not_called()

    def test_calendar_result_errors_and_action_poll_keep_their_purpose(self):
        for value, status in [(None, 503), ({'code': 'unknown'}, 503), ({'code': 'access_unavailable'}, 403),
                              ({'code': 'time_already_reserved'}, 409), ({'code': 'invalid_calendar_date'}, 422)]:
            self.store.studio_calendar_list.return_value = value
            self.assertEqual(self.post('studio/calendar/list', {'day': '2026-10-09'}).status_code, status)
        self.store.studio_pending_result.return_value = {'code': 'operation_not_found'}
        self.assertEqual(self.post('studio/calendar/action-result', {'operation_id': str(self.operation)}).status_code, 200)
        self.assertEqual(self.store.studio_pending_result.call_args.args[-1], 'calendar')

    def test_agency_cannot_read_customer_enquiries_or_payments_but_can_review_delivery_failures(self):
        self.actor.return_value = ('staff-session', {'role': 'agency'})
        self.assertEqual(self.post('studio/inbox/list', {'view': 'enquiries'}).status_code, 403)
        for family in ('enquiry:', 'payment:'):
            item = family + str(self.reference)
            self.assertEqual(self.post('studio/inbox/detail', {'item_key': item}).status_code, 403)
            self.assertEqual(self.post('studio/inbox/review', self.review | {'item_key': item}).status_code, 403)
        self.store.studio_inbox_detail.assert_not_called()
        self.store.studio_inbox_review.assert_not_called()
        self.assertEqual(self.post('studio/inbox/detail', {'item_key': 'delivery:' + str(self.reference)}).status_code, 200)
        self.actor.return_value = ('staff-session', {'role': 'unknown'})
        self.assertEqual(self.post('studio/inbox/list', {'view': 'issues'}).status_code, 403)

    def test_enquiry_only_area_cannot_be_used_to_reach_payment_work_while_booking_is_off(self):
        for path, body in [('detail', {'item_key': self.item}), ('review', self.review), ('retry', self.review),
                           ('list', {'view': 'issues', 'after': self.item})]:
            self.assertEqual(self.post('enquiry-studio/inbox/' + path, body).status_code, 403)
        for path in ('refund-verified', 'resource-reviewed'):
            self.assertEqual(self.post('enquiry-studio/inbox/' + path, self.review).status_code, 404)
        self.assertEqual(self.post('enquiry-studio/inbox/list', {'view': 'issues'}).status_code, 200)
        self.assertEqual(self.store.studio_inbox_list.call_args.args[-2:], ('enquiry-issues', None))
        self.assertEqual(self.actor.call_args.kwargs, {'allow_off': True})
        self.store.studio_pending_result.return_value = {'code': 'operation_not_found'}
        self.assertEqual(self.post('enquiry-studio/inbox/action-result', {'operation_id': str(self.operation)}).status_code, 200)
        self.assertEqual(self.store.studio_pending_result.call_args.args[-1], 'enquiry')

    def test_retry_is_delivery_work_and_preserves_saved_result_after_wake_failure(self):
        self.wake.publish.side_effect = RuntimeError('synthetic lost wake')
        self.store.studio_inbox_retry.return_value = {'code': 'retry_queued'}
        response = self.post('studio/inbox/retry', self.review | {'item_key': 'delivery:' + str(self.reference)})
        self.assertEqual(response.status_code, 200)
        self.wake.publish.assert_called_once()
        self.store.studio_inbox_retry.reset_mock()
        self.assertEqual(self.post('studio/inbox/retry', self.review | {'item_key': 'enquiry:' + str(self.reference)}).status_code, 403)
        self.actor.return_value = ('staff-session', {'role': 'agency'})
        self.assertEqual(self.post('studio/inbox/retry', self.review).status_code, 403)
        self.store.studio_inbox_retry.assert_not_called()

    def test_review_cannot_replace_financial_evidence_and_errors_never_look_saved(self):
        for name, code in [('refund-verified', 'refund_verified'), ('resource-reviewed', 'resource_reviewed')]:
            target = getattr(self.store, 'studio_inbox_' + name.replace('-', '_'))
            target.return_value = {'code': code}
            self.assertEqual(self.post('studio/inbox/' + name, self.review).json(), {'code': code})
            self.assertEqual(target.call_args.args[3:], (self.operation, self.item, 1, 'Synthetic review'))
            target.reset_mock()
            self.assertEqual(self.post('studio/inbox/' + name, self.review | {'item_key': 'delivery:' + str(self.reference)}).status_code, 403)
            target.assert_not_called()
        for value, status in [(None, 503), ({'code': 'unknown'}, 503), ({'code': 'access_unavailable'}, 403),
                              ({'code': 'refund_not_verified'}, 409), ({'code': 'invalid_request'}, 422)]:
            self.store.studio_inbox_review.return_value = value
            self.assertEqual(self.post('studio/inbox/review', self.review).status_code, status)
        self.wake.publish.assert_not_called()
        self.store.studio_inbox_review.reset_mock()
        for note in ('  ', 'bad\nnote', 'bad\x7fnote'):
            self.assertEqual(self.post('studio/inbox/review', self.review | {'note': note}).status_code, 422)
        self.store.studio_inbox_review.assert_not_called()
