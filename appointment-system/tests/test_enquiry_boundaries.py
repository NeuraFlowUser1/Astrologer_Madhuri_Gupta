"""Ordinary enquiries remain independent, private and replayable across migration."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib,hmac,json
from unittest import TestCase
from uuid import uuid4
from appointment_system.access import AccessDenied
from appointment_system.contact import ContactSecrets,EnquiryInput,enquiry_payload,public_enquiry
from appointment_system.credentials import ReceiptKeys
from appointment_system.configuration import installation
from appointment_system.keys import encode
from appointment_system.serialization import canonical
from .test_contact_protection import keys
from .test_keys import document,ring

class EnquiryBoundaries(TestCase):
    def body(self):
        return dict(request_id=str(uuid4()),name='Synthetic Person',email='person@example.com',subject='General question',message='Please share consultation details.')

    def environment(self):
        digest=document(purpose='enquiry-digest');encryption=document(purpose='enquiry-encryption')
        encryption['keys']={'k1':encode(b'3'*32),'k2':encode(b'4'*32)}
        return {'BOOKING_ENQUIRY_DIGEST_KEYS':json.dumps(digest),'BOOKING_ENQUIRY_ENCRYPTION_KEYS':json.dumps(encryption)}

    def legacy(self):
        facts=installation()
        return dict(version=1,installation_id=facts['installation_id'],environment=facts['environment'],receipt_readers={},cipher_readers={},
            materials={'retained':encode(b'L'*32)},digest_readers={'old-digest':{'key_id':'retained','audience':'saved-client'}})

    def test_general_enquiries_do_not_depend_on_a_current_booking_service(self):
        base=self.body();general=EnquiryInput(**base,service_interest='retired-service')
        self.assertEqual(general.phone,'');self.assertEqual(general.service_interest,'retired-service')
        for changes in ({'service_interest':'../service'},{'message':'unsafe\x00text'},{'kind':'prashna'},
            {'kind':'prashna','phone':'+919999999999','location':'x'},{'phone':'not a number'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):EnquiryInput(**(base|changes))
        complete=EnquiryInput(**base,kind='prashna',phone='+919999999999',location='Synthetic city')
        self.assertEqual(complete.phone,'+919999999999')
        value,digest=enquiry_payload(EnquiryInput(**base));self.assertNotIn('source',value);self.assertNotIn('service_interest',value)
        modern,modern_digest=enquiry_payload(EnquiryInput(**base,source='contact'))
        self.assertEqual(modern['source'],'contact');self.assertNotEqual(digest,modern_digest)
        self.assertNotIn('request_id',value)

    def test_explicit_retained_protection_is_scoped_and_matches_saved_hashes(self):
        environment=self.environment();protected=ContactSecrets.from_environment(environment)
        self.assertEqual(protected.digest_key.active,'k2')
        environment['BOOKING_LEGACY_ENQUIRY_PROTECTION']=json.dumps(self.legacy())
        retained=ContactSecrets.from_environment(environment)
        expected=hmac.new(b'L'*32,canonical(['saved-client','contact-v1','message','old-payload']),hashlib.sha256).hexdigest()
        self.assertEqual(retained.digest('message','old-payload',format='old-digest'),expected)
        with self.assertRaises(ValueError):retained.digest('message','old-payload',format='unknown')
        with self.assertRaises(AccessDenied):protected.receipt(uuid4(),'invalid credential')

    def test_invalid_or_cross_project_legacy_configuration_never_falls_back(self):
        environment=self.environment();legacy=self.legacy()
        changes=[{'installation_id':str(uuid4())},{'environment':'production'},{'version':True},{'materials':[]},
            {'materials':{str(n):encode(b'L'*32) for n in range(9)}},{'materials':{'retained':'bad'}},
            {'materials':{'retained':encode(b'L'*31)}},{'digest_readers':[]},
            {'digest_readers':{str(n):{'key_id':'retained','audience':'saved-client'} for n in range(9)}},
            {'digest_readers':{'v1':{'key_id':'retained','audience':'saved-client'}}},
            {'digest_readers':{'old-digest':{'key_id':'missing','audience':'saved-client'}}},
            {'digest_readers':{'old-digest':{'key_id':'retained','audience':''}}},
            {'digest_readers':{'old-digest':{'key_id':'retained','audience':'bad\nvalue'}}}]
        for changed in changes:
            with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'Contact protection is not configured'):
                ContactSecrets.from_environment(environment|{'BOOKING_LEGACY_ENQUIRY_PROTECTION':json.dumps(legacy|changed)})
        with self.assertRaises(ValueError):ContactSecrets.from_environment({})
        with self.assertRaises(ValueError):ContactSecrets.from_environment(environment|{'BOOKING_LEGACY_ENQUIRY_PROTECTION':'invalid'})

    def test_direct_protection_construction_keeps_purposes_and_reader_identity_separate(self):
        protected=keys()
        for changes in ({'digest_key':b'x'*32},{'cipher':None},{'receipt_keys':ReceiptKeys(ring())},
            {'legacy_digests':[]},{'legacy_digests':(('v1',b'L'*32,'audience'),)},
            {'legacy_digests':(('old',b'short','audience'),)},{'legacy_digests':(('old',b'L'*32,'bad space'),)},
            {'legacy_digests':(('old',b'L'*32,'audience'),('old',b'K'*32,'audience'))}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(protected,**changes)

    def test_decrypted_code_fields_are_checked_even_with_valid_encryption(self):
        protected=keys();reference=str(uuid4());email='person@example.com';now=datetime.now(timezone.utc)
        fields=dict(purpose='appointment:v1:enquiry-code',request_id=reference,email=email,generation=1,code='123456',digest_key_id='k2')
        record=protected.record('code',reference,email,1)
        for changes in ({'request_id':str(uuid4())},{'email':'another@example.com'},{'generation':True},{'generation':2},
            {'code':'12x456'},{'code':123456},{'digest_key_id':'missing'},{'extra':'field'}):
            encrypted=protected.cipher.seal(record,fields|changes)
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'could not be read safely'):
                protected.open_code(encrypted,reference,email,1,now+timedelta(minutes=2),now=now)
        encrypted=protected.cipher.seal(record,fields)
        for instant,expiry in ((now.replace(tzinfo=None),now+timedelta(minutes=2)),(now,now.replace(tzinfo=None)),(now,now)):
            with self.assertRaises(ValueError):protected.open_code(encrypted,reference,email,1,expiry,now=instant)

    def test_public_enquiry_never_releases_personal_payload_or_verification_material(self):
        now='2026-10-04T12:00:00+00:00'
        valid=dict(code='ok',request_id=str(uuid4()),state='awaiting_verification',generation=1,server_now=now,
            code_expires_at=now,resend_after=now,sends_remaining=2,verification_delivery='queued')
        self.assertEqual(public_enquiry(valid|{'payload':self.body(),'email':'private@example.com','verification_code':'123456','jobs':[]}),valid)
        changes=[{'request_id':'invalid'},{'state':'invented'},{'generation':True},{'generation':4},
            {'sends_remaining':True},{'sends_remaining':3},{'verification_delivery':'invented'},{'server_now':'invalid'},
            {'code_expires_at':None},{'resend_after':'invalid'}]
        for changed in changes:
            with self.subTest(changed=changed),self.assertRaises(ValueError):public_enquiry(valid|changed)
        with self.assertRaises(ValueError):public_enquiry(None)
        with self.assertRaises(ValueError):public_enquiry({'code':'ok'})
        self.assertEqual(public_enquiry({'code':'please_wait','payload':'private'}),{'code':'please_wait'})
