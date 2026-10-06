from appointment_system.configuration import configure
from .fixtures import installation,business
configure(installation(),business())
"""Interrupted protected orchestration, actual encrypted chain and reader keys."""
import copy,unittest
from uuid import uuid4
from appointment_system.privacy.ledger import Ledger,PrivacyError,PROJECT
from appointment_system.privacy.engine import Retention
from . import test_privacy_ledger as fixture

class Database:
 def __init__(self):self.saved={};self.events=[];self.minimum=0;self.applied=[];self.finished=[];self.fail_attach=False
 def inspect(self,*args,**kwargs):return {'approved':False,'targets':[]}
 def saved_intent(self,identity):return copy.deepcopy(self.saved.get(identity))
 def record(self,operation,policy,target,target_hash,base):
  self.events.append('intent');self.saved[operation]={'intent':{'policy_id':policy,'target_id':target,'target_hash':target_hash,'base_sequence':base,'created_at':'2026-10-01T12:00:00+00:00'},'policy':{'version':1,'minimum_days':30},'approval':{'approved_by':'synthetic-owner','approved_at':'2026-10-01'},'export':None,'document':None,'completion':None}
 def freeze(self,operation,record):self.events.append('freeze');self.saved[operation]['document']=record
 def attach(self,operation,proof):
  self.events.append('export')
  if self.fail_attach:self.fail_attach=False;raise PrivacyError('synthetic_lost_database_reply')
  self.saved[operation]['export']=proof
 def apply(self,operation):
  self.events.append('apply');self.saved[operation]['completion']={'outcome':'applied'};return {'outcome':'applied'}
 def required_sequence(self):return self.minimum
 def restore_intent(self,record,proof):self.events.append('restore');self.applied.append(record)
 def replay_apply(self,restore,identity):self.events.append('replay_apply');return {'outcome':'applied'}
 def finish_replay(self,operation,generation,sequence,head_hash):
  self.events.append('finish');self.finished.append(sequence)
  return {'project':PROJECT,'environment':'production','restore_generation':generation,'sequence':sequence,'head_hash':head_hash,'unresolved':0}

