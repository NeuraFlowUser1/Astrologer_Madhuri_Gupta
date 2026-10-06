"""Actual old encrypted formats, owner/audience boundaries and safe refresh."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import unittest
import httpx
from cryptography.fernet import Fernet
from appointment_system.google_oauth import Grant,GoogleFailure,scopes_for,RESOURCE_SCOPES,TOKEN,USERINFO
from appointment_system.google_resources import Resources,ResourceCipher
from appointment_system.serialization import canonical
from appointment_system.settings import Installation
from appointment_system.keys import encode
from tools.conversion.grants import GrantTransfer
from tools.conversion.source import catalogue,ConversionError
from .fixtures import installation
from .test_google_resources import spec,WEB,DESKTOP
from .test_keys import ring,IDENTITY

KEY=encode(b'L'*32)
NOW=datetime.now(timezone.utc)

def readers():
 base=dict(algorithm='fernet-token-json',prefix='astro003g2.',version=2,project='003',environment='production',
  purpose='calendar_refresh',role='client',keys=[KEY])
 return dict(version=1,installation_id=IDENTITY,environment='test',purpose='google-resource-grant',readers={
  'astro-calendar-bound':base,
  'astro-calendar-bare':base|dict(algorithm='fernet-token-raw',prefix='',version=1),
  **{role.replace('_','-')+'-'+kind:base|dict(prefix='astro003sheet1.',version=1,role=role,purpose=purpose)
     for role in ('client_sheet','agency_sheet') for kind,purpose in [('refresh','drive_refresh'),('secret','drive_client_secret')]}})

class HistoricalGoogleGrants(unittest.TestCase):
 def setUp(self):
  self.resources=Resources(spec(),ResourceCipher(ring(purpose='google-resource-grant'),readers()))
  self.transfer=GrantTransfer(Installation.parse(installation()),self.resources,old_keys=(KEY,),calendar_client=WEB,
   formats={'calendar-bound':'astro-calendar-bound','calendar-bare':'astro-calendar-bare',
    **{role+'-'+kind:role.replace('_','-')+'-'+kind for role in ('client_sheet','agency_sheet') for kind in ('refresh','secret')}})

 def full(self,owner_role='client',**changes):
  payload=dict(purpose='sarsa:004:google-grant:v1',client_id=WEB,role=owner_role,subject='123456789',
   email='agency@example.test' if owner_role=='agency' else 'practice@example.test',refresh_token='synthetic-refresh',
   scopes=sorted(scopes_for(owner_role)),refresh_expires_at=(NOW+timedelta(days=2)).isoformat())
  payload.update(changes)
  return dict(role=owner_role,subject='123456789',client_id=WEB,revision=7,encrypted_grant=Fernet(KEY).encrypt(canonical(payload)).decode(),
   connected_at=NOW.isoformat(),grant_expires_at=(NOW+timedelta(days=2)).isoformat(),refresh_lease=None,
   refresh_lease_until=None,refresh_revision=None)

 def calendar(self,bare=False):
  scopes=sorted(RESOURCE_SCOPES['calendar']);row=dict(singleton=True,google_subject='123456789',calendar_id='practice@example.test',
   scopes=' '.join(scopes),connected_at=NOW.isoformat())
  value=dict(version=2,project='003',environment='production',role='client',purpose='calendar_refresh',subject=row['google_subject'],
   identity=row['calendar_id'],audience=WEB,scopes=scopes,value='synthetic-refresh')
  row['refresh_token_encrypted']=Fernet(KEY).encrypt(b'synthetic-refresh').decode() if bare else 'astro003g2.'+Fernet(KEY).encrypt(canonical(value)).decode()
  return row

 def open(self,record,resource='calendar'):
  return self.resources.cipher.open(record|{'grant_id':record['id']},resource,now=NOW)

 def test_sarsa_client_permission_stays_combined_and_agency_stays_separate(self):
  for role,names in [('client',['calendar','client_sheet']),('agency',['agency_sheet'])]:
   result=self.transfer.full_grant(self.full(role));record=result['google_resource_grants'][0]
   self.assertEqual(record['resources'],names);self.assertEqual(record['revision'],7)
   self.assertIsNone(record['refresh_lease']);self.assertIsNone(record['refresh_revision'])
   self.assertEqual(self.open(record,names[0]).refresh_token,'synthetic-refresh')
   self.assertNotIn('synthetic-refresh',record['encrypted_grant']);self.assertEqual(len(result['google_resources']),len(names))

 def test_whole_grant_cannot_cross_owner_client_subject_role_scope_or_expiry(self):
  for changes in ({'purpose':'other'},{'client_id':DESKTOP},{'subject':'foreign'},{'email':'foreign@example.test'},
    {'role':'agency'},{'scopes':sorted(RESOURCE_SCOPES['calendar'])},{'scopes':['openid','openid']},
    {'refresh_expires_at':None},{'unexpected':1}):
   with self.subTest(changes=list(changes)),self.assertRaisesRegex(ConversionError,'resource_cipher_invalid'):
    self.transfer.full_grant(self.full(**changes))
  transfer=GrantTransfer(Installation.parse(installation()),self.resources)
  with self.assertRaisesRegex(ConversionError,'keys_missing'):transfer.full_grant(self.full())
  row=self.full();row['encrypted_grant']='invalid'
  with self.assertRaisesRegex(ConversionError,'resource_cipher_invalid'):self.transfer.full_grant(row)

 def test_bound_calendar_record_is_reencrypted_with_same_owner_client_scope_and_subject(self):
  record=self.transfer.calendar(self.calendar())['google_resource_grants'][0]
  self.assertEqual(record['grant_format'],'v1');self.assertEqual(record['resources'],['calendar'])
  grant=self.open(record);self.assertEqual(grant.subject,'123456789');self.assertEqual(grant.scopes,RESOURCE_SCOPES['calendar'])
  row=self.calendar();row['calendar_id']='agency@example.test'
  with self.assertRaisesRegex(ConversionError,'owner_unregistered'):self.transfer.calendar(row)
  row=self.calendar();row['google_subject']='wrong'
  with self.assertRaisesRegex(ConversionError,'cipher_invalid'):self.transfer.calendar(row)

 def test_bare_calendar_token_remains_unverified_until_actual_refresh_checks_its_owner(self):
  row=self.calendar(bare=True);record=self.transfer.calendar(row)['google_resource_grants'][0]
  self.assertEqual(record['encrypted_grant'],row['refresh_token_encrypted'])
  self.assertEqual(record['grant_format'],'astro-calendar-bare')
  self.assertEqual(record['last_error_code'],'legacy_owner_verification_required')
  grant=self.open(record);calls=[]
  def wrong_owner(request):
   calls.append(str(request.url))
   if str(request.url)==TOKEN:return httpx.Response(200,json={'access_token':'synthetic-access','token_type':'Bearer','expires_in':3600})
   return httpx.Response(200,json={'sub':'foreign','email':'foreign@example.test','email_verified':True})
  self.resources.transport=httpx.MockTransport(wrong_owner)
  with self.assertRaisesRegex(GoogleFailure,'account_mismatch'):
   self.resources.provider('calendar').refresh(grant,now=NOW)
  self.assertEqual(calls,[TOKEN,USERINFO])

 def test_desktop_sheet_client_secret_and_literal_grant_audience_are_preserved(self):
  row=dict(role='client_sheet',owner_email='practice@example.test',subject='123456789',client_id=DESKTOP,
   scopes='https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets',revision=3,connected_at=NOW.isoformat())
  base=dict(version=1,project='003',environment='production',role=row['role'],subject=row['subject'],identity=row['owner_email'],
   audience=DESKTOP,scopes=sorted(row['scopes'].split()))
  row['refresh_encrypted']='astro003sheet1.'+Fernet(KEY).encrypt(canonical(base|dict(purpose='drive_refresh',value='synthetic-refresh'))).decode()
  row['client_secret_encrypted']='astro003sheet1.'+Fernet(KEY).encrypt(canonical(base|dict(purpose='drive_client_secret',value='retained-secret'))).decode()
  record=self.transfer.sheet(row)['google_resource_grants'][0]
  self.assertEqual(record['client_id'],DESKTOP);self.assertEqual(self.open(record,'client_sheet').scopes,frozenset(row['scopes'].split()))
  changed=deepcopy(row);changed['client_id']=WEB
  with self.assertRaisesRegex(ConversionError,'cipher_invalid'):self.transfer.sheet(changed)

 def test_unregistered_table_layout_owner_or_reader_cannot_be_discovered_implicitly(self):
  layouts={item.identifier:item for item in catalogue()}
  with self.assertRaisesRegex(ConversionError,'table_unprepared'):self.transfer(layouts['legacy-003-16'],'sheet_rows',[{}])
  with self.assertRaisesRegex(ConversionError,'layout_mismatch'):self.transfer(layouts['legacy-003-16'],'google_connections',[self.full()])
  self.assertEqual(len(self.transfer(layouts['legacy-004-31'],'google_connections',[self.full()])['google_resources']),2)
  no_reader=GrantTransfer(Installation.parse(installation()),self.resources,calendar_client=WEB)
  with self.assertRaisesRegex(ConversionError,'reader_missing'):no_reader.calendar(self.calendar(bare=True))

 def test_invalid_historical_key_or_owner_binding_cannot_create_resource_access(self):
  for keys in [('invalid',),(KEY,KEY),[KEY]]:
   with self.assertRaisesRegex(ConversionError,'configuration_invalid'):GrantTransfer(Installation.parse(installation()),self.resources,old_keys=keys)
  with self.assertRaisesRegex(ConversionError,'client_unregistered'):self.transfer.binding(('calendar',),'unregistered','practice@example.test')
  for names,owner in [(('unknown_resource',),'practice@example.test'),(('calendar',),'foreign@example.test')]:
   with self.assertRaisesRegex(ConversionError,'owner_unregistered'):self.transfer.binding(names,WEB,owner)
  grant=Grant('client','123456789','practice@example.test','synthetic-refresh',RESOURCE_SCOPES['calendar'],None,('calendar',))
  for revision in [0,True,'1',None]:
   with self.assertRaisesRegex(ConversionError,'revision_invalid'):self.transfer.result(grant,WEB,{'revision':revision},'synthetic')
  with self.assertRaisesRegex(ConversionError,'owner_unregistered'):self.transfer.sheet({'role':'calendar'})
  layout=next(item for item in catalogue() if item.identifier=='legacy-004-31')
  self.assertEqual(self.transfer(layout,'google_connections',[]),{})
