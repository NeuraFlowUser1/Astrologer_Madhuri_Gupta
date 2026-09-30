import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from postgres import CONTAINER_CA, HOST, ROOT_CA, dump_encrypted


class DumpTrustTests(unittest.TestCase):
    def test_runner_bundle_is_read_only_and_password_is_not_in_docker_arguments(self):
        process = SimpleNamespace(stdout=io.BytesIO(b'synthetic dump bytes'),
                                 stderr=io.BytesIO(), wait=lambda **kwargs: 0,
                                 poll=lambda: 0, kill=lambda: None)
        metadata = {'project': '004-sarsa-jyotish-sansthan', 'format': 'postgres-custom', 'day': '2026-09-30'}
        with tempfile.TemporaryDirectory() as temporary, \
                patch('postgres.subprocess.Popen', return_value=process) as start, \
                patch('postgres.Path.is_file', return_value=True):
            dump_encrypted(f'postgresql://sarsa_booking_backup:synthetic-secret@{HOST}/neondb',
                           Path(temporary) / 'encrypted.aesgcm', b'k' * 32, metadata)
        command = start.call_args.args[0]
        self.assertIn('type=bind,src=' + ROOT_CA + ',dst=' + CONTAINER_CA + ',readonly', command)
        self.assertEqual(start.call_args.kwargs['env']['PGSSLROOTCERT'], CONTAINER_CA)
        self.assertEqual(start.call_args.kwargs['env']['PGSSLMODE'], 'verify-full')
        self.assertEqual(start.call_args.kwargs['env']['PGCHANNELBINDING'], 'require')
        self.assertNotIn('synthetic-secret', ' '.join(command))


if __name__ == '__main__':
    unittest.main()
