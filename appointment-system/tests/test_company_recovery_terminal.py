"""Recovery terminal errors never echo credentials or connect on missing input."""
from contextlib import ExitStack,redirect_stderr,redirect_stdout
import getpass
import io
import runpy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
from tools import company_recovery as recovery


class CompanyRecoveryTerminal(unittest.TestCase):
    def test_linked_recovery_entry_is_refused_before_loading_an_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            entry=Path(temporary)/'company_recovery.py';entry.symlink_to(Path(recovery.__file__))
            with self.assertRaisesRegex(SystemExit,'links are forbidden'):
                runpy.run_path(str(entry))

    def invoke(self,action='recover',*,answers=None,tty=True,arguments=True,operation_error=None):
        with ExitStack() as stack:
            stack.enter_context(patch('appointment_system.runtime.contained_release',return_value=(Path('/synthetic/appointment-system'),{})))
            profile=SimpleNamespace(installation=SimpleNamespace(document={'project_id':'synthetic-practice'}))
            stack.enter_context(patch('appointment_system.configuration.load',return_value=profile))
            database=stack.enter_context(patch('tools.conversion.handover.migration_connection'))
            stack.enter_context(patch('sys.stdin.isatty',return_value=tty))
            stack.enter_context(patch('builtins.input',return_value='company.owner'))
            hidden=stack.enter_context(patch('getpass.getpass',side_effect=answers))
            target=stack.enter_context(patch.object(recovery,action,return_value={'status':'synthetic_checked'},side_effect=operation_error))
            output=stack.enter_context(redirect_stdout(io.StringIO()))
            error=stack.enter_context(redirect_stderr(io.StringIO()))
            command=[action]
            if action=='recover' and arguments:
                command+=['--operation-id','1257662b-c555-4ce5-bd4f-0eab2bfe89b8','--expected-revision','1','--reason','Owner verified recovery request']
            status=recovery.main(command,environment={'BOOKING_MIGRATION_DATABASE_URL':'synthetic-private-connection'})
            return status,output.getvalue()+error.getvalue(),database.call_count,target.call_count,hidden.call_count

    def test_success_passes_hidden_password_only_to_private_recovery_and_redacts_output(self):
        result=self.invoke(answers=['Synthetic password that must stay private']*2)
        self.assertEqual((result[0],result[2:]),(0,(1,1,2)))
        self.assertNotIn('password that',result[1]);self.assertNotIn('private-connection',result[1])
        self.assertIn('synthetic_checked',result[1])

    def test_inspect_does_not_request_or_handle_a_password(self):
        result=self.invoke('inspect',answers=[])
        self.assertEqual((result[0],result[2:]),(0,(1,1,0)))

    def test_missing_metadata_piped_input_and_mismatched_password_never_connect(self):
        for kwargs,code in (({'arguments':False},'request_invalid'),({'tty':False},'private_terminal_required'),
            ({'answers':['Synthetic first password','Synthetic second password']},'password_mismatch')):
            result=self.invoke(**kwargs)
            self.assertEqual(result[0],1);self.assertEqual(result[2:4],(0,0));self.assertIn(code,result[1])
            self.assertNotIn('Synthetic first',result[1])

    def test_hidden_input_warning_cannot_fall_back_to_visible_password(self):
        def failure(_):
            warnings.warn('Synthetic terminal cannot hide input',getpass.GetPassWarning)
            self.fail('Visible fallback reached')
        result=self.invoke(answers=failure)
        self.assertEqual(result[0],1);self.assertEqual(result[2:4],(0,0));self.assertIn('private_terminal_required',result[1])

    def test_cancelled_and_provider_errors_do_not_expose_private_arguments(self):
        result=self.invoke(answers=EOFError())
        self.assertEqual(result[0],1);self.assertEqual(result[2:4],(0,0));self.assertIn('cancelled',result[1])
        for exception,code in ((RuntimeError('synthetic-private-connection'),'recovery_failed'),
            (recovery.SetupError('recovery_revision_conflict'),'recovery_revision_conflict')):
            result=self.invoke(answers=['Synthetic private password']*2,operation_error=exception)
            self.assertEqual(result[0],1);self.assertIn(code,result[1])
            self.assertNotIn('synthetic-private-connection',result[1]);self.assertNotIn('Synthetic private password',result[1])
