"""Saved support facts retain their limits and honestly incomplete evidence."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
import unittest
from appointment_system.receipt_recovery import recovery_code,code_digest
from appointment_system.secret_configuration import booking_settings
from tools.conversion.recovery import RecoveryTransfer
from tools.conversion.support import SupportHistoryTransfer
from tools.conversion.source import ConversionError
from tools.conversion import staff_history
from .test_application import environment


def fixture(book=None,reference=None):
 book=book or str(uuid4());reference=reference or str(uuid4());operation=str(uuid4())
 definition={'key_id':'old','code_audience':'astro:003:support-code:v1:',
  'digest_audience':'astro:003:support-code-digest:v1:'}
 keys=replace(booking_settings(environment()).receipt_key,legacy_keys=(('old',b'Synthetic historical protection key'),),
  recovery_readers={'historical-code':definition})
 code=recovery_code(keys,operation,reference,format='historical-code',key_id='old')
 record={'operation_id':operation,'booking_id':book,'action':'contact_correction','actor':'client:123456789',
  'body_hash':'a'*64,'previous_revision':1,'revision':2,'created_at':'2026-10-01T10:00:00Z',
  'result':{'code':'support_saved','operation_id':operation,'revision':2,'booking_id':book,'reference':reference}}
 history={'operation_id':operation,'previous_start':'2031-04-04T10:30:00Z','current_start':'2031-04-04T10:30:00Z',
  'notice_seconds':86400,'late_exception':False,'reason':'Synthetic verified support'}
 recovery={'operation_id':operation,'booking_id':book,'code_digest':code_digest(keys,reference,code,format='historical-code',key_id='old'),
  'expires_at':'2026-10-01T10:15:00Z','attempts':5,'superseded_at':None,
  'redeemed_at':'2026-10-01T10:05:00Z','redeemed_digest':'b'*64}
 source={'public.staff_operations':[record],'public.staff_appointment_history':[history],
  'public.bookings':[{'id':book,'request_id':reference,'email':'current@example.test','phone':'+919999999999'}]}
 return keys,source,recovery


class HistoricalStaffTransfer(unittest.TestCase):
 def setUp(self):
  self.layout=SimpleNamespace(project='003',schema='public');self.keys,self.source,self.row=fixture()
  self.reader=SupportHistoryTransfer(recovery=RecoveryTransfer(self.keys,'historical-code'))

 def test_records_preserve_original_actions_without_creating_current_action_authority(self):
  for table in ('staff_operations','staff_appointment_history'):
   rows=self.source['public.'+table];result=self.reader(self.layout,table,rows,self.source)
   self.assertEqual(result,{'historical_'+table:rows});self.assertIsNot(result['historical_'+table][0],rows[0])
  self.assertNotIn('receipt_recoveries',self.reader(self.layout,'staff_operations',self.source['public.staff_operations'],self.source))

 def test_code_keeps_expiry_wrong_attempts_and_redemption_without_invented_payment_or_contacts(self):
  before=deepcopy(self.row)
  translated=self.reader(self.layout,'receipt_recoveries',[self.row],self.source)['receipt_recoveries'][0]
  for field in ('expires_at','attempts','redeemed_at','redeemed_digest','superseded_at','operation_id','code_digest'):
   self.assertEqual(translated[field],self.row[field])
  self.assertEqual(translated['historical_operation_id'],self.row['operation_id'])
  self.assertEqual(translated['verification_method'],'retained_staff_operation')
  self.assertEqual(translated['request_id'],self.source['public.bookings'][0]['request_id'])
  self.assertEqual(translated['code_format'],'historical-code')
  for field in ('verified_payment_id','previous_email','previous_phone','new_email','new_phone'):self.assertIsNone(translated[field])
  self.assertEqual(self.row,before)

 def test_changed_code_key_parent_action_or_missing_history_cannot_create_a_grant(self):
  for change in ({'code_digest':'f'*64},{'booking_id':str(uuid4())},{'operation_id':str(uuid4())}):
   with self.subTest(change=change),self.assertRaises(ConversionError):
    self.reader(self.layout,'receipt_recoveries',[self.row|change],self.source)
  for change in ('missing','wrong_action'):
   source=deepcopy(self.source)
   if change=='missing':source['public.staff_appointment_history']=[]
   else:source['public.staff_operations'][0]['action']='cancel'
   with self.subTest(change=change),self.assertRaises(ConversionError):
    self.reader(self.layout,'receipt_recoveries',[self.row],source)

 def test_conflicting_action_receipt_and_duplicate_identity_stop_translation(self):
  for change in ('receipt','duplicate','history','revision','extra'):
   source=deepcopy(self.source);rows=source['public.staff_operations']
   if change=='receipt':rows[0]['result']['reference']=str(uuid4())
   elif change=='duplicate':rows.append(deepcopy(rows[0]))
   elif change=='history':source['public.staff_appointment_history'][0]['operation_id']=str(uuid4())
   elif change=='revision':rows[0]['revision']=0
   else:rows[0]['unclassified']='unreviewed'
   with self.subTest(change=change),self.assertRaises(ConversionError):self.reader(self.layout,'staff_operations',rows,source)

 def test_an_altered_subset_cannot_replace_the_frozen_source_record(self):
  row=self.source['public.staff_operations'][0]|{'actor':'foreign:123456789'}
  with self.assertRaisesRegex(ConversionError,'history_invalid'):
   staff_history.transfer(self.layout,'staff_operations',[row],self.source)

 def test_undeclared_readers_and_other_source_layouts_are_refused(self):
  for key,format in ((object(),'historical-code'),(self.keys,'undeclared')):
   with self.subTest(format=format),self.assertRaises(ConversionError):RecoveryTransfer(key,format)
  reader=RecoveryTransfer(self.keys,'historical-code')
  for layout,table in ((SimpleNamespace(project='005'),'receipt_recoveries'),(self.layout,'unknown_table')):
   with self.assertRaisesRegex(ConversionError,'layout_unprepared'):reader(layout,table,[self.row],self.source)
