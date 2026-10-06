from appointment_system.configuration import configure
from .fixtures import installation,business
configure(installation(),business())
"""Actual authenticated crypto and concurrent/lost-response ledger boundaries."""
import base64,json,unittest
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from appointment_system.privacy.ledger import Keys,Ledger,PrivacyError,canonical,digest,PROJECT,MAX_SEQUENCE,MAXIMUM

def synthetic_keys(reader=False):
 seed=b's'*32;public=Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
 encoded=lambda v:base64.urlsafe_b64encode(v).decode()
 return Keys({'encryption-v1':encoded(b'e'*32)},{'signing-v1':encoded(public)},None if reader else 'encryption-v1',None if reader else 'signing-v1',None if reader else encoded(seed))

def record():return {'operation_id':str(uuid4()),'policy_id':'routine-incidents-v1','target_id':str(uuid4()),'target_hash':'a'*64,'policy_version':1,'minimum_days':30,'approval_reference':'b'*64,'intent_created_at':'2026-10-01T12:00:00.000000Z'}

class MemoryStore:
 """Explicit synthetic storage; no account, provider or filesystem effects."""
 def __init__(self,keys):
  self.keys=keys;self.head=keys.seal({'kind':'head','sequence':0,'latest':None});self.version=1;self.entries={};self.cas_hook=None;self.read_hook=None
 def read_head(self):return self.head,str(self.version)
 def read_entry(self,identity):
  if self.read_hook:self.read_hook(identity)
  if identity not in self.entries:raise PrivacyError('privacy_storage_unavailable')
  return self.entries[identity]
 def create_entry(self,data,sequence,entry_hash):
  identity='synthetic-private-entry-'+str(len(self.entries)+1);self.entries[identity]=data;return identity
 def compare_and_swap_head(self,version,data):
  if self.cas_hook:self.cas_hook(version,data)
  if version!=str(self.version):raise PrivacyError('privacy_head_changed')
  self.head=data;self.version+=1
 def insert(self,document):
  identity=self.create_entry(self.keys.seal(document),document['sequence'],digest(document))
  pointer={'file_id':identity,'entry_hash':digest(document),'sequence':document['sequence']}
  self.head=self.keys.seal({'kind':'head','sequence':document['sequence'],'latest':pointer});self.version+=1;return pointer

