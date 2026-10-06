"""Payment callbacks need receipt authority and saved, independently fetched facts.

Only persistence is a strict test port. HTTP validation, receipt checks, account
pinning, signatures, provider decoding and the wake publisher are production code.
Native checkout tests separately prove the database transitions.
"""
from copy import deepcopy
import hashlib
import hmac
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.razorpay import Credentials, Razorpay
from appointment_system.recovery import Accounts
from appointment_system.secret_configuration import booking_settings
from appointment_system.wake import WakePublisher, WAKE_URL
from .test_application import environment, Reader
from .test_background_boundaries import WAKE_KEY


class CheckoutVerificationBoundaries(TestCase):
    def setUp(self):
        self.settings = booking_settings(environment())
        self.request_id, self.context_id, self.booking_id = uuid4(), uuid4(), uuid4()
        self.secret = self.settings.receipt_key.issue()
        self.calls = []
        self.store = Mock(spec=['receipt_snapshot', 'consume_limit', 'save_provider_event',
                               'order_intent', 'observe_payment', 'wake_payment_recovery',
                               'context_snapshot', 'payment_intake', 'reserve', 'claim_checkout_resume'])
        self.store.consume_limit.return_value = {'allowed': True, 'retry_after': 0}
        self.row = dict(request_id=str(self.request_id), context_id=str(self.context_id),
            booking_id=str(self.booking_id), receipt_format='v1', receipt_key_id='current',
            receipt_digest=self.settings.receipt_key.digest(self.request_id, self.secret),
            receipt_expires_at='2026-10-10T00:00:00Z', receipt_revoked_at=None,
            hold_expires_at='2026-10-05T00:10:00Z', state='held', order_state='ready',
            payment_state='unobserved', attempted_at='2026-10-04T23:59:00Z',
            provider_order_id='order_synthetic', merchant_id='ExampleSynthetic',
            mode='test', credential_version='old', resolution=None, resolved_at=None,
            captured_paise=0, refunded_paise=0, service_name='Synthetic consultation',
            amount_paise=100, currency='INR', starts_at='2026-10-09T10:00:00Z',
            ends_at='2026-10-09T10:20:00Z', practice_timezone='Asia/Kolkata',
            meeting_state='pending', acknowledgement_state='pending', meeting_email_state='pending')
        self.store.receipt_snapshot.side_effect = lambda _: dict(
            server_now='2026-10-05T00:00:00Z', booking=deepcopy(self.row))
        self.store.order_intent.return_value = dict(merchant_id='ExampleSynthetic', mode='test', credential_version='old')
        self.store.save_provider_event.side_effect = self.save_reference
        self.store.observe_payment.side_effect = self.observe
        self.provider_response = httpx.Response(200, json=dict(entity='payment', id='pay_synthetic',
            order_id='order_synthetic', status='captured', captured=True, amount=100,
            currency='INR', amount_refunded=0, email='private-provider-value@example.invalid'))
        self.old = Razorpay(Credentials('ExampleSynthetic', 'test', 'old', 'rzp_test_old', 'old-synthetic-secret'),
                            transport=httpx.MockTransport(self.provider))
        self.current = Razorpay(Credentials('ExampleSynthetic', 'test', 'new', 'rzp_test_new', 'new-synthetic-secret'),
                                transport=httpx.MockTransport(self.wrong_provider))
        self.accounts = Accounts([self.old, self.current], current_versions={('ExampleSynthetic', 'test'): 'new'})
        self.body = dict(request_id=str(self.request_id), razorpay_order_id='order_synthetic',
            razorpay_payment_id='pay_synthetic', razorpay_signature=self.signature('old-synthetic-secret'))
        self.headers = {'origin': self.settings.origin, 'x-booking-receipt': self.secret}

    def signature(self, secret):
        return hmac.new(secret.encode(), b'order_synthetic|pay_synthetic', hashlib.sha256).hexdigest()

    def save_reference(self, provider, merchant, mode, identity, digest, reference):
        self.calls.append('saved-reference')
        self.assertEqual((provider, merchant, mode, identity),
                         ('razorpay', 'ExampleSynthetic', 'test', 'checkout-verify:pay_synthetic'))
        self.assertEqual(reference, dict(event='checkout.verified', payment_id='pay_synthetic', order_id='order_synthetic'))
        return digest

    def provider(self, request):
        self.assertEqual(self.calls[-1], 'saved-reference')
        self.calls.append('provider-read')
        self.assertEqual((request.method, request.url.path), ('GET', '/v1/payments/pay_synthetic'))
        return self.provider_response

    def wrong_provider(self, request):
        self.fail('A saved payment must never be fetched through the replacement account.')

    def observe(self, context, booking, intent, evidence):
        self.calls.append('observed')
        self.assertEqual((context, booking), (str(self.context_id), str(self.booking_id)))
        self.assertEqual(evidence.id, 'pay_synthetic')
        self.assertNotIn('email', evidence.model_dump())
        self.row.update(state='confirmed', payment_state='captured', captured_paise=100,
                        resolution='confirmed', resolved_at='2026-10-05T00:00:00Z')
        return {'code': 'confirmed'}

    def client(self, *, accounts=True, wake=None):
        return TestClient(create_application(self.store, self.settings,
            verified_client_address=lambda _: '127.0.0.1', projection_reader=Reader(True),
            payment_accounts=self.accounts if accounts else None, wake_publisher=wake),
            base_url=self.settings.origin)

    def test_saved_account_and_receipt_authority_precede_provider_read_and_public_reply(self):
        with self.client() as client:
            result = client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['verification'], 'checked')
        self.assertEqual(result.json()['receipt']['appointment_state'], 'confirmed')
        self.assertEqual(self.calls, ['saved-reference', 'provider-read', 'observed'])
        self.assertEqual(self.store.consume_limit.call_args.args[0], 'checkout')
        self.assertIn('no-store', result.headers['cache-control'])
        self.assertNotIn(self.secret, result.text)
        self.assertNotIn('private-provider-value', result.text)

    def test_foreign_receipt_order_signature_and_origin_never_save_or_fetch(self):
        cases = [(self.body, self.headers | {'x-booking-receipt': self.settings.receipt_key.issue()}),
                 (self.body | {'razorpay_order_id': 'order_other'}, self.headers),
                 (self.body | {'razorpay_signature': self.signature('new-synthetic-secret')}, self.headers),
                 (self.body, self.headers | {'origin': 'https://foreign.example.test'})]
        with self.client() as client:
            for body, headers in cases:
                with self.subTest(body=body['razorpay_order_id'], origin=headers['origin']):
                    self.assertEqual(client.post('/api/checkout/verify-payment', json=body, headers=headers).status_code, 403)
        self.assertEqual(self.calls, [])
        self.store.save_provider_event.assert_not_called()
        self.store.order_intent.assert_not_called()

    def test_missing_account_or_failed_reference_commit_cannot_be_presented_as_verified(self):
        with self.client(accounts=False) as client:
            self.assertEqual(client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers).status_code, 503)
        self.store.save_provider_event.side_effect = None
        self.store.save_provider_event.return_value = 'different-digest'
        with self.client() as client:
            self.assertEqual(client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers).status_code, 503)
        self.assertEqual(self.calls, [])
        self.store.order_intent.assert_not_called()
        self.store.observe_payment.assert_not_called()

    def test_unavailable_provider_preserves_reference_and_returns_pending_without_another_payment(self):
        for wake in (None, self.failed_wake()):
            self.calls.clear()
            self.provider_response = httpx.Response(503)
            with self.client(wake=wake) as client:
                result = client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers)
            self.assertEqual(result.status_code, 202)
            self.assertEqual(result.json()['verification'], 'pending')
            self.assertEqual(result.json()['receipt']['captured_paise'], 0)
            self.assertNotIn('choose_new_time', result.json()['receipt']['next_actions'])
            self.store.wake_payment_recovery.assert_called_with(str(self.booking_id))
            self.assertEqual(self.calls, ['saved-reference', 'provider-read'])
        self.store.observe_payment.assert_not_called()

    def failed_wake(self):
        return WakePublisher(WAKE_URL, WAKE_KEY, transport=httpx.MockTransport(lambda _: httpx.Response(503)))

    def test_lost_wake_acknowledgement_does_not_erase_committed_payment(self):
        with self.client(wake=self.failed_wake()) as client:
            result = client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['receipt']['captured_paise'], 100)
        self.store.observe_payment.assert_called_once()

    def test_missing_saved_credential_version_stays_pending_without_reading_current_account(self):
        self.row['credential_version'] = 'missing'
        with self.client() as client:
            result = client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.json()['verification'], 'pending')
        self.assertEqual(self.calls, [])
        self.store.save_provider_event.assert_not_called()
        self.store.observe_payment.assert_not_called()

    def test_provider_payload_cannot_substitute_payment_identity_or_coerce_money(self):
        good = self.provider_response.json()
        for changed in ({'id': 'pay_other'}, {'amount': True}, {'amount_refunded': 101}):
            self.provider_response = httpx.Response(200, json=good | changed)
            with self.subTest(changed=changed), self.client() as client:
                result = client.post('/api/checkout/verify-payment', json=self.body, headers=self.headers)
                self.assertEqual(result.status_code, 202)
                self.assertEqual(result.json()['receipt']['captured_paise'], 0)
        self.store.observe_payment.assert_not_called()

    def prepare_context(self, client):
        from appointment_system.access import COOKIE_NAME
        context_id, token, digest = self.settings.context_key.issue()
        client.cookies.set(COOKIE_NAME, token)
        self.context_id = context_id
        self.row['context_id'] = str(context_id)
        self.store.context_snapshot.return_value = dict(server_now='2026-10-05T00:00:00Z',
            context=dict(credential_digest=digest, credential_format='v1', credential_key_id='current',
                         expires_at='2026-10-06T00:00:00Z'))
        self.store.payment_intake.return_value = dict(merchant_id='ExampleSynthetic', mode='test', credential_version='new')
        return dict(request_id=str(self.request_id), full_name='Synthetic Person', email='synthetic@example.com',
            phone='+919999999999', service_id='consultation', quote_version='a'*64, starts_at='2026-10-09T10:00:00Z')

    def test_intake_reports_saved_rejections_without_creating_or_fetching_a_payment(self):
        with self.client() as client:
            body = self.prepare_context(client)
            for code in ('payment_not_configured', 'request_conflict', 'request_rejected', 'checkout_in_progress',
                         'intake_closed', 'quote_changed', 'verification_required', 'service_unavailable',
                         'invalid_time', 'time_unavailable', 'context_expired', 'rate_limited', 'unexpected'):
                self.store.reserve.return_value = {'code': code}
                result = client.post('/api/checkout', json=body, headers=self.headers)
                expected = 503 if code in ('payment_not_configured', 'unexpected') else 429 if code == 'rate_limited' else 409
                self.assertEqual(result.status_code, expected, (code, result.text))
        self.assertEqual(self.calls, [])
        self.store.order_intent.assert_not_called()

    def test_unavailable_intake_credentials_are_not_borrowed_from_another_account(self):
        with self.client() as client:
            body = self.prepare_context(client) | {'verification_grant': 'synthetic-grant'}
            self.store.reserve.return_value = {'code': 'payment_not_configured'}
            for configured in (None, {}, {'merchant_id': 'ExampleSynthetic', 'mode': 'test', 'credential_version': 'old'},
                               {'merchant_id': 'UnknownSynthetic', 'mode': 'test', 'credential_version': 'new'}):
                self.store.payment_intake.return_value = configured
                result = client.post('/api/checkout', json=body, headers=self.headers)
                self.assertEqual(result.status_code, 503)
                self.assertEqual(self.store.reserve.call_args.kwargs, {'expected_merchant': None, 'verification_keys': None})
        self.assertEqual(self.calls, [])

    def test_checkout_receipt_authority_and_saved_booking_identity_are_independent(self):
        with self.client() as client:
            body = self.prepare_context(client)
            result = client.post('/api/checkout', json=body, headers=self.headers | {'x-booking-receipt': 'invalid'})
            self.assertEqual(result.status_code, 403)
            self.store.reserve.assert_not_called()
            self.store.reserve.return_value = {'code': 'reserved', 'booking_id': str(uuid4())}
            result = client.post('/api/checkout', json=body, headers=self.headers)
            self.assertEqual(result.status_code, 403)
        self.store.order_intent.assert_not_called()

    def test_resume_does_not_launch_when_off_settled_or_another_worker_owns_the_attempt(self):
        from appointment_system.checkout import resume_checkout
        original_snapshot = self.store.receipt_snapshot.side_effect
        self.store.receipt_snapshot.side_effect = lambda request: original_snapshot(request) | {'booking_product_enabled': False}
        result = resume_checkout(self.store, self.accounts, self.settings, self.request_id, self.secret, None)
        self.assertIsNone(result['checkout'])
        self.store.claim_checkout_resume.assert_not_called()
        self.store.receipt_snapshot.side_effect = original_snapshot
        self.row.update(state='confirmed', payment_state='captured', captured_paise=100,
                        resolution='confirmed', resolved_at='2026-10-05T00:00:00Z')
        result = resume_checkout(self.store, self.accounts, self.settings, self.request_id, self.secret, None)
        self.assertIsNone(result['checkout'])
        self.store.claim_checkout_resume.assert_not_called()
        self.row.update(state='held', payment_state='unobserved', captured_paise=0, resolution=None, resolved_at=None)
        self.store.claim_checkout_resume.return_value = None
        with self.client() as client:
            result = client.post('/api/checkout/resume', json={'request_id': str(self.request_id)}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['retry_after'], 15)
        self.assertIsNone(result.json()['checkout'])
        self.assertEqual(self.calls, [])

    def test_resume_missing_payment_configuration_returns_no_launch_credentials(self):
        with self.client(accounts=False) as client:
            response = client.post('/api/checkout/resume', json={'request_id': str(self.request_id)}, headers=self.headers)
            self.assertEqual(response.status_code, 503)
        self.row['credential_version'] = 'missing'
        with self.client() as client:
            response = client.post('/api/checkout/resume', json={'request_id': str(self.request_id)}, headers=self.headers)
            self.assertEqual(response.status_code, 503)
        self.assertNotIn('rzp_', response.text)
        self.store.claim_checkout_resume.assert_not_called()
