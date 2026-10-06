"""Preserve attempted mail exactly; conversion never calls a sending provider."""
from copy import deepcopy
from dataclasses import dataclass,field
import hmac,re
from types import MappingProxyType
from uuid import UUID
from appointment_system.contact import ContactSecrets
from appointment_system.contact_messages import seal_message
from appointment_system.email_configuration import EmailConnection
from appointment_system.email_messages import message_hash
from appointment_system.mail_identity import retained_key
from appointment_system.errors import Rejected
from .source import ConversionError,canonical

PROJECTS={'003':'003-astroadvice-by-kundan-singh','004':'sarsa004'}
FORMATS={'003':'resend-legacy-job-v1','004':'resend-legacy-flat-job-v1'}

@dataclass(frozen=True,repr=False)
class MailTransfer:
 connection:EmailConnection=field(repr=False)
 key_versions:object=field(repr=False)
 contact:object=field(default=None,repr=False)
 contact_formats:object=field(default=None,repr=False)

 def __post_init__(self):
  if (not isinstance(self.connection,EmailConnection) or type(self.key_versions) is not dict
      or not self.key_versions or set(self.key_versions)-set(PROJECTS)):
   raise ConversionError('legacy_mail_reader_invalid')
  for project,version in self.key_versions.items():
   try:
    self.connection.pinned(version)
    if self.connection.identity(FORMATS[project]).project!=PROJECTS[project]:raise ValueError()
   except (ValueError,TypeError):raise ConversionError('legacy_mail_reader_invalid') from None
  formats=self.contact_formats or {}
  if (type(formats) is not dict or set(formats)-{'004'} or
      any(type(value) is not tuple or len(value)!=2 or
       any(type(name) is not str or name=='v1' or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',name) for name in value)
       for value in formats.values()) or self.contact is not None and not isinstance(self.contact,ContactSecrets)):
   raise ConversionError('legacy_mail_reader_invalid')
  if formats and (self.contact is None or any(value[0] not in self.contact.cipher.readers or
      value[1] not in {item[0] for item in self.contact.legacy_digests} for value in formats.values())):
   raise ConversionError('legacy_mail_reader_invalid')
  object.__setattr__(self,'key_versions',MappingProxyType(deepcopy(self.key_versions)))
  object.__setattr__(self,'contact_formats',MappingProxyType(deepcopy(formats)))

 def _encrypted004(self,row):
  try:
   cipher_format,digest_format=self.contact_formats['004']
   value,raw=self.contact.cipher.read(self.contact.record('message',row['id']),row['message_ciphertext'],
      format=cipher_format,purpose='appointment:v1:enquiry-message')
   expected=self.contact.digest('message',raw.decode(),format=digest_format)
   if (set(value)!={'purpose','job_id','payload'} or value['purpose']!='sarsa004-contact-message-v1'
       or value['job_id']!=str(UUID(row['id'])) or not hmac.compare_digest(expected,row['message_digest'])):raise ValueError()
   return value['payload']
  except (Rejected,KeyError,ValueError,TypeError,UnicodeError):raise ConversionError('legacy_mail_snapshot_invalid') from None

 def __call__(self,layout,table,original):
  if (layout.project not in self.key_versions or table not in ('delivery_jobs','enquiry_delivery_jobs')
      or type(original) is not dict):raise ConversionError('legacy_mail_reader_unprepared')
  row=deepcopy(original);project=layout.project
  try:
   identifier=str(UUID(row['id']));identity=self.connection.identity(FORMATS[project])
   if identifier!=row['id']:raise ValueError()
   key=row.get('mail_idempotency_key')
   if key is None and project=='004':key='sarsa004/'+identifier
   if key is None and project=='003':
    kind=row.get('mail_key_kind');role=row.get('mail_key_role');version=row['template_version']
    if type(version) is not int or not 1<=version<=9999:raise ValueError()
    key=('inquiry/'+identifier+'/v'+str(version) if table=='enquiry_delivery_jobs' else
         'booking/'+str(UUID(row['booking_id']))+'/'+kind+'/'+role+'/v'+str(version))
   key=retained_key(key,identifier,identity,booking_id=row.get('booking_id'),
                    kind=row.get('mail_key_kind'),role=row.get('mail_key_role'))
   body=row.get('message_snapshot')
   if table=='enquiry_delivery_jobs' and row.get('message_ciphertext') is not None:
    if project!='004' or self.contact is None:raise ValueError()
    body=self._encrypted004(row)
   if body is not None and 'tags' not in body:
    if project!='003':raise ValueError()
    identity=self.connection.identity('resend-legacy-untagged-job-v1')
    if identity.project!=PROJECTS[project]:raise ValueError()
    retained_key(key,identifier,identity,booking_id=row.get('booking_id'),
                 kind=row.get('mail_key_kind'),role=row.get('mail_key_role'))
   row.update(mail_account_id=self.connection.account_id,mail_event_account_id=identity.event_account_id,
     mail_credential_version=self.key_versions[project],mail_format=identity.format,mail_idempotency_key=key)
   if body is None:
    # Definite completed evidence may remain after approved old ciphertext
    # erasure. An unresolved attempt without its saved body must never resend.
    if row['state'] not in ('completed','suppressed'):
     row['state']='needs_review';row['last_error_code']='legacy_mail_snapshot_unavailable'
    return row
   fields={'from','to','reply_to','subject','text','html'}
   if identity.format!='resend-legacy-untagged-job-v1':fields.add('tags')
   if (type(body) is not dict or set(body)!=fields or not identity.accepts(body,identifier)
       or type(body['to']) is not list or body['to']!=[row['destination']]
       or any(type(body[name]) is not str or not body[name] for name in ('subject','text','html','reply_to'))
       or len(canonical(body))>16384):raise ValueError()
   binding=identity.binding(body.get('tags'))
   if binding is not None and binding[1] is not None and binding[1]!=str(row['template_version']):raise ValueError()
   practice=table=='enquiry_delivery_jobs' and row['kind']=='practice_notice'
   expected_reply=(row['payload']['email'] if practice and (project=='003' or row['template_version']>=2)
                   else identity.reply_to)
   if (body['reply_to']!=expected_reply or
       practice and body['to']!=[identity.reply_to]):raise ValueError()
   if table=='delivery_jobs':
    saved=row.get('message_hash');expected=message_hash(body)
    if saved is not None and not hmac.compare_digest(saved,expected):raise ValueError()
    row['message_snapshot']=body;row['message_hash']=expected
   else:
    if self.contact is None:raise ValueError()
    row['message_ciphertext'],row['message_digest']=seal_message(self.contact,row,body)
    row['message_format']='v1';row['message_digest_format']='v1'
    row.pop('message_snapshot',None)
   return row
  except ConversionError:raise
  except (KeyError,ValueError,TypeError,AttributeError):raise ConversionError('legacy_mail_snapshot_invalid') from None
