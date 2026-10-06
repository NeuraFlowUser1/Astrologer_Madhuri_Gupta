from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import unittest
from uuid import uuid4
from appointment_system.credentials import ReceiptKeys,ContextKeys
from appointment_system.access import authorize_receipt,authorize_context,AccessDenied,new_context,parse_context,context_identifier
from appointment_system.security import receipt_digest,receipt_matches
from appointment_system.errors import Rejected
from appointment_system.serialization import canonical
from .test_keys import ring,document


class CredentialTests(unittest.TestCase):
    def test_runtime_never_issues_or_guesses_an_undeclared_raw_key_protocol(self):
        reference=uuid4();secret='x'*43;token=str(reference)+'.'+secret
        for key in (b'1'*32,None,'plain-text-key',object()):
            with self.subTest(key_type=type(key).__name__):
                with self.assertRaises(ValueError):receipt_digest(reference,secret,key)
                self.assertFalse(receipt_matches(reference,secret,key,'a'*64))
                with self.assertRaises(ValueError):new_context(key)
                with self.assertRaises(AccessDenied):context_identifier(token,key)
                with self.assertRaises(AccessDenied):parse_context(token,key,{'credential_format':'v1'})
        keys=ContextKeys(ring(purpose='context'));identifier,token,_=new_context(keys)
        self.assertEqual(context_identifier(token,keys),identifier)
        with self.assertRaises(AccessDenied):context_identifier('invalid',keys)

    def test_new_receipt_is_record_purpose_environment_and_key_version_bound(self):
        keys=ReceiptKeys(ring());reference=uuid4();token=keys.issue();digest=keys.digest(reference,token)
        self.assertEqual(len(token.split(".")[-1]),43);self.assertNotIn(token,repr(keys))
        self.assertTrue(keys.matches(reference,token,digest,format="v1",key_id="k2"))
        self.assertFalse(keys.matches(uuid4(),token,digest));self.assertFalse(keys.matches(reference,token,digest,key_id="k1"))
        swapped=deepcopy(document());swapped["active"]="k1";retained=ReceiptKeys(ring(swapped))
        self.assertTrue(retained.matches(reference,token,digest,key_id="k2"))
        self.assertFalse(retained.matches(reference,token+"x",digest))

    def test_historical_receipts_preserve_exact_algorithms_and_need_saved_format(self):
        legacy={"old-json":{"algorithm":"json-sha256","audience":"","purpose":"booking","key_id":None,"encoding":"hex64"},
                "old-hmac":{"algorithm":"hmac-sha256","audience":"historical-client:004:booking-receipt:v1:",
                            "purpose":"booking","key_id":"k1","encoding":"url43"}}
        keys=ReceiptKeys(ring(),legacy,(("k1",b"1"*32),));reference=uuid4();oldhex="a"*64;oldurl="x"*43
        sha=hashlib.sha256(canonical(["booking",str(reference),oldhex])).hexdigest()
        mac=hmac.new(b"1"*32,("historical-client:004:booking-receipt:v1:"+str(reference)+":"+oldurl).encode(),hashlib.sha256).hexdigest()
        self.assertTrue(keys.matches(reference,oldhex,sha,format="old-json"))
        self.assertTrue(keys.matches(reference,oldurl,mac,format="old-hmac",key_id="k1"))
        self.assertFalse(keys.matches(reference,oldhex,sha));self.assertFalse(keys.matches(reference,oldurl,mac))
        self.assertFalse(keys.matches(reference,oldhex,sha,format="old-hmac"))
        self.assertFalse(ReceiptKeys(ring()).matches(reference,oldurl,mac,format="old-hmac"))

    def test_expiry_and_revocation_are_not_extended_by_reader_or_key_rotation(self):
        keys=ReceiptKeys(ring());reference=uuid4();token=keys.issue();now=datetime.now(timezone.utc)
        row={"request_id":str(reference),"receipt_digest":keys.digest(reference,token),"receipt_format":"v1",
             "receipt_key_id":"k2","receipt_expires_at":now+timedelta(seconds=1),"receipt_revoked_at":None}
        authorize_receipt(row,reference,token,keys,now)
        for changes in ({"receipt_expires_at":now},{"receipt_revoked_at":now},{"receipt_key_id":"k1"}):
            with self.assertRaises(AccessDenied):authorize_receipt(row|changes,reference,token,keys,now)

    def test_new_context_carries_its_reader_and_rotation_does_not_guess_a_legacy_format(self):
        keys=ContextKeys(ring(purpose="context"));identifier,token,digest=new_context(keys)
        row={"credential_format":"v1","credential_key_id":"k2"}
        self.assertEqual(parse_context(token,keys,row),(identifier,digest))
        with self.assertRaises(AccessDenied):parse_context(token,keys)
        for change in ({"credential_format":"unknown"},{"credential_key_id":"k1"}):
            with self.assertRaises(AccessDenied):parse_context(token,keys,row|change)
        spec=document(purpose="context");spec["active"]="k1"
        self.assertEqual(parse_context(token,ContextKeys(ring(spec,purpose="context")),row),(identifier,digest))

    def test_historical_context_uses_saved_encoding_and_audience(self):
        definitions={}
        identifier=uuid4()
        for name,encoding,token in (("old-hex","uuid-hex64",str(identifier)+"."+"a"*64),
                                   ("old-url","uuid-url43",str(identifier)+"."+"x"*43)):
            definitions[name]={"algorithm":"hmac-sha256","purpose":"context","audience":name+":context:v1:",
                              "key_id":"k1","encoding":encoding}
            keys=ContextKeys(ring(purpose="context"),definitions,(("k1",b"1"*32),))
            expected=hmac.new(b"1"*32,(name+":context:v1:"+token).encode(),hashlib.sha256).hexdigest()
            self.assertEqual(keys.digest(token,format=name,key_id="k1"),expected)
            with self.assertRaises(Rejected):keys.digest(token,format="v1")
            with self.assertRaises(Rejected):keys.digest(token,format="unknown")

    def test_original_context_text_key_is_not_silently_decoded_as_a_new_binary_key(self):
        name="old-text";identifier=uuid4();token=str(identifier)+"."+"a"*64
        text_key="The original printable key, stored as text"
        definition={name:{"algorithm":"hmac-sha256","purpose":"context","audience":"astro:003:checkout-context:v1:",
                         "key_id":"saved-text","encoding":"uuid-hex64"}}
        keys=ContextKeys(ring(purpose="context"),definition,(("saved-text",text_key.encode()),))
        expected=hmac.new(text_key.encode(),("astro:003:checkout-context:v1:"+token).encode(),hashlib.sha256).hexdigest()
        self.assertEqual(keys.digest(token,format=name),expected)
        with self.assertRaises(Rejected):ContextKeys(ring(purpose="context"),definition)

    def test_malformed_credentials_and_unapproved_readers_are_rejected(self):
        receipts=ReceiptKeys(ring());contexts=ContextKeys(ring(purpose="context"))
        for token in (None,"short","r1.unknown."+"x"*43,"r1.k2."+("="*43)):
            with self.assertRaises(Rejected):receipts.metadata(token)
        for token in (None,"short","c1.k2."+str(uuid4())+"."+("="*43),
                      "c1.k2.00000000-0000-0000-0000-000000000000."+"x"*43):
            with self.assertRaises(Rejected):contexts.metadata(token)
        with self.assertRaises(Rejected):ContextKeys(ring())
        with self.assertRaises(Rejected):ReceiptKeys(ring(purpose="context"))
        with self.assertRaises(Rejected):ReceiptKeys(ring(),{"v1":{}})
