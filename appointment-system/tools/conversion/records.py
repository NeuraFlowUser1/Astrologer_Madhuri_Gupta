"""One-time historical record translation, never an alternative booking engine.

Accepted money comes from saved payment evidence, never an appointment label.
Private provider/grant bindings are supplied by separately validated adapters.
Every source table receives a disposition; raw history stays read-only until
its approved erasure/retention, rather than being silently discarded.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
import hashlib,re,json
from types import MappingProxyType
from uuid import UUID,uuid5
from zoneinfo import ZoneInfo
from appointment_system.razorpay import Credentials
from appointment_system.settings import Installation,BusinessSettings
from .source import ConversionError,Layout,canonical
from .calendar import protocol as calendar_protocol

EPHEMERAL={
 'admin_login_challenges','admin_sessions','google_authorizations','email_challenges','email_verifications',
 'google_attempts','studio_sessions','company_sessions','login_challenges','grant_repairs','login_limits',
 'recovery_heartbeat','recovery_lanes','recovery_lane_incidents','operational_incidents',
}
DIRECT_004={
 'booking_policies','checkout_contexts','checkout_admissions','bookings','payment_orders','payment_observations',
 'accepted_payments','provider_inbox','payment_cases','delivery_jobs','email_observations','email_reservations',
 'enquiries','enquiry_delivery_jobs','enquiry_email_observations','enquiry_resends','slot_claims',
 'staff_appointment_actions','staff_calendar_actions','staff_reviews','studio_audit','studio_identities',
 'meeting_events','sheet_rows','enquiry_sheet_rows','google_workbooks','google_workbook_volumes',
 'financial_resource_facts','financial_resource_states','mail_acceptance_claims',
}
RESOURCE_TABLES={'google_connection','google_connections','sheet_owner_grants','sheet_volumes','sheet_tab_counters',
 'sheet_job_snapshots','sheet_record_rows','sheet_history_rows','google_workbooks','google_workbook_volumes',
 'sheet_rows','enquiry_sheet_rows','booking_calendar_events','booking_event_revisions','meeting_events'}
HISTORICAL_CONTROL={'company_enrolment_evidence','company_identities','maintenance_control_actions','operations',
 'privacy_completions','privacy_documents','privacy_exports','privacy_intents','privacy_policies',
 'privacy_policy_approvals','privacy_replay_progress','product_state','publications','restore_completions','restore_operations'}
HISTORY_003={'admin_identity','google_refresh_evidence','accepted_payment_bindings','payment_evidence_journal',
 'mail_acceptance_conflicts','mail_acceptance_evidence','mail_provider_ownership','mail_recipient_suppressions',
 'payment_callback_references','payment_case_actions','staff_appointment_history','staff_operations',
 'verification_emails','verification_mail','verification_mail_conflicts','verification_mail_evidence','email_events',
 'rate_limits','receipt_recoveries','financial_resource_facts','financial_resource_states'}

def stamp(value):
 try:
  result=datetime.fromisoformat(value.replace('Z','+00:00')) if type(value) is str else value
  if not isinstance(result,datetime) or result.tzinfo is None or result.utcoffset() is None:raise ValueError()
  return result.astimezone(timezone.utc)
 except (ValueError,TypeError,AttributeError):raise ConversionError('legacy_timestamp_invalid') from None

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def private_reference(namespace,kind,value):return str(uuid5(UUID(namespace),kind+':'+str(value)))

@dataclass(frozen=True)
class ConfigurationOnly:
 table:str
 source_digest:str
 reason:str

CONFIGURATION_RETIREMENTS={'email_policy':'historical_limits_replaced','product_state':'historical_activation_retired',
                          'rate_limits':'historical_throttles_retired'}

@dataclass(frozen=True,repr=False)
class Bindings:
 installation:Installation
 business:BusinessSettings
 now:datetime
 payment_readers:tuple=field(default=(),repr=False)
 receipt_formats:dict=field(default_factory=dict,repr=False)
 resource_mapper:object=field(default=None,repr=False)
 mail_mapper:object=field(default=None,repr=False)
 transport_mapper:object=field(default=None,repr=False)
 history_mapper:object=field(default=None,repr=False)
 quota_mapper:object=field(default=None,repr=False)
 enquiry_mapper:object=field(default=None,repr=False)

 def __post_init__(self):
  if not isinstance(self.installation,Installation) or not isinstance(self.business,BusinessSettings):
   raise ConversionError('conversion_identity_invalid')
  object.__setattr__(self,'now',stamp(self.now))
  if (type(self.payment_readers) is not tuple or any(not isinstance(item,Credentials) for item in self.payment_readers)
      or len({(item.merchant_id,item.mode,item.version) for item in self.payment_readers})!=len(self.payment_readers)
      or type(self.receipt_formats) is not dict):raise ConversionError('conversion_reader_invalid')
  for value in self.receipt_formats.values():
   if type(value) is not str or value=='v1' or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',value):
    raise ConversionError('conversion_reader_invalid')
  object.__setattr__(self,'receipt_formats',MappingProxyType(deepcopy(self.receipt_formats)))
  for callback in (self.resource_mapper,self.mail_mapper,self.transport_mapper,self.history_mapper,self.quota_mapper,self.enquiry_mapper):
   if callback is not None and not callable(callback):raise ConversionError('conversion_reader_invalid')

 def payment(self,*,key_id=None,merchant=None,mode=None,version=None):
  matches=[item for item in self.payment_readers if (key_id is None or item.key_id==key_id)
   and (merchant is None or item.merchant_id==merchant) and (mode is None or item.mode==mode)
   and (version is None or item.version==version)]
  if len(matches)!=1:raise ConversionError('legacy_payment_binding_unresolved')
  item=matches[0];return {'merchant_id':item.merchant_id,'mode':item.mode,'credential_version':item.version}

 def format(self,name):
  try:return self.receipt_formats[name]
  except KeyError:raise ConversionError('legacy_reader_not_prepared') from None

@dataclass(frozen=True,repr=False,init=False)
class Translation:
 layout:str
 source_digest:str
 _tables:bytes=field(repr=False)
 _disposition:bytes=field(repr=False)
 _comparisons:bytes=field(repr=False)

 def __init__(self,layout,source_digest,tables,disposition,comparisons):
  object.__setattr__(self,'layout',layout);object.__setattr__(self,'source_digest',source_digest)
  for name,value in (('_tables',tables),('_disposition',disposition),('_comparisons',comparisons)):
   object.__setattr__(self,name,canonical(value))

 @property
 def tables(self):return json.loads(self._tables)
 @property
 def disposition(self):return json.loads(self._disposition)
 @property
 def comparisons(self):return json.loads(self._comparisons)
 @property
 def target_digest(self):return hashlib.sha256(self._tables).hexdigest()

 def summary(self):
  return {'layout':self.layout,'source_digest':self.source_digest,'target_counts':{key:len(value) for key,value in self.tables.items()},
   'source_dispositions':self.disposition,'target_digest':self.target_digest}

class Mapper:
 def __init__(self,layout,rows,bindings):
  if (not isinstance(layout,Layout) or not isinstance(bindings,Bindings) or type(rows) is not dict
      or set(rows)!=set(layout.structure['relations'])):
   raise ConversionError('conversion_source_incomplete')
  for table,records in rows.items():
   columns={column['name'] for column in layout.structure['relations'][table]}
   if type(records) is not list or any(type(row) is not dict or set(row)!=columns for row in records):
    raise ConversionError('conversion_source_row_incomplete')
  self.layout=layout;self.rows=deepcopy(rows);self.bindings=bindings;self.output={};self.disposition={};self.comparisons={}
  self.namespace=bindings.installation.installation_id
  # Historical activation provenance is explicitly different from a new ON.
  self.epoch=private_reference(self.namespace,'historical-activation',layout.project)
  self.orders={row['booking_id']:row for row in self.source('payment_orders')}
  self.bookings={row['id']:row for row in self.source('bookings')}
  self.accepted={row['booking_id']:row for row in self.source('accepted_payments' if layout.project=='004' else 'payments')
   if layout.project=='004' or row['disposition']=='accepted'}
  if (len(self.orders)!=len(self.source('payment_orders')) or len(self.bookings)!=len(self.source('bookings'))
      or len(self.accepted)!=sum(layout.project=='004' or row['disposition']=='accepted'
       for row in self.source('accepted_payments' if layout.project=='004' else 'payments'))):
   raise ConversionError('legacy_duplicate_identity')
  if layout.project=='004':self._validate_accepted004()

 def _validate_accepted004(self):
  observed={row['id']:row for row in self.source('payment_observations')}
  for booking_id,accepted in self.accepted.items():
   booking=self.bookings.get(booking_id);order=self.orders.get(booking_id);evidence=observed.get(accepted['observation_id'])
   if (booking is None or order is None or evidence is None or evidence['booking_id']!=booking_id
       or not evidence['captured'] or evidence['status'] not in ('captured','refunded')
       or evidence['amount_paise']!=booking['amount_paise'] or evidence['currency']!=booking['currency']
       or evidence['merchant_id']!=order['merchant_id'] or evidence['mode']!=order['mode']
       or evidence['provider_order_id']!=order['provider_order_id']
       or any(accepted[field]!=evidence[field] for field in ('merchant_id','mode','payment_id'))):
    raise ConversionError('legacy_accepted_payment_conflict')
   self.bindings.payment(merchant=order['merchant_id'],mode=order['mode'],version=order['credential_version'])

 def adapter(self,callback,table,rows,code):
  if not rows:return
  if callback is None:raise ConversionError(code+'_unresolved')
  result=callback(self.layout,table,deepcopy(rows),deepcopy(self.rows))
  if isinstance(result,ConfigurationOnly):
   if (result.table!=table or result.source_digest!=digest(rows)
       or CONFIGURATION_RETIREMENTS.get(table)!=result.reason):raise ConversionError(code+'_invalid')
   return
  if (type(result) is not dict or any(type(target) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,62}',target)
      or type(items) is not list or any(type(item) is not dict for item in items) for target,items in result.items())
      or not any(result.values())):raise ConversionError(code+'_invalid')
  for target,items in result.items():
   for item in items:self.add(target,deepcopy(item))

 def source(self,table):return self.rows.get(self.layout.schema+'.'+table,[])
 def add(self,table,row):
  if table in ('provider_inbox','meeting_events'):
   identity=('provider','account_id','environment','event_id') if table=='provider_inbox' else ('booking_id','booking_revision')
   previous=[item for item in self.output.get(table,[]) if all(item[field]==row[field] for field in identity)]
   if previous:
    if len(previous)!=1 or canonical(previous[0])!=canonical(row):raise ConversionError('legacy_provider_event_collision' if table=='provider_inbox' else 'legacy_calendar_event_collision')
    return
  self.output.setdefault(table,[]).append(row)
 def uid(self,kind,value):return private_reference(self.namespace,kind,value)

 def _unresolved_confirmation(self,row):
  if row['state']=='confirmed' and row['id'] not in self.accepted:
   row['preparation']['_legacy_unproved_confirmation']=True;row['state']='payment_review'
   self.add('payment_cases',dict(id=self.uid('unproved-confirmation',row['id']),booking_id=row['id'],
      event_key='legacy:unproved-confirmation:'+row['id'],reason='legacy_confirmation_unverified',next_check_at=self.bindings.now.isoformat()))

 def _job(self,table,row):
  row=deepcopy(row)
  row['lease_token']=None;row['lease_expires_at']=None
  if row['state'] in ('processing','failed'):
   row['state']='delivery_unknown' if row.get('first_attempt_at') else 'retry_wait'
  else:row['state']={'accepted':'completed','delivered':'completed','done':'completed','expired':'suppressed',
    'uncertain':'delivery_unknown','attention':'needs_review'}.get(row['state'],row['state'])
  verification=False
  if table=='enquiry_delivery_jobs' and row['kind']=='verification':
   parents=[item for item in self.source('enquiries') if item['request_id']==row['request_id']]
   if len(parents)!=1:raise ConversionError('legacy_mail_enquiry_missing')
   parent=parents[0]
   verification=(parent['verified_at'] is None and parent['generation']==row['generation']
                 and parent['code_digest'] is not None and parent['code_ciphertext'] is not None
                 and stamp(parent['code_expires_at'])>self.bindings.now
                 and stamp(row['deadline_at'])>self.bindings.now and parent['attempts']<5)
   if not verification:
    if row['state']!='completed':row['state']='suppressed'
    row['message_ciphertext']=None
  if table=='delivery_jobs' and row['kind']=='booking_calendar':row.setdefault('payload',{})
  is_mail=(table=='delivery_jobs' and row.get('recipient_role') in ('customer','client') or
           table=='enquiry_delivery_jobs' and (row.get('kind') in ('acknowledgement','practice_notice') or verification))
  if is_mail and (row.get('message_snapshot') or row.get('message_ciphertext') or row.get('first_attempt_at')):
   if self.bindings.mail_mapper is None:raise ConversionError('legacy_mail_binding_unresolved')
   if table=='enquiry_delivery_jobs':
    parents=[item for item in self.source('enquiries') if item['request_id']==row['request_id']]
    if len(parents)!=1:raise ConversionError('legacy_mail_enquiry_missing')
    row['payload']=deepcopy(parents[0]['payload'])
   row=self.bindings.mail_mapper(self.layout,table,deepcopy(row))
   if type(row) is not dict:raise ConversionError('legacy_mail_binding_invalid')
   if table=='enquiry_delivery_jobs':row.pop('payload',None)
  return row

 def _direct(self,table,original):
  row=deepcopy(original)
  if table in ('checkout_contexts','checkout_admissions','bookings'):row['activation_epoch']=self.epoch
  if table=='checkout_contexts':
   row['credential_format']=self.bindings.format('context-004');row['credential_key_id']=None
   row['verification_id']=None
  elif table=='bookings':
   row['preparation']=deepcopy(row['preparation']);row['receipt_format']=self.bindings.format('receipt-004')
   # The inspected legacy Sarsa writer only offered Google Meet. Its saved
   # platform label is not the common engine's field; preserve that label and
   # add the normalized accepted choice, never the new installation default.
   snapshot=row['service_snapshot']
   if (type(snapshot) is not dict
       or snapshot.get('meeting_platform','Google Meet')!='Google Meet'
       or snapshot.get('meeting','google_meet')!='google_meet'):
    raise ConversionError('legacy_meeting_contract_invalid')
   row['service_snapshot']=snapshot|{'meeting':'google_meet'}
   row['receipt_key_id']=None;row['provider_receipt_format']='sarsa-order-receipt-v1';row['calendar_protocol']='legacy-sarsa004'
   self._unresolved_confirmation(row)
   if 'original_starts_at' not in row:
    # starts_at in a saved action is the PREVIOUS time. A later surviving
    # action cannot prove the original time if the first revision is absent.
    history=[item for item in self.source('staff_appointment_actions')
     if item['booking_id']==row['id'] and item['previous_revision']==1]
    if len(history)>1:raise ConversionError('legacy_original_time_conflict')
    row['original_starts_at']=history[0]['starts_at'] if history else (row['starts_at'] if row['revision']==1 else None)
    if row['original_starts_at'] is None:row['preparation']['_legacy_original_time_unknown']=True
  elif table=='payment_orders':
   self.bindings.payment(merchant=row['merchant_id'],mode=row['mode'],version=row['credential_version'])
   row['lease_token']=None;row['lease_expires_at']=None;row['resume_started_at']=None
   row['resume_lease_token']=None
   if row['state']=='creating':row['state']='creation_unknown';row['recovery_followup']=True
   if row['attempted_at'] and row.get('order_search_from') is None:
    attempted=stamp(row['attempted_at'])
    row['order_search_from']=(attempted-timedelta(minutes=5)).isoformat()
    row['order_search_until']=(attempted+timedelta(days=1)).isoformat()
  elif table=='payment_observations':
   order=self.orders.get(row['booking_id'])
   if order is None or row['merchant_id']!=order['merchant_id'] or row['mode']!=order['mode']:
    raise ConversionError('legacy_payment_ownership_conflict')
   self.bindings.payment(merchant=row['merchant_id'],mode=row['mode'],version=order['credential_version'])
  elif table=='enquiries':
   row['receipt_format']=self.bindings.format('enquiry-004');row['receipt_key_id']=None
   if row['verified_at'] is None and stamp(row['code_expires_at'])>self.bindings.now and row['code_digest'] is not None:
    if self.bindings.enquiry_mapper is None:raise ConversionError('legacy_enquiry_binding_unresolved')
    original=deepcopy(row);row=self.bindings.enquiry_mapper(row,self.bindings.now)
    changed={'code_digest','code_ciphertext','code_format','code_digest_format','code_digest_key_id'}
    if (type(row) is not dict or set(row)-set(original)-changed
        or any(row.get(key)!=value for key,value in original.items() if key not in changed)):
     raise ConversionError('legacy_enquiry_binding_invalid')
   else:
    row['code_digest']=None;row['code_ciphertext']=None
  elif table in ('delivery_jobs','enquiry_delivery_jobs'):row=self._job(table,row)
  elif table=='provider_inbox':row['lease_token']=None;row['lease_expires_at']=None
  elif table=='email_reservations' and not row.get('job_id') and not row.get('enquiry_job_id'):
   raise ConversionError('legacy_mail_quota_binding_missing')
  if table=='email_reservations':
   job=next((item for item in self.source('enquiry_delivery_jobs') if item['id']==row.get('enquiry_job_id')),None)
   row['verification']=bool(job and job['kind']=='verification')
  return row

 def _book003(self,row):
  identifier=row['id'];context=row.get('context_id') or self.uid('legacy-context',identifier)
  created=stamp(row['created_at']);start=stamp(row['starts_at']);end=start+timedelta(minutes=row['duration_minutes'])
  preparation={name:row.get(name) for name in ('birth_date','birth_time','birth_place','notes')}
  preparation['_legacy']=dict(birth_details=row['birth_details'],phone=row['phone'],quote_version=row.get('quote_version'),
    request_hash=row['request_hash'],cancelled_by=row.get('cancelled_by'))
  preparation['_legacy_late_reschedule_used']=row.get('late_reschedule_used',False)
  original=row.get('original_starts_at')
  if row.get('original_timing_provenance')=='legacy_baseline':
   preparation['_legacy_original_timing']={'starts_at':original,'provenance':'legacy_baseline'};original=None
  phone=row['phone'];phone=phone if re.fullmatch(r'\+[1-9][0-9]{6,14}',phone) else None
  questions=row['question_count'];amount=row['amount_paise']
  if amount%questions:raise ConversionError('legacy_question_quote_not_exact')
  service={'id':row['service_id'],'name':row['service_name'],'enabled':True,'duration_minutes':row['duration_minutes'],
    'pricing':{'kind':'per_question' if row['service_id']=='prashna-kundali' else 'fixed','amount_paise':amount//questions,
      'maximum_questions':10 if row['service_id']=='prashna-kundali' else 1},'required_preparation':[]}
  policy=deepcopy(self.bindings.business.document);policy['services']=[service];version=digest(policy)
  if not any(item['version']==version for item in self.output.get('booking_policies',[])):
   self.add('booking_policies',{'version':version,'specification':policy,'created_at':row['created_at']})
  # These synthetic private contexts do not issue a usable old browser cookie.
  if not any(item['id']==context for item in self.output.get('checkout_contexts',[])) and not any(
      item['id']==context for item in self.source('checkout_contexts')):
   self.add('checkout_contexts',dict(id=context,credential_digest=digest(['no-browser-credential',context]),
    created_at=created.isoformat(),expires_at=(created+timedelta(days=1)).isoformat(),active_checkout_id=None,
    activation_epoch=self.epoch,credential_format='v1',credential_key_id=None))
  receipt=row.get('receipt_digest');revoked=None
  if not receipt:
   receipt=digest(['unissued-historical-receipt',identifier]);revoked=self.bindings.now.isoformat()
  self.add('checkout_admissions',dict(request_id=row['request_id'],context_id=context,receipt_digest=receipt,
    request_fingerprint=row['request_hash'],outcome='committed',created_at=row['created_at'],activation_epoch=self.epoch))
  result=dict(id=identifier,request_id=row['request_id'],context_id=context,state=row['state'],service_id=row['service_id'],
    policy_version=version,service_snapshot=service|{'questions':questions,'meeting':'google_meet'},amount_paise=amount,currency=row['currency'],starts_at=start.isoformat(),
    ends_at=end.isoformat(),practice_timezone='Asia/Kolkata',full_name=row['full_name'],email=row['email'],phone=phone,
    preparation=preparation,revision=row.get('revision',1),hold_expires_at=row['hold_expires_at'],
    receipt_expires_at=row.get('receipt_expires_at') or (end+timedelta(hours=24)).isoformat(),receipt_revoked_at=revoked,
    created_at=row['created_at'],reschedule_deadline_at=row.get('late_reschedule_deadline'),activation_epoch=self.epoch,
    original_starts_at=original,receipt_format=self.bindings.format('receipt-003'),receipt_key_id=None,
    cancelled_at=row.get('cancelled_at'),provider_receipt_format='astro-order-receipt-v1',
    calendar_protocol=calendar_protocol(self.layout,self.rows,identifier,row.get('revision',1)))
  if result['original_starts_at'] is None:preparation['_legacy_original_time_unknown']=True
  self._unresolved_confirmation(result)
  self.add('bookings',result)

 def _order003(self,row):
  binding=self.bindings.payment(key_id=row['key_id'],mode=row['mode'])
  state=row['state']
  if state in ('creating','preparing'):
   state='creation_unknown' if row.get('attempted_at') else 'not_attempted'
  result=dict(booking_id=row['booking_id'],**binding,provider_order_id=row.get('order_id'),state=state,
   attempted_at=row.get('attempted_at'),resolution=row.get('resolution'),resolved_at=row.get('resolved_at'),
   resolution_actor=row.get('resolution_actor'),resolution_note=row.get('resolution_note'),
   next_check_at=row.get('next_check_at') or row.get('last_checked_at') or row['created_at'],attempts=row.get('check_attempts',0),
   recovery_followup=state=='creation_unknown',last_recovery_error=None,order_search_skip=row.get('order_search_skip',0),
   order_search_from=row.get('order_search_from'),order_search_until=row.get('order_search_until'))
  if result['attempted_at'] and result['order_search_from'] is None:
   attempted=stamp(result['attempted_at'])
   result['order_search_from']=(attempted-timedelta(minutes=5)).isoformat()
   result['order_search_until']=(attempted+timedelta(days=1)).isoformat()
  if row['booking_id'] in self.accepted:
   result['resolution']='confirmed';result['resolved_at']=self.accepted[row['booking_id']]['received_at']
  self.add('payment_orders',result)

 def _payments003(self):
  observations={}
  for row in self.source('payment_observations'):
   binding=self.bindings.payment(key_id=row['key_id']);order=self.orders.get(row.get('booking_id'))
   if order is None:raise ConversionError('legacy_payment_order_missing')
   identifier=self.uid('observation',row['key_id']+':'+row['payment_id'])
   converted=dict(id=identifier,booking_id=row['booking_id'],merchant_id=binding['merchant_id'],mode=binding['mode'],
    payment_id=row['payment_id'],provider_order_id=row['order_id'],evidence_hash=digest(row),status=row['status'],
    amount_paise=row['amount_paise'],currency=row['currency'],refunded_paise=row['amount_refunded'],
    observed_at=row['observed_at'],captured=row['status'] in ('captured','refunded'))
   self.add('payment_observations',converted);observations[(row['booking_id'],row['payment_id'])]=converted
  for row in self.source('payments'):
   order=self.orders.get(row['booking_id'])
   if order is None or not order.get('order_id'):raise ConversionError('legacy_payment_order_missing')
   binding=self.bindings.payment(key_id=order['key_id'],mode=order['mode'])
   observed=observations.get((row['booking_id'],row['payment_id']))
   if observed is None:
    observed=dict(id=self.uid('accepted-observation',row['payment_id']),booking_id=row['booking_id'],
      merchant_id=binding['merchant_id'],mode=binding['mode'],payment_id=row['payment_id'],provider_order_id=order['order_id'],
      evidence_hash=digest(row),status='captured',amount_paise=row['amount_paise'],currency=row['currency'],
      refunded_paise=0,observed_at=row['received_at'],captured=True)
    # A saved accepted/review payment is captured evidence, not a booking label.
    self.add('payment_observations',observed)
   if row['disposition']=='accepted':
    booking=self.bookings[row['booking_id']]
    if (observed['merchant_id']!=binding['merchant_id'] or observed['mode']!=binding['mode']
       or not observed['captured'] or observed['amount_paise']!=booking['amount_paise']
       or observed['currency']!=booking['currency'] or observed['provider_order_id']!=order['order_id']):
     raise ConversionError('legacy_accepted_payment_conflict')
    self.add('accepted_payments',dict(booking_id=row['booking_id'],observation_id=observed['id'],
      merchant_id=binding['merchant_id'],mode=binding['mode'],payment_id=row['payment_id']))

 def _enquiry003(self,row):
  payload={key:row[key] for key in ('name','email','phone','dob','subject','message','location','kind')}
  payload.update(request_id=row['request_id'],source=row.get('source') or ('prashna' if row['kind']=='prashna' else 'contact'),service_interest=row.get('service_interest'))
  payload['_legacy_reference']=row['id']
  receipt=row.get('receipt_digest')
  if not receipt:raise ConversionError('legacy_enquiry_receipt_missing')
  created=stamp(row['created_at'])
  self.add('enquiries',dict(request_id=row['request_id'],email_key=digest(['legacy-mailbox',payload['email']]),
    receipt_digest=receipt,request_fingerprint=row['request_hash'],payload=payload,generation=1,code_digest=None,
    code_ciphertext=None,code_expires_at=created.isoformat(),resend_after=created.isoformat(),attempts=0,
    created_at=created.isoformat(),verified_at=created.isoformat(),receipt_expires_at=row['receipt_expires_at'],
    receipt_format=self.bindings.format('enquiry-003'),receipt_key_id=None))

 def _capacity003(self):
  closures={row['id']:row for row in self.source('closures')}
  groups={}
  for row in self.source('slot_claims'):
   if 'id' in row:
    reason=closures.get(row.get('closure_id'),{}).get('reason','') if row.get('closure_id') else None
    self.add('slot_claims',dict(id=row['id'],booking_id=row.get('booking_id'),closure_reason=reason,
      starts_at=row['starts_at'],ends_at=row['ends_at'],released_at=row.get('released_at')))
   else:groups.setdefault((row.get('booking_id'),row.get('closure_id')),[]).append(stamp(row['starts_at']))
  for (booking,closure),starts in groups.items():
   intervals=[]
   for start in sorted(starts):
    if intervals and intervals[-1][1]==start:intervals[-1]=(intervals[-1][0],start+timedelta(minutes=30))
    else:intervals.append((start,start+timedelta(minutes=30)))
   if booking and len(intervals)!=1:raise ConversionError('legacy_booking_capacity_discontinuous')
   for start,end in intervals:
    reason=closures.get(closure,{}).get('reason','') if closure else None
    self.add('slot_claims',dict(id=self.uid('capacity',str(booking or closure)+':'+start.isoformat()),booking_id=booking,
      closure_reason=reason,starts_at=start.isoformat(),ends_at=end.isoformat(),released_at=None))

 def translate(self):
  # The published AstroAdvice format has no owned context or recoverable code
  # payload from which the common challenge can be reconstructed. Do not retire
  # still-valid customer authority as if it were an expired login session.
  # The read-only preview and the final fenced import enforce the same check.
  if self.layout.project=='003':
   for table in ('email_challenges','email_verifications'):
    if any(stamp(row['expires_at'])>self.bindings.now for row in self.source(table)):
     raise ConversionError('legacy_verification_continuation_required')
  # Leased old I/O must finish/reconcile before its result authority is retired.
  for records in self.rows.values():
   for row in records:
    for key in ('lease_expires_at','lease_until','refresh_lease_until'):
     if row.get(key) and stamp(row[key])>self.bindings.now:raise ConversionError('legacy_provider_lease_active')
  for qualified,rows in self.rows.items():
   schema,table=qualified.split('.');action='retained-history'
   if table in EPHEMERAL:action='retired-ephemeral-authority'
   elif schema=='booking_control' and table in HISTORICAL_CONTROL:
    self.adapter(self.bindings.history_mapper,table,rows,'legacy_control_history_binding')
    action='canonical-control-history'
   elif table in RESOURCE_TABLES:
    self.adapter(self.bindings.resource_mapper,table,rows,'legacy_resource_binding')
    action='resource-adapter'
   elif self.layout.project=='004' and table in DIRECT_004:
    for row in rows:self.add(table,self._direct(table,row))
    action='canonical-records'
   elif self.layout.project=='004' and table in ('contact_intake','intake_settings','email_policy','request_limits','receipt_recoveries'):
    if table in ('request_limits','receipt_recoveries'):
     self.adapter(self.bindings.history_mapper,table,rows,'legacy_support_history_binding')
    elif table=='email_policy':
     self.adapter(self.bindings.quota_mapper,table,rows,'legacy_quota_binding')
    # New configured intake/identity is authoritative. Spent tokens are not renewed.
    action='canonical-configuration-or-spent-authority'
   elif self.layout.project=='003' and table=='bookings':
    for row in rows:self._book003(row)
    action='canonical-records'
   elif self.layout.project=='003' and table=='payment_orders':
    for row in rows:self._order003(row)
    action='canonical-records'
   elif self.layout.project=='003' and table in ('payments','payment_observations'):action='canonical-payment-evidence'
   elif self.layout.project=='003' and table=='inquiries':
    for row in rows:self._enquiry003(row)
    action='canonical-records'
   elif self.layout.project=='003' and table in ('slot_claims','closures'):action='canonical-capacity'
   elif self.layout.project=='003' and table in ('delivery_jobs','payment_events','payment_cases','checkout_contexts'):
    self.adapter(self.bindings.transport_mapper,table,rows,'legacy_transport_binding')
    action='transport-adapter'
   elif self.layout.project=='003' and table in HISTORY_003:
    self.adapter(self.bindings.quota_mapper if table=='rate_limits' else self.bindings.history_mapper,
     table,rows,'legacy_quota_binding' if table=='rate_limits' else 'legacy_history_binding')
    action='canonical-history'
   else:raise ConversionError('legacy_table_disposition_missing')
   self.disposition[qualified]={'rows':len(rows),'action':action}
   self.comparisons[qualified]=digest(sorted((canonical(item).decode() for item in rows)))
  if self.layout.project=='003':self._payments003();self._capacity003()
  return Translation(self.layout.identifier,digest(self.comparisons),deepcopy(self.output),deepcopy(self.disposition),deepcopy(self.comparisons))
