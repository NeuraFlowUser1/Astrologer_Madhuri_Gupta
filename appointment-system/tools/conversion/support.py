"""Preserve saved support and throttle facts without issuing new authority."""
from copy import deepcopy
from .records import stamp
from .recovery import RecoveryTransfer
from .source import ConversionError
from .mail_events import MailEventTransfer
from . import staff_history


class SupportHistoryTransfer:
 def __init__(self,recovery=None,mail_events=None):
  if recovery is not None and not isinstance(recovery,RecoveryTransfer):raise ConversionError('legacy_support_configuration_invalid')
  if mail_events is not None and not isinstance(mail_events,MailEventTransfer):raise ConversionError('legacy_support_configuration_invalid')
  self.recovery=recovery;self.mail_events=mail_events

 def __call__(self,layout,table,rows,source=None):
  if table in ('staff_operations','staff_appointment_history'):
   return staff_history.transfer(layout,table,rows,source)
  if table in ('email_events','verification_emails'):
   if self.mail_events is None:raise ConversionError('legacy_mail_event_binding_missing')
   return self.mail_events(layout,table,rows,source)
  if table=='receipt_recoveries':
   if self.recovery is None:raise ConversionError('legacy_recovery_reader_missing')
   return self.recovery(layout,table,rows,source)
  if layout.project=='003' and table=='admin_identity':
   if len(rows)!=1 or set(rows[0])!={'singleton','google_subject','authorized_at'}:
    raise ConversionError('legacy_staff_identity_invalid')
   row=rows[0];subject=row['google_subject']
   if row['singleton'] is not True or type(subject) is not str or not 1<=len(subject)<=255:
    raise ConversionError('legacy_staff_identity_invalid')
   stamp(row['authorized_at'])
   connections=(source or {}).get(layout.schema+'.google_connection',[])
   if any(item['google_subject']!=subject for item in connections):raise ConversionError('legacy_staff_identity_conflict')
   # Keep the pinned Google identity. No session, company authority, or new
   # sign-in audit event is invented. Original authorisation evidence remains
   # in the fenced source and its exact conversion fingerprint.
   return {'studio_identities':[{'role':'client','subject':subject}]}
  if layout.project=='004' and table=='request_limits':
   # Same saved windows/counters, no reset or extension. Rotated purpose keys
   # do not make these old digests authority for a different identity.
   return {'request_limits':deepcopy(rows)}
  raise ConversionError('legacy_support_table_unprepared')
