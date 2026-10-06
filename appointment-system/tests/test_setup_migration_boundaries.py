"""Setup command routing, migration refusal and redacted operator outcomes."""
from contextlib import ExitStack,redirect_stdout,redirect_stderr,nullcontext
import hashlib,io,json,os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import psycopg
from tools import setup
from appointment_system import migrate
from appointment_system.settings import Installation,BusinessSettings
from .fixtures import installation,business


class SetupMigrationBoundaries(unittest.TestCase):
    def profile(self):
        facts=installation();facts['database_targets']['migration']=dict(facts['database_targets']['web'],role='synthetic_owner',pooling=False)
        return SimpleNamespace(installation=Installation.parse(facts),initial_business=BusinessSettings.parse(business()))

    def test_migration_source_bytes_checksums_and_links_are_checked_without_applying_sql(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(migrate,'MIGRATIONS',Path(directory)):
            with self.assertRaises(ValueError):migrate.migration_sources()
            target=Path(directory)/'001_fixture.sql';target.write_text('SELECT 1;')
            self.assertEqual(migrate.migration_sources(),[('001_fixture.sql','SELECT 1;',hashlib.sha256(b'SELECT 1;').hexdigest())])
            link=Path(directory)/'002_link.sql';link.symlink_to(target)
            with self.assertRaises(ValueError):migrate.migration_sources()

    def test_migration_history_refuses_unknown_or_changed_sources_and_replay_avoids_ddl(self):
        for applied,expected in [({},'apply'),({'001_fixture.sql':'a'*64},'same'),({'999_foreign.sql':'a'*64},'unknown'),({'001_fixture.sql':'b'*64},'changed')]:
            connection=Mock();connection.transaction.return_value=nullcontext()
            def execute(query,values=None):
                if 'to_regclass' in query:return Mock(fetchone=lambda:('schema_migrations' if applied else None,))
                if query.startswith('SELECT version'):return Mock(fetchall=lambda:list(applied.items()))
                return Mock()
            connection.execute.side_effect=execute
            with patch.object(migrate,'migration_sources',return_value=[('001_fixture.sql','SELECT fixture_ddl();','a'*64)]):
                if expected in ('unknown','changed'):
                    with self.assertRaises(ValueError):migrate.apply(connection)
                else:migrate.apply(connection)
            ddl=[c for c in connection.execute.call_args_list if c.args[0]=='SELECT fixture_ddl();']
            self.assertEqual(len(ddl),int(expected=='apply'))
            self.assertTrue(any('pg_advisory_xact_lock' in c.args[0] for c in connection.execute.call_args_list))

    def test_setup_routes_only_the_selected_action_and_never_prints_private_material(self):
        profile=self.profile();target=profile.installation.document['database_targets']['migration']
        for action,function in [('install-schema','appointment_system.migrate.apply'),('initialize','tools.setup.initialize'),('register-logins','tools.setup.register'),('enroll-company','tools.setup.enroll')]:
            with ExitStack() as stack:
                stack.enter_context(patch('appointment_system.runtime.contained_release',return_value=(Path('/synthetic/appointment-system'),{})))
                stack.enter_context(patch('appointment_system.configuration.load',return_value=profile))
                connection=Mock();connection.execute.return_value.fetchone.return_value=(target['database'],target['role'])
                database=stack.enter_context(patch('tools.conversion.handover.migration_connection',return_value=nullcontext(connection)))
                operation=stack.enter_context(patch(function,return_value={'status':'fixture-complete'}))
                stack.enter_context(patch('sys.stdin.isatty',return_value=True));stack.enter_context(patch('builtins.input',return_value='synthetic.owner'))
                stack.enter_context(patch('getpass.getpass',return_value='Synthetic secret never printed'))
                output=stack.enter_context(redirect_stdout(io.StringIO()));errors=stack.enter_context(redirect_stderr(io.StringIO()))
                self.assertEqual(setup.main([action],environment={'BOOKING_MIGRATION_DATABASE_URL':'synthetic-private-connection'}),0)
                self.assertEqual(json.loads(output.getvalue())['action'],action);operation.assert_called_once();database.assert_called_once()
                self.assertNotIn('Synthetic secret',output.getvalue()+errors.getvalue());self.assertNotIn('synthetic-private-connection',output.getvalue()+errors.getvalue())

    def test_setup_schema_wrong_database_is_refused_before_migration(self):
        profile=self.profile();connection=Mock();connection.execute.return_value.fetchone.return_value=('wrong','wrong')
        with patch('appointment_system.runtime.contained_release',return_value=(Path('/synthetic/appointment-system'),{})),patch('appointment_system.configuration.load',return_value=profile),\
             patch('tools.conversion.handover.migration_connection',return_value=nullcontext(connection)),patch.object(migrate,'apply') as apply,redirect_stderr(io.StringIO()) as output:
            self.assertEqual(setup.main(['install-schema'],environment={}),1);self.assertIn('setup_target_invalid',output.getvalue());apply.assert_not_called()

    def test_setup_owner_and_registration_refusals_cannot_silently_provision_a_login(self):
        profile=self.profile();connection=Mock(autocommit=False)
        with self.assertRaises(setup.SetupError):
            with setup.owner(connection,profile.installation):self.fail('Owner not verified')
        connection.autocommit=True;connection.transaction.return_value=nullcontext()
        target=profile.installation.document['database_targets']['migration']
        def execute(query,values=None):
            if 'current_database()' in query:return Mock(fetchone=lambda:(target['database'],target['role'],True))
            if 'SELECT specification' in query:return Mock(fetchone=lambda:(profile.installation.document,))
            if 'rolcanlogin' in query:return Mock(fetchone=lambda:(True,))
            if 'SELECT purpose' in query:return Mock(fetchone=lambda:None)
            if 'provision_login' in query:return Mock(fetchone=lambda:(False,))
            return Mock()
        connection.execute.side_effect=execute
        with self.assertRaisesRegex(setup.SetupError,'login_rejected'):setup.register(connection,profile.installation)
        with self.assertRaisesRegex(setup.SetupError,'business_invalid'):setup.initialize(connection,profile.installation,None)

    def test_schema_entrypoint_pins_tls_and_redacts_driver_errors(self):
        profile=self.profile();connection=Mock()
        for failure in (False,True):
            with ExitStack() as stack:
                stack.enter_context(patch('appointment_system.runtime.contained_release',return_value=(Path('/synthetic/appointment-system'),{})))
                stack.enter_context(patch('appointment_system.configuration.load'));stack.enter_context(patch('appointment_system.configuration.installation',return_value=profile.installation.document))
                stack.enter_context(patch.object(migrate,'checked_config',return_value={'host':'synthetic.example.test'}))
                connect=stack.enter_context(patch.object(psycopg,'connect',return_value=nullcontext(connection)))
                stack.enter_context(patch.object(migrate,'apply',side_effect=psycopg.OperationalError('synthetic-secret') if failure else None))
                out=stack.enter_context(redirect_stdout(io.StringIO()))
                if failure:
                    with self.assertRaises(SystemExit) as raised:migrate.main()
                    self.assertNotIn('synthetic-secret',str(raised.exception))
                else:migrate.main();self.assertIn('verified and installed',out.getvalue())
                self.assertEqual(connect.call_args.kwargs['sslmode'],'verify-full');self.assertEqual(connect.call_args.kwargs['channel_binding'],'require');self.assertTrue(connect.call_args.kwargs['autocommit'])
