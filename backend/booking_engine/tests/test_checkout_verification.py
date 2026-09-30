import hashlib
import hmac
import unittest
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.booking_engine.application import Settings, create_application
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.razorpay import Credentials, RazorpayFailure
from backend.booking_engine.recovery import Accounts
from backend.booking_engine.tests import test_access_and_views


ORIGIN = 'https://sarsa.example.invalid'


class CheckoutVerificationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.request_id, self.secret, key = test_access_and_views.ReceiptViewTests().fixture()
        self.row = self.snapshot['booking']
        self.row.update(booking_id=str(uuid4()), merchant_id='sarsaTest', mode='test', credential_version='v1')
        self.store = Mock()
        self.store.receipt_snapshot.return_value = self.snapshot
        self.store.consume_limit.return_value = {'allowed': True}
        self.store.save_provider_event.side_effect = lambda *args: args[4]
        self.store.order_intent.return_value = dict(merchant_id='sarsaTest', mode='test',
            credential_version='v1', amount_paise=210000, currency='INR')
        self.adapter = Mock()
        self.adapter.credentials = Credentials('sarsaTest', 'test', 'v1', 'rzp_test_synthetic', 'synthetic-secret')
        self.adapter.payment.return_value = dict(entity='payment', id='pay_synthetic', order_id='order_synthetic',
            status='captured', amount=210000, currency='INR', amount_refunded=0, captured=True)
        self.accounts = Accounts([self.adapter], current_versions={('sarsaTest', 'test'): 'v1'})
        self.wake = Mock()
        self.settings = Settings(ORIGIN, key, b'b'*32, b'c'*32)
        self.headers = {'Origin': ORIGIN, 'x-booking-receipt': self.secret}
        self.body = dict(request_id=str(self.request_id), razorpay_order_id='order_synthetic',
            razorpay_payment_id='pay_synthetic', razorpay_signature=hmac.new(b'synthetic-secret',
                b'order_synthetic|pay_synthetic', hashlib.sha256).hexdigest())
        self.client = self.client_for(self.accounts)

    def client_for(self, accounts):
        app = create_application(self.store, self.settings, verified_client_address=lambda _: '192.0.2.1',
            payment_accounts=accounts, wake_publisher=self.wake)
        return TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)

    def post(self, **changes):
        return self.client.post('/api/checkout/verify-payment', json=dict(self.body, **changes), headers=self.headers)

    def test_receipt_without_context_uses_pinned_credentials_and_finalizer(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['verification'], 'checked')
        self.adapter.payment.assert_called_once_with('pay_synthetic')
        self.store.observe_payment.assert_called_once()
        self.assertEqual(self.store.observe_payment.call_args.args[:2], (self.row['context_id'], self.row['booking_id']))
        self.assertEqual(self.store.consume_limit.call_args.args[0], 'checkout')
        self.wake.publish.assert_called_once()
        self.store.context_snapshot.assert_not_called()
        for private in ('merchant_id', 'booking_id', 'credential_version', self.secret, 'synthetic-secret'):
            self.assertNotIn(private, response.text)

    def test_wrong_receipt_origin_signature_order_never_fetch_or_mutate(self):
        for change in ('receipt', 'origin', 'signature', 'order'):
            with self.subTest(change=change):
                headers = dict(self.headers)
                body = dict(self.body)
                if change == 'receipt': headers['x-booking-receipt'] = 'x'*43
                if change == 'origin': headers['Origin'] = ORIGIN + '.evil'
                if change == 'signature': body['razorpay_signature'] = '0'*64
                if change == 'order': body['razorpay_order_id'] = 'order_other'
                response = self.client.post('/api/checkout/verify-payment', json=body, headers=headers)
                self.assertEqual(response.status_code, 403)
        self.adapter.payment.assert_not_called()
        self.store.observe_payment.assert_not_called()
        self.store.save_provider_event.assert_not_called()
        self.wake.publish.assert_not_called()

    def test_signature_is_not_confirmation_and_authorized_is_saved_as_authorized(self):
        self.adapter.payment.return_value.update(status='authorized', captured=False)
        self.row.update(state='held', resolution=None, resolved_at=None, payment_state='pending', captured_paise=0)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['receipt']['appointment_state'], 'held')
        evidence = self.store.observe_payment.call_args.args[-1]
        self.assertEqual(evidence.status, 'authorized')
        self.assertFalse(evidence.captured)

    def test_timeout_keeps_recovery_and_returns_pending_not_failed_payment(self):
        self.adapter.payment.side_effect = RazorpayFailure('payment_provider_unavailable')
        response = self.post()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['verification'], 'pending')
        self.store.observe_payment.assert_not_called()
        self.store.wake_payment_recovery.assert_called_once_with(self.row['booking_id'])
        self.wake.publish.assert_called_once()

    def test_uncertain_database_commit_never_returns_confirmation_or_wakes(self):
        self.store.observe_payment.side_effect = StorageUnavailable('synthetic-private-commit')
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('synthetic-private-commit', response.text)
        self.wake.publish.assert_not_called()

    def test_payment_reference_commits_before_provider_lookup_and_survives_timeout(self):
        order = []
        def save(*args):
            order.append('saved')
            self.assertEqual(args[3], 'checkout-verify:pay_synthetic')
            self.assertNotIn('signature', str(args[-1]))
            return args[4]
        def fetch(_):
            order.append('fetched')
            raise RazorpayFailure('payment_provider_unavailable')
        self.store.save_provider_event.side_effect = save
        self.adapter.payment.side_effect = fetch
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(order, ['saved', 'fetched'])
        self.store.save_provider_event.side_effect = StorageUnavailable('uncertain reference commit')
        self.adapter.payment.reset_mock()
        self.assertEqual(self.post().status_code, 503)
        self.adapter.payment.assert_not_called()

    def test_old_version_must_not_fall_back_to_current_key(self):
        self.row['credential_version'] = 'retired'
        response = self.post()
        self.assertEqual(response.status_code, 202)
        self.adapter.payment.assert_not_called()
        self.store.observe_payment.assert_not_called()

    def test_missing_accounts_quota_and_extra_amount_fail_closed(self):
        self.client = self.client_for(None)
        self.assertEqual(self.post().status_code, 503)
        self.client = self.client_for(self.accounts)
        self.assertEqual(self.post(amount=1).status_code, 422)
        self.store.consume_limit.return_value = {'allowed': False, 'retry_after': 60}
        self.assertEqual(self.post().status_code, 429)
        self.adapter.payment.assert_not_called()

    def test_late_capture_returns_review_from_database_not_browser_success(self):
        self.row.update(state='payment_review', payment_state='needs_attention', resolution=None, resolved_at=None)
        response = self.post()
        self.assertEqual(response.json()['receipt']['appointment_state'], 'payment_review')
        self.assertNotIn('resume_payment', response.json()['receipt']['next_actions'])


if __name__ == '__main__':
    unittest.main()
