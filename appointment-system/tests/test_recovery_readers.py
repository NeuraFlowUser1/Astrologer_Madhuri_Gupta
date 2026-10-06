"""Old code algorithms remain explicit readers; new codes never use old scopes."""
from dataclasses import replace
import hashlib
import hmac
from types import SimpleNamespace
from uuid import uuid4
import unittest
from appointment_system.credentials import ReceiptKeys
from appointment_system.receipt_recovery import recovery_code,code_digest,support_protection,support_key
from appointment_system.connection import StorageUnavailable
from appointment_system.errors import Rejected
from appointment_system.secret_configuration import booking_settings
from appointment_system.serialization import canonical
from appointment_system.keys import encode
from tools.conversion.recovery import RecoveryTransfer
from tools.conversion.support import SupportHistoryTransfer
from tools.conversion.source import ConversionError
from .test_application import environment

class RecoveryReaders(unittest.TestCase):
 def setUp(self):
  self.key=b'Synthetic historical protection key';self.operation=uuid4();self.reference=uuid4()
  self.definition={'key_id':'old','code_audience':'sarsa:004:support-code:v1:','digest_audience':'sarsa:004:support-code-digest:v1:'}
  self.current=booking_settings(environment()).receipt_key
  self.keys=replace(self.current,legacy_keys=(('old',self.key),),recovery_readers={'historical-code':self.definition})

 def test_both_inspected_algorithms_retain_exact_bytes_and_do_not_change_new_issuance(self):
  for prefix in ('sarsa:004:','astro:003:'):
   definition=self.definition|{'code_audience':prefix+'support-code:v1:','digest_audience':prefix+'support-code-digest:v1:'}
   keys=replace(self.keys,recovery_readers={'historical-code':definition})
   raw=hmac.new(self.key,f'{prefix}support-code:v1:{self.operation}:{self.reference}'.encode(),hashlib.sha256).digest()
   code=str(int.from_bytes(raw,'big')%100000000).zfill(8)
   self.assertEqual(recovery_code(keys,self.operation,self.reference,format='historical-code',key_id='old'),code)
   self.assertEqual(code_digest(keys,self.reference,code,format='historical-code',key_id='old'),hmac.new(self.key,f'{prefix}support-code-digest:v1:{self.reference}:{code}'.encode(),hashlib.sha256).hexdigest())
   self.assertEqual(recovery_code(keys,self.operation,self.reference),recovery_code(self.current,self.operation,self.reference))

 def test_reader_format_and_key_are_selected_from_saved_metadata_not_supplied_code(self):
  saved={'format':'historical-code','key_id':'old'};store=SimpleNamespace(recovery_protection=lambda *_:saved)
  self.assertEqual(support_protection(self.keys,store,self.reference),saved)
  with self.assertRaises(StorageUnavailable):support_key(self.keys,store,self.reference,new=True)
  for wrong in ({'format':'missing','key_id':'old'},{'format':'historical-code','key_id':'wrong'}):
   store.recovery_protection=lambda *_:wrong
   with self.assertRaises(StorageUnavailable):support_protection(self.keys,store,self.reference)

 def test_malformed_definitions_and_unowned_materials_are_rejected(self):
  for definition in (self.definition|{'key_id':[]},self.definition|{'key_id':'missing'},self.definition|{'code_audience':'unsafe\n'},self.definition|{'digest_audience':self.definition['code_audience']}):
   with self.assertRaises(Rejected):replace(self.keys,recovery_readers={'historical-code':definition})
  with self.assertRaises(Rejected):replace(self.keys,recovery_readers={'v1':self.definition})

 def test_conversion_proves_the_old_key_and_preserves_all_existing_authority_limits(self):
  code=recovery_code(self.keys,self.operation,self.reference,format='historical-code',key_id='old')
  row={'operation_id':str(self.operation),'request_id':str(self.reference),'code_digest':code_digest(self.keys,self.reference,code,format='historical-code',key_id='old'),
   'attempts':5,'expires_at':'2026-10-01T10:00:00+00:00','redeemed_at':'2026-10-01T09:59:00+00:00','superseded_at':None}
  transfer=RecoveryTransfer(self.keys,'historical-code');converted=transfer(SimpleNamespace(project='004'),'receipt_recoveries',[row])['receipt_recoveries'][0]
  self.assertEqual({key:converted[key] for key in row},row);self.assertEqual(converted['code_format'],'historical-code')
  self.assertNotIn('code_format',row)
  with self.assertRaises(ConversionError):transfer(SimpleNamespace(project='004'),'receipt_recoveries',[row|{'code_digest':'a'*64}])
  with self.assertRaises(ConversionError):transfer(SimpleNamespace(project='003'),'receipt_recoveries',[row])

 def test_private_configuration_binds_the_optional_readers_to_the_installation(self):
  from appointment_system.configuration import installation
  facts=installation();env=environment()
  env['BOOKING_LEGACY_PROTECTION']=canonical({'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
   'readers':{'receipt':{},'context':{},'recovery':{'historical-code':self.definition}},'materials':{'old':encode(self.key)}})
  configured=booking_settings(env).receipt_key
  self.assertEqual(recovery_code(configured,self.operation,self.reference,format='historical-code',key_id='old'),recovery_code(self.keys,self.operation,self.reference,format='historical-code',key_id='old'))

 def test_existing_staff_pin_is_retained_without_a_session_or_invented_signin(self):
  layout=SimpleNamespace(project='003',schema='public');reader=SupportHistoryTransfer()
  identity={'singleton':True,'google_subject':'12345678','authorized_at':'2026-10-01T10:00:00Z'}
  result=reader(layout,'admin_identity',[identity],{'public.google_connection':[{'google_subject':'12345678'}]})
  self.assertEqual(result,{'studio_identities':[{'role':'client','subject':'12345678'}]})
  with self.assertRaisesRegex(ConversionError,'identity_conflict'):
   reader(layout,'admin_identity',[identity],{'public.google_connection':[{'google_subject':'foreign'}]})
  with self.assertRaisesRegex(ConversionError,'identity_invalid'):reader(layout,'admin_identity',[identity|{'singleton':False}])
  with self.assertRaisesRegex(ConversionError,'reader_missing'):reader(layout,'receipt_recoveries',[{}])
  with self.assertRaisesRegex(ConversionError,'table_unprepared'):reader(layout,'company_identities',[{}])
