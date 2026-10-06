"""Signed payment notifications retain references without inventing settlement."""
import hashlib
import hmac
import json
from unittest import TestCase
from unittest.mock import Mock
from appointment_system.webhook import WebhookAccount, WebhookRegistry, InvalidWebhook, EventConflict, accept_webhook


class WebhookBoundaries(TestCase):
    def setUp(self):
        self.secret = 'synthetic-webhook-signing-secret'
        self.account = WebhookAccount('SyntheticMerchant', 'test', (self.secret,))
        self.store = Mock(spec=['save_provider_event'])
        self.store.save_provider_event.side_effect = lambda *args: args[4]
        self.saved = Mock()

    def event(self, event='payment.captured', payload=None):
        return dict(entity='event', account_id='SyntheticMerchant', event=event,
            payload={'payment': {'entity': {'id': 'pay_Synthetic', 'order_id': 'order_Synthetic'}}} if payload is None else payload)

    def accept(self, value, *, account=None, event_id='event_synthetic'):
        body = value if type(value) is bytes else json.dumps(value).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        return accept_webhook(self.store, self.account if account is None else account, body, signature, event_id, on_saved=self.saved)

    def test_invalid_registry_and_account_shapes_cannot_be_used_for_authentication(self):
        for secrets in ((), ('short',), [self.secret], (self.secret,) * 3):
            with self.assertRaises(ValueError):
                WebhookAccount('SyntheticMerchant', 'test', secrets)
        for accounts in ((), [self.account], (object(),), (self.account,) * 9):
            with self.assertRaises(ValueError):
                WebhookRegistry(accounts)
        with self.assertRaises(InvalidWebhook):
            self.accept(self.event(), account=WebhookRegistry((self.account, self.account)))
        self.store.save_provider_event.assert_not_called()

    def test_duplicate_json_wrong_envelopes_and_missing_parent_are_rejected_before_storage(self):
        invalid = [b'{"entity":"event","entity":"event"}', b'not-json', b'[]', b'\xff',
                   self.event() | {'account_id': 'OtherMerchant'}, self.event() | {'event': 1},
                   self.event(payload={}), self.event(payload={'payment': {'entity': {'id': 'order_wrong'}}}),
                   self.event(payload={'order': {'entity': {'id': 'pay_wrong'}}})]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(InvalidWebhook):
                self.accept(value)
        for event_id in ('', '../bad', 'a' * 129, None):
            with self.assertRaises(InvalidWebhook):
                self.accept(self.event(), event_id=event_id)
        self.store.save_provider_event.assert_not_called()
        self.saved.assert_not_called()

    def test_order_only_event_keeps_no_invented_payment_and_unsupported_event_is_not_applied(self):
        self.assertEqual(self.accept(self.event('order.paid', {'order': {'entity': {'id': 'order_Synthetic'}}})), {'received': True})
        self.assertEqual(self.store.save_provider_event.call_args.args[5],
                         {'event': 'order.paid', 'payment_id': None, 'order_id': 'order_Synthetic'})
        self.store.reset_mock(); self.saved.reset_mock()
        self.assertEqual(self.accept(self.event('future.event')), {'received': True, 'code': 'payment_event_unsupported'})
        self.store.save_provider_event.assert_not_called(); self.saved.assert_not_called()

    def test_financial_notification_parent_conflicts_are_rejected_and_valid_fact_has_signed_provenance(self):
        refund = dict(entity='refund', id='rfnd_Synthetic', payment_id='pay_Synthetic', status='processed',
                      currency='INR', amount=100, created_at=1700000000)
        payload = {'refund': {'entity': refund}, 'payment': {'entity': {'id': 'pay_other', 'order_id': 'order_Synthetic'}}}
        with self.assertRaises(InvalidWebhook):
            self.accept(self.event('refund.processed', payload))
        self.store.save_provider_event.assert_not_called()
        self.assertEqual(self.accept(self.event('refund.processed', {'refund': {'entity': refund}})), {'received': True})
        saved = self.store.save_provider_event.call_args.args[5]
        self.assertEqual((saved['payment_id'], saved['order_id']), ('pay_Synthetic', None))
        self.assertEqual(saved['resource_fact']['id'], 'rfnd_Synthetic')
        self.assertNotIn('fetched', saved['resource_fact'])

    def test_unmapped_original_notification_conflict_is_not_acknowledged_or_woken(self):
        self.store = Mock(spec=['buffers_original_events', 'save_verified_provider_event'])
        self.store.buffers_original_events = True
        self.store.save_verified_provider_event.return_value = 'different-digest'
        with self.assertRaises(EventConflict):
            self.accept(self.event('future.event'))
        self.saved.assert_not_called()
        self.store.save_verified_provider_event.side_effect = lambda *args: args[4]
        body = json.dumps(self.event('future.event')).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(accept_webhook(self.store, self.account, body, signature, 'event_synthetic'),
                         {'received': True, 'code': 'payment_event_saved_for_review'})
        self.assertEqual(self.store.save_verified_provider_event.call_args.args[-1], body)

    def test_optional_wake_is_after_commit_and_never_the_source_of_payment_truth(self):
        body = json.dumps(self.event()).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(accept_webhook(self.store, self.account, body, signature, 'event_synthetic'), {'received': True})
        self.store.save_provider_event.return_value = 'different-digest'
        self.store.save_provider_event.side_effect = None
        with self.assertRaises(EventConflict):
            self.accept(self.event())
        self.saved.assert_not_called()
