"""Committed company authority and fenced commands on owned synthetic databases."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from copy import deepcopy
import hashlib
import os
import unittest
from uuid import uuid4
from appointment_system.company_auth import password_hash
from appointment_system.serialization import canonical
from appointment_system.settings import BusinessSettings
from tools.checks.sql_target import SQLTarget,literal
from .fixtures import installation,business


@unittest.skipUnless(os.environ.get("BOOKING_SQL_TEST_TARGET"),"Owned isolated SQL target required.")
class CompanyFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=SQLTarget(os.environ["BOOKING_SQL_TEST_TARGET"]);cls.db.check_owned()
        cls.declared=installation();cls.declared["database_targets"]["web"]["role"]="appointment_system_web"
        cls.db.scalar("SELECT appointment_system.configure_installation("+literal(cls.declared)+"::jsonb,"+
                      literal(BusinessSettings.parse(business()).document)+"::jsonb,true);")
        cls.hash=password_hash("Synthetic company password for tests")

    def setUp(self):
        self.db.sql("TRUNCATE appointment_system.company_login_attempts CASCADE;"
                    "TRUNCATE appointment_system.control_company_sessions;"
                    "UPDATE appointment_system.control_product_state SET winning_operation=NULL,enabled=true,requested_enabled=true;"
                    "DELETE FROM appointment_system.control_command_progress;"
                    "DELETE FROM appointment_system.control_publications;"
                    "DELETE FROM appointment_system.control_operations;")
        self.db.scalar("SELECT appointment_system.configure_installation("+literal(self.declared)+"::jsonb,"+
                      literal(BusinessSettings.parse(business()).document)+"::jsonb,true);")
        self.db.scalar("SELECT appointment_system.provision_login('abs_company','company');")
        self.subject=self.db.scalar("SELECT appointment_system.provision_company_password('company.owner',"+literal(self.hash)+");")
        self.token=uuid4().hex*2;self.csrf=uuid4().hex*2
        self.assertTrue(self.finish(self.begin(),True))

    def begin(self,name="company.owner",risk=None):
        return self.db.value("SELECT appointment_system.company_login_begin("+literal(name)+","+
                  literal(risk or uuid4().hex*2)+","+literal(hashlib.sha256(name.encode()).hexdigest())+");",role='abs_company')

    def finish(self,attempt,verified,revision=None):
        return self.db.scalar("SELECT appointment_system.company_login_finish("+literal(attempt["attempt_id"])+","+
               str(attempt["credential_revision"] if revision is None else revision)+","+
               ("true" if verified else "false")+","+literal(self.token)+","+literal(self.csrf)+");",role='abs_company')=="t"

    def status(self):
        return self.db.value("SELECT appointment_system.control_control_status("+literal(self.token)+");",role='abs_company')

    def change(self,enabled,*,operation=None,status=None,reason="Synthetic switch test"):
        snap=(status or self.status())["snapshot"];operation=operation or str(uuid4())
        body={"operation_id":operation,"generation":snap["restore_generation"],"revision":snap["revision"],
              "enabled":enabled,"reason":reason}
        digest=hashlib.sha256(canonical(body)).hexdigest()
        statement="SELECT appointment_system.control_command("+",".join((
          literal(self.token),literal(self.csrf),literal(operation),literal(snap["restore_generation"]),
          snap["revision"],"true" if enabled else "false",literal(reason),literal(digest)))+");"
        return self.db.value(statement,role='abs_company'),statement

    def claim(self):
        return self.db.value("SELECT appointment_system.control_claim_publication();",role='abs_company')

    def acknowledge(self,job,ack=None,error=None):
        return self.db.scalar("SELECT appointment_system.control_finish_publication("+literal(job["operation_id"])+","+
                   literal(job["lease_token"])+","+literal(job["snapshot"] if ack is None else ack)+"::jsonb,"+
                   ("NULL" if error is None else literal(error))+");",role='abs_company')=="t"

class CompanySQL(CompanyFixture):
    def test_password_reset_revokes_old_sessions_and_prevents_stale_hash_login(self):
        attempt=self.begin()
        self.db.scalar("SELECT appointment_system.provision_company_password('company.owner',"+literal(self.hash)+");")
        self.assertFalse(self.finish(attempt,True))
        self.assertEqual(self.db.scalar("SELECT appointment_system.company_session_touch("+literal(self.token)+");"),"f")

    def test_failed_unknown_expired_and_replayed_login_cannot_open_session(self):
        attempt=self.begin();self.assertFalse(self.finish(attempt,False));self.assertFalse(self.finish(attempt,True))
        unknown=self.begin("unknown.owner");self.assertIsNone(unknown["password_hash"])
        unknown["credential_revision"]=1;self.assertFalse(self.finish(unknown,True))
        attempt=self.begin();self.db.sql("UPDATE appointment_system.company_login_attempts SET expires_at=clock_timestamp()-interval '1 second';")
        self.assertFalse(self.finish(attempt,True))

    def test_admission_limits_and_idle_expiry_are_enforced_in_database(self):
        for _ in range(4):self.assertIn("attempt_id",self.begin())
        self.assertEqual(self.begin(),{"code":"please_wait"})
        self.db.sql("UPDATE appointment_system.control_company_sessions SET last_used_at=clock_timestamp()-interval '31 minutes';")
        self.assertEqual(self.db.scalar("SELECT appointment_system.company_session_touch("+literal(self.token)+");"),"f")

    def test_off_denies_immediately_and_only_verified_current_probe_is_effective(self):
        result,_=self.change(False);self.assertEqual(result["progress"],"accepted")
        self.assertEqual(self.status()["admission_mode"],"off")
        job=self.claim();self.assertTrue(self.acknowledge(job))
        self.assertEqual(self.status()["progress"],"published")
        mismatch=deepcopy(job["snapshot"]);mismatch["revision"]="1"
        self.assertEqual(self.db.scalar("SELECT appointment_system.control_record_probe("+literal(job["operation_id"])+","+
                       literal(mismatch)+"::jsonb);"),"f")
        self.assertEqual(self.db.scalar("SELECT appointment_system.control_record_probe("+literal(job["operation_id"])+","+
                       literal(job["snapshot"])+"::jsonb);"),"t")
        self.assertEqual(self.status()["progress"],"effective")

    def test_on_keeps_admission_off_until_exact_publication_acknowledgement(self):
        result,_=self.change(True);self.assertEqual(result["current"]["admission_mode"],"off")
        job=self.claim();bad=deepcopy(job["snapshot"]);bad["activation_epoch"]=str(uuid4())
        self.assertTrue(self.acknowledge(job,bad))
        self.assertEqual(self.status()["admission_mode"],"off")
        self.db.sql("UPDATE appointment_system.control_publications SET next_attempt_at=clock_timestamp();")
        retry=self.claim();self.assertTrue(self.acknowledge(retry))
        self.assertEqual(self.status()["admission_mode"],"on")

    def test_interrupted_host_probe_is_claimed_without_another_publication(self):
        accepted,_=self.change(False);published=self.claim();self.assertTrue(self.acknowledge(published))
        self.assertIsNone(self.claim())
        probe=self.db.value('SELECT appointment_system.control_claim_probe();',role='abs_company')
        self.assertEqual(probe['operation_id'],accepted['receipt']['operation_id'])
        self.assertEqual(probe['snapshot'],published['snapshot'])
        self.assertIsNone(self.db.value('SELECT appointment_system.control_claim_probe();',role='abs_company'))
        self.assertEqual(self.db.scalar('SELECT appointment_system.control_probe_retry('+literal(probe['operation_id'])+
            ','+literal(probe['lease_token'])+",'hosted_probe_unavailable');",role='abs_company'),'t')
        self.assertIsNone(self.db.value('SELECT appointment_system.control_claim_probe();',role='abs_company'))
        self.db.sql('UPDATE appointment_system.control_publications SET next_attempt_at=clock_timestamp();')
        retry=self.db.value('SELECT appointment_system.control_claim_probe();',role='abs_company')
        self.assertNotEqual(retry['lease_token'],probe['lease_token'])
        self.assertEqual(self.db.scalar('SELECT appointment_system.control_record_probe('+literal(retry['operation_id'])+
            ','+literal(retry['snapshot'])+'::jsonb);',role='abs_company'),'t')
        self.assertIsNone(self.db.value('SELECT appointment_system.control_claim_probe();',role='abs_company'))
        self.assertEqual(self.status()['progress'],'effective')

    def test_late_on_ack_cannot_defeat_newer_off(self):
        old,_=self.change(True);job=self.claim();new,_=self.change(False)
        self.assertFalse(self.acknowledge(job));current=self.status()
        self.assertEqual(current["requested_mode"],"off");self.assertEqual(current["admission_mode"],"off")
        self.assertEqual(current["operation_id"],new["receipt"]["operation_id"])
        old_progress=self.db.value("SELECT appointment_system.control_command_result("+literal(self.token)+","+
                                  literal(old["receipt"]["operation_id"])+");")
        self.assertEqual(old_progress["progress"],"superseded")

    def test_replay_preserves_accepted_receipt_and_changed_body_is_rejected(self):
        first,statement=self.change(False);job=self.claim();self.acknowledge(job)
        replay=self.db.value(statement)
        self.assertEqual(first["receipt"],replay["receipt"]);self.assertEqual(replay["progress"],"published")
        bad=statement.replace("Synthetic switch test","Different switch reason")
        self.assertNotEqual(self.db.sql(bad,check=False).returncode,0)

    def test_concurrent_commands_have_one_winner_and_no_stale_update(self):
        state=self.status()
        start=Barrier(8)
        def command(index):
            start.wait(timeout=15)
            try:return self.change(index%2==0,status=state)[0]
            except AssertionError as error:
                self.assertIn("control state changed",str(error));return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(command,range(8)))
        self.assertEqual(sum(result is not None for result in results),1)

    def test_fresh_password_confirmation_is_required_for_new_command_not_receipt_retry(self):
        accepted,statement=self.change(False)
        self.db.sql("UPDATE appointment_system.control_company_sessions SET created_at=clock_timestamp()-interval '1 hour',"
                    "fresh_until=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.db.value(statement)["receipt"],accepted["receipt"])
        with self.assertRaises(AssertionError):self.change(True)
