"""Production company connection checks precede every operation in one transaction."""
from dataclasses import replace
import hashlib
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4
import psycopg
from appointment_system.configuration import installation
from appointment_system.serialization import canonical
from appointment_system.service_control import ControlDatabase, ControlSettings, ControlError, settings_from_environment
from appointment_system.connection import StorageUnavailable
from .test_keys import ring, document


class CompanyConnectionBoundaries(TestCase):
    def setUp(self):
        self.facts = installation()
        self.dsn = 'host=localhost dbname=postgres user=abs_company password=synthetic-connection-only sslmode=require'
        self.settings = ControlSettings(self.dsn, self.facts['database_targets']['company'], ring(purpose='company-session'))
        self.database = ControlDatabase(self.settings)
        self.connection = MagicMock()
        self.connection.__enter__.return_value = self.connection
        self.operations = []
        self.identity = True
        self.authorized = True
        self.value = {'saved': True}
        self.connection.execute.side_effect = self.execute

    def execute(self, statement, parameters=()):
        self.operations.append((statement, parameters))
        if 'validate_caller' in statement:
            value = self.identity
        elif 'authorize_resource_operation' in statement:
            value = self.authorized
        else:
            value = self.value
        cursor = Mock(spec=['fetchone'])
        cursor.fetchone.return_value = (value,)
        return cursor

    def test_exact_installation_role_and_database_target_are_validated_before_the_operation(self):
        with patch('appointment_system.service_control.psycopg.connect', return_value=self.connection) as connect:
            result = self.database.call('SELECT protected_operation(%s)', ('synthetic-value',))
        self.assertEqual(result, {'saved': True})
        self.assertEqual(self.operations[:3], [
            ("SET LOCAL statement_timeout='5s'", ()), ("SET LOCAL lock_timeout='2s'", ()),
            ('SELECT appointment_system.validate_caller(%s,%s,%s,%s)',
             (self.facts['installation_id'], self.facts['environment'], 'company', 1))])
        self.assertEqual(self.operations[3], ('SELECT protected_operation(%s)', ('synthetic-value',)))
        self.assertEqual(connect.call_args.kwargs['sslmode'], 'verify-full')
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 3)
        self.assertIsNone(connect.call_args.kwargs['prepare_threshold'])
        self.connection.__exit__.assert_called_once_with(None, None, None)

    def test_rejected_or_numeric_caller_identity_stops_before_private_operation(self):
        for identity in (False, None, 1):
            self.identity = identity
            self.operations.clear()
            with patch('appointment_system.service_control.psycopg.connect', return_value=self.connection):
                with self.assertRaises(ControlError):
                    self.database.call('SELECT protected_operation()')
            self.assertEqual(len(self.operations), 3)
        self.assertNotIn(self.dsn, str(ControlError()))

    def test_resource_consent_authority_is_checked_inside_the_same_transaction(self):
        authority = ('session', 'csrf', 'owner', 'grant')
        with patch('appointment_system.service_control.psycopg.connect', return_value=self.connection):
            self.assertEqual(self.database.call('SELECT protected_resource()', resource_authority=authority), self.value)
        self.assertEqual(self.operations[3], ('SELECT appointment_system.authorize_resource_operation(%s,%s,%s,%s)', authority))
        self.assertEqual(self.operations[4], ('SELECT protected_resource()', ()))
        for invalid in ((), authority[:3], list(authority)):
            self.operations.clear()
            with patch('appointment_system.service_control.psycopg.connect', return_value=self.connection):
                with self.assertRaises(ControlError) as error:
                    self.database.call('SELECT protected_resource()', resource_authority=invalid)
            self.assertEqual(error.exception.status, 403)
            self.assertEqual(len(self.operations), 3)
        for authorized in (False, None, 1):
            self.authorized = authorized
            self.operations.clear()
            with patch('appointment_system.service_control.psycopg.connect', return_value=self.connection):
                with self.assertRaises(ControlError) as error:
                    self.database.call('SELECT protected_resource()', resource_authority=authority)
            self.assertEqual(error.exception.status, 401)
            self.assertEqual(len(self.operations), 4)

    def test_database_failures_have_named_public_codes_without_connection_details(self):
        for code, expected, status in [('P0401', 'company_session_required', 401),
            ('P0409', 'company_state_changed', 409), ('P0422', 'invalid_company_request', 422),
            ('42501', 'company_access_rejected', 403), ('08006', 'company_tools_unavailable', 503)]:
            class Failure(psycopg.Error):
                sqlstate = code
            with patch('appointment_system.service_control.psycopg.connect', side_effect=Failure(self.dsn)):
                with self.assertRaises(ControlError) as error:
                    self.database.call('SELECT protected_operation()')
            self.assertEqual((error.exception.code, error.exception.status), (expected, status))
            self.assertNotIn('synthetic-connection', str(error.exception))

    def test_changed_connection_or_session_audience_is_rejected_before_connecting(self):
        for changed in ({'dsn': self.dsn.replace('abs_company', 'appointment_system_web')},
            {'session_keys': ring()}, {'session_keys': replace(self.settings.session_keys, installation_id=str(uuid4()))},
            {'session_keys': replace(self.settings.session_keys, environment='production')}):
            with patch('appointment_system.service_control.psycopg.connect') as connect:
                with self.assertRaises((ControlError, StorageUnavailable)):
                    replace(self.settings, **changed)
                connect.assert_not_called()
        for value in (None, '', 'x' * 8193):
            with self.assertRaises(ControlError) as error:
                self.settings.digest('session', value)
            self.assertEqual(error.exception.status, 401)
        self.assertNotEqual(self.settings.digest('session', 'token'), self.settings.digest('csrf', 'token'))

    def test_configuration_uses_its_declared_company_target_and_returns_no_partial_settings(self):
        environment = {'BOOKING_COMPANY_DATABASE_URL': self.dsn,
                       'BOOKING_COMPANY_SESSION_KEYS': canonical(document(purpose='company-session'))}
        value = settings_from_environment(environment=environment)
        self.assertIsInstance(value, ControlSettings)
        self.assertEqual(value.expected_host, self.facts['database_targets']['company']['host'])
        self.assertEqual(value.google_client_id, '')
        for changed in ({'BOOKING_COMPANY_DATABASE_URL': ''}, {'BOOKING_COMPANY_SESSION_KEYS': '{}'}):
            self.assertIsNone(settings_from_environment(environment=environment | changed))
        self.assertIsNone(settings_from_environment(environment={}))

    def test_control_command_binds_exact_operation_intent_and_does_not_interpolate_parameters(self):
        operation, generation = uuid4(), uuid4()
        body = dict(operation_id=str(operation), generation=str(generation), revision='7', enabled=False, reason='Reviewed pause')
        with patch.object(self.database, 'call', return_value={'progress': 'applying'}) as call:
            result = self.database.command('token', 'csrf', operation, generation, '7', False, 'Reviewed pause')
        self.assertEqual(result, {'progress': 'applying'})
        self.assertEqual(call.call_args.args, ('SELECT appointment_system.control_command(%s,%s,%s,%s,%s,%s,%s,%s)',
            ('token', 'csrf', operation, generation, 7, False, 'Reviewed pause', hashlib.sha256(canonical(body)).hexdigest())))

    def test_publication_and_probe_wrappers_keep_owned_operation_and_lease(self):
        job = {'operation_id': str(uuid4()), 'lease_token': str(uuid4())}
        with patch.object(self.database, 'call', return_value={'code': 'ok'}) as call:
            self.database.finish_publication(job, {'enabled': False})
            statement, args = call.call_args.args
            self.assertEqual(statement, 'SELECT appointment_system.control_finish_publication(%s,%s,%s,%s)')
            self.assertEqual(args[:2], (job['operation_id'], job['lease_token']))
            self.assertEqual(args[2].obj, {'enabled': False})
            self.database.finish_publication(job, error='projection_unavailable')
            self.assertEqual(call.call_args.args[1][2:], (None, 'projection_unavailable'))
            self.database.record_probe(job, {'observed': True})
            self.assertEqual(call.call_args.args[1][1].obj, {'observed': True})
            self.database.probe_retry(job, 'retry')
            self.assertEqual(call.call_args.args[1], (job['operation_id'], job['lease_token'], 'retry'))
            for method, sql, args in [('status', 'control_control_status', ('token',)),
                ('incidents', 'read_operation_incidents', ('token',)),
                ('claim_probe', 'control_claim_probe', ()), ('claim_publication', 'control_claim_publication', ())]:
                self.assertEqual(getattr(self.database, method)(*args), {'code': 'ok'})
                self.assertEqual(call.call_args.args[0], 'SELECT appointment_system.' + sql + ('(%s)' if args else '()'))
