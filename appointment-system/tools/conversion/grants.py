"""Exact historical Google permission readers used only during handover.

Bound records become the current resource envelope. An older bare token stays
in its explicitly registered old format until the common refresh verifies its
actual owner and commits a bound replacement. No access cache/session moves.
"""
from copy import deepcopy
from cryptography.fernet import Fernet,MultiFernet,InvalidToken
from appointment_system.google_resources import Resources,normalized_scopes
from appointment_system.google_oauth import Grant,RESOURCE_ROLES,GoogleFailure
from appointment_system.errors import Rejected
from appointment_system.serialization import decode
from appointment_system.keys import material
from appointment_system.settings import Installation
from .source import ConversionError
from .records import private_reference,stamp

class GrantTransfer:
 def __init__(self,installation,resources,*,old_keys=(),calendar_client=None,formats=None,calendar_reauthorization=False):
  if (not isinstance(installation,Installation) or not isinstance(resources,Resources) or resources.cipher.ring.installation_id!=installation.installation_id
      or resources.cipher.ring.environment!=installation.document['environment'] or type(old_keys) is not tuple
      or len(old_keys)>8 or len(set(old_keys))!=len(old_keys) or type(formats or {}) is not dict
      or type(calendar_reauthorization) is not bool
      or calendar_reauthorization and (old_keys or formats)):
   raise ConversionError('legacy_resource_configuration_invalid')
  try:
   for key in old_keys:material(key,32)
   self.crypt=MultiFernet([Fernet(key) for key in old_keys]) if old_keys else None
  except (ValueError,TypeError,Rejected):raise ConversionError('legacy_resource_configuration_invalid') from None
  self.installation=installation;self.resources=resources;self.calendar_client=calendar_client;self.formats=deepcopy(formats or {})
  self.calendar_reauthorization=calendar_reauthorization

 def binding(self,names,client,owner):
  if client not in self.resources.clients:raise ConversionError('legacy_resource_client_unregistered')
  for name in names:
   spec=self.resources.resources.get(name)
   if spec is None or owner!=spec.owner_email or client not in spec.retained_clients:
    raise ConversionError('legacy_resource_owner_unregistered')

 def identifier(self,kind,value):return private_reference(self.installation.installation_id,kind,value)

 def result(self,grant,client,row,source,*,encrypted=None,format='v1',unverified=False):
  self.binding(grant.resources,client,grant.email)
  revision=row.get('revision',1)
  if type(revision) is not int or revision<1:raise ConversionError('legacy_resource_revision_invalid')
  identifier=self.identifier('legacy-google-grant',source+':'+grant.role+':'+client+':'+grant.subject+':'+str(revision))
  record=dict(id=identifier,owner_role=grant.role,owner_email=grant.email,subject=grant.subject,client_id=client,
   resources=list(grant.resources),scopes=sorted(grant.scopes),encrypted_grant=encrypted or self.resources.cipher.seal(identifier,client,grant),
   grant_format=format,revision=revision,grant_expires_at=grant.refresh_expires_at.isoformat() if grant.refresh_expires_at else None,
   connected_at=row['connected_at'],revoked_at=None,refresh_lease=None,refresh_lease_until=None,refresh_revision=None,
   last_error_code='legacy_owner_verification_required' if unverified else row.get('last_error_code'))
  bindings=[]
  for name in grant.resources:
   spec=self.resources.resources[name]
   bindings.append(dict(resource=name,owner_email=spec.owner_email,active_client=spec.active_client,
    retained_clients=list(spec.retained_clients),grant_id=identifier,revision=revision,updated_at=row['connected_at']))
  return {'google_resource_grants':[record],'google_resources':bindings}

 def full_grant(self,row):
  if self.crypt is None:raise ConversionError('legacy_resource_keys_missing')
  try:
   value=decode(self.crypt.decrypt(row['encrypted_grant'].encode()))
   if (set(value)!={'purpose','client_id','role','subject','email','refresh_token','scopes','refresh_expires_at'}
       or value['purpose']!='sarsa:004:google-grant:v1' or value['client_id']!=row['client_id']
       or value['role']!=row['role'] or value['subject']!=row['subject']):raise ValueError()
   owner=self.installation.document['owners']['agency_email' if row['role']=='agency' else 'client_email']
   if row['role'] not in ('client','agency') or value['email']!=owner:raise ValueError()
   names=('agency_sheet',) if row['role']=='agency' else ('calendar','client_sheet')
   expiry=stamp(value['refresh_expires_at']) if value['refresh_expires_at'] else None
   if (stamp(row['grant_expires_at']) if row['grant_expires_at'] else None)!=expiry:raise ValueError()
   grant=Grant(row['role'],row['subject'],owner,value['refresh_token'],normalized_scopes(value['scopes']),expiry,names)
   return self.result(grant,row['client_id'],row,'sarsa-google-grant-v1')
  except (InvalidToken,KeyError,ValueError,TypeError,UnicodeError,GoogleFailure,Rejected):
   raise ConversionError('legacy_resource_cipher_invalid') from None

 def calendar(self,row):
  client=self.calendar_client;owner=self.installation.document['owners']['client_email']
  if row['calendar_id']!=owner:raise ConversionError('legacy_resource_owner_unregistered')
  names=('calendar',);self.binding(names,client,owner)
  scopes=row['scopes'].split();normalized=normalized_scopes(scopes)
  if self.calendar_reauthorization:return self.pending_calendar(row,client,owner,normalized)
  format=self.formats.get('calendar-bound' if row['refresh_token_encrypted'].startswith('astro003g2.') else 'calendar-bare')
  if format is None:raise ConversionError('legacy_resource_reader_missing')
  saved=dict(subject=row['google_subject'],owner_email=owner,client_id=client,scopes=sorted(scopes))
  try:
   token=self.resources.cipher.legacy_value(saved,row['refresh_token_encrypted'],format)
   grant=Grant('client',row['google_subject'],owner,token,normalized,None,names)
   unverified=not row['refresh_token_encrypted'].startswith('astro003g2.')
   return self.result(grant,client,row,'astro-calendar',encrypted=row['refresh_token_encrypted'] if unverified else None,
    format=format if unverified else 'v1',unverified=unverified)
  except (GoogleFailure,Rejected,ValueError,TypeError,KeyError):raise ConversionError('legacy_resource_cipher_invalid') from None

 def pending_calendar(self,row,client,owner,scopes):
  """Keep historical identity, never pretend an unreadable token is usable.

  Only explicit published-source handover selects this disposition. The normal
  resource consent flow pins the retained subject and replaces the binding after
  verified owner approval. No provider request or decryption is attempted here.
  """
  from .reauthorization import pending_calendar
  return pending_calendar(self,row,client,owner,scopes)

 def sheet(self,row):
  name=row['role'];role=RESOURCE_ROLES.get(name)
  if name not in ('client_sheet','agency_sheet'):raise ConversionError('legacy_resource_owner_unregistered')
  self.binding((name,),row['client_id'],row['owner_email'])
  saved=dict(subject=row['subject'],owner_email=row['owner_email'],client_id=row['client_id'],scopes=sorted(row['scopes'].split()))
  try:
   format=self.formats[name+'-refresh'];secret_format=self.formats[name+'-secret']
   refresh=self.resources.cipher.legacy_value(saved,row['refresh_encrypted'],format)
   secret=self.resources.cipher.legacy_value(saved,row['client_secret_encrypted'],secret_format)
   if secret!=self.resources.clients[row['client_id']].secret:raise ValueError()
   grant=Grant(role,row['subject'],row['owner_email'],refresh,normalized_scopes(saved['scopes']),None,(name,))
   return self.result(grant,row['client_id'],row,'astro-owner-sheet')
  except (GoogleFailure,Rejected,ValueError,TypeError,KeyError):raise ConversionError('legacy_resource_cipher_invalid') from None

 def __call__(self,layout,table,rows,source=None):
  if self.calendar_reauthorization and (layout.identifier!='legacy-003-16' or table!='google_connection'):
   raise ConversionError('legacy_resource_reauthorization_layout_invalid')
  reader={'google_connections':self.full_grant,'google_connection':self.calendar,'sheet_owner_grants':self.sheet}.get(table)
  if reader is None:raise ConversionError('legacy_resource_table_unprepared')
  if ((table=='google_connections')!=(layout.project=='004')):raise ConversionError('legacy_resource_layout_mismatch')
  result={}
  for row in rows:
   for target,records in reader(deepcopy(row)).items():result.setdefault(target,[]).extend(records)
  return result
