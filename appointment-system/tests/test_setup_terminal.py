"""A failed private terminal must never expose a password or open a database."""
from contextlib import ExitStack, redirect_stderr
import getpass
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings

from tools import setup


class SetupTerminal(unittest.TestCase):
    def attempt(self, answers, *, tty=True):
        with ExitStack() as context:
            context.enter_context(patch('appointment_system.runtime.contained_release', return_value=(Path('/synthetic/appointment-system'), {})))
            context.enter_context(patch('appointment_system.configuration.load', return_value=SimpleNamespace()))
            database = context.enter_context(patch('tools.conversion.handover.migration_connection'))
            context.enter_context(patch('sys.stdin.isatty', return_value=tty))
            context.enter_context(patch('builtins.input', return_value='company-owner'))
            context.enter_context(patch('getpass.getpass', side_effect=answers))
            output = context.enter_context(redirect_stderr(io.StringIO()))
            self.assertEqual(setup.main(['enroll-company'], environment={}), 1)
            database.assert_not_called()
            return output.getvalue()

    def test_hidden_input_failure_stops_before_reading_a_password(self):
        def no_hidden_input(_):
            warnings.warn('Synthetic terminal does not hide input.', getpass.GetPassWarning)
            self.fail('The warning must stop execution before the password fallback.')
        self.assertIn('setup_private_terminal_required', self.attempt(no_hidden_input))

    def test_piped_input_and_mismatched_confirmation_never_reach_database(self):
        self.assertIn('setup_private_terminal_required', self.attempt([], tty=False))
        output = self.attempt(['synthetic-secret-one', 'synthetic-secret-two'])
        self.assertIn('setup_password_mismatch', output)
        self.assertNotIn('synthetic-secret', output)

    def test_cancelled_or_unexpected_terminal_failure_is_redacted(self):
        self.assertIn('Setup cancelled.', self.attempt(EOFError()))
        output = self.attempt(RuntimeError('synthetic-private-secret'))
        self.assertIn('setup_failed', output)
        self.assertNotIn('synthetic-private-secret', output)
