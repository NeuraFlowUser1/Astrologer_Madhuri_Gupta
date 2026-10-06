"""Inspected foundation SHA256: 3a0c3bb4844901c7c9e71f8029b299b1713241e08b45ba53236906e0901acaa2."""
"""Purpose-bound encrypted/signature-verified privacy history, outside archives.

Head mutation requires a proven provider compare-and-swap. Content deletion
uses only a referenced, read-back entry; uploaded orphan entries confer nothing.
"""
import base64,hashlib,json,os,re
from dataclasses import dataclass,field
from uuid import UUID
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..configuration import installation
FACTS=installation()
PROJECT=FACTS['project_id'];ENVIRONMENT=FACTS['environment'];INSTALLATION=FACTS['installation_id']
NAMESPACE=b'appointment-system:privacy:v1:'+INSTALLATION.encode()+b':'+ENVIRONMENT.encode()+b':'
MAXIMUM=65536;MAX_SEQUENCE=9223372036854775807
class PrivacyError(Exception):pass

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=True).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def unique(data):
 def pairs(items):
  result={}
  for name,value in items:
   if name in result:raise ValueError()
   result[name]=value
  return result
 if not isinstance(data,bytes) or len(data)>MAXIMUM:raise PrivacyError('privacy_document_limit')
 try:return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
 except (ValueError,TypeError,UnicodeError,RecursionError):raise PrivacyError('privacy_document_invalid') from None

def checked_id(value):
 if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,180}',value):raise PrivacyError('privacy_file_identity_invalid')
 return value

def checked_hash(value):
 if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):raise PrivacyError('privacy_hash_invalid')
 return value

def checked_uuid(value):
 try:
  if not isinstance(value,str) or str(UUID(value))!=value or not UUID(value).int:raise ValueError()
  return value
 except (ValueError,TypeError,AttributeError):raise PrivacyError('privacy_operation_invalid') from None

