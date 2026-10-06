"""Contained setup routes maintenance-only authority and redacts failures."""
import base64,io,json,runpy
from contextlib import ExitStack,nullcontext,redirect_stdout,redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
from tools import initialize_projection
from appointment_system.configuration import installation

class ProjectionSetupCommandTests(TestCase):
    def setUp(self):
        self.operation=str(uuid4());self.facts=installation()
        self.env={'BOOKING_CONTROL_READ_KEY':base64.urlsafe_b64encode(b'R'*32).decode(),
                  'BOOKING_CONTROL_RECONCILE_KEY':base64.urlsafe_b64encode(b'C'*32).decode(),
                  'BOOKING_CONTROL_PUBLISH_KEY':base64.urlsafe_b64encode(b'P'*32).decode(),
                  'BOOKING_MAINTENANCE_DATABASE_URL':'private-dsn-not-output'}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('appointment_system.runtime.contained_release',return_value=(Path('/fixture/appointment-system'),{})))
        self.stack.enter_context(patch('appointment_system.configuration.load',return_value=SimpleNamespace(facts=lambda:self.facts)))
        self.config=self.stack.enter_context(patch('appointment_system.connection.checked_config',return_value={'password':'private-dsn-not-output'}))
        self.connect=self.stack.enter_context(patch('psycopg.connect',return_value=nullcontext(Mock())))
        self.database=self.stack.enter_context(patch('appointment_system.control_recovery.RecoveryDatabase'))
        self.run=self.stack.enter_context(patch('appointment_system.control_recovery.ProjectionInitialization.run',return_value={'verified':True,'enabled':False,'operation_id':self.operation}))
    def invoke(self,operation=None,env=None):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            code=initialize_projection.main(['--operation',operation or self.operation],self.env if env is None else env)
        self.assertNotIn('private-dsn-not-output',out.getvalue()+err.getvalue())
        for name in ('BOOKING_CONTROL_READ_KEY','BOOKING_CONTROL_RECONCILE_KEY','BOOKING_CONTROL_PUBLISH_KEY'):
            self.assertNotIn(self.env[name],out.getvalue()+err.getvalue())
        return code,out.getvalue(),err.getvalue()
    def test_success_uses_declared_maintenance_connection_and_verified_result(self):
        code,out,err=self.invoke();self.assertEqual(code,0);self.assertEqual(err,'')
        self.assertEqual(json.loads(out),{'project':self.facts['project_id'],'verified':True,'enabled':False,'operation_id':self.operation})
        self.config.assert_called_once_with(self.env['BOOKING_MAINTENANCE_DATABASE_URL'],self.facts['database_targets']['maintenance']['host'],purpose='maintenance')
        self.assertEqual(self.connect.call_args.kwargs['sslmode'],'verify-full')
        self.assertEqual(self.connect.call_args.kwargs['channel_binding'],'require')
        self.run.assert_called_once_with(self.operation)
    def test_invalid_operation_missing_or_shared_keys_never_connect(self):
        for operation,env in [('bad',self.env),(self.operation,{}),(self.operation,self.env|{'BOOKING_CONTROL_RECONCILE_KEY':self.env['BOOKING_CONTROL_READ_KEY']})]:
            self.assertEqual(self.invoke(operation,env)[0],1)
        self.connect.assert_not_called();self.run.assert_not_called()
    def test_database_or_remote_failure_and_interruption_are_redacted(self):
        for error in (RuntimeError('private-dsn-not-output'),KeyboardInterrupt()):
            self.run.side_effect=error
            code,out,err=self.invoke();self.assertEqual(code,1);self.assertEqual(out,'');self.assertIn('No booking was enabled',err)
    def test_integrity_failure_precedes_any_private_database_use(self):
        with patch('appointment_system.runtime.contained_release',side_effect=ValueError('private-dsn-not-output')):
            self.assertEqual(self.invoke()[0],1)
        self.connect.assert_not_called()
    def test_actual_command_entrypoint_uses_same_checked_path(self):
        with patch('sys.argv',['initialize_projection.py','--operation',self.operation]),patch.dict('os.environ',self.env,clear=True),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(initialize_projection.__file__,run_name='__main__')
        self.assertEqual(result.exception.code,0);self.run.assert_called_once_with(self.operation)
