"""Only declared historical encodings and independent purposes can read old access."""
from types import MappingProxyType
from uuid import uuid4
import hashlib,hmac,unittest
from appointment_system.credentials import readers,historical_keys,recovery_readers,ReceiptKeys,ContextKeys
from appointment_system.errors import Rejected
from appointment_system.serialization import canonical
from .test_keys import ring


class ReaderBoundaries(unittest.TestCase):
    def definition(self,**changes):
        return dict(algorithm='hmac-sha256',audience='historical:receipt:',purpose='booking',key_id='old',encoding='url43')|changes

    def test_reader_metadata_is_bounded_immutable_and_requires_an_exact_supported_algorithm(self):
        original=self.definition();source={'legacy':MappingProxyType(original)};saved=readers(MappingProxyType(source))
        original['audience']='changed:';self.assertEqual(saved['legacy']['audience'],'historical:receipt:')
        invalid=[None,[],{str(i):self.definition() for i in range(9)},{'UPPER':self.definition()},
            {'v1':self.definition()},{'legacy':self.definition(extra='field')}]
        for change in ({'algorithm':'invented'},{'purpose':'invented'},{'encoding':'invented'},{'audience':None},
            {'audience':'x'*201},{'audience':'bad\n'},{'key_id':None},{'key_id':'Bad'},
            {'algorithm':'json-sha256','key_id':'old'}):invalid.append({'legacy':self.definition(**change)})
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(Rejected):readers(value)
        self.assertEqual(readers({'legacy':self.definition(algorithm='json-sha256',key_id=None)})['legacy']['key_id'],None)
        with self.assertRaises(TypeError):saved['legacy']['audience']='modified'

    def test_historical_materials_are_explicit_unique_and_not_guessed_from_printable_strings(self):
        self.assertEqual(historical_keys((('old',b'a'*32),)),{'old':b'a'*32})
        for values in ([],tuple((f'k{i}',b'a'*32) for i in range(9)),(('old',b'a'*32),('old',b'b'*32)),
            (('UPPER',b'a'*32),),(('old','a'*32),),(('old',b'a'*31),),(('old',b'a'*1025),)):
            with self.subTest(values_type=type(values).__name__),self.assertRaises(Rejected):historical_keys(values)

    def test_recovery_readers_require_two_distinct_declared_audiences_and_saved_material(self):
        good={'key_id':'old','code_audience':'historical:code:','digest_audience':'historical:digest:'}
        value=recovery_readers({'legacy':MappingProxyType(good)},{'old':b'a'*32});self.assertEqual(dict(value['legacy']),good)
        for data in (None,[],{'v1':good},{'UPPER':good},*({'legacy':good|change} for change in
            ({'key_id':'missing'},{'key_id':None},{'code_audience':''},{'digest_audience':'no-ending'},
             {'code_audience':'bad space:'},{'digest_audience':'historical:code:'}))):
            with self.subTest(data=data),self.assertRaises(Rejected):recovery_readers(data,{'old':b'a'*32})
        with self.assertRaises(Rejected):ReceiptKeys(ring(purpose='enquiry-digest'),legacy_keys=(('old',b'a'*32),),recovery_readers={'legacy':good})

    def test_wrong_reader_family_and_missing_key_do_not_create_a_fallback(self):
        for definition in (self.definition(purpose='context'),self.definition(encoding='uuid-url43')):
            with self.assertRaises(Rejected):ReceiptKeys(ring(),{'legacy':definition},(('old',b'a'*32),))
        with self.assertRaises(Rejected):ReceiptKeys(ring(),{'legacy':self.definition()})
        for definition in (self.definition(),self.definition(purpose='context',algorithm='json-sha256',key_id=None,encoding='uuid-url43'),
            self.definition(purpose='context',encoding='url43')):
            with self.assertRaises(Rejected):ContextKeys(ring(purpose='context'),{'legacy':definition},(('old',b'a'*32),))
        with self.assertRaises(Rejected):ContextKeys(ring(purpose='context'),{'legacy':self.definition(purpose='context',encoding='uuid-url43')})

    def test_historical_contact_digest_uses_original_bytes_and_cannot_authorize_booking(self):
        definition=self.definition(algorithm='contact-json-hmac-sha256',purpose='inquiry',audience='original-project')
        keys=ReceiptKeys(ring(purpose='enquiry-digest'),{'legacy':definition},(('old',b'a'*32),))
        reference=uuid4();secret='x'*43
        expected=hmac.new(b'a'*32,canonical(['original-project','contact-v1','receipt',str(reference),secret]),hashlib.sha256).hexdigest()
        self.assertEqual(keys.digest(reference,secret,format='legacy',key_id='old'),expected)
        with self.assertRaises(Rejected):ReceiptKeys(ring(),{'legacy':definition},(('old',b'a'*32),)).digest(reference,secret,format='legacy')
        with self.assertRaises(Rejected):keys.digest(reference,secret,format='legacy',key_id='wrong')
        context=ContextKeys(ring(purpose='context'),{'legacy':self.definition(purpose='context',encoding='uuid-url43')},(('old',b'a'*32),))
        for token in (str(reference)+'.short',str(reference).upper()+'.'+'x'*43):
            with self.assertRaises(Rejected):context.digest(token,format='legacy')
