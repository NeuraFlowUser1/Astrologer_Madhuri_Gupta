"""Support authority, contact correction and one-use receipt replacement boundaries."""
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.access import AccessDenied
from appointment_system.connection import StorageUnavailable
from appointment_system.receipt_recovery import add_staff_recovery_routes, code_digest, recovery_code
from appointment_system.application import create_application
from appointment_system.secret_configuration import booking_settings
from .test_application import environment, Reader


class ReceiptSupportBoundaries(TestCase):
    def setUp(self):
        self.settings = booking_settings(environment())
        self.key = self.settings.receipt_key
        self.operation, self.reference = uuid4(), uuid4()
        self.store = Mock(spec=['recovery_protection', 'studio_support_change', 'redeem_receipt_recovery', 'consume_limit'])
        self.store.consume_limit.return_value = {'allowed': True, 'retry_after': 0}
        self.store.recovery_protection.return_value = None
        self.store.studio_support_change.return_value = {'code': 'support_saved', 'active': True}
        self.actor = Mock(return_value=('saved-session', {'role': 'client'}))
        self.boundary, self.limit, self.wake = Mock(), Mock(), Mock(spec=['publish'])
        self.body = dict(operation_id=str(self.operation), reference=str(self.reference), expected_revision=1,
            action='receipt_recovery', verified_payment_id='pay_Synthetic', verification_confirmed=True,
            reason='Synthetic approved verification')
        app = FastAPI()
        @app.exception_handler(AccessDenied)
        async def denied(request, error):
            return JSONResponse({'code': 'access_unavailable'}, 403)
        @app.exception_handler(StorageUnavailable)
        async def unavailable(request, error):
            return JSONResponse({'code': 'temporarily_unavailable'}, 503)
        add_staff_recovery_routes(app, self.store, 'synthetic-google-client', self.settings.origin,
            self.actor, self.boundary, self.limit, self.key, self.wake)
        self.client = TestClient(app)

    def post(self, body=None):
        return self.client.post('/api/studio/appointments/support', json=self.body if body is None else body)

    def test_recovery_issues_only_the_short_code_and_keeps_receipt_secret_customer_owned(self):
        result = self.post()
        self.assertEqual(result.status_code, 200)
        code = recovery_code(self.key, self.operation, self.reference, key_id='current')
        self.assertEqual(result.json(), {'code': 'support_saved', 'active': True, 'activation_code': code})
        self.store.studio_support_change.assert_called_once_with('saved-session', 'synthetic-google-client',
            self.settings.origin, self.operation, self.reference, 1, 'receipt_recovery', self.body['reason'],
            'pay_Synthetic', None, None, code_digest(self.key, self.reference, code, key_id='current'), 'current')
        self.limit.assert_called_once()
        self.assertEqual(self.limit.call_args.args[1], 'studio')
        self.boundary.assert_called_once()
        self.wake.publish.assert_not_called()
        self.store.studio_support_change.return_value = {'code': 'support_saved', 'active': False}
        self.assertIsNone(self.post().json()['activation_code'])

    def test_contact_correction_keeps_both_contacts_and_saved_result_when_wake_fails(self):
        self.wake.publish.side_effect = RuntimeError('synthetic private transport failure')
        body = self.body | {'action': 'contact_correction', 'email': 'MixedCase@Example.com', 'phone': '+919999999999'}
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.studio_support_change.call_args.args[9:11], ('MixedCase@example.com', '+919999999999'))
        self.wake.publish.assert_called_once()
        self.assertNotIn('private transport', response.text)

    def test_nonclient_origin_failure_and_unverified_request_do_not_reach_saved_support(self):
        self.actor.return_value = ('saved-session', {'role': 'agency'})
        self.assertEqual(self.post().status_code, 403)
        self.store.recovery_protection.assert_not_called()
        self.actor.return_value = ('saved-session', {'role': 'client'})
        self.boundary.side_effect = AccessDenied()
        self.assertEqual(self.post().status_code, 403)
        self.boundary.side_effect = None
        for change in ({'verification_confirmed': False}, {'verification_confirmed': 1}, {'expected_revision': True},
            {'action': 'contact_correction'}, {'action': 'contact_correction', 'email': 'new@example.com'},
            {'email': 'new@example.com'}, {'phone': '+919999999999'},
            {'action': 'contact_correction', 'email': 'new@example.com', 'phone': '+not-a-number'}):
            with self.subTest(change=change):
                self.assertEqual(self.post(self.body | change).status_code, 422)
        self.store.studio_support_change.assert_not_called()
        self.wake.publish.assert_not_called()

    def test_conflicts_and_unknown_storage_replies_never_return_an_activation_code(self):
        for code in ('booking_unavailable', 'revision_changed', 'request_conflict',
                     'support_verification_unavailable', 'support_wait', 'invalid_change'):
            self.store.studio_support_change.return_value = {'code': code}
            response = self.post()
            self.assertEqual(response.status_code, 422 if code == 'invalid_change' else 409)
            self.assertEqual(response.json(), {'code': code})
        for value, status in ((None, 503), ({'code': 'access_unavailable'}, 403), ({'code': 'unexpected'}, 503),
                              ({'code': 'support_saved', 'active': 1}, 503)):
            self.store.studio_support_change.return_value = value
            response = self.post()
            self.assertEqual(response.status_code, status)
            self.assertNotIn('activation_code', response.text)
        self.wake.publish.assert_not_called()

    def public_client(self, enabled=True):
        return TestClient(create_application(self.store, self.settings, verified_client_address=lambda _: '127.0.0.1',
            projection_reader=Reader(enabled)), base_url=self.settings.origin)

    def test_customer_redeems_to_its_own_new_secret_without_echoing_or_saving_plaintext(self):
        secret = self.key.issue()
        code = recovery_code(self.key, self.operation, self.reference, key_id='current')
        self.store.recovery_protection.return_value = {'format': 'v1', 'key_id': 'current'}
        self.store.redeem_receipt_recovery.return_value = {'code': 'receipt_restored'}
        body = {'request_id': str(self.reference), 'code': code, 'secret': secret}
        with self.public_client() as client:
            response = client.post('/api/checkout/recover-receipt', json=body, headers={'origin': self.settings.origin})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'code': 'receipt_restored'})
        self.store.redeem_receipt_recovery.assert_called_once_with(self.reference,
            code_digest(self.key, self.reference, code, key_id='current'), self.key.digest(self.reference, secret), 'current')
        self.assertNotIn(secret, response.text)
        self.assertNotIn(code, response.text)

    def test_unknown_or_rejected_redemption_never_claims_success_and_off_denies_before_storage(self):
        body = {'request_id': str(self.reference), 'code': '12345678', 'secret': self.key.issue()}
        self.store.recovery_protection.return_value = {'format': 'v1', 'key_id': 'current'}
        with self.public_client() as client:
            for value, status in ((None, 503), ({'code': 'access_unavailable'}, 403), ({'code': 'unexpected'}, 503)):
                self.store.redeem_receipt_recovery.return_value = value
                response = client.post('/api/checkout/recover-receipt', json=body, headers={'origin': self.settings.origin})
                self.assertEqual(response.status_code, status)
                self.assertNotIn('receipt_restored', response.text)
        self.store.reset_mock()
        with self.public_client(False) as client:
            self.assertEqual(client.post('/api/checkout/recover-receipt', json=body, headers={'origin': self.settings.origin}).status_code, 404)
        self.store.recovery_protection.assert_not_called()
        self.store.redeem_receipt_recovery.assert_not_called()
        self.store.consume_limit.assert_not_called()
