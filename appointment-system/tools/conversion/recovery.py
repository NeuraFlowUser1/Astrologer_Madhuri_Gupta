"""Verify issued recovery-code provenance rather than relabelling old digests."""
from copy import deepcopy
import hmac
from appointment_system.credentials import ReceiptKeys
from appointment_system.receipt_recovery import recovery_code,code_digest
from .source import ConversionError
from . import staff_history

class RecoveryTransfer:
 def __init__(self,keys,format):
  if not isinstance(keys,ReceiptKeys) or format not in keys.recovery_readers:
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
    code=recovery_code(self.keys,row['operation_id'],row['request_id'],format=self.format,key_id=self.key_id)
    digest=code_digest(self.keys,row['request_id'],code,format=self.format,key_id=self.key_id)
    if type(row['code_digest']) is not str or not hmac.compare_digest(row['code_digest'],digest):raise ValueError()
   except (KeyError,ValueError,TypeError):raise ConversionError('legacy_recovery_key_unproved') from None
   # Expiry, supersession, wrong-attempt and redemption facts are copied exactly.
   # This does not issue a new code or revive exhausted/expired authority.
   row.update(code_format=self.format,code_key_id=self.key_id);result.append(row)
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
