import unittest

from appointment_system.errors import Rejected, invalid, unavailable
from appointment_system.serialization import canonical, decode, fingerprint, integer, object_fields, record_id, text


class BoundaryTests(unittest.TestCase):
    def test_json_rejects_ambiguous_unbounded_and_wrong_numeric_types(self):
        for value in ('{"x":1,"x":2}', '{"x":{"a":1,"a":2}}', '{"x":NaN}',
                      '{"x":Infinity}', '{"x":1.5}', '[', b'\xff', None,
                      '{"x":9223372036854775808}', '[' * 40 + '0' + ']' * 40,
                      '"' + 'x' * 131072 + '"'):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(Rejected):
                    decode(value)
        for maximum in (True, 0, 131073, "10"):
            with self.assertRaises(Rejected):
                decode('{}', maximum=maximum)

    def test_canonical_unicode_order_and_distinct_body_fingerprints(self):
        one, two = {"b": [True, None, "नमस्ते"], "a": 1}, {"a": 1, "b": [True, None, "नमस्ते"]}
        self.assertEqual(canonical(one), canonical(two))
        self.assertEqual(decode(canonical(one)), one)
        self.assertEqual(fingerprint(one), fingerprint(two))
        self.assertNotEqual(fingerprint(one), fingerprint({"a": 2}))
        for value in ({1: 'x'}, {"x": 1.1}, {"x": set()}, {"x": 2**63},
                      {"x": '\ud800'}, {"x": 'a' * 131073}):
            with self.assertRaises(Rejected):
                canonical(value)

    def test_identifiers_types_and_field_errors(self):
        good = "b85d019f-850c-4f84-a47b-cd0b90e7e0f8"
        self.assertEqual(record_id(good), good)
        for value in (good.upper(), None, "bad", "00000000-0000-0000-0000-000000000000"):
            with self.assertRaises(Rejected): record_id(value)
        self.assertEqual(integer(5, 1, 5), 5)
        for value in (True, 0, 6, 5.0):
            with self.assertRaises(Rejected): integer(value, 1, 5)
        self.assertEqual(text('hello', 1, 5), 'hello')
        for value in (None, '', ' too long ', 'a\n', 'a\x7f'):
            with self.assertRaises(Rejected): text(value, 1, 5)
        self.assertEqual(object_fields({'a': 1, 'b': 2}, {'a'}, {'b'}), {'a': 1, 'b': 2})
        for value in ([], {}, {'a': 1, 'extra': 2}):
            with self.assertRaises(Rejected): object_fields(value, {'a'})
        self.assertEqual(invalid('email').public()['fields'], ['email'])
        self.assertEqual(unavailable().status, 503)
        self.assertNotIn('exception', unavailable().public())
