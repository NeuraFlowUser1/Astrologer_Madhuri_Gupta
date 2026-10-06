"""A provider permission is returned only after a matched database commit.

The native SQL suites prove the routines. These tests inject driver failures
at the actual Store boundary, where a lost commit reply must not mean success.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
import psycopg
from psycopg.conninfo import make_conninfo
from appointment_system.configuration import installation
from appointment_system.connection import StorageUnavailable
from appointment_system.storage import Store,UnavailableStore
from appointment_system.job_authority import JobClaim
from appointment_system.worker_authority import Turn,admitted
from appointment_system.recovery_contract import LANES
from appointment_system.request_budget import BudgetExpired
from appointment_system.service_control import ControlError


class Driver:
    def __init__(self,*,matched=True,failure=None,commit_failure=False):
        self.calls=[];self.matched=matched;self.failure=failure;self.commit_failure=commit_failure;self.events=[]
    def __enter__(self):self.events.append('entered');return self
    def __exit__(self,kind,value,traceback):
        self.events.append('rollback' if kind else 'commit')
        if self.commit_failure and kind is None:raise psycopg.OperationalError('synthetic-private-connection')
    def execute(self,statement,parameters=()):
        self.calls.append((statement,parameters))
        if 'validate_caller' in statement:return SimpleNamespace(fetchone=lambda:[self.matched])
        if statement=='SELECT synthetic_permission' and self.failure:raise self.failure
        return SimpleNamespace(fetchone=lambda:[{'permission':'synthetic'}])


class StorageTransactions(unittest.TestCase):
    def store(self,purpose='web'):
        target=installation()['database_targets'][purpose]
        return Store(make_conninfo(host=target['host'],dbname=target['database'],user=target['role'],password='synthetic-private-password',sslmode='require'),expected_host=target['host'],purpose=purpose)

    def test_tls_purpose_identity_and_commit_are_checked_before_returning_any_permission(self):
        store=self.store();driver=Driver()
        with patch('appointment_system.storage.psycopg.connect',return_value=driver) as connect:
            self.assertEqual(store._call('SELECT synthetic_permission'),{'permission':'synthetic'})
        self.assertEqual(driver.events,['entered','commit']);options=connect.call_args.kwargs
        self.assertEqual(options['sslmode'],'verify-full');self.assertTrue(options['sslrootcert']);self.assertEqual(options['connect_timeout'],3);self.assertIsNone(options['prepare_threshold'])
        identity=next(parameters for statement,parameters in driver.calls if 'validate_caller' in statement)
        self.assertEqual(identity,(installation()['installation_id'],installation()['environment'],'web',1))
        self.assertEqual(driver.calls[-1][0],'SELECT synthetic_permission')

    def test_nonboolean_or_wrong_database_match_rolls_back_before_the_requested_call(self):
        for match in (False,None,1,'true'):
            driver=Driver(matched=match)
            with self.subTest(match=match),patch('appointment_system.storage.psycopg.connect',return_value=driver),self.assertRaises(StorageUnavailable):self.store()._call('SELECT synthetic_permission')
            self.assertEqual(driver.events,['entered','rollback']);self.assertFalse(any(s=='SELECT synthetic_permission' for s,_ in driver.calls))

    def test_uncertain_commit_and_driver_errors_never_return_or_expose_connection_values(self):
        for driver in (Driver(commit_failure=True),Driver(failure=psycopg.OperationalError('synthetic-private-password'))):
            with patch('appointment_system.storage.psycopg.connect',return_value=driver),self.assertRaises(StorageUnavailable) as error:self.store()._call('SELECT synthetic_permission')
            self.assertNotIn('synthetic-private',str(error.exception))
        for code,status,message in [('P0444',404,'booking_disabled'),('P0409',409,'booking_activation_changed')]:
            error_type=type('SyntheticControlError',(psycopg.Error,),{'sqlstate':code});driver=Driver(failure=error_type('private details'))
            with patch('appointment_system.storage.psycopg.connect',return_value=driver),self.assertRaises(ControlError) as error:self.store()._call('SELECT synthetic_permission')
            self.assertEqual(error.exception.code,message);self.assertEqual(error.exception.status,status)

    def test_time_budget_stops_before_connection_or_rolls_back_before_commit(self):
        with patch('appointment_system.request_budget.remaining',side_effect=BudgetExpired()),patch('appointment_system.storage.psycopg.connect') as connect,self.assertRaises(BudgetExpired):self.store()._call('SELECT synthetic_permission')
        connect.assert_not_called()
        driver=Driver()
        with patch('appointment_system.request_budget.remaining',side_effect=[5,BudgetExpired()]),patch('appointment_system.storage.psycopg.connect',return_value=driver),self.assertRaises(BudgetExpired):self.store()._call('SELECT synthetic_permission')
        self.assertEqual(driver.events,['entered','rollback'])

    def test_worker_turn_and_transport_claim_are_enforced_before_business_sql(self):
        turn=Turn(str(uuid4()),next(iter(LANES)),str(uuid4()),'a'*64,str(uuid4()))
        claim=JobClaim('booking',str(uuid4()),str(uuid4()),2,installation()['installation_id'],turn.generation,'a'*64,1)
        driver=Driver()
        with admitted(turn),patch('appointment_system.storage.psycopg.connect',return_value=driver):self.store('worker')._call('SELECT synthetic_permission',job_authority=claim)
        calls=[(s,p) for s,p in driver.calls if 'require_' in s];self.assertEqual(calls[0][1],turn.parameters());self.assertEqual(calls[1][1],claim.parameters());self.assertEqual(driver.calls[-1][0],'SELECT synthetic_permission')
        with patch('appointment_system.storage.psycopg.connect',return_value=Driver()),self.assertRaisesRegex(ValueError,'job_claim_invalid'):self.store('worker')._call('SELECT synthetic_permission',job_authority={})
        driver=Driver()
        with admitted(turn),patch('appointment_system.storage.psycopg.connect',return_value=driver):self.store('staff')._call('SELECT synthetic_permission')
        self.assertFalse(any('require_worker_turn' in s for s,_ in driver.calls))

    def test_diagnostic_connection_has_shorter_limits_and_missing_purpose_never_borrows_credentials(self):
        driver=Driver()
        with patch('appointment_system.storage.psycopg.connect',return_value=driver) as connect:self.store().record_operation_incident(str(uuid4()),'booking','request','service_unavailable',20)
        self.assertEqual(connect.call_args.kwargs['connect_timeout'],2);self.assertEqual(connect.call_args.kwargs['tcp_user_timeout'],2000)
        self.assertEqual(driver.calls[0][0],"SET LOCAL statement_timeout = '300ms'");self.assertEqual(driver.calls[1][0],"SET LOCAL lock_timeout = '100ms'")
        unavailable=UnavailableStore()
        with self.assertRaises(AttributeError):unavailable._dsn
        with self.assertRaises(StorageUnavailable):unavailable.start_order_creation('synthetic')
        store=self.store();store._expected_host='foreign.example.test'
        with patch('appointment_system.storage.psycopg.connect') as connect,self.assertRaises(StorageUnavailable):store._call('SELECT synthetic_permission')
        connect.assert_not_called()
