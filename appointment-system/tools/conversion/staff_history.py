"""Retain old staff facts without inventing missing claim or contact history."""
from copy import deepcopy
from uuid import UUID
from .records import stamp
from .source import ConversionError

OPERATIONS={'operation_id','booking_id','action','actor','body_hash','previous_revision','revision','result','created_at'}
HISTORY={'operation_id','previous_start','current_start','notice_seconds','late_exception','reason'}


def indexed(rows,key):
 try:
  result={row[key]:row for row in rows}
  if len(result)!=len(rows):raise ValueError()
  return result
 except (KeyError,TypeError,ValueError):raise ConversionError('legacy_staff_history_invalid') from None


def originals(layout,source):
 if layout.project!='003' or type(source) is not dict:raise ConversionError('legacy_staff_history_unprepared')
 operations=indexed(source.get(layout.schema+'.staff_operations',[]),'operation_id')
 histories=indexed(source.get(layout.schema+'.staff_appointment_history',[]),'operation_id')
 bookings=indexed(source.get(layout.schema+'.bookings',[]),'id')
 for identifier,row in operations.items():
  try:
   if (set(row)!=OPERATIONS or row['action'] not in ('cancel','reschedule','receipt_recovery','contact_correction')
       or row['booking_id'] not in bookings or type(row['actor']) is not str or not row['actor']
       or type(row['body_hash']) is not str or len(row['body_hash'])!=64
       or any(c not in '0123456789abcdef' for c in row['body_hash'])
       or type(row['previous_revision']) is not int or row['previous_revision']<1
       or type(row['revision']) is not int or row['revision']<row['previous_revision']
       or type(row['result']) is not dict):raise ValueError()
   UUID(identifier);UUID(row['booking_id']);stamp(row['created_at'])
   result=row['result'];book=bookings[row['booking_id']]
   if (result.get('operation_id')!=identifier or result.get('booking_id')!=row['booking_id']
       or result.get('reference')!=book['request_id'] or result.get('revision')!=row['revision']):raise ValueError()
  except (ValueError,KeyError,TypeError,AttributeError):raise ConversionError('legacy_staff_history_invalid') from None
 for identifier,row in histories.items():
  if (set(row)!=HISTORY or identifier not in operations or type(row['notice_seconds']) is not int
      or type(row['late_exception']) is not bool or type(row['reason']) is not str
      or not 2<=len(row['reason'])<=500):raise ConversionError('legacy_staff_history_invalid')
  stamp(row['previous_start']);stamp(row['current_start'])
 return operations,histories,bookings


def transfer(layout,table,rows,source):
 operations,histories,_=originals(layout,source)
 expected=operations if table=='staff_operations' else histories if table=='staff_appointment_history' else None
 if expected is None:raise ConversionError('legacy_staff_history_unprepared')
 if any(expected.get(row.get('operation_id'))!=row for row in rows):raise ConversionError('legacy_staff_history_invalid')
 return {'historical_'+table:deepcopy(rows)}
