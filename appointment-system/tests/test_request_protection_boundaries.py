"""Request quotas preserve privacy and reject uncertain admission decisions."""
from unittest import TestCase
from unittest.mock import Mock

from appointment_system.connection import StorageUnavailable
from appointment_system.errors import Rejected
from appointment_system.keys import KeyRing, encode
from appointment_system.rate_limit import RateLimited, consume_limit, risk_digest
from .test_keys import IDENTITY, ring


class RequestProtectionBoundaries(TestCase):
    def test_ipv6_address_rotation_and_ipv4_mapping_do_not_reset_a_shared_quota(self):
        key = ring(purpose='risk')
        self.assertEqual(risk_digest('2001:db8:abcd:42::1', key), risk_digest('2001:db8:abcd:42::ffff', key))
        self.assertNotEqual(risk_digest('2001:db8:abcd:42::1', key), risk_digest('2001:db8:abcd:43::1', key))
        self.assertEqual(risk_digest('::ffff:192.0.2.9', key), risk_digest('192.0.2.9', key))
        self.assertNotEqual(risk_digest('192.0.2.9', key), risk_digest('192.0.2.10', key))
        self.assertRegex(risk_digest('192.0.2.9', key), r'^[a-f0-9]{64}$')

    def test_unverified_source_shares_a_quota_and_invalid_address_never_reaches_storage(self):
        key = ring(purpose='risk')
        store = Mock(spec_set=['consume_limit'])
        store.consume_limit.return_value = {'allowed': True}
        for _ in range(2):
            consume_limit(store, 'contact', None, key)
        digest = risk_digest(None, key)
        self.assertEqual(store.consume_limit.call_args.args, ('contact', digest))
        self.assertEqual(store.consume_limit.call_args_list[0], store.consume_limit.call_args_list[1])
        store.reset_mock()
        for address in ('not-an-address', '', '192.0.2.9,192.0.2.10', object()):
            with self.subTest(address_type=type(address).__name__), self.assertRaises(StorageUnavailable):
                consume_limit(store, 'contact', address, key)
        store.consume_limit.assert_not_called()

    def test_different_duty_key_and_malformed_admission_never_allow_a_request(self):
        store = Mock(spec_set=['consume_limit'])
        with self.assertRaises(StorageUnavailable):
            consume_limit(store, 'contact', '192.0.2.9', ring(purpose='receipt'))
        store.consume_limit.assert_not_called()
        for result in (None, [], {}, {'allowed': 1}, {'allowed': 'true'}):
            store.consume_limit.return_value = result
            with self.subTest(result=result), self.assertRaises(StorageUnavailable):
                consume_limit(store, 'contact', '192.0.2.9', ring(purpose='risk'))
        store.consume_limit.side_effect = StorageUnavailable('synthetic uncertain quota commit')
        with self.assertRaises(StorageUnavailable):
            consume_limit(store, 'contact', '192.0.2.9', ring(purpose='risk'))

    def test_booking_flag_is_preserved_and_denied_requests_get_bounded_retry_times(self):
        store = Mock(spec_set=['consume_limit'])
        key = ring(purpose='risk')
        store.consume_limit.return_value = {'allowed': True}
        consume_limit(store, 'checkout', '192.0.2.9', key, booking=True)
        store.consume_limit.assert_called_once_with('checkout', risk_digest('192.0.2.9', key), booking=True)
        for value, expected in [(0, 1), (-100, 1), (120, 120), (999999, 3600), (None, 60)]:
            store.consume_limit.return_value = {'allowed': False} | ({} if value is None else {'retry_after': value})
            with self.assertRaises(RateLimited) as caught:
                consume_limit(store, 'checkout', '192.0.2.9', key, booking=True)
            self.assertEqual(caught.exception.retry_after, expected)

    def test_direct_key_construction_cannot_bypass_shape_or_active_key_checks(self):
        valid = dict(installation_id=IDENTITY, environment='test', purpose='risk', active='first', keys=(('first', b'A' * 32),))
        for change in ({'environment': 'unknown'}, {'keys': [('first', b'A' * 32)]},
                       {'keys': (['first', b'A' * 32],)}, {'keys': (('first',),)},
                       {'keys': (('first', b'A' * 31),)}, {'active': 'missing'},
                       {'keys': (('first', b'A' * 32), ('first', b'B' * 32))},
                       {'keys': (('first', b'A' * 32), ('second', b'A' * 32))}):
            with self.subTest(change=list(change)), self.assertRaises(Rejected):
                KeyRing(**(valid | change))
        protected = KeyRing(**valid).seal('synthetic-record', b'')
        # Encoded length alone does not prove the decoded payload is within
        # the 64 KiB plaintext plus authentication-tag limit.
        with self.assertRaises(Rejected):
            KeyRing(**valid).open('synthetic-record', protected | {'ciphertext': encode(b'X' * 65553)})
