"""Company access and publication cannot turn overload or uncertainty into success."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

from appointment_system.company_auth import Credentials, password_hash
from appointment_system.configuration import worker_origin
from appointment_system.control_publication import Publisher, PublicationSettings
from appointment_system.errors import Rejected
from appointment_system.service_control import ControlError


class CompanyFailureBoundaries(TestCase):
    def test_password_hash_capacity_is_bounded_and_does_not_release_an_unacquired_slot(self):
        with patch('appointment_system.company_auth.HASH_SLOTS') as slots, patch('appointment_system.company_auth.HASHER') as hasher:
            slots.acquire.return_value = False
            with self.assertRaises(Rejected) as caught:
                password_hash('Synthetic company password only')
            self.assertEqual(caught.exception.status, 429)
            hasher.hash.assert_not_called()
            slots.release.assert_not_called()

    def test_throttled_credential_change_does_not_hash_or_finish_an_attempt(self):
        database = Mock(spec_set=['call'])
        database.call.return_value = {'code': 'please_wait'}
        credentials = Credentials(database, SimpleNamespace(digest=lambda purpose, value: 'a' * 64))
        with patch('appointment_system.company_auth.verify') as verify:
            with self.assertRaises(Rejected) as caught:
                credentials.credential_action('synthetic-session', 'synthetic-csrf',
                    'Synthetic company password only', 'synthetic-risk', 'Synthetic replacement password')
            self.assertEqual(caught.exception.status, 429)
            verify.assert_not_called()
        database.call.assert_called_once()
        self.assertIn('company_credential_begin', database.call.call_args.args[0])

    def test_invalid_publication_settings_cannot_claim_a_job_or_contact_a_worker(self):
        for publish, read, origin in [(b'P' * 31, b'R' * 32, worker_origin()),
                                      (b'P' * 32, b'P' * 32, worker_origin()),
                                      (b'P' * 32, b'R' * 32, 'https://foreign.example.test')]:
            with self.assertRaises(ControlError):
                PublicationSettings(publish, read, origin)
        database = Mock(spec_set=['claim_publication', 'claim_probe'])
        with self.assertRaises(ControlError):
            Publisher(database, None)()
        self.assertEqual(database.mock_calls, [])

    def test_retry_only_probe_reports_the_saved_host_result_without_republishing(self):
        database = Mock(spec_set=['claim_publication', 'claim_probe', 'record_probe', 'probe_retry'])
        database.claim_publication.return_value = None
        job = {'operation_id': 'synthetic-operation'}
        database.claim_probe.return_value = job
        reader = Mock(spec_set=['attestation'])
        reader.attestation = AsyncMock(return_value={'snapshot': {'synthetic': 'observed-state'}})
        publisher = Publisher(database, PublicationSettings(b'P' * 32, b'R' * 32, worker_origin()))
        with patch('appointment_system.control_publication.ProjectionReader', return_value=reader):
            database.record_probe.return_value = False
            self.assertEqual(publisher(), {'processed': 1, 'retry': True})
            database.probe_retry.assert_called_once_with(job, 'hosted_probe_changed')
            database.record_probe.assert_called_once_with(job, {'synthetic': 'observed-state'})
            database.probe_retry.reset_mock()
            database.record_probe.return_value = True
            self.assertEqual(publisher(), {'processed': 1, 'retry': False})
            database.probe_retry.assert_not_called()
            reader.attestation.side_effect = ControlError('projection_unavailable')
            self.assertEqual(publisher(), {'processed': 1, 'retry': True})
            database.probe_retry.assert_called_once_with(job, 'projection_unavailable')
        self.assertEqual(database.record_probe.call_count, 2)
