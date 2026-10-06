"""Saved owner, client, scope and resource boundaries, with no live requests."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import unittest
import httpx
from cryptography.fernet import Fernet
from appointment_system.errors import Rejected
from appointment_system.google_oauth import Grant,Attempt,GoogleFailure,RESOURCE_SCOPES,FILE_SCOPE,SHEET_SCOPE,TOKEN,USERINFO,DRIVE_IDENTITY,scopes_for
from appointment_system.google_resources import Resources,ResourceCipher,normalized_scopes
from appointment_system.keys import encode
from appointment_system.serialization import canonical
from .test_keys import ring,IDENTITY

WEB='123456789-syntheticclient.apps.googleusercontent.com'
DESKTOP='987654321-syntheticdesktop.apps.googleusercontent.com'
NOW=datetime.now(timezone.utc)

def cipher(legacy=None):return ResourceCipher(ring(purpose='google-resource-grant'),legacy)

def spec():
    return dict(version=1,installation_id=IDENTITY,environment='test',purpose='google-resource-connections',
      clients=[dict(client_id=WEB,client_secret='synthetic-secret',kind='web'),dict(client_id=DESKTOP,client_secret='retained-secret',kind='desktop')],
      resources={name:dict(owner_email='agency@example.test' if name=='agency_sheet' else 'practice@example.test',
       active_client=WEB,retained_clients=[WEB,DESKTOP]) for name in RESOURCE_SCOPES})

def saved(resource='calendar',scopes=None,client=WEB,resources=None):
    resources=tuple(resources or (resource,));role='agency' if resource=='agency_sheet' else 'client'
    grant=Grant(role,'123456789','agency@example.test' if role=='agency' else 'practice@example.test','synthetic-refresh',
      scopes or RESOURCE_SCOPES[resource],NOW+timedelta(days=3),resources)
    identifier=str(uuid4())
    return grant,dict(grant_id=identifier,client_id=client,resources=list(resources),owner_email=grant.email,
      subject=grant.subject,scopes=sorted(grant.scopes),grant_format='v1',encrypted_grant=cipher().seal(identifier,client,grant))

class ResourceTests(unittest.TestCase):
    def test_current_resource_cipher_binds_all_saved_metadata(self):
        grant,row=saved();self.assertEqual(cipher().open(row,'calendar',now=NOW),grant)
        for field,value in [('grant_id',str(uuid4())),('client_id',DESKTOP),('owner_email','agency@example.test'),
                            ('subject','different'),('resources',['client_sheet']),('scopes',sorted(RESOURCE_SCOPES['client_sheet']))]:
            changed=deepcopy(row);changed[field]=value
            with self.subTest(field=field),self.assertRaises(GoogleFailure):cipher().open(changed,'calendar',now=NOW)
        with self.assertRaises(GoogleFailure):cipher().open(row,'client_sheet',now=NOW)
        with self.assertRaises(GoogleFailure):cipher().open(row,'calendar',now=NOW+timedelta(days=4))

    def test_shared_old_grant_is_exactly_calendar_and_client_sheet(self):
        grant,row=saved(resources=['calendar','client_sheet'],scopes=scopes_for('client'))
        for resource in ('calendar','client_sheet'):self.assertEqual(cipher().open(row,resource,now=NOW),grant)
        with self.assertRaises(GoogleFailure):cipher().open(row,'agency_sheet',now=NOW)
        with self.assertRaises(GoogleFailure):Grant('client','123456789','practice@example.test','refresh',
             RESOURCE_SCOPES['calendar'],None,('calendar','client_sheet'))

    def test_registry_uses_selected_client_and_never_exposes_its_secret(self):
        registry=Resources(spec(),cipher())
        self.assertEqual(registry.provider('client_sheet',client_id=DESKTOP).settings.client_id,DESKTOP)
        self.assertEqual(registry.provider('calendar').resource,'calendar')
        self.assertNotIn('secret',repr(registry.metadata()))
        for name,client in [('missing',WEB),('client_sheet','111-other.apps.googleusercontent.com')]:
            with self.assertRaises(GoogleFailure):registry.provider(name,client_id=client)

    def test_registry_rejects_owner_client_shape_and_scope_ambiguity(self):
        for field,value in [('owner_email','agency@example.test'),('active_client',DESKTOP),('retained_clients',[{}]),
                            ('retained_clients',[WEB,WEB]),('retained_clients',[]),('active_client','missing')]:
            document=spec();document['resources']['calendar'][field]=value
            with self.subTest(field=field),self.assertRaises((Rejected,GoogleFailure)):Resources(document,cipher())
        for scopes in [[],['email','https://www.googleapis.com/auth/userinfo.email'],[False],['email','email']]:
            with self.assertRaises(Rejected):normalized_scopes(scopes)

    def test_retained_astro_sheet_reader_keeps_desktop_audience_and_literal_scopes(self):
        key=encode(b'L'*32);prefix='astro003sheet1.'
        legacy=dict(version=1,installation_id=IDENTITY,environment='test',purpose='google-resource-grant',
          readers={'astro-sheet':dict(algorithm='fernet-token-json',prefix=prefix,version=1,project='003',environment='production',
              purpose='drive_refresh',role='client_sheet',keys=[key])})
        scopes=sorted([FILE_SCOPE,SHEET_SCOPE]);row=dict(grant_id=str(uuid4()),client_id=DESKTOP,resources=['client_sheet'],
          owner_email='practice@example.test',subject='123456789',scopes=scopes,grant_format='astro-sheet',grant_expires_at=None)
        payload=dict(version=1,project='003',environment='production',role='client_sheet',purpose='drive_refresh',subject=row['subject'],
            identity=row['owner_email'],audience=DESKTOP,scopes=scopes,value='synthetic-refresh')
        row['encrypted_grant']=prefix+Fernet(key).encrypt(canonical(payload)).decode()
        opened=cipher(legacy).open(row,'client_sheet',now=NOW);self.assertEqual(opened.scopes,frozenset(scopes))
        for field,value in [('client_id',WEB),('subject','other'),('grant_format','missing')]:
            changed=row|{field:value}
            with self.assertRaises(GoogleFailure):cipher(legacy).open(changed,'client_sheet',now=NOW)
        legacy['readers']['astro-sheet']['purpose']='drive_client_secret'
        with self.assertRaises(GoogleFailure):cipher(legacy).open(row,'client_sheet',now=NOW)

    def test_retained_desktop_refresh_verifies_owner_via_drive_without_adding_scopes(self):
        calls=[]
        def provider(request):
            calls.append((request.method,str(request.url)))
            if str(request.url)==TOKEN:return httpx.Response(200,json={'access_token':'synthetic-access','token_type':'Bearer','expires_in':3600})
            self.assertEqual(request.url.path,'/drive/v3/about');self.assertEqual(request.url.params['fields'],'user(emailAddress)')
            return httpx.Response(200,json={'user':{'emailAddress':'practice@example.test'}})
        registry=Resources(spec(),cipher(),transport=httpx.MockTransport(provider))
        grant,_=saved('client_sheet',frozenset([FILE_SCOPE,SHEET_SCOPE]),DESKTOP)
        access=registry.provider('client_sheet',client_id=DESKTOP).refresh(grant,now=NOW)
        self.assertEqual(access.grant.scopes,grant.scopes);self.assertEqual(len(calls),2)
        self.assertNotIn(USERINFO,[url for _,url in calls])

    def test_invalid_grant_requests_reconnection_and_wrong_owner_never_releases_access(self):
        grant,_=saved()
        registry=Resources(spec(),cipher(),transport=httpx.MockTransport(lambda request:httpx.Response(400,json={'error':'invalid_grant'})))
        with self.assertRaisesRegex(GoogleFailure,'reconnect'):registry.provider('calendar').refresh(grant,now=NOW)
        def provider(request):
            if str(request.url)==TOKEN:return httpx.Response(200,json={'access_token':'synthetic-access','token_type':'Bearer','expires_in':3600})
            return httpx.Response(200,json={'sub':'123456789','email':'wrong@example.test','email_verified':True})
        registry=Resources(spec(),cipher(),transport=httpx.MockTransport(provider))
        with self.assertRaisesRegex(GoogleFailure,'account'):registry.provider('calendar').refresh(grant,now=NOW)

    def test_returned_permission_changes_and_cross_resource_refresh_are_refused(self):
        grant,_=saved()
        registry=Resources(spec(),cipher(),transport=httpx.MockTransport(lambda request:httpx.Response(200,json={
           'access_token':'synthetic-access','token_type':'Bearer','expires_in':3600,'scope':' '.join(sorted(RESOURCE_SCOPES['client_sheet']))})))
        with self.assertRaisesRegex(GoogleFailure,'permissions'):registry.provider('calendar').refresh(grant,now=NOW)
        with self.assertRaisesRegex(GoogleFailure,'resource'):registry.provider('client_sheet').refresh(grant,now=NOW)

    def test_configuration_cannot_cross_installations_or_replace_keys_with_another_purpose(self):
        for change in ({'installation_id':str(uuid4())},{'environment':'production'},
                       {'clients':[]},{'resources':{}},{'clients':[spec()['clients'][0]]*2}):
            with self.subTest(fields=list(change)),self.assertRaises((Rejected,GoogleFailure)):
                Resources(spec()|change,cipher())
        with self.assertRaises(Rejected):Resources(spec(),object())
        with self.assertRaises(Rejected):ResourceCipher(ring(purpose='receipt'))

    def test_consent_envelope_cannot_be_swapped_between_resource_client_state_or_operation(self):
        encrypted=cipher();attempt=Attempt.new('client');identifier=str(uuid4())
        row=dict(id=identifier,resource='calendar',client_id=WEB,
                 encrypted_attempt=encrypted.seal_attempt(identifier,'calendar',WEB,attempt))
        self.assertEqual(encrypted.open_attempt(row,attempt.state),attempt)
        for change in ({'id':str(uuid4())},{'resource':'client_sheet'},{'client_id':DESKTOP},{'encrypted_attempt':'corrupt'}):
            with self.subTest(fields=list(change)),self.assertRaises(GoogleFailure):
                encrypted.open_attempt(row|change,attempt.state)
        with self.assertRaises(GoogleFailure):encrypted.open_attempt(row,Attempt.new('client').state)
        for resource,client,value in [('calendar',WEB,Attempt.new('agency')),('unknown',WEB,attempt),('calendar','bad-client',attempt),('calendar',WEB,None)]:
            with self.subTest(resource=resource,client=client),self.assertRaises(GoogleFailure):
                encrypted.seal_attempt(identifier,resource,client,value)

    def test_legacy_reader_rejects_ambiguous_keys_purpose_and_envelope_identity(self):
        key=encode(b'L'*32)
        definition=dict(algorithm='fernet-token-raw',prefix='',version=1,project='003',environment='production',
                        purpose='calendar_refresh',role='client',keys=[key])
        legacy=dict(version=1,installation_id=IDENTITY,environment='test',purpose='google-resource-grant',readers={'old':definition})
        for change in ({'installation_id':str(uuid4())},{'environment':'production'},{'readers':[]},{'purpose':'other'}):
            with self.subTest(fields=list(change)),self.assertRaises(Rejected):cipher(legacy|change)
        for change in ({'keys':[key,key]},{'purpose':'drive_refresh'},{'prefix':'unexpected.'},{'version':True},{'role':'agency_sheet'}):
            with self.subTest(fields=list(change)),self.assertRaises(Rejected):cipher(legacy|{'readers':{'old':definition|change}})
        reader=cipher(legacy)
        for token in (b'',b'secret with spaces',b'\xff',b'a'*8193):
            with self.subTest(size=len(token)),self.assertRaises(GoogleFailure):
                reader.legacy_value({},Fernet(key).encrypt(token).decode(),'old')
        for token,format in (('x'*32769,'old'),('corrupt','old'),('corrupt','missing')):
            with self.subTest(format=format),self.assertRaises(GoogleFailure):reader.legacy_value({},token,format)
