"""Import actual translated old support records and exercise current SQL/HTTP."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import UUID
import psycopg
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from tools.conversion.handover import Handover
from tools.conversion.records import Translation
from tools.conversion.recovery import RecoveryTransfer
from tools.conversion.support import SupportHistoryTransfer
from tools.conversion import verification
from .test_conversion_staff_history import fixture
from .test_conversion_records import bindings
from . import test_sql_receipt_recovery as receipt_tests
from .test_sql_staff import CLIENT,ORIGIN


class HistoricalStaffSQL(receipt_tests.ReceiptRecoveryFixture):
 def imported(self,*,attempts=0,expired=False):
  booking=self.confirmed();keys,source,row=fixture(booking['booking'],booking['request'])
  now=datetime.now(timezone.utc);operation=source['public.staff_operations'][0]
  operation['created_at']=(now-timedelta(minutes=2)).isoformat()
  row.update(attempts=attempts,redeemed_at=None,redeemed_digest=None,
   expires_at=(now+timedelta(minutes=-1 if expired else 10)).isoformat())
  reader=SupportHistoryTransfer(recovery=RecoveryTransfer(keys,'historical-code'))
  layout=SimpleNamespace(project='003',schema='public');tables={}
  for table in ('staff_operations','staff_appointment_history','receipt_recoveries'):
   records=[row] if table=='receipt_recoveries' else source['public.'+table]
   tables.update(reader(layout,table,records,source))
  with psycopg.connect(host=self.db.native_socket(),dbname='postgres',user='postgres',autocommit=True) as connection:
   with connection.transaction():
    Handover(connection,bindings(),'a'*64,('old_fixture_writer',)).insert(
     Translation('legacy-003-40','b'*64,tables,{},{}))
    manifest=verification.capture(connection,tables)
    self.assertRegex(verification.verify(connection,manifest),r'^[0-9a-f]{64}$')
  return booking,row,None

 def test_imported_history_has_no_customer_code_authority(self):
  booking,row,_=self.imported()
  result=self.staff.studio_support_change(self.session,CLIENT,ORIGIN,UUID(row['operation_id']),UUID(booking['request']),1,
   'contact_correction','Synthetic verified support','pay_synthetic','replacement@example.test','+919999999999')
  self.assertEqual(result['code'],'request_conflict')
  saved=self.db.value("SELECT jsonb_build_object('method',verification_method,'payment',verified_payment_id,'email',previous_email,'phone',new_phone) FROM appointment_system.receipt_recoveries;")
  self.assertEqual(saved,{'method':'retained_staff_operation','payment':None,'email':None,'phone':None})
  for table in ('historical_staff_operations','historical_staff_appointment_history'):
   self.assertEqual(self.db.scalar("SELECT has_table_privilege('appointment_system_web','appointment_system."+table+"','SELECT');"),'f')
   self.assertEqual(self.db.scalar("SELECT has_table_privilege('appointment_system_backup_access','appointment_system."+table+"','SELECT');"),'t')


 def test_transfer_does_not_restore_exhausted_or_expired_codes(self):
  for attempts,expired in ((5,False),(0,True)):
   with self.subTest(attempts=attempts,expired=expired):
    self.db.sql('TRUNCATE appointment_system.checkout_contexts CASCADE;')
    booking,row,code=self.imported(attempts=attempts,expired=expired)
    self.assertEqual(self.db.scalar("SELECT to_regprocedure('appointment_system.redeem_receipt_recovery(uuid,text,text,text)') IS NULL;"),'t')
    self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.receipt_recoveries;'),str(attempts))
    self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.receipt_recoveries WHERE redeemed_at IS NOT NULL;'),'0')

 def test_incomplete_history_cannot_be_relabelled_as_a_current_verified_action(self):
  self.imported()
  with psycopg.connect(host=self.db.native_socket(),dbname='postgres',user='postgres',autocommit=True) as connection:
   for statement in ("UPDATE appointment_system.receipt_recoveries SET verification_method='existing_phone_callback'",
    "UPDATE appointment_system.receipt_recoveries SET historical_operation_id=NULL"):
    with self.subTest(statement=statement),self.assertRaises(psycopg.errors.CheckViolation):connection.execute(statement)
