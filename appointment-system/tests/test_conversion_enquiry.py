"""Historical code bytes, exact lifetime and common verification after handover."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hmac,hashlib,unittest
from uuid import uuid4
from cryptography.fernet import Fernet
from appointment_system.contact import ContactSecrets
from appointment_system.keys import encode
from appointment_system.serialization import canonical
from tools.conversion.enquiry import EnquiryTransfer
from tools.conversion.records import Mapper
from tools.conversion.source import catalogue,ConversionError
from .test_contact_protection import keys
from .test_conversion_records import bindings,empty


def fixture():
    key=encode(b'L'*32)
    base=keys(legacy={'old-code':dict(algorithm='fernet-json',keys=[key],purpose='sarsa004-contact-code-v1'),
                      'old-message':dict(algorithm='fernet-json',keys=[key],purpose='sarsa004-contact-message-v1')})
    protection=ContactSecrets(base.digest_key,base.cipher,legacy_digests=(('old-digest',b'D'*32,'sarsa004'),))
    layout=next(item for item in catalogue() if item.identifier=='legacy-004-31')
    row={column['name']:None for column in layout.structure['relations']['sarsa_booking.enquiries']}
    now=datetime.now(timezone.utc);reference=str(uuid4());email='customer@example.test';code='123456'
    saved=dict(purpose='sarsa004-contact-code-v1',request_id=reference,email=email,generation=2,code=code)
    raw=canonical(['sarsa004','contact-v1','code',reference,'2',email,code])
    row.update(request_id=reference,email_key='a'*64,receipt_digest='b'*64,request_fingerprint='c'*64,
               payload=dict(name='Synthetic enquiry',email=email,message='Please help with the appointment.'),
               code_digest=hmac.new(b'D'*32,raw,hashlib.sha256).hexdigest(),
               code_ciphertext=Fernet(key).encrypt(canonical(saved)).decode(),
               code_expires_at=(now+timedelta(minutes=4)).isoformat(),
               resend_after=(now+timedelta(seconds=20)).isoformat(),generation=2,attempts=3,
               created_at=(now-timedelta(minutes=1)).isoformat(),receipt_expires_at=(now+timedelta(hours=23)).isoformat())
    return layout,row,protection,now


class EnquiryConversion(unittest.TestCase):
    def test_same_code_remains_valid_without_extending_expiry_or_resetting_limits(self):
        layout,row,protection,now=fixture();before=deepcopy(row)
        result=EnquiryTransfer(protection,'old-code','old-digest')(row,now)
        changed={'code_ciphertext','code_digest','code_format','code_digest_format','code_digest_key_id'}
        self.assertEqual({k:v for k,v in result.items() if k not in changed},
                         {k:v for k,v in row.items() if k not in changed})
        self.assertEqual(row,before)
        self.assertEqual(protection.open_code(result['code_ciphertext'],row['request_id'],row['payload']['email'],2,
                         datetime.fromisoformat(row['code_expires_at']),now=now),'123456')
        self.assertEqual(result['code_digest'],protection.digest('code',row['request_id'],2,row['payload']['email'],'123456'))

    def test_mismatched_code_owner_generation_digest_expiry_or_reader_refuses(self):
        _,row,protection,now=fixture();transfer=EnquiryTransfer(protection,'old-code','old-digest')
        for change in ({'request_id':str(uuid4())},{'generation':1},{'code_digest':'a'*64},
                       {'payload':row['payload']|{'email':'another@example.test'}},{'code_ciphertext':'invalid'},
                       {'verified_at':now.isoformat()},{'code_expires_at':now.isoformat()}):
            with self.subTest(fields=list(change)),self.assertRaisesRegex(ConversionError,'legacy_enquiry_code_invalid'):
                transfer(row|change,now)
        for cipher,digest in (('missing','old-digest'),('old-code','missing')):
            with self.assertRaisesRegex(ConversionError,'legacy_enquiry_reader_invalid'):
                EnquiryTransfer(protection,cipher,digest)

    def test_import_refuses_live_code_without_reader_and_preserves_expired_deadline(self):
        layout,row,protection,now=fixture();rows=empty(layout);rows['sarsa_booking.enquiries']=[row]
        with self.assertRaisesRegex(ConversionError,'legacy_enquiry_binding_unresolved'):
            Mapper(layout,rows,bindings()).translate()
        row['code_expires_at']=(now-timedelta(minutes=3)).isoformat()
        converted=Mapper(layout,rows,bindings()).translate().tables['enquiries'][0]
        self.assertEqual(converted['code_expires_at'],row['code_expires_at'])
        self.assertIsNone(converted['code_ciphertext']);self.assertIsNone(converted['verified_at'])

    def test_translator_must_not_change_payload_lifetime_receipt_or_verification_state(self):
        layout,row,protection,now=fixture();rows=empty(layout);rows['sarsa_booking.enquiries']=[row]
        for change in ({'payload':{}},{'code_expires_at':(now+timedelta(days=1)).isoformat()},
                       {'verified_at':now.isoformat()},{'receipt_digest':'f'*64}):
            with self.subTest(fields=list(change)),self.assertRaisesRegex(ConversionError,'legacy_enquiry_binding_invalid'):
                Mapper(layout,rows,bindings(enquiry_mapper=lambda saved,instant:saved|change)).translate()
