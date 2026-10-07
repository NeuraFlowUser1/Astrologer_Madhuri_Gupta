"""Real HTTP/receipt ownership and explicitly safe copy projections."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.access import AccessDenied
from appointment_system.connection import StorageUnavailable
from appointment_system.receipt_view import receipt_view,email_copy_view
from appointment_system.secret_configuration import booking_settings
from .test_application import PublicStore,Reader,environment


def copy_state(operation=None,*,email=True):
    return dict(operation_id=operation,booking_revision=1 if operation else None,
        state='pending' if operation else 'not_requested',has_booking_email=email,target_hint='c***@example.test' if operation else None,
        next_request_at=None,remaining_requests=2 if operation else 3,can_request=not bool(operation),blocked_reason='delivery_pending' if operation else None)


class ReceiptCopyBoundaries(TestCase):
    def setUp(self):
        self.settings=booking_settings(environment());self.request,self.operation=uuid4(),uuid4()
        self.secret=self.settings.receipt_key.issue();now=datetime.now(timezone.utc)
        self.snapshot=dict(server_now=now.isoformat(),booking=dict(request_id=str(self.request),state='confirmed',
            receipt_digest=self.settings.receipt_key.digest(self.request,self.secret),receipt_format='v1',receipt_key_id='current',
            receipt_expires_at=(now+timedelta(days=2)).isoformat(),receipt_revoked_at=None,hold_expires_at=(now+timedelta(minutes=10)).isoformat(),
            order_state='ready',payment_state='captured',attempted_at=(now-timedelta(seconds=5)).isoformat(),provider_order_id='order_synthetic',
            resolution=None,resolved_at=None,service_name='Consultation',amount_paise=210000,currency='INR',captured_paise=210000,refunded_paise=0,
            starts_at=(now+timedelta(days=1)).isoformat(),ends_at=(now+timedelta(days=1,minutes=30)).isoformat(),practice_timezone='Asia/Kolkata',
            booking_revision=1,meeting_mode='google_meet',meeting_state='ready',meet_url='https://meet.google.com/abc-defg-hij',
            acknowledgement_state='pending',meeting_email_state='pending',email_copy=copy_state()))
        self.store=PublicStore();self.store.receipt_snapshot=Mock(side_effect=lambda _:deepcopy(self.snapshot))
        self.store.request_receipt_copy=Mock(return_value=dict(code='receipt_copy_accepted',request_id=str(self.request),
            operation_id=str(self.operation),booking_revision=1,email_copy=copy_state(str(self.operation)),replayed=False,private='must not escape'))
        self.reader=Reader(True);self.wake=Mock(spec=['publish'])
        self.client=TestClient(create_application(self.store,self.settings,verified_client_address=lambda _:'127.0.0.1',
            projection_reader=self.reader,email_sender=Mock(),wake_publisher=self.wake),base_url=self.settings.origin)
        self.headers={'Origin':self.settings.origin,'X-Booking-Receipt':self.secret}
        self.body=dict(request_id=str(self.request),operation_id=str(self.operation),expected_revision=1)

    def tearDown(self):self.client.close()
    def post(self,body=None,headers=None):
        return self.client.post('/api/checkout/email-details',json=self.body if body is None else body,headers=self.headers if headers is None else headers)

    def test_owned_receipt_needs_no_old_checkout_cookie_and_accepts_only_safe_fields(self):
        r=self.post();self.assertEqual(r.status_code,200);self.assertNotIn('private',r.json())
        self.assertEqual(len(r.json()),6);self.wake.publish.assert_called_once()
        self.assertEqual(self.store.calls,[('limit','checkout')]);self.assertNotIn(self.secret,r.text)
        self.store.request_receipt_copy.assert_called_once_with(self.request,self.secret,self.settings.receipt_key,self.operation,1,None,sending_ready=True)

    def test_off_and_foreign_origin_fail_before_any_copy_admission(self):
        self.assertEqual(self.post(headers=self.headers|{'Origin':'https://other.example.test'}).status_code,403)
        self.reader.enabled=False;self.assertEqual(self.post().status_code,404)
        self.store.request_receipt_copy.assert_not_called();self.store.receipt_snapshot.assert_not_called()

    def test_missing_wrong_revoked_and_expired_receipts_have_the_same_refusal(self):
        for change in ('missing','wrong','revoked','expired'):
            with self.subTest(change=change):
                snap=deepcopy(self.snapshot);headers=dict(self.headers)
                if change=='missing':headers.pop('X-Booking-Receipt')
                elif change=='wrong':headers['X-Booking-Receipt']=self.settings.receipt_key.issue()
                elif change=='revoked':snap['booking']['receipt_revoked_at']=snap['server_now']
                else:snap['booking']['receipt_expires_at']=snap['server_now']
                self.store.receipt_snapshot.side_effect=lambda _,s=snap:deepcopy(s)
                self.assertEqual(self.post(headers=headers).status_code,403)
        self.store.request_receipt_copy.assert_not_called()

    def test_strict_body_rejects_extra_fields_zero_ids_boolean_revision_and_invalid_addresses(self):
        for change in [dict(expected_revision=True),dict(expected_revision='1'),dict(expected_revision=0),dict(expected_revision=2147483648),
            dict(operation_id=str(uuid4()),extra='x'),dict(operation_id='00000000-0000-0000-0000-000000000000'),
            dict(request_id='00000000-0000-0000-0000-000000000000'),dict(email='bad'),dict(email=True),dict(email='x'*255+'@example.test')]:
            with self.subTest(change=change):self.assertEqual(self.post(self.body|change).status_code,422)
        self.store.request_receipt_copy.assert_not_called()

    def test_storage_uncertainty_and_malformed_success_do_not_claim_a_saved_request(self):
        self.store.request_receipt_copy.side_effect=StorageUnavailable();self.assertEqual(self.post().json(),{'code':'request_pending'})
        self.store.request_receipt_copy.side_effect=None
        good=deepcopy(self.store.request_receipt_copy.return_value)
        for result in [None,{'code':'unknown'},good|{'operation_id':str(uuid4())},good|{'booking_revision':True},
            good|{'email_copy':copy_state()},good|{'replayed':1}]:
            self.store.request_receipt_copy.return_value=result;r=self.post();self.assertEqual(r.status_code,503);self.assertEqual(r.json(),{'code':'request_pending'})
        self.wake.publish.assert_not_called()

    def test_definite_errors_project_only_safe_state_and_actual_retry_wait(self):
        for code,status in [('copy_pending',409),('copy_limit',429),('copy_cooldown',429),('copy_unavailable',503),('invalid_request',422),
            ('request_conflict',409),('revision_changed',409),('email_destination_conflict',409),('booking_not_confirmed',409),('email_destination_unavailable',409)]:
            self.store.request_receipt_copy.return_value=dict(code=code,retry_after=37,private='do not serialize')
            r=self.post();self.assertEqual(r.status_code,status);self.assertEqual(r.json(),{'code':code})
            self.assertEqual(r.headers.get('Retry-After'),'37' if status==429 else None)

    def test_wake_failure_does_not_erase_a_saved_result_and_second_off_check_hides_it(self):
        self.wake.publish.side_effect=RuntimeError('synthetic queue issue');self.assertEqual(self.post().status_code,200)
        def saved(*args,**kwargs):self.reader.enabled=False;return self.store.request_receipt_copy.return_value
        self.store.request_receipt_copy.side_effect=saved;r=self.post();self.assertEqual(r.status_code,404);self.assertNotIn('receipt_copy_accepted',r.text)

    def test_receipt_view_keeps_financial_facts_and_sanitizes_missing_or_unsafe_meeting_links(self):
        for url in (None,'javascript:alert(1)','https://evil.example.test/'):
            self.snapshot['booking']['meet_url']=url
            r=receipt_view(self.snapshot,self.request,self.secret,self.settings.receipt_key)
            self.assertEqual(r['meet_url'],None);self.assertEqual(r['meeting_state'],'needs_attention');self.assertEqual(r['captured_paise'],210000)
        self.snapshot['booking']['meet_url']='https://meet.google.com/abc-defg-hij'
        r=receipt_view(self.snapshot,self.request,self.secret,self.settings.receipt_key,sending_ready=False)
        self.assertEqual(r['email_copy']['blocked_reason'],'copy_unavailable');self.assertFalse(r['email_copy']['can_request'])

    def test_copy_projection_rejects_private_and_contradictory_state(self):
        for change in [dict(extra='x'),dict(state=[]),dict(state='delivered'),dict(operation_id=str(uuid4()),booking_revision=1),
            dict(target_hint='customer@example.test'),dict(remaining_requests=True),dict(can_request=False),dict(blocked_reason=[]),
            dict(next_request_at='yesterday'),dict(next_request_at='2026-10-07T12:00:00')]:
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):email_copy_view(copy_state()|change)
