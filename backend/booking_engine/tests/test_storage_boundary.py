import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.booking_engine.connection import StorageUnavailable, checked_config
from backend.booking_engine.security import new_secret
from backend.booking_engine.storage import Store
from backend.booking_engine.models import BookingInput, BookingRequest

HOST = 'sarsa.example.invalid'
DSN = f'host={HOST} dbname=neondb user=sarsa_app sslmode=require'


class StorageBoundaryTests(unittest.TestCase):
    def test_email_v2_preserves_local_case_and_v1_keeps_legacy_retry_fingerprint(self):
        payload = dict(request_id=str(uuid4()),full_name='Test Person',email='CaseSensitive@EXAMPLE.com',
            phone='+919876543210',service_id='numerology',quote_version='a'*64,
            starts_at='2026-10-01T10:00:00+05:30')
        legacy = BookingInput.model_validate(payload)
        v1 = BookingRequest.model_validate(dict(payload, normalization_version=1))
        v2 = BookingRequest.model_validate(payload)
        self.assertEqual(v2.email, 'CaseSensitive@example.com')
        self.assertEqual(v1.email, legacy.email)
        with patch.dict('os.environ',{},clear=True):
            store = Store(DSN,expected_host=HOST)
        context, secret = uuid4(), new_secret()
        with patch.object(store,'_call',return_value='rate_limited') as call:
            bindings=[]
            for draft in (legacy,v1,v2):
                store.reserve(context,draft,secret,b'a'*32)
                bindings.append(call.call_args.args[1])
        self.assertEqual(bindings[0],bindings[1])
        self.assertNotEqual(bindings[1],bindings[2])

    def test_explicit_target_and_secure_transport(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(checked_config(DSN,HOST)['host'],HOST)
            for suffix, expected in (('', 'other.example.invalid'), (' hostaddr=127.0.0.1',HOST),
                    (' options=-csearch_path=public',HOST), (' service=other',HOST),
                    (' sslmode=disable',HOST), (' host=a,b',HOST), (' dbname=',HOST)):
                with self.subTest(suffix=suffix), self.assertRaises(StorageUnavailable):
                    checked_config(DSN+suffix, expected)
            for name in ('PGOPTIONS','PGSERVICE','PGHOSTADDR'):
                with patch.dict('os.environ',{name:'untrusted'}), self.assertRaises(StorageUnavailable):
                    checked_config(DSN,HOST)

    def test_reservation_does_not_continue_after_uncertain_admission_commit(self):
        with patch.dict('os.environ',{},clear=True):
            store = Store(DSN,expected_host=HOST)
        payload = dict(request_id=str(uuid4()),full_name='Test Person',email='test@example.com',
                       phone='+919876543210',service_id='numerology',quote_version='a'*64,
                       starts_at='2026-10-01T10:00:00+05:30')
        with patch.object(store,'_call',side_effect=StorageUnavailable('uncertain')) as call:
            with self.assertRaises(StorageUnavailable):
                store.reserve(uuid4(),payload,new_secret(),b'a'*32)
            self.assertEqual(call.call_count,1)

    def test_retries_bind_same_normalized_input_and_never_accept_client_price(self):
        with patch.dict('os.environ',{},clear=True):
            store = Store(DSN,expected_host=HOST)
        payload = dict(request_id=str(uuid4()),full_name='Test Person',email='test@example.com',
                       phone='+91 98765 43210',service_id='numerology',quote_version='a'*64,
                       starts_at='2026-10-01T10:00:00+05:30')
        context, secret = uuid4(),new_secret()
        with patch.object(store,'_call',return_value='rate_limited') as call:
            self.assertEqual(store.reserve(context,payload,secret,b'a'*32),{'code':'rate_limited'})
            first = call.call_args.args[1]
            payload['phone'] = '+919876543210'
            store.reserve(context,payload,secret,b'a'*32)
            self.assertEqual(call.call_args.args[1],first)
            payload['amount_paise'] = 1
            with self.assertRaises(ValueError):
                store.reserve(context,payload,secret,b'a'*32)
            self.assertEqual(call.call_count,2)


if __name__ == '__main__':
    unittest.main()
