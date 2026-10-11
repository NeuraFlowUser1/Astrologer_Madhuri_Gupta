"""Verify issued recovery-code provenance and retain inert audit facts."""
from copy import deepcopy
import hmac
import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID
import re
from appointment_system.credentials import historical_keys
from appointment_system.keys import KEY_ID
from appointment_system.serialization import object_fields
from appointment_system.errors import invalid
from appointment_system.secret_configuration import historical
from .source import ConversionError
from . import staff_history

def recovery_readers(value, materials):
    if type(value) not in (dict,MappingProxyType) or len(value)>8:raise invalid('legacy_recovery_readers')
    result={}
    for name,reader in value.items():
        if type(reader) is MappingProxyType:reader=dict(reader)
        if type(name) is not str or name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name):
            raise invalid('legacy_recovery_readers')
        object_fields(reader,{'key_id','code_audience','digest_audience'})
        if type(reader['key_id']) is not str or not KEY_ID.fullmatch(reader['key_id']) or reader['key_id'] not in materials:raise invalid('legacy_recovery_keys')
        for field_name in ('code_audience','digest_audience'):
            audience=reader[field_name]
            if type(audience) is not str or not 1<=len(audience)<=128 or not re.fullmatch(r'[a-zA-Z0-9:-]+',audience) or not audience.endswith(':'):
                raise invalid('legacy_recovery_readers')
        if reader['code_audience']==reader['digest_audience']:raise invalid('legacy_recovery_readers')
        result[name]=MappingProxyType(dict(reader))
    return MappingProxyType(result)


@dataclass(frozen=True,repr=False)
class RecoveryKeys:
 recovery_readers: object
 materials: object

def recovery_keys(environment):
 definitions,materials=historical(environment)
 accepted=historical_keys(materials)
 return RecoveryKeys(recovery_readers(definitions.get('recovery',{}),accepted),accepted)


def provenance_digest(keys,operation,reference,format,key_id):
 definition=keys.recovery_readers[format]
 if definition['key_id']!=key_id:raise ValueError()
 material=keys.materials[key_id]
 raw=hmac.new(material,(definition['code_audience']+str(UUID(str(operation)))+':'+str(UUID(str(reference)))).encode(),hashlib.sha256).digest()
 code=str(int.from_bytes(raw,'big')%100000000).zfill(8)
 return hmac.new(material,(definition['digest_audience']+str(UUID(str(reference)))+':'+code).encode(),hashlib.sha256).hexdigest()

class RecoveryTransfer:
 def __init__(self,keys,format):
  if not isinstance(keys,RecoveryKeys) or format not in keys.recovery_readers:
   raise ConversionError('legacy_recovery_reader_missing')
  self.keys=keys;self.format=format;self.key_id=keys.recovery_readers[format]['key_id']

 def __call__(self,layout,table,rows,source=None):
  if layout.project not in ('003','004') or table!='receipt_recoveries':
   raise ConversionError('legacy_recovery_layout_unprepared')
  history=staff_history.originals(layout,source) if layout.project=='003' else None
  result=[]
  for original in rows:
   row=deepcopy(original)
   if history is not None:row=self.from_operation(row,*history)
   try:
    digest=provenance_digest(self.keys,row['operation_id'],row['request_id'],self.format,self.key_id)
    if type(row['code_digest']) is not str or not hmac.compare_digest(row['code_digest'],digest):raise ValueError()
   except (KeyError,ValueError,TypeError):raise ConversionError('legacy_recovery_key_unproved') from None
   # Expiry, supersession, wrong-attempt and redemption facts are copied exactly.
   # This does not issue a new code or revive exhausted/expired authority.
   for field in ('code_digest','redeemed_digest','code_format','code_key_id'):row.pop(field,None)
   result.append(row)
  return {'receipt_recoveries':result}

 def from_operation(self,row,operations,histories,bookings):
  try:
   operation=operations[row['operation_id']];history=histories[row['operation_id']]
   book=bookings[row['booking_id']]
   if (set(row)!={'operation_id','booking_id','code_digest','expires_at','attempts','superseded_at','redeemed_at','redeemed_digest'}
       or operation['booking_id']!=row['booking_id']
       or operation['action'] not in ('receipt_recovery','contact_correction')):raise ValueError()
  except (KeyError,ValueError,TypeError):raise ConversionError('legacy_recovery_history_missing') from None
  # This source saved a request hash, not the verified payment or before/after
  # contact values. Preserve that limitation; current contact data is not proof
  # of what staff saw at the earlier operation.
  row.pop('booking_id')
  row.update(request_id=book['request_id'],action=operation['action'],actor=operation['actor'],
   reason=history['reason'],verified_payment_id=None,verification_method='retained_staff_operation',
   historical_operation_id=operation['operation_id'],previous_revision=operation['previous_revision'],
   revision=operation['revision'],created_at=operation['created_at'],
   previous_email=None,previous_phone=None,new_email=None,new_phone=None)
  return row
