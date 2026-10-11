"""Old code algorithms remain explicit readers; new codes never use old scopes."""
from dataclasses import replace
import hashlib
import hmac
from types import SimpleNamespace
from uuid import uuid4
import unittest
from appointment_system.credentials import ReceiptKeys
from tools.conversion.recovery import RecoveryKeys,recovery_readers,provenance_digest,recovery_keys
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
  self.keys=RecoveryKeys(recovery_readers({'historical-code':self.definition},{'old':self.key}),{'old':self.key})

 def test_both_original_algorithms_are_verified_offline(self):
  for prefix in ('sarsa:004:','astro:003:'):
   definition=self.definition|{'code_audience':prefix+'support-code:v1:','digest_audience':prefix+'support-code-digest:v1:'}
   keys=RecoveryKeys(recovery_readers({'historical-code':definition},{'old':self.key}),{'old':self.key})
   raw=hmac.new(self.key,f'{prefix}support-code:v1:{self.operation}:{self.reference}'.encode(),hashlib.sha256).digest()
   code=str(int.from_bytes(raw,'big')%100000000).zfill(8)
   expected=hmac.new(self.key,f'{prefix}support-code-digest:v1:{self.reference}:{code}'.encode(),hashlib.sha256).hexdigest()
   self.assertEqual(provenance_digest(keys,self.operation,self.reference,'historical-code','old'),expected)




 def test_malformed_definitions_and_unowned_materials_are_rejected(self):
  for definition in (self.definition|{'key_id':[]},self.definition|{'key_id':'missing'},self.definition|{'code_audience':'unsafe\n'},self.definition|{'digest_audience':self.definition['code_audience']}):
   with self.assertRaises(Rejected):recovery_readers({'historical-code':definition},{'old':self.key})
  with self.assertRaises(Rejected):recovery_readers({'v1':self.definition},{'old':self.key})

 def test_conversion_proves_the_old_key_and_preserves_all_existing_authority_limits(self):
  row={'operation_id':str(self.operation),'request_id':str(self.reference),'code_digest':provenance_digest(self.keys,self.operation,self.reference,'historical-code','old'),
   'attempts':5,'expires_at':'2026-10-01T10:00:00+00:00','redeemed_at':'2026-10-01T09:59:00+00:00','superseded_at':None}
  transfer=RecoveryTransfer(self.keys,'historical-code');converted=transfer(SimpleNamespace(project='004'),'receipt_recoveries',[row])['receipt_recoveries'][0]
  self.assertEqual({key:converted[key] for key in row if key!='code_digest'},{key:value for key,value in row.items() if key!='code_digest'})
  for field in ('code_digest','code_format','code_key_id','redeemed_digest'):self.assertNotIn(field,converted)
  self.assertNotIn('code_format',row)
  with self.assertRaises(ConversionError):transfer(SimpleNamespace(project='004'),'receipt_recoveries',[row|{'code_digest':'a'*64}])
  with self.assertRaises(ConversionError):transfer(SimpleNamespace(project='003'),'receipt_recoveries',[row])

 def test_private_configuration_binds_the_optional_readers_to_the_installation(self):
  from appointment_system.configuration import installation
  facts=installation();env=environment()
  env['BOOKING_LEGACY_PROTECTION']=canonical({'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
   'readers':{'receipt':{},'context':{},'recovery':{'historical-code':self.definition}},'materials':{'old':encode(self.key)}})
  configured=recovery_keys(env)
  self.assertFalse(hasattr(booking_settings(env).receipt_key,'recovery_readers'))
  self.assertEqual(provenance_digest(configured,self.operation,self.reference,'historical-code','old'),provenance_digest(self.keys,self.operation,self.reference,'historical-code','old'))

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