class LedgerTests(unittest.TestCase):
 def setUp(self):self.keys=synthetic_keys();self.store=MemoryStore(self.keys);self.ledger=Ledger(self.store,self.keys)
 def test_real_crypto_roundtrip_omits_metadata_from_ciphertext(self):
  doc=record()|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'};sealed=self.keys.seal(doc)
  self.assertEqual(self.keys.open(sealed),doc);self.assertNotIn(doc['target_id'].encode(),sealed);self.assertNotIn(doc['intent_created_at'].encode(),sealed)
 def test_readonly_retained_keys_can_read_old_key_after_rotation(self):
  old=self.store.head;new_seed=b'n'*32;enc=lambda b:base64.urlsafe_b64encode(b).decode()
  keys=Keys(self.keys.encryption|{'encryption-v2':enc(b'f'*32)},self.keys.verification|{'signing-v2':enc(Ed25519PrivateKey.from_private_bytes(new_seed).public_key().public_bytes_raw())},'encryption-v2','signing-v2',enc(new_seed))
  self.assertEqual(keys.open(old)['sequence'],0);self.assertEqual(synthetic_keys(True).open(old)['sequence'],0)
  with self.assertRaisesRegex(PrivacyError,'reader_cannot_write'):synthetic_keys(True).seal({'kind':'head','sequence':0,'latest':None})
  self.assertEqual(keys.open(keys.seal({'kind':'head','sequence':0,'latest':None}))['sequence'],0)
 def test_cross_project_environment_purpose_and_unknown_keys_cannot_authenticate(self):
  for field,value in [('project','004' if PROJECT=='003' else '003'),('environment','preview'),('purpose','backup'),('version',True),('encryption_id','retired'),('signing_id','retired'),('nonce',[]),('ciphertext',[]),('signature',[]),('extra',1)]:
   with self.subTest(field=field):
    obj=json.loads(self.store.head);obj[field]=value
    with self.assertRaises(PrivacyError):self.keys.open(canonical(obj))
 def test_ciphertext_signature_and_nonce_tampering_never_return_plaintext(self):
  for field in ('ciphertext','signature','nonce'):
   obj=json.loads(self.store.head);old=obj[field];obj[field]=('A' if old[0]!='A' else 'B')+old[1:]
   with self.subTest(field=field),self.assertRaises(PrivacyError):self.keys.open(canonical(obj))
 def test_duplicate_json_nonfinite_oversized_and_non_bytes_are_rejected(self):
  for data in (b'{"version":1,"version":1}',b'{"version":NaN}',b'\xff',b'x'*(MAXIMUM+1),'string',b'[]'):
   with self.subTest(kind=type(data).__name__),self.assertRaises(PrivacyError):self.keys.open(data)
 def test_distinct_key_purposes_and_canonical_bounded_keyrings(self):
  enc=lambda b:base64.urlsafe_b64encode(b).decode()
  for encryption,verification,active,seed in [({},self.keys.verification,None,None),({'x':enc(b'a')},self.keys.verification,None,None),({'X':enc(b'a'*32)},self.keys.verification,None,None),({str(i):enc(b'a'*32) for i in range(9)},self.keys.verification,None,None),({'x':enc(b's'*32)},self.keys.verification,'x',self.keys.signing_seed),(self.keys.encryption,self.keys.verification,'absent',None),(self.keys.encryption,self.keys.verification,'encryption-v1',enc(b'x'*32))]:
   with self.assertRaises(PrivacyError):Keys(encryption,verification,active,'signing-v1',seed)
 def test_invalid_document_shapes_times_links_and_policy_do_not_get_signed(self):
  document=record()|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'}
  for change in ({'sequence':True},{'sequence':0},{'sequence':MAX_SEQUENCE+1},{'operation_id':'bad'},{'target_hash':'A'*64},{'approval_reference':[]},{'intent_created_at':'2026-10-01'},{'intent_created_at':'2026-13-01T00:00:00.000000Z'},{'policy_id':[]},{'phase':[]},{'policy_version':True},{'minimum_days':7},{'previous':{'file_id':'somewhere'}},{'extra':1}):
   with self.subTest(change=change),self.assertRaises(PrivacyError):self.keys.seal(document|change)
  for doc in (None,{}, {'kind':'wrong'}, {'kind':'head','sequence':-1,'latest':None},{'kind':'head','sequence':1,'latest':None},{'kind':'head','sequence':0,'latest':{'file_id':'elsewhere'}},{'kind':'head','sequence':1,'latest':{'file_id':'../elsewhere','entry_hash':'a'*64,'sequence':1}}):
   with self.assertRaises(PrivacyError):self.keys.seal(doc)
 def test_intent_outcome_and_retry_are_same_linked_proof_without_duplicate(self):
  value=record();first=self.ledger.append(value,'intent');again=self.ledger.append(value,'intent');self.assertEqual(first,again)
  terminal=self.ledger.append(value,'applied');self.assertEqual(terminal,self.ledger.append(value,'applied'))
  self.assertEqual(self.ledger.append(value,'intent'),first);self.assertEqual(self.ledger.head()[0]['sequence'],2);self.assertEqual(len(self.store.entries),2)
  self.assertEqual([e['phase'] for e,_ in self.ledger.walk(self.ledger.head()[0])],['applied','intent'])
 def test_changed_request_or_conflicting_terminal_and_missing_original_are_rejected(self):
  value=record()
  with self.assertRaisesRegex(PrivacyError,'original_intent_missing'):self.ledger.append(value,'applied')
  self.ledger.append(value,'intent')
  with self.assertRaisesRegex(PrivacyError,'operation_changed'):self.ledger.append(value|{'target_hash':'f'*64},'intent')
  self.ledger.append(value,'cancelled')
  with self.assertRaisesRegex(PrivacyError,'outcome_changed'):self.ledger.append(value,'applied')
  with self.assertRaisesRegex(PrivacyError,'phase_invalid'):self.ledger.append(value,'delete')
 def test_actual_cas_race_keeps_both_independent_operations_and_orphan_has_no_power(self):
  other=record();fired=[]
  def race(version,data):
   if fired:return
   fired.append(True);self.store.cas_hook=None;self.ledger.append(other,'intent')
  self.store.cas_hook=race;value=record();result=self.ledger.append(value,'intent')
  self.assertEqual(result['sequence'],2);self.assertEqual(self.ledger.head()[0]['sequence'],2)
  self.assertEqual(len(self.store.entries),3);self.assertEqual({e['operation_id'] for e,_ in self.ledger.walk(self.ledger.head()[0])},{other['operation_id'],value['operation_id']})
 def test_lost_cas_reply_resolves_linked_operation_and_stable_historical_head(self):
  fired=[]
  def lost(version,data):
   if fired:return
   fired.append(True);self.store.head=data;self.store.version+=1;raise PrivacyError('privacy_head_changed')
  self.store.cas_hook=lost;value=record();result=self.ledger.append(value,'intent');self.store.cas_hook=None
  self.ledger.append(record(),'intent');self.assertEqual(self.ledger.append(value,'intent'),result);self.assertEqual(len(self.store.entries),2)
 def test_unlinked_failed_write_and_unconfirmed_entry_do_not_authorize_erasure(self):
  self.store.cas_hook=lambda *args:(_ for _ in ()).throw(PrivacyError('privacy_storage_unavailable'))
  with self.assertRaisesRegex(PrivacyError,'storage_unavailable'):self.ledger.append(record(),'intent')
  self.assertEqual(self.ledger.head()[0]['sequence'],0)
  self.store.cas_hook=None;self.store.read_hook=lambda identity:self.store.entries.__setitem__(identity,self.keys.seal({'kind':'head','sequence':0,'latest':None}))
  with self.assertRaisesRegex(PrivacyError,'entry_unconfirmed'):self.ledger.append(record(),'intent')
  self.assertEqual(self.ledger.head()[0]['sequence'],0)
 def test_busy_writers_are_bounded_and_never_blindly_overwrite_head(self):
  self.store.cas_hook=lambda *args:(_ for _ in ()).throw(PrivacyError('privacy_head_changed'))
  with self.assertRaisesRegex(PrivacyError,'head_busy'):self.ledger.append(record(),'intent')
  self.assertEqual(len(self.store.entries),4);self.assertEqual(self.ledger.head()[0]['sequence'],0)
 def test_missing_tampered_wrong_sequence_or_wrong_document_breaks_authenticated_chain(self):
  self.ledger.append(record(),'intent');head=self.ledger.head()[0];identity=head['latest']['file_id'];original=self.store.entries[identity]
  for data in (None,b'broken',self.keys.seal({'kind':'head','sequence':0,'latest':None}),self.keys.seal(record()|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'})):
   if data is None:del self.store.entries[identity]
   else:self.store.entries[identity]=data
   with self.assertRaises(PrivacyError):list(self.ledger.walk(head))
   self.store.entries[identity]=original
 def test_regression_floor_and_sequence_exhaustion_are_rejected(self):
  for floor in (-1,True,MAX_SEQUENCE+1):
   with self.assertRaisesRegex(PrivacyError,'head_regressed'):self.ledger.head(floor)
  with self.assertRaisesRegex(PrivacyError,'head_regressed'):self.ledger.head(1)
  self.ledger.append(record(),'intent');head=self.ledger.head()[0]
  with self.assertRaisesRegex(PrivacyError,'chain_invalid'):list(self.ledger.walk(head,floor=2))
  pointer={'sequence':MAX_SEQUENCE,'file_id':'synthetic-last-entry','entry_hash':'a'*64}
  self.store.head=self.keys.seal({'kind':'head','sequence':MAX_SEQUENCE,'latest':pointer})
  with self.assertRaisesRegex(PrivacyError,'sequence_exhausted'):self.ledger.append(record(),'intent',floor=MAX_SEQUENCE)

if __name__=='__main__':unittest.main()
