import io
import unittest
from diagnostics import LIMIT, PrivateErrors


class DiagnosticTests(unittest.TestCase):
    def test_provider_password_and_query_never_enter_diagnostic(self):
        stream = io.BytesIO(b'pg_dump: permission denied; password=private-marker; SELECT customer_name FROM bookings')
        errors = PrivateErrors(stream)
        errors.finish()
        self.assertEqual(errors.code('dump'), 'postgres_dump_permission_denied')
        self.assertNotIn('private-marker', errors.code('dump'))

    def test_diagnostic_reader_is_bounded_but_drains_the_stream(self):
        stream = io.BytesIO(b'a' * (LIMIT * 3))
        errors = PrivateErrors(stream)
        errors.finish()
        self.assertEqual(len(errors.captured), LIMIT)
        self.assertEqual(stream.tell(), LIMIT * 3)
        self.assertEqual(errors.code('dump'), 'postgres_dump_failed')

    def test_certificate_problem_is_a_fixed_code(self):
        errors = PrivateErrors(io.BytesIO(b'certificate verify failed: private-marker'))
        errors.finish()
        self.assertEqual(errors.code('dump'), 'postgres_dump_certificate_failed')


if __name__ == '__main__':
    unittest.main()
