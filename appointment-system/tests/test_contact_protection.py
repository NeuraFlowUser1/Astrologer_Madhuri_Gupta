"""Enquiry credentials and frozen mail retain their original record authority."""
import hashlib,hmac,json,unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from cryptography.fernet import Fernet
from appointment_system.contact import ContactSecrets
from appointment_system.credentials import ReceiptKeys
from appointment_system.protected_records import ProtectedRecords
from appointment_system.contact_messages import seal_message,open_message,REPLY_TO
from appointment_system.email_delivery import EmailFailure
from appointment_system.serialization import canonical
from appointment_system.keys import encode
from .test_keys import ring,document

def keys(*,active='k2',legacy=None):
    digest=document(purpose='enquiry-digest');digest['active']=active
    encryption=document(purpose='enquiry-encryption');encryption['active']=active
    encryption['keys']={'k1':encode(b'3'*32),'k2':encode(b'4'*32)}
    return ContactSecrets(ring(digest,purpose='enquiry-digest'),
        ProtectedRecords(ring(encryption,purpose='enquiry-encryption'),legacy))

class ContactProtectionTests(unittest.TestCase):
    def test_new_challenge_is_bound_to_reference_email_generation_and_expiry(self):
        protection=keys();reference=uuid4();email='customer@example.test';now=datetime.now(timezone.utc)
        digest,encrypted=protection.challenge(reference,email,1)
        code=protection.open_code(encrypted,reference,email,1,now+timedelta(minutes=5),now=now)
        self.assertRegex(code,r'^[0-9]{6}$');self.assertEqual(digest,protection.digest('code',reference,1,email,code))
        self.assertNotIn(code,encrypted)
        for changed in [(uuid4(),email,1,now+timedelta(minutes=5)),(reference,'other@example.test',1,now+timedelta(minutes=5)),
                        (reference,email,2,now+timedelta(minutes=5)),(reference,email,1,now)]:
            with self.subTest(changed=changed),self.assertRaises(ValueError):protection.open_code(encrypted,*changed,now=now)
        for generation in (True,0,4):
            with self.assertRaises(ValueError):protection.challenge(reference,email,generation)

    def test_key_rotation_does_not_change_saved_code_or_frozen_message_digest(self):
        first=keys(active='k1');current=keys();reference=uuid4();now=datetime.now(timezone.utc)
        digest,encrypted=first.challenge(reference,'customer@example.test',1)
        code=current.open_code(encrypted,reference,'customer@example.test',1,now+timedelta(minutes=5))
        self.assertEqual(current.digest('code',reference,1,'customer@example.test',code,key_id='k1'),digest)
        job={'id':str(uuid4()),'kind':'acknowledgement','destination':'customer@example.test'}
        payload={'to':['customer@example.test'],'reply_to':REPLY_TO,'subject':'Saved subject','text':'Unicode: नमस्ते'}
        encrypted,digest=seal_message(first,job,payload)
        self.assertEqual(open_message(current,job|{'message_ciphertext':encrypted,'message_digest':digest,'message_format':'v1'}),payload)
        with self.assertRaises(EmailFailure):open_message(current,job|{'id':str(uuid4()),
            'message_ciphertext':encrypted,'message_digest':digest,'message_format':'v1'})
        with self.assertRaises(EmailFailure):open_message(current,job|{'destination':'another@example.test',
            'message_ciphertext':encrypted,'message_digest':digest,'message_format':'v1'})

    def test_enquiry_receipt_cannot_be_used_as_a_booking_receipt(self):
        protection=keys();reference=uuid4();token=protection.receipt_keys.issue()
        self.assertTrue(token.startswith('q1.k2.'))
        self.assertTrue(protection.receipt_keys.matches(reference,token,protection.receipt(reference,token)))
        with self.assertRaises(ValueError):ReceiptKeys(ring()).digest(reference,token)
        self.assertNotEqual(protection.digest('email-quota','customer@example.test'),protection.digest('code','customer@example.test'))
        with self.assertRaises(ValueError):protection.digest('booking','customer@example.test')

    def test_explicit_old_code_reader_rejects_other_purpose_and_never_guesses(self):
        legacy_key=encode(b'L'*32)
        legacy={'old-code':{'algorithm':'fernet-json','keys':[legacy_key],'purpose':'sarsa004-contact-code-v1'}}
        protection=keys(legacy=legacy);reference=str(uuid4());email='customer@example.test';now=datetime.now(timezone.utc)
        data={'purpose':'sarsa004-contact-code-v1','request_id':reference,'email':email,'generation':1,'code':'123456'}
        encrypted=Fernet(legacy_key).encrypt(canonical(data)).decode()
        self.assertEqual(protection.open_code(encrypted,reference,email,1,now+timedelta(minutes=5),format='old-code'),'123456')
        with self.assertRaises(ValueError):protection.open_code(encrypted,reference,email,1,now+timedelta(minutes=5))
        data['purpose']='other-project'
        with self.assertRaises(ValueError):protection.open_code(Fernet(legacy_key).encrypt(canonical(data)).decode(),
            reference,email,1,now+timedelta(minutes=5),format='old-code')

    def test_old_message_hash_uses_the_exact_saved_bytes_including_unicode_escaping(self):
        legacy_key=encode(b'L'*32);raw_key=b'D'*32
        legacy={'old-message':{'algorithm':'fernet-json','keys':[legacy_key],'purpose':'sarsa004-contact-message-v1'}}
        base=keys(legacy=legacy)
        protection=ContactSecrets(base.digest_key,base.cipher,legacy_digests=(('old-digest',raw_key,'sarsa004'),))
        job={'id':str(uuid4()),'kind':'acknowledgement','destination':'customer@example.test','message_format':'old-message',
             'message_digest_format':'old-digest'}
        payload={'to':['customer@example.test'],'reply_to':REPLY_TO,'text':'नमस्ते'}
        raw=json.dumps({'purpose':'sarsa004-contact-message-v1','job_id':job['id'],'payload':payload},sort_keys=True,separators=(',',':'))
        digest=hmac.new(raw_key,canonical(['sarsa004','contact-v1','message',raw]),hashlib.sha256).hexdigest()
        job|={'message_ciphertext':Fernet(legacy_key).encrypt(raw.encode()).decode(),'message_digest':digest}
        self.assertEqual(open_message(protection,job),payload)
        with self.assertRaises(EmailFailure):open_message(protection,job|{'message_digest_format':'missing'})

    def test_envelope_limits_duplicates_and_unrelated_key_material_are_rejected(self):
        protection=keys();reference=uuid4();digest,encrypted=protection.challenge(reference,'customer@example.test',1)
        for value in ('e1.{}',encrypted[:-1]+',"version":1}',encrypted+'x'):
            with self.assertRaises(ValueError):protection.open_code(value,reference,'customer@example.test',1,datetime.now(timezone.utc)+timedelta(minutes=5))
        with self.assertRaises(ValueError):ContactSecrets(protection.digest_key,ProtectedRecords(ring(purpose='enquiry-encryption')))
        with self.assertRaises(ValueError):ProtectedRecords(protection.cipher.ring,{'v1':{}})
        with self.assertRaises(ValueError):ContactSecrets(protection.digest_key,protection.cipher,legacy_digests=(('short',),))
