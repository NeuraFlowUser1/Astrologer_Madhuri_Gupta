"""Real login privileges, independent of HTTP checks. No RLS claim is made."""
import json
import os
import unittest
from pathlib import Path
from uuid import uuid4
from appointment_system.settings import BusinessSettings
from tools.checks.sql_target import SQLTarget,literal
from .fixtures import installation,business


@unittest.skipUnless(os.environ.get("BOOKING_SQL_TEST_TARGET"),"Owned isolated SQL target required.")
class PermissionsSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=SQLTarget(os.environ["BOOKING_SQL_TEST_TARGET"]);cls.db.check_owned()
        cls.profile=installation()
        cls.db.scalar("SELECT appointment_system.configure_installation("+literal(cls.profile)+"::jsonb,"+
                       literal(BusinessSettings.parse(business()).document)+"::jsonb,true);")
        for purpose,target in cls.profile["database_targets"].items():
            cls.db.scalar("SELECT appointment_system.provision_login("+literal(target["role"])+","+literal(purpose)+");")

    def denied(self,statement,role):
        result=self.db.sql("\\set VERBOSITY verbose\n"+statement,role=role,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("42501",result.stderr)

    def test_only_the_declared_purpose_and_installation_pass_the_caller_check(self):
        for purpose,target in self.profile["database_targets"].items():
            role=target["role"]
            self.assertEqual(self.db.scalar("SELECT appointment_system.validate_caller("+
                literal(self.profile["installation_id"])+",'test',"+literal(purpose)+",1);",role=role),"t")
            for wrong in ("wrong-purpose","production",str(uuid4())):
                installation_id=str(uuid4()) if "-" in wrong and wrong!="wrong-purpose" else self.profile["installation_id"]
                environment=wrong if wrong=="production" else "test"
                requested=wrong if wrong=="wrong-purpose" else purpose
                self.assertEqual(self.db.scalar("SELECT appointment_system.validate_caller("+
                  literal(installation_id)+","+literal(environment)+","+literal(requested)+",1);",role=role),"f")
        self.assertEqual(self.db.scalar("SELECT appointment_system.validate_caller("+
             literal(self.profile["installation_id"])+",'test','web',1);"),"f")

    def test_application_roles_cannot_read_or_rewrite_tables_or_create_objects(self):
        for role in ("appointment_system_web","abs_staff","abs_worker","abs_company","abs_maintenance","abs_journal"):
            for statement in ("SELECT * FROM appointment_system.bookings;",
                              "SELECT password_hash FROM appointment_system.company_credentials;",
                              "DELETE FROM appointment_system.control_product_state;",
                              "UPDATE appointment_system.intake_settings SET public_open=true;",
                              "CREATE TABLE appointment_system.intrusion(id integer);"):
                with self.subTest(role=role,statement=statement):self.denied(statement,role)

    def test_web_cannot_use_company_auth_maintenance_or_worker_claims(self):
        for statement in ("SELECT appointment_system.company_login_begin('company.owner',repeat('a',64),repeat('b',64));",
                          "SELECT appointment_system.control_claim_publication();",
                          "SELECT appointment_system.claim_google_delivery();",
                          "SELECT appointment_system.provision_company_password('company.owner','bad');"):
            self.denied(statement,"appointment_system_web")

    def test_worker_and_staff_cannot_create_company_password_authority(self):
        for role in ("abs_worker","abs_staff"):
            self.denied("SELECT appointment_system.company_login_begin('company.owner',repeat('a',64),repeat('b',64));",role)
            self.denied("SELECT appointment_system.control_control_status(repeat('a',64));",role)

    def test_retired_google_company_login_helpers_are_absent_for_every_application_role(self):
        for role in ('appointment_system_web','abs_staff','abs_worker','abs_company'):
            self.assertEqual(self.db.scalar("SELECT to_regprocedure('appointment_system.control_login_start(text,text,text,text)') IS NULL;",role=role),'t')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='appointment_system' AND p.proname IN('control_login_start','control_login_consume','control_session_start','begin_recovery_lane','finish_recovery_lane');"),'0')

    def test_backup_can_dump_records_but_cannot_change_data_or_run_money_or_control(self):
        self.assertEqual(self.db.scalar("SELECT count(*)>=0 FROM appointment_system.bookings;",role="abs_backup"),"t")
        self.denied("DELETE FROM appointment_system.bookings;","abs_backup")
        self.denied("SELECT appointment_system.control_claim_publication();","abs_backup")
        self.denied("SELECT appointment_system.start_order_creation(gen_random_uuid(),gen_random_uuid());","abs_backup")

    def test_revoked_writer_is_rejected_even_if_its_password_and_membership_still_work(self):
        self.db.sql("UPDATE appointment_system.caller_logins SET enabled=false WHERE login_role='appointment_system_web';")
        try:
            self.assertEqual(self.db.scalar("SELECT appointment_system.validate_caller("+
               literal(self.profile["installation_id"])+",'test','web',1);",role="appointment_system_web"),"f")
            self.denied("SELECT appointment_system.public_policy();","appointment_system_web")
        finally:self.db.sql("UPDATE appointment_system.caller_logins SET enabled=true WHERE login_role='appointment_system_web';")

    def test_definer_functions_have_fixed_safe_lookup_order_and_no_public_execute(self):
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
          "WHERE n.nspname='appointment_system' AND p.prosecdef AND NOT "
          "('search_path=pg_catalog, appointment_system, pg_temp'=ANY(p.proconfig));"),"0")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
          "CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
          "WHERE n.nspname='appointment_system' AND a.grantee=0 AND a.privilege_type='EXECUTE';"),"0")

    def test_schema_routines_and_records_have_one_nonlogin_owner(self):
        self.assertEqual(self.db.scalar("SELECT NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolbypassrls FROM pg_roles WHERE rolname='appointment_system_owner';"),'t')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='appointment_system' AND pg_get_userbyid(p.proowner)<>'appointment_system_owner';"),'0')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='appointment_system' AND c.relkind IN ('r','p') AND pg_get_userbyid(c.relowner)<>'appointment_system_owner';"),'0')
        for target in self.profile['database_targets'].values():
            self.assertEqual(self.db.scalar("SELECT pg_has_role("+literal(target['role'])+",'appointment_system_owner','MEMBER');"),'f')

    def test_accidentally_privileged_runtime_login_is_refused(self):
        self.db.sql('ALTER ROLE appointment_system_web CREATEDB;')
        try:
            self.assertEqual(self.db.scalar('SELECT appointment_system.validate_caller('+literal(self.profile['installation_id'])+",'test','web',1);",role='appointment_system_web'),'f')
            self.denied('SELECT appointment_system.public_policy();','appointment_system_web')
        finally:self.db.sql('ALTER ROLE appointment_system_web NOCREATEDB;')

    def test_an_unrelated_capability_membership_cannot_expand_a_runtime_login(self):
        self.db.sql('GRANT appointment_system_company_access TO appointment_system_web;')
        try:
            self.assertEqual(self.db.scalar('SELECT appointment_system.validate_caller('+literal(self.profile['installation_id'])+",'test','web',1);",role='appointment_system_web'),'f')
            self.denied('SELECT appointment_system.public_policy();','appointment_system_web')
            self.denied('SELECT appointment_system.company_login_begin(\'company.owner\',repeat(\'a\',64),repeat(\'b\',64));','appointment_system_web')
        finally:self.db.sql('REVOKE appointment_system_company_access FROM appointment_system_web;')
