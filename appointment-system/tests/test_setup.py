"""Native first-installation proof using one owned synthetic database only."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import unittest
import psycopg
from psycopg import sql
from tests.fixtures import installation,business
from tools.checks.sql_target import SQLTarget,ROOT
from appointment_system.settings import Installation,BusinessSettings
from appointment_system.company_auth import verify

from tools import setup
DATABASE='abs_setup_proof'


@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned isolated SQL target required.')
class SetupSQL(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.target=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET']);cls.target.check_owned();cls.socket=cls.target.native_socket()
  # Provider-created logins are an input to installation, not a side effect of
  # another test. Prepare them even when this suite is first in a fresh target.
  # Only synthetic fixture names are used in the owned, disconnected container.
  with psycopg.connect(host=cls.socket,dbname='postgres',user='postgres',autocommit=True) as admin:
   for target in installation()['database_targets'].values():
    role=target['role']
    if admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone() is None:
     admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(role)))

 def setUp(self):
  with psycopg.connect(host=self.socket,dbname='postgres',user='postgres',autocommit=True) as admin:
   admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(DATABASE)))
   admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DATABASE)))
  self.connection=self.connect();self.addCleanup(self.connection.close)
  for path in sorted((ROOT/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql')):
   self.connection.execute(path.read_text(),prepare=False)
  self.facts=installation()
  for target in self.facts['database_targets'].values():target['database']=DATABASE
  self.facts['database_targets']['migration']=dict(self.facts['database_targets']['web'],role='postgres',pooling=False)
  self.installation=Installation.parse(self.facts);self.business=BusinessSettings.parse(business())

 def connect(self):return psycopg.connect(host=self.socket,dbname=DATABASE,user='postgres',autocommit=True)

 def test_initialize_is_off_and_replaying_setup_never_resets_current_business_or_mode(self):
  self.assertEqual(setup.initialize(self.connection,self.installation,self.business)['status'],'initialized')
  self.assertIs(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],False)
  self.connection.execute('UPDATE appointment_system.control_product_state SET enabled=true,requested_enabled=true')
  changed=business();changed['services'][0]['duration_minutes']=60
  before=self.connection.execute('SELECT policy_version FROM appointment_system.intake_settings').fetchone()[0]
  self.assertEqual(setup.initialize(self.connection,self.installation,BusinessSettings.parse(changed)),{'status':'existing','changed':False})
  self.assertEqual(self.connection.execute('SELECT policy_version FROM appointment_system.intake_settings').fetchone()[0],before)
  self.assertIs(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],True)

 def test_wrong_target_and_foreign_manifest_are_refused_before_mutation(self):
  setup.initialize(self.connection,self.installation,self.business)
  foreign=installation();foreign['installation_id']='22222222-2222-4222-8222-222222222222';foreign['database_targets']=self.facts['database_targets']
  with self.assertRaisesRegex(setup.SetupError,'installation_mismatch'):setup.initialize(self.connection,Installation.parse(foreign),self.business)
  foreign['database_targets']['migration']['database']='not_this_database'
  with self.assertRaisesRegex(setup.SetupError,'owner_required'):setup.initialize(self.connection,Installation.parse(foreign),self.business)

 def test_missing_login_rolls_back_the_whole_registration_and_does_not_create_a_role(self):
  self.facts['database_targets']['journal']['role']='abs_setup_missing_login'
  profile=Installation.parse(self.facts);setup.initialize(self.connection,profile,self.business)
  with self.assertRaisesRegex(setup.SetupError,'login_missing'):setup.register(self.connection,profile)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.caller_logins').fetchone()[0],0)
  self.assertIsNone(self.connection.execute("SELECT 1 FROM pg_roles WHERE rolname='abs_setup_missing_login'").fetchone())

 def test_registration_is_scoped_idempotent_and_cannot_restore_a_revoked_login(self):
  setup.initialize(self.connection,self.installation,self.business)
  first=setup.register(self.connection,self.installation)
  self.assertFalse(first['passwords_changed']);self.assertEqual(setup.register(self.connection,self.installation),first)
  self.connection.execute("UPDATE appointment_system.caller_logins SET enabled=false WHERE purpose='web'")
  with self.assertRaisesRegex(setup.SetupError,'requires_review'):setup.register(self.connection,self.installation)
  self.assertIs(self.connection.execute("SELECT enabled FROM appointment_system.caller_logins WHERE purpose='web'").fetchone()[0],False)

 def test_company_enrolment_is_once_only_and_never_resets_a_saved_password(self):
  setup.initialize(self.connection,self.installation,self.business)
  secret='Synthetic first company credential'
  self.assertEqual(setup.enroll(self.connection,self.installation,'Company.Owner',secret)['status'],'enrolled')
  for name in ('company.owner','different.owner'):
   with self.assertRaisesRegex(setup.SetupError,'already_enrolled'):setup.enroll(self.connection,self.installation,name,'Synthetic replacement not accepted')
  rows=self.connection.execute('SELECT username,password_hash,credential_revision FROM appointment_system.company_credentials').fetchall()
  self.assertEqual(len(rows),1);self.assertEqual((rows[0][0],rows[0][2]),('company.owner',1));self.assertTrue(verify(rows[0][1],secret))
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.control_company_sessions').fetchone()[0],0)

 def test_two_first_company_enrolments_cannot_create_two_owners(self):
  setup.initialize(self.connection,self.installation,self.business)
  def enroll(index):
   with self.connect() as connection:
    try:return setup.enroll(connection,self.installation,'company.owner'+str(index),'Synthetic simultaneous company credential')['status']
    except setup.SetupError as error:return str(error)
  with ThreadPoolExecutor(max_workers=2) as workers:outcomes=list(workers.map(enroll,(1,2)))
  self.assertCountEqual(outcomes,['enrolled','setup_company_already_enrolled'])
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.company_credentials').fetchone()[0],1)


if __name__=='__main__':unittest.main(verbosity=2)
