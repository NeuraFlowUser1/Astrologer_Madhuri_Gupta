"""Native owner recovery preserves authority, retry identity and immutable audit."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
import unittest
from uuid import uuid4
import psycopg
from appointment_system.company_auth import verify
from appointment_system.settings import Installation
from tools import company_recovery as recovery,setup
from tools.checks.sql_target import ROOT
from . import test_setup as first_setup


@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned isolated SQL target required.')
class CompanyRecoverySQL(unittest.TestCase):
    setUpClass=classmethod(first_setup.SetupSQL.setUpClass.__func__)
    connect=first_setup.SetupSQL.connect

    def setUp(self):
        first_setup.SetupSQL.setUp(self)
        setup.initialize(self.connection,self.installation,self.business)
        setup.register(self.connection,self.installation)
        self.old='Synthetic initial private company password'
        self.new='Synthetic replacement private company password'
        setup.enroll(self.connection,self.installation,'company.owner',self.old)
        self.args={'operation':str(uuid4()),'expected_revision':1,'reason':'Verified owner lost the saved credential'}

    def recover(self,connection=None,**changes):
        return recovery.recover(connection or self.connection,self.installation,'company.owner',self.new,**(self.args|changes))

    def state(self):
        return self.connection.execute('SELECT credential_revision,password_hash,enabled FROM appointment_system.company_credentials').fetchone()

    def test_recovery_revokes_sessions_and_pending_login_then_retries_without_resetting_again(self):
        token=uuid4().hex*2
        with psycopg.connect(host=self.socket,dbname=self.facts['database_targets']['company']['database'],user='abs_company',autocommit=True) as caller:
            attempt=caller.execute('SELECT appointment_system.company_login_begin(%s,%s,%s)',
                ('company.owner',uuid4().hex*2,hashlib.sha256(b'company.owner').hexdigest())).fetchone()[0]
            self.assertTrue(caller.execute('SELECT appointment_system.company_login_finish(%s,%s,true,%s,%s)',
                (attempt['attempt_id'],attempt['credential_revision'],token,uuid4().hex*2)).fetchone()[0])
            pending=caller.execute('SELECT appointment_system.company_login_begin(%s,%s,%s)',
                ('company.owner',uuid4().hex*2,hashlib.sha256(b'company.owner').hexdigest())).fetchone()[0]
            self.assertEqual(self.recover(),{'status':'recovered','credential_revision':2,'changed':True})
            self.assertFalse(caller.execute('SELECT appointment_system.company_session_touch(%s)',(token,)).fetchone()[0])
            self.assertFalse(caller.execute('SELECT appointment_system.company_login_finish(%s,%s,true,%s,%s)',
                (pending['attempt_id'],pending['credential_revision'],uuid4().hex*2,uuid4().hex*2)).fetchone()[0])
        before=self.state();self.assertTrue(verify(before[1],self.new));self.assertFalse(verify(before[1],self.old))
        self.assertEqual(self.recover(),{'status':'existing','credential_revision':2,'changed':False})
        self.assertEqual(self.state(),before)
        audit=self.connection.execute('SELECT previous_revision,resulting_revision,operator_role,reason FROM appointment_system.company_password_recoveries').fetchall()
        self.assertEqual(audit,[(1,2,'postgres',self.args['reason'])])
        self.assertNotIn(self.new,str(audit));self.assertNotIn(before[1],str(audit))
        self.assertEqual(recovery.inspect(self.connection,self.installation,'Company.Owner'),{'status':'inspected','credential_revision':2,'enabled':True})

    def test_missing_disabled_or_invalid_target_is_not_created_or_reactivated(self):
        with self.assertRaisesRegex(setup.SetupError,'account_missing'):
            recovery.recover(self.connection,self.installation,'wrong.owner',self.new,**self.args)
        with self.assertRaisesRegex(setup.SetupError,'account_missing'):
            recovery.inspect(self.connection,self.installation,'wrong.owner')
        self.connection.execute('UPDATE appointment_system.company_credentials SET enabled=false')
        with self.assertRaisesRegex(setup.SetupError,'disabled_account'):self.recover()
        self.assertEqual(self.state()[::2],(1,False))
        for changed in ({'operation':'invalid'},{'operation':'1257662B-C555-4CE5-BD4F-0EAB2BFE89B8'},{'operation':'0'*32},
            {'expected_revision':True},{'expected_revision':0},{'expected_revision':2**63-1},
            {'reason':'short'},{'reason':'a'*301},{'reason':'bad\nnew line'}):
            with self.subTest(changed=changed),self.assertRaisesRegex(setup.SetupError,'request_invalid'):
                self.recover(**changed)

    def test_stale_conflicting_and_superseded_operations_cannot_reset_current_access(self):
        with self.assertRaisesRegex(setup.SetupError,'revision_conflict'):self.recover(expected_revision=2)
        self.recover();before=self.state()
        with self.assertRaisesRegex(setup.SetupError,'operation_conflict'):self.recover(reason='A different recovery reason')
        with self.assertRaisesRegex(setup.SetupError,'operation_conflict'):
            recovery.recover(self.connection,self.installation,'company.owner',self.old,**self.args)
        self.assertEqual(self.state(),before)
        self.recover(operation=str(uuid4()),expected_revision=2)
        with self.assertRaisesRegex(setup.SetupError,'operation_conflict'):self.recover()
        self.assertEqual(self.state()[0],3)

    def test_foreign_installation_or_ordinary_runtime_authority_cannot_recover(self):
        facts=deepcopy(self.facts);facts['installation_id']=str(uuid4())
        with self.assertRaisesRegex(setup.SetupError,'installation_mismatch'):
            recovery.recover(self.connection,Installation.parse(facts),'company.owner',self.new,**self.args)
        facts=deepcopy(self.facts);facts['database_targets']['migration']['database']='foreign_database'
        with self.assertRaisesRegex(setup.SetupError,'owner_required'):
            recovery.inspect(self.connection,Installation.parse(facts),'company.owner')
        for purpose in ('web','staff','worker','company','backup','maintenance','journal'):
            target=self.facts['database_targets'][purpose]
            with psycopg.connect(host=self.socket,dbname=target['database'],user=target['role'],autocommit=True) as connection:
                with self.assertRaisesRegex(setup.SetupError,'owner_required'):self.recover(connection)
        self.assertEqual(self.state()[0],1)

    def test_audit_failure_rolls_back_password_change_and_session_revocation(self):
        before=self.state()
        token=uuid4().hex*2
        caller=psycopg.connect(host=self.socket,dbname=self.facts['database_targets']['company']['database'],user='abs_company',autocommit=True)
        self.addCleanup(caller.close)
        attempt=caller.execute('SELECT appointment_system.company_login_begin(%s,%s,%s)',
            ('company.owner',uuid4().hex*2,hashlib.sha256(b'company.owner').hexdigest())).fetchone()[0]
        self.assertTrue(caller.execute('SELECT appointment_system.company_login_finish(%s,%s,true,%s,%s)',
            (attempt['attempt_id'],attempt['credential_revision'],token,uuid4().hex*2)).fetchone()[0])
        self.connection.execute("CREATE FUNCTION appointment_system.synthetic_recovery_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic audit failure'; END $$; CREATE TRIGGER synthetic_recovery_failure BEFORE INSERT ON appointment_system.company_password_recoveries FOR EACH ROW EXECUTE FUNCTION appointment_system.synthetic_recovery_failure();")
        with self.assertRaises(psycopg.Error):self.recover()
        self.assertEqual(self.state(),before)
        self.assertTrue(caller.execute('SELECT appointment_system.company_session_touch(%s)',(token,)).fetchone()[0])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.company_password_recoveries').fetchone()[0],0)

    def test_simultaneous_different_operations_accept_only_one_expected_revision(self):
        def attempt(_):
            with self.connect() as connection:
                try:return self.recover(connection,operation=str(uuid4()))['status']
                except setup.SetupError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertCountEqual(results,['recovered','recovery_revision_conflict'])
        self.assertEqual(self.state()[0],2)

    def test_simultaneous_identical_operations_do_not_duplicate_recovery(self):
        def attempt(_):
            with self.connect() as connection:return self.recover(connection)['status']
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertCountEqual(results,['recovered','existing'])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.company_password_recoveries').fetchone()[0],1)

    def test_audit_is_immutable_readable_by_backup_and_in_its_inventory(self):
        self.recover()
        for command in ('DELETE FROM appointment_system.company_password_recoveries',
            "UPDATE appointment_system.company_password_recoveries SET reason='Changed old evidence'"):
            with self.assertRaises(psycopg.Error):self.connection.execute(command)
        with psycopg.connect(host=self.socket,dbname=self.facts['database_targets']['backup']['database'],user='abs_backup',autocommit=True) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM appointment_system.company_password_recoveries').fetchone()[0],1)
            with self.assertRaises(psycopg.Error):connection.execute('DELETE FROM appointment_system.company_password_recoveries')
        inventory=json.loads((ROOT/'database/relations.json').read_text())
        self.assertIn('appointment_system.company_password_recoveries',inventory)

    def test_unexpected_database_identity_result_rolls_back_the_operation(self):
        before=self.state()
        self.connection.execute("CREATE OR REPLACE FUNCTION appointment_system.provision_company_password(p_username text,p_hash text) RETURNS text LANGUAGE plpgsql AS $$ BEGIN UPDATE appointment_system.company_credentials SET password_hash=p_hash,credential_revision=credential_revision+1 WHERE username=p_username; RETURN 'synthetic-wrong-principal'; END $$;")
        with self.assertRaisesRegex(setup.SetupError,'identity_changed'):self.recover()
        self.assertEqual(self.state(),before)
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.company_password_recoveries').fetchone()[0],0)
