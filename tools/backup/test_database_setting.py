import io
import unittest
from types import SimpleNamespace
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from database_setting import acquire_connection, connection_failure, main, validate_connection
from envelope import BackupError
from postgres import ROOT_CA

DSN = 'postgresql://sarsa_booking_backup:synthetic@ep-dry-hill-b3ujpil7.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'


class ClipboardConnectionTests(unittest.TestCase):
    def test_wait_captures_a_connection_after_empty_clipboard(self):
        now = [0]
        values = iter(['', 'irrelevant clipboard text', DSN])
        def advance(seconds):
            now[0] += seconds
        self.assertEqual(acquire_connection(10, reader=lambda: next(values), clock=lambda: now[0], pause=advance), DSN)
        self.assertEqual(now[0], 4)

    def test_missing_connection_expires_without_credentials_in_error(self):
        now = [0]
        def advance(seconds):
            now[0] += seconds
        with self.assertRaisesRegex(BackupError, '^backup_database_connection_not_on_clipboard$'):
            acquire_connection(3, reader=lambda: '', clock=lambda: now[0], pause=advance)
        self.assertEqual(now[0], 3)

    def test_another_role_is_rejected_before_connecting(self):
        with self.assertRaisesRegex(BackupError, '^backup_database_identity_invalid$'):
            acquire_connection(reader=lambda: DSN.replace('sarsa_booking_backup', 'neondb_owner'))

    def test_error_categories_never_return_provider_text(self):
        for message, expected in (
            ('password authentication failed: secret-value', 'backup_database_authentication_failed'),
            ('certificate verify failed: secret-value', 'backup_database_certificate_failed'),
            ('unrecognised failure secret-value', 'backup_database_connection_failed'),
        ):
            self.assertEqual(connection_failure(RuntimeError(message)), expected)

    def test_validation_preserves_tls_and_uses_installed_certificate_bundle(self):
        connector = MagicMock()
        connection = connector.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.side_effect = [
            ('sarsa_booking_backup', 'neondb', True, False), (19,),
        ]
        with patch.dict('sys.modules', {'psycopg': SimpleNamespace(connect=connector)}):
            self.assertEqual(validate_connection(DSN), 19)
        self.assertEqual(connector.call_args.kwargs['sslmode'], 'verify-full')
        self.assertEqual(connector.call_args.kwargs['sslrootcert'], ROOT_CA)
        self.assertEqual(connector.call_args.kwargs['channel_binding'], 'require')

    def test_no_github_write_after_invalid_access(self):
        with patch('database_setting.acquire_connection', return_value=DSN), \
                patch('database_setting.validate_connection', side_effect=BackupError('backup_database_access_invalid')), \
                patch('database_setting.subprocess.run') as command:
            with redirect_stdout(io.StringIO()), self.assertRaises(BackupError):
                main()
            command.assert_not_called()

    def test_secret_uses_private_pipe_and_never_stdout_or_arguments(self):
        output = io.StringIO()
        with patch('database_setting.acquire_connection', return_value=DSN), \
                patch('database_setting.validate_connection', return_value=19), \
                patch('database_setting.subprocess.run') as command, redirect_stdout(output):
            command.return_value.returncode = 0
            main()
        self.assertNotIn(DSN, output.getvalue())
        self.assertNotIn('synthetic', output.getvalue())
        self.assertNotIn(DSN, ' '.join(command.call_args.args[0]))
        self.assertEqual(command.call_args.kwargs['input'], DSN.encode())


if __name__ == '__main__':
    unittest.main()
