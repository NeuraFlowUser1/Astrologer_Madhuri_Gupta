import unittest
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.booking_engine.access import COOKIE_NAME, new_context
from backend.booking_engine.application import Settings, create_application
from backend.booking_engine.razorpay import Credentials, RazorpayFailure, order_receipt
from backend.booking_engine.recovery import Accounts
from backend.booking_engine.tests import test_access_and_views


ORIGIN = 'https://sarsa.example.invalid'


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.request_id, self.secret, key = test_access_and_views.ReceiptViewTests().fixture()
        self.context_id, self.token, self.digest = new_context(b'b'*32)
        self.row = self.snapshot['booking']
        self.row.update(booking_id=str(uuid4()), context_id=str(self.context_id), merchant_id='sarsaTest', mode='test',
            credential_version='v1', state='held', resolution=None, resolved_at=None, payment_state='unobserved', captured_paise=0)
        self.store = Mock()
        self.store.receipt_snapshot.return_value = self.snapshot
        self.store.consume_limit.return_value = {'allowed': True}
        self.store.claim_checkout_resume.return_value = dict(booking_id=self.row['booking_id'],
            lease_token=str(uuid4()), recovery_cursor=0, order_search_skip=0)
        self.store.finish_payment_recovery.return_value = True
        self.store.checkout_launchable.return_value = True
        self.store.start_order_creation.return_value = False
        self.store.order_intent.return_value = self.row
        self.store.reserve.return_value = dict(code='existing', booking_id=self.row['booking_id'])
        self.store.context_snapshot.return_value = dict(server_now=self.snapshot['server_now'], context=dict(
            credential_digest=self.digest, expires_at=self.row['receipt_expires_at']))
        self.adapter = Mock()
        self.adapter.credentials = Credentials('sarsaTest', 'test', 'v1', 'rzp_test_synthetic', 'synthetic-secret')
        self.adapter.order.return_value = dict(entity='order', id='order_synthetic',
            receipt=order_receipt(self.row['booking_id'], 'test'), amount=210000, currency='INR',
            status='created', amount_paid=0, amount_due=210000, partial_payment=False)
        self.adapter.order_payments.return_value = dict(entity='collection', count=0, items=[])
        self.accounts = Accounts([self.adapter], current_versions={('sarsaTest', 'test'): 'v1'})
        self.wake = Mock()
        app = create_application(self.store, Settings(ORIGIN, key, b'b'*32, b'c'*32),
            verified_client_address=lambda _: '192.0.2.1', payment_accounts=self.accounts, wake_publisher=self.wake)
        self.client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.headers = {'Origin': ORIGIN, 'x-booking-receipt': self.secret}

    def resume(self):
        return self.client.post('/api/checkout/resume', json={'request_id':str(self.request_id)}, headers=self.headers)

    def test_only_fresh_unpaid_order_with_live_claim_can_launch(self):
        result = self.resume()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['checkout'], dict(key_id='rzp_test_synthetic', order_id='order_synthetic',
            amount_paise=210000, currency='INR'))
        self.adapter.create_order.assert_not_called()
        self.store.context_snapshot.assert_not_called()
        self.assertNotIn('synthetic-secret', result.text)

    def test_coalesced_click_does_not_query_provider(self):
        self.store.claim_checkout_resume.return_value = None
        result = self.resume()
        self.assertIsNone(result.json()['checkout'])
        self.assertEqual(result.json()['retry_after'], 15)
        self.adapter.order.assert_not_called()

    def test_lost_lease_or_claim_cannot_launch(self):
        self.store.finish_payment_recovery.return_value = False
        self.assertIsNone(self.resume().json()['checkout'])
        self.store.finish_payment_recovery.return_value = True
        self.store.checkout_launchable.return_value = False
        self.assertIsNone(self.resume().json()['checkout'])

    def test_unknown_creation_expiry_and_confirmation_never_create_or_launch(self):
        for change in [dict(order_state='creation_unknown', provider_order_id=None),
                       dict(state='expired'), dict(state='confirmed')]:
            saved = dict(self.row)
            self.row.update(change)
            self.assertIsNone(self.resume().json()['checkout'])
            self.row.clear(); self.row.update(saved)
        self.adapter.order.assert_not_called()
        self.adapter.create_order.assert_not_called()

    def test_authorized_or_captured_collection_uses_finalizer_never_launches(self):
        for status, captured in [('authorized', False), ('captured', True)]:
            evidence = dict(entity='payment', id='pay_synthetic', order_id='order_synthetic', status=status,
                amount=210000, currency='INR', amount_refunded=0, captured=captured)
            self.adapter.order_payments.return_value = dict(entity='collection', count=1, items=[evidence])
            self.assertIsNone(self.resume().json()['checkout'])
            self.assertEqual(self.store.observe_payment.call_args.args[-1].status, status)

    def test_full_collection_and_wrong_order_fail_closed(self):
        self.adapter.order_payments.return_value = dict(entity='collection', count=100, items=[{}]*100)
        self.assertIsNone(self.resume().json()['checkout'])
        self.store.observe_payment.assert_not_called()
        self.adapter.order.return_value['id'] = 'order_other'
        self.assertIsNone(self.resume().json()['checkout'])
        self.assertEqual(self.store.finish_payment_recovery.call_args.kwargs['error'], 'payment_order_mismatch')

    def test_failed_attempt_is_recorded_but_does_not_create_a_replacement_order(self):
        evidence = dict(entity='payment',id='pay_failed',order_id='order_synthetic',status='failed',
            amount=210000,currency='INR',amount_refunded=0,captured=False)
        self.adapter.order_payments.return_value = dict(entity='collection',count=1,items=[evidence])
        self.adapter.order.return_value.update(status='attempted')
        self.assertIsNotNone(self.resume().json()['checkout'])
        self.assertEqual(self.store.observe_payment.call_args.args[-1].status,'failed')
        self.adapter.create_order.assert_not_called()

    def test_more_than_two_observations_keep_followup_after_confirmation(self):
        items=[dict(entity='payment',id=f'pay_extra{i}',order_id='order_synthetic',status='captured',
            amount=210000,currency='INR',amount_refunded=0,captured=True) for i in range(3)]
        self.adapter.order_payments.return_value = dict(entity='collection',count=3,items=items)
        self.assertIsNone(self.resume().json()['checkout'])
        self.assertEqual(self.store.observe_payment.call_count,2)
        self.assertGreater(self.store.finish_payment_recovery.call_args.args[2],0)

    def test_provider_outage_releases_lease_without_second_order(self):
        self.adapter.order.side_effect = RazorpayFailure('payment_provider_unavailable')
        self.assertIsNone(self.resume().json()['checkout'])
        self.store.finish_payment_recovery.assert_called_once()
        self.adapter.create_order.assert_not_called()

    def test_checkout_requires_context_and_immutable_reservation_outcome(self):
        payload = dict(request_id=str(self.request_id), full_name='Synthetic Person', email='synthetic@example.com',
            phone='+919876543210', service_id='numerology', quote_version='a'*64, starts_at='2026-10-01T10:00:00+05:30')
        response = self.client.post('/api/checkout', json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.store.reserve.assert_not_called()
        self.client.cookies.set(COOKIE_NAME, self.token)
        response = self.client.post('/api/checkout', json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.adapter.create_order.assert_not_called()
        self.store.reserve.return_value = {'code':'request_conflict'}
        response = self.client.post('/api/checkout', json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'request_conflict')

    def test_missing_or_stale_merchant_is_durably_classified_before_clear(self):
        payload = dict(request_id=str(self.request_id), full_name='Synthetic Person', email='synthetic@example.com',
            phone='+919876543210', service_id='numerology', quote_version='a'*64, starts_at='2026-10-01T10:00:00+05:30')
        self.client.cookies.set(COOKIE_NAME, self.token)
        self.store.reserve.return_value = {'code':'payment_not_configured'}
        for merchant, version in [(None,'v1'),('absent','v1'),('sarsaTest','old')]:
            self.store.payment_intake.return_value = dict(merchant_id=merchant,mode='test',credential_version=version)
            response = self.client.post('/api/checkout',json=payload,headers=self.headers)
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['code'],'payment_not_configured')
            self.assertIsNone(self.store.reserve.call_args.kwargs['expected_merchant'])
        self.store.start_order_creation.assert_not_called()
        self.adapter.create_order.assert_not_called()

    def test_reservation_receives_exact_credential_tuple(self):
        self.store.payment_intake.return_value = dict(merchant_id='sarsaTest',mode='test',credential_version='v1')
        self.client.cookies.set(COOKIE_NAME,self.token)
        payload = dict(request_id=str(self.request_id), full_name='Synthetic Person', email='synthetic@example.com',
            phone='+919876543210', service_id='numerology', quote_version='a'*64, starts_at='2026-10-01T10:00:00+05:30')
        self.assertEqual(self.client.post('/api/checkout',json=payload,headers=self.headers).status_code,200)
        self.assertEqual(self.store.reserve.call_args.kwargs['expected_merchant'],self.store.payment_intake.return_value)


if __name__ == '__main__': unittest.main()
