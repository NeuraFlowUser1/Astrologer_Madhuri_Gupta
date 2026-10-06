"""New Google and staff formats, explicit retained readers and authority bounds."""
import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from cryptography.fernet import Fernet
from appointment_system.google_oauth import Attempt,Grant,GrantCipher,GoogleFailure,OAuthSettings,scopes_for
from appointment_system.keys import encode
from appointment_system.serialization import canonical
from appointment_system.studio import StudioServices
from appointment_system.access import AccessDenied
from .test_keys import ring,document,IDENTITY

CLIENT='123456789-syntheticclient.apps.googleusercontent.com'
NOW=datetime.now(timezone.utc)

def grant():
    return Grant('client','123456789','practice@example.test','synthetic-refresh',scopes_for('client'),NOW+timedelta(days=3))

def cipher(spec=None,legacy=None):
    return GrantCipher(CLIENT,ring(spec,purpose='google-grant'),legacy)

class GoogleCredentialTests(unittest.TestCase):
    def test_new_grant_opens_after_rotation_and_keeps_original_expiry(self):
        spec=document(purpose='google-grant');spec['active']='k1'
        protected=cipher(spec).seal(grant())
        reopened=cipher().open(protected,role='client',subject='123456789',now=NOW)
        self.assertEqual(reopened,grant());self.assertNotIn('synthetic-refresh',protected)
        with self.assertRaisesRegex(GoogleFailure,'reconnect'):
            cipher().open(protected,role='client',subject='123456789',now=NOW+timedelta(days=4))

    def test_installation_record_role_subject_and_purpose_cannot_be_swapped(self):
        original=cipher().seal(grant())
        for role,subject in [('agency','123456789'),('client','other')]:
            with self.subTest(role=role,subject=subject),self.assertRaises(GoogleFailure):
                cipher().open(original,role=role,subject=subject,now=NOW)
        envelope=json.loads(original[3:]);envelope['purpose']='staff-session'
        with self.assertRaises(GoogleFailure):
            cipher().open('g1.'+canonical(envelope).decode(),role='client',subject='123456789',now=NOW)
        with self.assertRaises(GoogleFailure):GrantCipher(CLIENT,ring())

    def test_attempt_is_bound_to_flow_role_and_state(self):
        attempt=Attempt.new('client');protected=cipher().seal_attempt(attempt,'signin')
        self.assertEqual(cipher().open_attempt(protected,state=attempt.state,role='client',purpose='signin'),attempt)
        for changes in [{'state':'x'*43},{'role':'agency'},{'purpose':'connect'}]:
            values=dict(state=attempt.state,role='client',purpose='signin');values.update(changes)
            with self.subTest(changes=changes),self.assertRaises(GoogleFailure):cipher().open_attempt(protected,**values)
        with self.assertRaises(GoogleFailure):cipher().seal_attempt(attempt,'not-approved')

    def test_old_ciphertext_requires_its_declared_reader_and_exact_old_purpose(self):
        key=encode(b'L'*32);f=Fernet(key)
        old={'version':1,'installation_id':IDENTITY,'environment':'test','purpose':'google-grant',
             'readers':{'old-format':{'algorithm':'fernet-json','keys':[key],
                 'grant_purpose':'historical:google-grant:v1','attempt_purpose':'historical:google-attempt:v1'}}}
        value=grant();payload=dict(purpose='historical:google-grant:v1',client_id=CLIENT,
            role=value.role,subject=value.subject,email=value.email,refresh_token=value.refresh_token,
            scopes=sorted(value.scopes),refresh_expires_at=value.refresh_expires_at.isoformat())
        encrypted=f.encrypt(canonical(payload)).decode()
        opened=cipher(legacy=old).open(encrypted,role=value.role,subject=value.subject,now=NOW,format='old-format')
        self.assertEqual(opened,value)
        with self.assertRaises(GoogleFailure):cipher(legacy=old).open(encrypted,role=value.role,subject=value.subject,now=NOW)
        payload['purpose']='another-product'
        with self.assertRaises(GoogleFailure):cipher(legacy=old).open(f.encrypt(canonical(payload)).decode(),
                role=value.role,subject=value.subject,now=NOW,format='old-format')

    def test_envelope_ambiguity_and_missing_reader_do_not_fall_back(self):
        token=cipher().seal(grant())
        for changed in ('bad','g1.{}',token[:-1]+',"version":1}',token):
            with self.assertRaises(GoogleFailure):cipher().open(changed,role='client',subject='123456789',now=NOW,format='missing')
        with self.assertRaises(GoogleFailure):cipher().open(token[:-1]+',"version":1}',role='client',subject='123456789',now=NOW)

    def test_staff_tokens_survive_retained_key_rotation_and_never_become_company_tokens(self):
        class Google:
            settings=OAuthSettings(CLIENT,'synthetic-client-secret','https://practice.example.test')
        spec=document(purpose='staff-session');spec['active']='k1'
        first=StudioServices(Google(),None,ring(spec,purpose='staff-session'))
        token=first.issue('session');digest=first.digest('session',token)
        current=StudioServices(Google(),None,ring(purpose='staff-session'))
        self.assertEqual(current.digest('session',token),digest)
        self.assertNotEqual(current.digest('csrf',token),digest)
        state=current.attempt('client');self.assertTrue(state.state.startswith('a1.k2.'))
        self.assertEqual(cipher().open_attempt(cipher().seal_attempt(state,'connect'),
            state=state.state,role='client',purpose='connect'),state)
        for purpose,bad in [('state',token),('session','x'*43),('company',token),('session','s1.missing.'+'x'*43)]:
            with self.subTest(purpose=purpose),self.assertRaises(AccessDenied):current.digest(purpose,bad)
