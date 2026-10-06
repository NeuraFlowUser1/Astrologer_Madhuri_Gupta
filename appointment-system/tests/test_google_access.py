"""An access token is released only after its owned refreshed grant is saved."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import unittest
import httpx

from appointment_system.connection import StorageUnavailable
from appointment_system.google_access import refresh_connection, refresh_resource_connection
from appointment_system.google_oauth import GoogleFailure, TOKEN, USERINFO
from appointment_system.google_resources import Resources
from . import test_google_resources as fixtures


class SavedGoogleAccess(unittest.TestCase):
    def setUp(self):
        self.grant, self.row = fixtures.saved()
        self.row.update(resource='calendar', revision=2, lease=str(uuid4()), server_now=fixtures.NOW.isoformat())
        self.store = Mock()
        self.store.claim_google_resource_refresh.return_value = self.row
        self.store.finish_google_resource_refresh.return_value = True
        self.calls = []

    def resources(self, *, failure=None, email=None):
        def provider(request):
            self.calls.append(request)
            if failure is not None: return httpx.Response(400, json={'error':failure})
            if str(request.url) == TOKEN:
                return httpx.Response(200, json=dict(access_token='synthetic-access', token_type='Bearer', expires_in=3600))
            self.assertEqual(str(request.url), USERINFO)
            return httpx.Response(200, json=dict(sub=self.grant.subject,
                email=email or self.grant.email, email_verified=True))
        return Resources(fixtures.spec(), fixtures.cipher(), transport=httpx.MockTransport(provider))

    def test_retained_grant_is_renewed_and_confirmed_before_returning_access(self):
        resources = self.resources()
        result = refresh_connection(self.store, SimpleNamespace(resources=resources), 'client',
            resource='calendar', grant_id=self.row['grant_id'])
        self.assertEqual(result.token, 'synthetic-access')
        self.store.claim_google_resource_refresh.assert_called_once_with('calendar', self.row['grant_id'])
        args = self.store.finish_google_resource_refresh.call_args.args
        refreshed = dict(self.row, encrypted_grant=args[1])
        self.assertEqual(resources.cipher.open(refreshed, 'calendar', now=fixtures.NOW), self.grant)
        self.assertEqual(args[2:], (self.grant.refresh_expires_at, sorted(self.grant.scopes)))
        self.assertEqual(len(self.calls), 2)

    def test_lost_database_reply_or_changed_lease_never_releases_access(self):
        for failure in (False, None, StorageUnavailable('synthetic unknown commit')):
            with self.subTest(failure=type(failure).__name__):
                self.store.finish_google_resource_refresh.reset_mock(side_effect=True)
                if isinstance(failure, Exception): self.store.finish_google_resource_refresh.side_effect = failure
                else: self.store.finish_google_resource_refresh.return_value = failure
                with self.assertRaises((StorageUnavailable, GoogleFailure)):
                    refresh_resource_connection(self.store, self.resources(), 'calendar')
                self.assertEqual(self.store.finish_google_resource_refresh.call_count, 1)

    def test_revocation_and_identity_changes_are_saved_as_bounded_failures(self):
        for provider_error, email, expected in (
            ('invalid_grant', None, 'google_reconnect_required'),
            (None, 'different@example.test', 'google_account_mismatch'),
            ('temporarily_unavailable', None, 'google_request_failed'),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(GoogleFailure, expected):
                    refresh_resource_connection(self.store, self.resources(failure=provider_error, email=email), 'calendar')
                self.store.finish_google_resource_refresh.assert_called_with(self.row, error=expected)

    def test_missing_revoked_or_wrong_resource_configuration_never_calls_google(self):
        resources = self.resources()
        for result in (None, {'code':'google_reconnect_required'}):
            self.store.claim_google_resource_refresh.return_value = result
            with self.assertRaises(GoogleFailure): refresh_resource_connection(self.store, resources, 'calendar')
        for role, resource in (('unknown', None), ('agency', 'calendar'), ('client', 'agency_sheet')):
            with self.assertRaisesRegex(GoogleFailure, 'google_account_mismatch'):
                refresh_connection(self.store, SimpleNamespace(resources=resources), role, resource=resource)
        with self.assertRaisesRegex(GoogleFailure, 'google_connection_unavailable'):
            refresh_connection(self.store, SimpleNamespace(), 'client')
        self.assertEqual(self.calls, [])
        self.store.finish_google_resource_refresh.assert_not_called()

    def test_corrupt_saved_grant_is_not_silently_replaced_or_used(self):
        for field, value in (('revision', True), ('revision', 0), ('resource', 'agency_sheet'),
                             ('lease', 'invalid'), ('encrypted_grant', 'invalid'), ('server_now', 'invalid')):
            with self.subTest(field=field):
                row = deepcopy(self.row); row[field] = value
                self.store.claim_google_resource_refresh.return_value = row
                with self.assertRaises(GoogleFailure): refresh_resource_connection(self.store, self.resources(), 'calendar')
                self.assertEqual(self.store.finish_google_resource_refresh.call_args.kwargs,
                    {'error':'google_saved_grant_invalid'})
        self.assertEqual(self.calls, [])