class EngineTests(unittest.TestCase):
 def setUp(self):self.keys=fixture.synthetic_keys();self.store=fixture.MemoryStore(self.keys);self.ledger=Ledger(self.store,self.keys);self.db=Database();self.engine=Retention(self.db,self.ledger)
 def intent(self):
  value=fixture.record();self.engine.record_intent(value['operation_id'],value['policy_id'],value['target_id'],value['target_hash']);return value['operation_id']
 def test_dry_inspection_has_no_intent_storage_or_erasure_side_effect(self):
  self.assertFalse(self.engine.inspect('routine-incidents-v1')['approved']);self.assertEqual(self.db.events,[]);self.assertEqual(self.ledger.head()[0]['sequence'],0)
 def test_actual_durable_intent_and_changed_retry_do_not_erase(self):
  identity=self.intent();saved=self.db.saved[identity];self.assertEqual(self.db.events,['intent','freeze','export']);self.assertIsNone(saved['completion'])
  args=(identity,saved['intent']['policy_id'],saved['intent']['target_id'],saved['intent']['target_hash'])
  self.engine.record_intent(*args);self.assertEqual(self.ledger.head()[0]['sequence'],1)
  with self.assertRaisesRegex(PrivacyError,'operation_changed'):self.engine.record_intent(*args[:3],'f'*64)
 def test_lost_sql_export_reply_resumes_identical_frozen_approval_and_chain_pointer(self):
  value=fixture.record();self.db.fail_attach=True
  with self.assertRaises(PrivacyError):self.engine.record_intent(value['operation_id'],value['policy_id'],value['target_id'],value['target_hash'])
  saved_document=copy.deepcopy(self.db.saved[value['operation_id']]['document']);self.ledger.append(fixture.record(),'intent');self.db.saved[value['operation_id']]['approval']['approved_at']='later'
  self.engine.record_intent(value['operation_id'],value['policy_id'],value['target_id'],value['target_hash']);self.assertEqual(self.db.saved[value['operation_id']]['document'],saved_document);self.assertEqual(self.db.saved[value['operation_id']]['export']['sequence'],1);self.assertEqual(self.ledger.head()[0]['sequence'],2)
 def test_missing_frozen_document_export_external_chain_or_changed_pointer_prevents_erase(self):
  with self.assertRaisesRegex(PrivacyError,'independent_intent_required'):self.engine.apply(str(uuid4()))
  identity=self.intent();original=copy.deepcopy(self.db.saved[identity])
  for field in ('document','export'):
   self.db.saved[identity]=copy.deepcopy(original);self.db.saved[identity][field]=None
   with self.assertRaises(PrivacyError):self.engine.apply(identity)
  self.db.saved[identity]=copy.deepcopy(original);self.db.saved[identity]['export']['file_id']='synthetic-wrong-pointer'
  with self.assertRaises(PrivacyError):self.engine.apply(identity)
  self.db.saved[identity]=original;self.store.entries.clear()
  with self.assertRaises(PrivacyError):self.engine.apply(identity)
  self.assertNotIn('apply',self.db.events)
 def test_interruption_after_sql_erasure_resumes_same_terminal_outcome(self):
  identity=self.intent();self.store.cas_hook=lambda *args:(_ for _ in ()).throw(PrivacyError('synthetic_storage_down'))
  with self.assertRaises(PrivacyError):self.engine.apply(identity)
  self.assertEqual(self.db.saved[identity]['completion']['outcome'],'applied');self.assertEqual(self.ledger.head()[0]['sequence'],1)
  self.store.cas_hook=None;self.assertTrue(self.engine.apply(identity)['outcome_recorded']);self.assertTrue(self.engine.apply(identity)['erased']);self.assertEqual(self.ledger.head()[0]['sequence'],2)
 def test_readonly_keys_replay_authenticated_history_and_cancelled_intent_preserves_target(self):
  identity=self.intent();self.engine.apply(identity);cancelled=fixture.record();self.ledger.append(cancelled,'intent');self.ledger.append(cancelled,'cancelled')
  reader=Retention(self.db,Ledger(self.store,fixture.synthetic_keys(True)));proof=reader.replay(str(uuid4()),str(uuid4()))
  self.assertEqual(proof['sequence'],4);self.assertEqual(len(self.db.applied),1);self.assertEqual(self.db.applied[0]['operation_id'],identity);self.assertEqual(self.db.finished,[4])
 def test_pending_terminal_without_original_corrupt_chain_and_regression_never_complete(self):
  identity=self.intent()
  with self.assertRaisesRegex(PrivacyError,'unresolved_intent'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.assertNotIn('restore',self.db.events);self.assertEqual(self.db.finished,[])
  self.engine.apply(identity);self.db.minimum=3
  with self.assertRaisesRegex(PrivacyError,'head_regressed'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.db.minimum=0;self.store.entries.clear()
  with self.assertRaises(PrivacyError):self.engine.replay(str(uuid4()),str(uuid4()))
  self.assertEqual(self.db.finished,[])
 def test_signed_conflicting_or_backwards_phase_history_never_erases(self):
  value=fixture.record()
  intent=value|{'kind':'entry','sequence':1,'previous':None,'phase':'applied'};pointer=self.store.insert(intent)
  self.store.insert(value|{'kind':'entry','sequence':2,'previous':pointer,'phase':'intent'})
  with self.assertRaisesRegex(PrivacyError,'operation_changed'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.assertEqual(self.db.applied,[]);self.assertEqual(self.db.finished,[])
 def test_missing_original_and_duplicate_intent_are_isolated_before_database_changes(self):
  value=fixture.record();self.store.insert(value|{'kind':'entry','sequence':1,'previous':None,'phase':'applied'})
  with self.assertRaisesRegex(PrivacyError,'original_intent_missing'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.store=fixture.MemoryStore(self.keys);self.ledger=Ledger(self.store,self.keys);self.engine=Retention(self.db,self.ledger)
  first=self.store.insert(value|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'})
  self.store.insert(value|{'kind':'entry','sequence':2,'previous':first,'phase':'intent'})
  with self.assertRaisesRegex(PrivacyError,'duplicate_intent'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.assertEqual(self.db.applied,[])
 def test_head_changing_during_recovery_cannot_certify_old_privacy_history(self):
  identity=self.intent();self.engine.apply(identity);original=self.db.replay_apply
  def change(restore,operation):self.ledger.append(fixture.record(),'intent');return original(restore,operation)
  self.db.replay_apply=change
  with self.assertRaisesRegex(PrivacyError,'head_changed_during_replay'):self.engine.replay(str(uuid4()),str(uuid4()))
  self.assertEqual(self.db.finished,[])


 def test_changed_protected_intent_cannot_be_republished_under_a_saved_operation(self):
  identity=self.intent();original=copy.deepcopy(self.db.saved[identity]);intent=original['intent']
  for value in ['wrong',original|{'intent':intent|{'policy_id':'wrong'}},original|{'intent':intent|{'target_id':str(uuid4())}},original|{'intent':intent|{'target_hash':'b'*64}}]:
   with self.subTest(value=type(value).__name__):
    self.db.saved[identity]=value
    with self.assertRaisesRegex(PrivacyError,'privacy_operation_changed'):self.engine.record_intent(identity,intent['policy_id'],intent['target_id'],intent['target_hash'])
  self.assertEqual(self.ledger.head()[0]['sequence'],1)
 def test_unconfirmed_erasure_outcome_cannot_be_written_to_independent_history(self):
  identity=self.intent();self.db.apply=lambda operation:{'outcome':'failed'}
  with self.assertRaisesRegex(PrivacyError,'privacy_outcome_unconfirmed'):self.engine.apply(identity)
  self.assertEqual(self.ledger.head()[0]['sequence'],1)

if __name__=='__main__':unittest.main()
