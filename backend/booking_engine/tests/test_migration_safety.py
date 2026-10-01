"""Migration atomicity, unchanged-history checks and target guard failures."""
import hashlib
import io
import os
import unittest
from unittest.mock import MagicMock,patch

import psycopg
from backend.booking_engine import migrate


class MigrationSafetyTests(unittest.TestCase):
    def connection(self,applied):
        connection=MagicMock()
        def execute(query,*parameters):
            result=MagicMock()
            if 'to_regclass' in query:result.fetchone.return_value=[None if applied is None else 'sarsa_booking.schema_migrations']
            elif query.startswith('SELECT version'):result.fetchall.return_value=list(applied.items())
            return result
        connection.execute.side_effect=execute
        return connection

    def test_history_mismatch_or_unknown_migration_aborts_before_application(self):
        sources=[('001_example.sql','CREATE TABLE example(id int)','a'*64)]
        for applied in [{'unrecognised.sql':'b'*64},{'001_example.sql':'b'*64}]:
            connection=self.connection(applied)
            with patch.object(migrate,'migration_sources',return_value=sources),self.assertRaises(ValueError):migrate.apply(connection)
            self.assertFalse(any(call.args[0].startswith('CREATE') for call in connection.execute.call_args_list))
            connection.transaction.return_value.__exit__.assert_called_once()

    def test_only_new_source_is_applied_and_recorded_inside_one_transaction(self):
        sources=[('001_example.sql','CREATE TABLE first(id int)','a'*64),('002_example.sql','CREATE TABLE second(id int)','b'*64)]
        for existing in [None,{'001_example.sql':'a'*64},{name:digest for name,_,digest in sources}]:
            connection=self.connection(existing)
            with patch.object(migrate,'migration_sources',return_value=sources):migrate.apply(connection)
            calls=[call.args for call in connection.execute.call_args_list]
            expected=2 if existing is None else 1 if len(existing)==1 else 0
            self.assertEqual(sum(query.startswith('CREATE') for query,*_ in calls),expected)
            self.assertEqual(sum(query.startswith('INSERT') for query,*_ in calls),expected)
            self.assertIn(('SELECT pg_advisory_xact_lock(%s)',(migrate.LOCK_ID,)),calls)
            connection.transaction.assert_called_once()

    def test_source_hashes_are_real_sorted_and_complete(self):
        sources=migrate.migration_sources()
        self.assertEqual([name for name,_,_ in sources],sorted(name for name,_,_ in sources))
        self.assertEqual(len(sources),31)
        for name,source,digest in sources:
            self.assertEqual(digest,hashlib.sha256((migrate.MIGRATIONS/name).read_bytes()).hexdigest())
            self.assertTrue(source.strip())

    def test_cli_refuses_pooler_or_wrong_host_and_suppresses_connection_details(self):
        for target,expected in [('same-pooler.example','same-pooler.example'),('wrong.example','approved.example')]:
            connection=MagicMock()
            with patch.dict(os.environ,{'SARSA_MIGRATION_DATABASE_URL':'synthetic-secret','SARSA_MIGRATION_EXPECTED_HOST':expected}),patch.object(migrate,'checked_config',return_value={'host':target,'sslmode':'verify-full'}),patch.object(migrate.psycopg,'connect',connection):
                with self.assertRaises(SystemExit) as error:migrate.main()
                self.assertNotIn('synthetic-secret',str(error.exception));connection.assert_not_called()

    def test_cli_success_and_connection_failure_preserve_explicit_target(self):
        environment={'SARSA_MIGRATION_DATABASE_URL':'synthetic-private','SARSA_MIGRATION_EXPECTED_HOST':'approved.example'}
        with patch.dict(os.environ,environment),patch.object(migrate,'checked_config',return_value={'host':'approved.example','sslmode':'verify-full'}),patch.object(migrate.psycopg,'connect') as connect,patch.object(migrate,'apply') as apply,patch('sys.stdout',new_callable=io.StringIO):
            migrate.main();apply.assert_called_once_with(connect.return_value.__enter__.return_value)
            connect.assert_called_once_with('synthetic-private',connect_timeout=10,autocommit=True)
        with patch.dict(os.environ,environment),patch.object(migrate,'checked_config',return_value={'host':'approved.example','sslmode':'disable'}),patch.object(migrate.psycopg,'connect') as connect:
            with self.assertRaises(SystemExit):migrate.main()
            connect.assert_not_called()
        with patch.dict(os.environ,environment),patch.object(migrate,'checked_config',return_value={'host':'approved.example','sslmode':'verify-full'}),patch.object(migrate.psycopg,'connect',side_effect=psycopg.OperationalError('synthetic-private')):
            with self.assertRaises(SystemExit) as error:migrate.main()
            self.assertNotIn('synthetic-private',str(error.exception))