def timestamp(value):
 try:
  if not isinstance(value,str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",value):raise ValueError()
  parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
  if parsed.year<2020:raise ValueError()
  return parsed
 except (TypeError,ValueError):raise PrivacyError("privacy_intent_time_invalid") from None

def raw_key(value,size=32):
 try:
  if not isinstance(value,str) or len(value)>256:raise ValueError()
  raw=base64.b64decode(value,altchars=b'-_',validate=True)
  if len(raw)!=size or base64.urlsafe_b64encode(raw).decode()!=value:raise ValueError()
  return raw
 except Exception:raise PrivacyError('privacy_key_invalid') from None

def keyring(value):
 if not isinstance(value,dict) or not 1<=len(value)<=8 or any(not isinstance(k,str) or not re.fullmatch(r'[a-z0-9_-]{1,48}',k) for k in value):raise PrivacyError('privacy_keyring_invalid')
 return {name:raw_key(key) for name,key in value.items()}

@dataclass(frozen=True,repr=False)
class Keys:
 encryption:dict=field(repr=False)
 verification:dict=field(repr=False)
 active_encryption:str|None=None
 signing_id:str|None=None
 signing_seed:str|None=field(default=None,repr=False)
 def __post_init__(self):
  encryption=keyring(self.encryption);verification=keyring(self.verification)
  if self.active_encryption is not None and self.active_encryption not in encryption:raise PrivacyError('privacy_key_invalid')
  if self.signing_seed is not None:
   if self.signing_id not in verification:raise PrivacyError('privacy_key_invalid')
   if raw_key(self.signing_seed) in encryption.values():raise PrivacyError('privacy_key_purposes_must_differ')
   signing=Ed25519PrivateKey.from_private_bytes(raw_key(self.signing_seed))
   if signing.public_key().public_bytes_raw()!=verification[self.signing_id]:raise PrivacyError('privacy_key_invalid')
 def seal(self,document):
  self.__post_init__();checked(document)
  if self.active_encryption is None or self.signing_seed is None:raise PrivacyError('privacy_reader_cannot_write')
  nonce=os.urandom(12);header={'version':1,'installation_id':INSTALLATION,'project':PROJECT,'environment':ENVIRONMENT,'purpose':'privacy-ledger','encryption_id':self.active_encryption,'signing_id':self.signing_id}
  payload=AESGCM(raw_key(self.encryption[self.active_encryption])).encrypt(nonce,canonical(document),canonical(header))
  unsigned=header|{'nonce':base64.urlsafe_b64encode(nonce).decode(),'ciphertext':base64.urlsafe_b64encode(payload).decode()}
  signed=Ed25519PrivateKey.from_private_bytes(raw_key(self.signing_seed)).sign(NAMESPACE+canonical(unsigned))
  data=canonical(unsigned|{'signature':base64.urlsafe_b64encode(signed).decode()})
  if len(data)>MAXIMUM:raise PrivacyError('privacy_document_limit')
  return data
 def open(self,data):
  self.__post_init__();value=unique(data)
  names={'version','installation_id','project','environment','purpose','encryption_id','signing_id','nonce','ciphertext','signature'}
  try:
   if (not isinstance(value,dict) or set(value)!=names or type(value['version']) is not int or value['version']!=1
       or value['installation_id']!=INSTALLATION or value['project']!=PROJECT or value['environment']!=ENVIRONMENT or value['purpose']!='privacy-ledger'
       or value['encryption_id'] not in self.encryption or value['signing_id'] not in self.verification):raise ValueError()
   unsigned={k:v for k,v in value.items() if k!='signature'}
   Ed25519PublicKey.from_public_bytes(raw_key(self.verification[value['signing_id']])).verify(raw_key(value['signature'],64),NAMESPACE+canonical(unsigned))
   nonce=raw_key(value['nonce'],12)
   ciphertext=base64.b64decode(value['ciphertext'],altchars=b'-_',validate=True)
   if base64.urlsafe_b64encode(ciphertext).decode()!=value['ciphertext'] or len(ciphertext)>MAXIMUM:raise ValueError()
   header={k:v for k,v in value.items() if k not in ('nonce','ciphertext','signature')}
   document=unique(AESGCM(raw_key(self.encryption[value['encryption_id']])).decrypt(nonce,ciphertext,canonical(header)))
   return checked(document)
  except PrivacyError:raise
  except Exception:raise PrivacyError('privacy_authentication_failed') from None

def checked(document):
 if not isinstance(document,dict) or document.get('kind') not in ('head','entry'):raise PrivacyError('privacy_document_invalid')
 if document['kind']=='head':
  if set(document)!={'kind','sequence','latest'} or type(document['sequence']) is not int or not 0<=document['sequence']<=MAX_SEQUENCE:raise PrivacyError('privacy_head_invalid')
  if document['sequence']==0:
   if document['latest'] is not None:raise PrivacyError('privacy_head_invalid')
  else:link(document['latest'],document['sequence'])
 else:
  names={'kind','sequence','previous','operation_id','phase','policy_id','target_id','target_hash','policy_version','minimum_days','approval_reference','intent_created_at'}
  if set(document)!=names or type(document['sequence']) is not int or not 1<=document['sequence']<=MAX_SEQUENCE:raise PrivacyError('privacy_entry_invalid')
  if document['sequence']==1:
   if document['previous'] is not None:raise PrivacyError('privacy_entry_invalid')
  else:link(document['previous'],document['sequence']-1)
  checked_uuid(document['operation_id']);checked_uuid(document['target_id']);checked_hash(document['target_hash']);checked_hash(document['approval_reference']);timestamp(document['intent_created_at'])
  days={'abandoned-enquiry-v1':7,'routine-incidents-v1':30,'resolved-transport-v1':90}
  if not isinstance(document['phase'],str) or document['phase'] not in ('intent','applied','cancelled') or type(document['policy_version']) is not int or document['policy_version']!=1 or not isinstance(document['policy_id'],str) or document['policy_id'] not in days or type(document['minimum_days']) is not int or document['minimum_days']!=days[document['policy_id']]:raise PrivacyError('privacy_entry_invalid')
 return document

def link(value,sequence):
 if not isinstance(value,dict) or set(value)!={'file_id','entry_hash','sequence'} or type(value['sequence']) is not int or value['sequence']!=sequence:raise PrivacyError('privacy_chain_invalid')
 checked_id(value['file_id']);checked_hash(value['entry_hash']);return value

class Ledger:
 def __init__(self,store,keys):self.store,self.keys=store,keys
 def head(self,minimum=0):
  if type(minimum) is not int or not 0<=minimum<=MAX_SEQUENCE:raise PrivacyError('privacy_head_regressed')
  data,version=self.store.read_head();document=self.keys.open(data)
  if document['kind']!='head' or document['sequence']<minimum:raise PrivacyError('privacy_head_regressed')
  return document,version
 def walk(self,head,*,floor=0):
  checked(head)
  if head['kind']!='head' or type(floor) is not int or not 0<=floor<=head['sequence']:raise PrivacyError('privacy_chain_invalid')
  current=head['latest'];steps=0
  while current is not None and current['sequence']>floor:
   steps+=1
   if steps>100000:raise PrivacyError('privacy_replay_budget')
   data=self.store.read_entry(current['file_id']);entry=self.keys.open(data)
   if entry['kind']!='entry' or digest(entry)!=current['entry_hash'] or entry['sequence']!=current['sequence']:raise PrivacyError('privacy_chain_invalid')
   yield entry,current
   current=entry['previous']
  if current is not None and current['sequence']!=floor:raise PrivacyError('privacy_chain_invalid')
 def verify_intent(self,record,proof,*,floor=0):
  checked(record|{'kind':'entry','sequence':1,'previous':None,'phase':'intent'})
  expected={k:proof[k] for k in ('sequence','entry_hash','head_hash','file_id')}
  checked_hash(expected['head_hash']);link({k:v for k,v in expected.items() if k!='head_hash'},expected['sequence'])
  head,_=self.head(max(floor,expected['sequence']))
  for entry,pointer in self.walk(head,floor=floor):
   if entry['operation_id']!=record['operation_id'] or entry['phase']!='intent':continue
   fields={k:v for k,v in entry.items() if k not in ('kind','sequence','previous','phase')}
   actual={'sequence':entry['sequence'],'entry_hash':pointer['entry_hash'],'file_id':pointer['file_id'],'head_hash':digest({'kind':'head','sequence':entry['sequence'],'latest':pointer})}
   if fields!=record or actual!=expected:raise PrivacyError('privacy_independent_intent_changed')
   return True
  raise PrivacyError('privacy_independent_intent_missing')
 def append(self,record,phase,*,floor=0):
  if phase not in ('intent','applied','cancelled'):raise PrivacyError('privacy_phase_invalid')
  checked(record|{'kind':'entry','sequence':1,'previous':None,'phase':phase})
  # The caller saves its observed floor with the SQL intent before network I/O.
  # Existing operations use that original floor on retry; no full history scan.
  for _ in range(4):
   head,version=self.head(floor);intent_found=False
   for previous,pointer in self.walk(head,floor=floor):
    if previous['operation_id']!=record['operation_id']:continue
    fields={k:v for k,v in previous.items() if k not in ('kind','sequence','previous','phase')}
    if fields!=record:raise PrivacyError('privacy_operation_changed')
    if previous['phase']=='intent':intent_found=True
    if previous['phase'] in ('applied','cancelled') and phase not in ('intent',previous['phase']):raise PrivacyError('privacy_outcome_changed')
    if previous['phase']==phase:
     fields={k:v for k,v in previous.items() if k not in ('kind','sequence','previous','phase')}
     if fields!=record:raise PrivacyError('privacy_operation_changed')
     return {'sequence':previous['sequence'],'entry_hash':pointer['entry_hash'],'head_hash':digest({'kind':'head','sequence':previous['sequence'],'latest':pointer}),'file_id':pointer['file_id']}
   if phase!='intent' and not intent_found:raise PrivacyError('privacy_original_intent_missing')
   if head['sequence']==MAX_SEQUENCE:raise PrivacyError('privacy_sequence_exhausted')
   entry=checked(record|{'kind':'entry','sequence':head['sequence']+1,'previous':head['latest'],'phase':phase})
   identity=self.store.create_entry(self.keys.seal(entry),entry['sequence'],digest(entry))
   pointer={'sequence':entry['sequence'],'file_id':checked_id(identity),'entry_hash':digest(entry)}
   # Stored ciphertext is independently read, authenticated and identity-bound.
   if self.keys.open(self.store.read_entry(identity))!=entry:raise PrivacyError('privacy_entry_unconfirmed')
   updated={'kind':'head','sequence':entry['sequence'],'latest':pointer}
   try:self.store.compare_and_swap_head(version,self.keys.seal(updated))
   except PrivacyError as error:
    if str(error)!='privacy_head_changed':raise
    continue
   confirmed,_=self.head(updated['sequence'])
   for actual,reference in self.walk(confirmed,floor=entry['sequence']-1):
    if actual==entry and reference==pointer:
     return {'sequence':entry['sequence'],'entry_hash':pointer['entry_hash'],'head_hash':digest(updated),'file_id':identity}
   raise PrivacyError('privacy_head_unconfirmed')
  raise PrivacyError('privacy_head_busy')
