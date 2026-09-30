import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from cryptography.fernet import Fernet

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.google_access import refresh_connection
from backend.booking_engine.google_oauth import Access, Grant, GrantCipher, GoogleFailure, OWNERS, scopes_for


class GoogleAccessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.cipher = GrantCipher('synthetic-client', [Fernet.generate_key()])
        self.grant = Grant('client', 'subject', OWNERS['client'], 'synthetic-refresh', scopes_for('client'))
        self.store = Mock()
        self.store.claim_google_refresh.return_value = dict(role='client', subject='subject',
            client_id='synthetic-client', revision=1, lease=str(uuid4()),
            encrypted_grant=self.cipher.seal(self.grant), server_now=self.now.isoformat())
        self.store.finish_google_refresh.return_value = True
        self.google = Mock()
        self.google.settings = SimpleNamespace(client_id='synthetic-client')
        self.google.refresh.return_value = Access('synthetic-access', self.now+timedelta(hours=1), self.grant)
        self.services = SimpleNamespace(google=self.google, cipher=self.cipher)

    def test_refresh_saved_encrypted_before_return_and_does_not_log_secrets(self):
        sequence = []
        self.google.refresh.side_effect = lambda *a, **kw: (sequence.append('provider') or self.google.refresh.return_value)
        self.store.finish_google_refresh.side_effect = lambda *a: (sequence.append('commit') or True)
        access = refresh_connection(self.store, self.services, 'client')
        self.assertEqual(sequence, ['provider', 'commit'])
        saved = self.store.finish_google_refresh.call_args.args
        self.assertNotIn('synthetic-refresh', saved[5])
        self.assertEqual(self.cipher.open(saved[5], role='client', subject='subject', now=self.now), self.grant)
        self.assertEqual(access.token, 'synthetic-access')
        self.assertNotIn('synthetic-access', repr(access))

    def test_busy_missing_or_unknown_claim_does_not_call_google(self):
        self.store.claim_google_refresh.return_value = None
        with self.assertRaises(GoogleFailure):
            refresh_connection(self.store, self.services, 'client')
        self.google.refresh.assert_not_called()
        self.store.claim_google_refresh.side_effect = StorageUnavailable('uncertain commit')
        with self.assertRaises(StorageUnavailable):
            refresh_connection(self.store, self.services, 'client')
        self.google.refresh.assert_not_called()

    def test_mismatched_connection_rejected_before_refresh(self):
        self.store.claim_google_refresh.return_value['role'] = 'agency'
        with self.assertRaises(GoogleFailure):
            refresh_connection(self.store, self.services, 'client')
        self.google.refresh.assert_not_called()

    def test_provider_failure_preserves_saved_grant_without_automatic_retry(self):
        self.google.refresh.side_effect = GoogleFailure('google_request_failed')
        with self.assertRaises(GoogleFailure):
            refresh_connection(self.store, self.services, 'client')
        self.google.refresh.assert_called_once()
        self.store.finish_google_refresh.assert_not_called()

    def test_stale_or_uncertain_save_does_not_release_access_token(self):
        self.store.finish_google_refresh.return_value = False
        with self.assertRaises(GoogleFailure):
            refresh_connection(self.store, self.services, 'client')
        self.store.finish_google_refresh.side_effect = StorageUnavailable('uncertain commit')
        with self.assertRaises(StorageUnavailable):
            refresh_connection(self.store, self.services, 'client')


if __name__ == '__main__':
    unittest.main()
