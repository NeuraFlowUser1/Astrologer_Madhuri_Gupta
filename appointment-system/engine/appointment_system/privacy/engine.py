"""Inspected foundation SHA256: 0cbe4df23a302a68362b888348db46da43c25c4ae4cdc7ab10cd7abc7eb858a8."""
"""Protected orchestration: independent intent -> SQL erase -> external outcome.

Interrupted steps reuse immutable identities. Pending external outcomes make a
restore incomplete rather than inventing whether content was actually erased.
"""
from .ledger import PrivacyError,checked,checked_uuid,digest
from datetime import datetime,timezone

def body(entry):return {k:v for k,v in entry.items() if k not in ('kind','sequence','previous','phase')}
def proof(entry,pointer):return {'sequence':entry['sequence'],'entry_hash':pointer['entry_hash'],'file_id':pointer['file_id'],'head_hash':digest({'kind':'head','sequence':entry['sequence'],'latest':pointer})}

class Retention:
 def __init__(self,database,ledger):self.database,self.ledger=database,ledger
 def inspect(self,policy,*,limit=100,after=None):return self.database.inspect(policy,limit=limit,after=after)
 def record_intent(self,operation,policy,target,target_hash):
  checked_uuid(operation);checked_uuid(target)
  saved=self.database.saved_intent(operation)
  if saved is None:
   head,_=self.ledger.head();self.database.record(operation,policy,target,target_hash,head['sequence'])
   saved=self.database.saved_intent(operation)
  if (not isinstance(saved,dict) or saved['intent']['policy_id']!=policy or saved['intent']['target_id']!=target or saved['intent']['target_hash']!=target_hash):raise PrivacyError('privacy_operation_changed')
  record=saved.get('document')
  if record is None:
   record={'operation_id':operation,'policy_id':policy,'target_id':target,'target_hash':target_hash,'policy_version':saved['policy']['version'],'minimum_days':saved['policy']['minimum_days'],'approval_reference':digest(saved['approval']),'intent_created_at':datetime.fromisoformat(saved['intent']['created_at']).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
   checked(record|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'});self.database.freeze(operation,record)
  if saved['export'] is None:
   evidence=self.ledger.append(record,'intent',floor=saved['intent']['base_sequence'])
   self.database.attach(operation,evidence)
  return {'recorded':True,'erased':False}
 def apply(self,operation):
  checked_uuid(operation);saved=self.database.saved_intent(operation)
  if saved is None or saved.get('document') is None or saved.get('export') is None:raise PrivacyError('privacy_independent_intent_required')
  self.ledger.verify_intent(saved['document'],saved['export'],floor=saved['intent']['base_sequence'])
  # Eligibility is checked under actual record locks by the SQL owner function.
  completion=self.database.apply(operation);phase=completion['outcome']
  if phase not in ('applied','cancelled'):raise PrivacyError('privacy_outcome_unconfirmed')
  self.ledger.append(saved['document'],phase,floor=saved['intent']['base_sequence'])
  return {'recorded':True,'erased':phase=='applied','outcome_recorded':True}
 def replay(self,operation,generation,*,minimum_sequence=0):
  checked_uuid(operation);checked_uuid(generation)
  minimum_sequence=max(minimum_sequence,self.database.required_sequence())
  head,_=self.ledger.head(minimum_sequence);outcomes={};intents={};count=0
  # Backwards traversal authenticates every link before any target is erased.
  # No partial/corrupt chain can be called a successful privacy recovery.
  for entry,pointer in self.ledger.walk(head):
   count+=1
   if count>100000:raise PrivacyError('privacy_replay_budget')
   identity=entry['operation_id'];record=body(entry)
   if entry['phase']=='intent':
    if identity in intents:raise PrivacyError('privacy_duplicate_intent')
    intents[identity]=(record,proof(entry,pointer))
   else:
    if identity in outcomes:raise PrivacyError('privacy_duplicate_outcome')
    outcomes[identity]=(entry['phase'],record,entry['sequence'])
  if set(outcomes)-set(intents):raise PrivacyError('privacy_original_intent_missing')
  if set(intents)-set(outcomes):raise PrivacyError('privacy_unresolved_intent')
  for identity,(phase,record,outcome_sequence) in outcomes.items():
   original,export=intents[identity]
   if record!=original or outcome_sequence<=export['sequence']:raise PrivacyError('privacy_operation_changed')
  for identity,(phase,record,outcome_sequence) in outcomes.items():
   if phase=='cancelled':continue
   self.database.restore_intent(record,intents[identity][1])
   if self.database.replay_apply(operation,identity)['outcome']!='applied':raise PrivacyError('privacy_restored_target_changed')
  latest,_=self.ledger.head(head['sequence'])
  if latest!=head:raise PrivacyError('privacy_head_changed_during_replay')
  return self.database.finish_replay(operation,generation,head['sequence'],digest(head))
