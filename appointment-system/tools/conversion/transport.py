"""Historical queued work becomes common jobs, never a second active worker."""
from copy import deepcopy
from datetime import timedelta
from .source import ConversionError
from .records import Bindings,stamp,digest,private_reference
from .mail import MailTransfer
from .allowance import baselines
from .calendar import protocol as calendar_protocol

def job_state(row):
 if row['state']=='sent':
  return 'suppressed' if row.get('last_error_code')=='superseded_by_cancellation' else 'completed'
 if row['state'] in ('processing','failed'):
  if row.get('send_uncertain'):return 'delivery_unknown'
  if row['state']=='failed':return 'needs_review'
  return 'retry_wait'
 if row['state']=='pending':return 'delivery_unknown' if row.get('send_uncertain') else 'pending'
 raise ConversionError('legacy_job_state_invalid')

class TransportTransfer:
 def __init__(self,bindings,mail=None):
  if not isinstance(bindings,Bindings) or mail is not None and not isinstance(mail,MailTransfer):
   raise ConversionError('legacy_transport_configuration_invalid')
  self.bindings=bindings;self.mail=mail

 def __call__(self,layout,table,rows,source=None):
  if layout.project!='003' or type(source) is not dict:raise ConversionError('legacy_transport_layout_mismatch')
  if table=='delivery_jobs':return self.jobs(layout,rows,source)
  result=[]
  for original in rows:
   row=deepcopy(original)
   if table=='checkout_contexts':
    row['credential_format']=self.bindings.format('context-003');row['credential_key_id']=None
    row['activation_epoch']=private_reference(self.bindings.installation.installation_id,'historical-activation',layout.project)
    result.append(row)
   elif table=='payment_cases':
    self.bindings.payment(key_id=row['key_id'])
    closed=row['state']!='open'
    if closed and not row.get('handled_at'):raise ConversionError('legacy_case_resolution_missing')
    result.append(dict(id=row['id'],booking_id=row['booking_id'],event_key='legacy:'+row['external_reference'],
     reason=row['kind'],next_check_at=row.get('next_check_at') or row['created_at'],
     financial_first_seen=row.get('financial_first_seen') or row['created_at'],financial_lease_token=None,
     financial_lease_until=None,financial_attempts=row.get('financial_attempts',0),financial_error=row.get('financial_error'),
     resolved_at=row['handled_at'] if closed else None,resolution_actor=row['handled_by'] if closed else None,
     resolution_note=(row['note'] or row['resolution'] or 'Historical staff resolution') if closed else None))
   elif table=='payment_events':
    binding=self.bindings.payment(key_id=row['key_id'],mode=row.get('mode'),merchant=row.get('merchant_scope'))
    if row['account_id'] not in ('',binding['merchant_id']):raise ConversionError('legacy_payment_ownership_conflict')
    payload={'event':row['kind'],'payment_id':row['payment_id'],'order_id':row.get('order_id'),
       'legacy_record_id':row['record_id'],'legacy_verified_event':True}
    if row.get('resource_fact') is not None:payload['resource_fact']=row['resource_fact']
    result.append(dict(provider='razorpay',account_id=binding['merchant_id'],environment=binding['mode'],
     event_id=row['event_id'],body_hash=row['payload_hash'],payload=payload,received_at=row['received_at'],
     processed_at=row['processed_at'],next_attempt_at=row['next_attempt_at'],attempts=row['attempts'],
     lease_token=None,lease_expires_at=None,last_error_code=row['last_error']))
   else:raise ConversionError('legacy_transport_table_unprepared')
  return {('provider_inbox' if table=='payment_events' else table):result}

 def jobs(self,layout,rows,source):
  result={}
  books={row['id']:row for row in source.get(layout.schema+'.bookings',[])}
  enquiries={row['id']:row for row in source.get(layout.schema+'.inquiries',[])}
  baseline={row['bucket_date']:row for row in baselines(self.bindings,source.get(layout.schema+'.rate_limits',[]))}
  counts={}
  for row in source.get(layout.schema+'.delivery_jobs',[]):
   if row['recipient_role'] in ('customer','client') and row['first_attempt_at']:
    day=stamp(row['first_attempt_at']).date().isoformat();counts[day]=counts.get(day,0)+1
  for day,count in counts.items():
   if day in baseline and count>baseline[day]['total_count']:raise ConversionError('legacy_allowance_reservation_conflict')
  for original in rows:
   row=deepcopy(original);kind=row['kind'];role=row['recipient_role'];record=row['record_id']
   if kind=='payment_event':
    events=[event for event in source.get(layout.schema+'.payment_events',[]) if event['record_id']==record]
    if len(events)!=1:raise ConversionError('legacy_payment_job_identity_missing')
    for target,records in self(layout,'payment_events',events,source).items():result.setdefault(target,[]).extend(records)
    continue
   if role in ('customer','client') and row['first_attempt_at']:
    day=stamp(row['first_attempt_at']).date().isoformat()
    result.setdefault('email_reservations',[]).append(dict(job_id=None if kind=='inquiry_received' else row['id'],
     enquiry_job_id=row['id'] if kind=='inquiry_received' else None,verification_job_id=None,
     reserved_at=row['first_attempt_at'],verification=False,counted_in_legacy_baseline=day in baseline))
   common=dict(id=row['id'],state=job_state(row),attempts=row['attempts'],
    next_attempt_at=row['next_attempt_at'],first_attempt_at=row['first_attempt_at'],provider_id=row['provider_id'],
    lease_token=None,lease_expires_at=None,last_error_code=row['last_error_code'],template_version=row['message_version'],
    send_uncertain=row['send_uncertain'],prior_send_uncertain=row['send_uncertain'],
    message_snapshot=row['message_payload'],mail_idempotency_key=row.get('mail_key'),
    mail_key_kind=kind,mail_key_role=role)
   if kind in ('inquiry_received','sheet_inquiry'):
    parent=enquiries.get(record)
    is_sheet=kind=='sheet_inquiry'
    if parent is None or role not in (('client_sheet','agency_sheet') if is_sheet else ('customer','client')):
     raise ConversionError('legacy_enquiry_job_identity_missing')
    common.update(request_id=parent['request_id'],kind=role if is_sheet else 'acknowledgement' if role=='customer' else 'practice_notice',
     generation=0,created_at=row['created_at'],destination=None if is_sheet else parent['email'] if role=='customer' else self.bindings.installation.document['owners']['client_email'],
     payload={'email':parent['email']},deadline_at=((stamp(row['first_attempt_at'])+timedelta(hours=23)).isoformat()
      if row['first_attempt_at'] else (self.bindings.now+timedelta(hours=23)).isoformat()))
    if not is_sheet and (row['message_payload'] is not None or row['first_attempt_at'] is not None):
     if self.mail is None:raise ConversionError('legacy_mail_binding_unresolved')
     common=self.mail(layout,'enquiry_delivery_jobs',common)
    else:common.pop('message_snapshot',None)
    if is_sheet:self.sheet_continuation(common,row,layout,source)
    for field in ('mail_key_kind','mail_key_role','payload'):common.pop(field,None)
    result.setdefault('enquiry_delivery_jobs',[]).append(common);continue
   book=books.get(record)
   if book is None:raise ConversionError('legacy_booking_job_identity_missing')
   if kind=='booking_confirmed':
    target_kind={'customer':'booking_details','client':'booking_ack','calendar':'booking_calendar'}.get(role)
   elif kind in ('booking_cancelled','payment_review','sheet_booking'):target_kind=kind
   else:raise ConversionError('legacy_booking_job_kind_invalid')
   if target_kind is None:raise ConversionError('legacy_booking_job_role_invalid')
   common.update(booking_id=record,kind=target_kind,recipient_role=role,booking_revision=row.get('booking_revision',1),
    event_key=row['dedupe_key'] if kind=='payment_review' else '',accepted_at=row['accepted_at'],
    destination=(row['message_payload']['to'][0] if row['message_payload'] is not None else
      book['email'] if role=='customer' else self.bindings.installation.document['owners']['client_email'] if role=='client' else None),
    message_hash=None,send_deadline_at=(stamp(row['first_attempt_at'])+timedelta(hours=23)).isoformat() if row['first_attempt_at'] else None,
    ever_uncertain=row['send_uncertain'],payload=self.snapshot(row.get('booking_snapshot') or book))
   common['payload']['calendar_protocol']=calendar_protocol(layout,source,record,common['booking_revision'])
   if kind=='sheet_booking':self.sheet_continuation(common,row,layout,source)
   if role in ('customer','client') and (row['message_payload'] is not None or row['first_attempt_at'] is not None):
    if self.mail is None:raise ConversionError('legacy_mail_binding_unresolved')
    common=self.mail(layout,'delivery_jobs',common)
   result.setdefault('delivery_jobs',[]).append(common)
  return result

 def sheet_continuation(self,common,original,layout,source):
  # The original 16-migration layout stored completion, not allocated row
  # addresses. Keep completed work completed. An uncertain attempted old copy
  # cannot safely select a new owner/file/row and write again automatically.
  if (original['first_attempt_at'] is not None and common['state'] not in ('completed','suppressed')
      and not any(row['job_id']==original['id'] and row['role']==original['recipient_role']
                  for row in source.get(layout.schema+'.sheet_history_rows',[]))):
   common['state']='needs_review';common['last_error_code']='legacy_sheet_address_unresolved'

 def snapshot(self,book):
  required=('id','service_id','service_name','amount_paise','currency','starts_at','duration_minutes','full_name','email','phone','state')
  if any(name not in book for name in required):raise ConversionError('legacy_booking_snapshot_incomplete')
  return dict(id=book['id'],reference=book['id'],revision=book.get('revision',1),state=book['state'],
   service=book['service_name'],service_snapshot={'id':book['service_id'],'name':book['service_name'],
    'duration_minutes':book['duration_minutes'],'questions':book.get('question_count',1)},
   amount_paise=book['amount_paise'],currency=book['currency'],starts_at=book['starts_at'],
   ends_at=(stamp(book['starts_at'])+timedelta(minutes=book['duration_minutes'])).isoformat(),
   practice_timezone='Asia/Kolkata',full_name=book['full_name'],email=book['email'],phone=book['phone'],
   preparation={name:book.get(name) for name in ('birth_date','birth_time','birth_place','notes')})
