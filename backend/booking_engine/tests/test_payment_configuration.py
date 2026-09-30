import json
import unittest
from unittest.mock import patch

from backend.booking_engine.payment_configuration import payment_accounts, payment_webhook
from backend.booking_engine.razorpay import RazorpayFailure


class PaymentConfigurationTests(unittest.TestCase):
    def config(self):
        return dict(merchant_id='sarsaSynthetic', mode='live', current_version='v2', versions=[
            dict(version='v1', key_id='rzp_live_old', key_secret='synthetic-old'),
            dict(version='v2', key_id='rzp_live_new', key_secret='synthetic-new')])

    def test_retained_version_and_current_version_are_distinct_no_network(self):
        with patch('httpx.Client', side_effect=AssertionError('Unexpected provider request')):
            accounts = payment_accounts(json.dumps(self.config()))
            self.assertEqual(accounts.current('acc_sarsaSynthetic', 'live').credentials.version, 'v2')
            self.assertEqual(accounts.pinned('sarsaSynthetic', 'live', 'v1').credentials.version, 'v1')
        for identity in [('other', 'live', 'v1'), ('sarsaSynthetic', 'test', 'v1'), ('sarsaSynthetic', 'live', 'v0')]:
            with self.assertRaises(RazorpayFailure): accounts.pinned(*identity)

    def test_invalid_duplicate_or_missing_current_configuration_rejected(self):
        config = self.config()
        values = ['', '[]', '{"mode":"live","mode":"test"}',
            json.dumps(dict(config, mode='test')), json.dumps(dict(config, current_version='v3')),
            json.dumps(dict(config, versions=config['versions'] * 2)), json.dumps(dict(config, extra='x')),
            json.dumps(dict(config, versions=[dict(config['versions'][0], unexpected=True)]))]
        for value in values:
            with self.subTest(value=value), self.assertRaises((ValueError, RazorpayFailure)):
                payment_accounts(value)

    def test_webhook_cannot_use_another_merchant_or_mode_and_supports_rotation(self):
        accounts = payment_accounts(json.dumps(self.config()))
        webhook = dict(merchant_id='acc_sarsaSynthetic', mode='live',
                       signing_secrets=['synthetic-new-webhook', 'synthetic-old-webhook'])
        self.assertEqual(len(payment_webhook(json.dumps(webhook), accounts).signing_secrets), 2)
        for change in [dict(merchant_id='other'), dict(mode='test'), dict(signing_secrets=['short'])]:
            with self.assertRaises((ValueError, RazorpayFailure)):
                payment_webhook(json.dumps(dict(webhook, **change)), accounts)


if __name__ == '__main__': unittest.main()
