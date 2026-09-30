"""Security boundaries of the private transfer; synthetic values only."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('sarsa_private_connect', Path(__file__).with_name('connect.py'))
connect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connect)


class PrivateTransferTests(unittest.TestCase):
    def setUp(self):
        self.keys = {name: base64.urlsafe_b64encode(bytes([i + 1]) * 32).decode()
                     for i, name in enumerate(connect.NAMES)}
        self.plan = {'application': '004-sarsa-jyotish-sansthan', 'version': 1,
                     'attention': False, 'lanes': dict.fromkeys(connect.LANES)}

    def test_four_distinct_canonical_values_required(self):
        self.assertEqual(connect.checked_keys(self.keys), self.keys)
        for invalid in [dict.fromkeys(connect.NAMES, self.keys[connect.NAMES[0]]),
                        {**self.keys, 'other': 'unexpected'},
                        {**self.keys, connect.NAMES[0]: self.keys[connect.NAMES[0]][:-1]},
                        {**self.keys, connect.NAMES[0]: 'x' * 43 + '='}]:
            with self.assertRaises(connect.SafeFailure):
                connect.checked_keys(invalid)

    def test_read_only_request_pins_origin_and_never_consumes_work(self):
        response = self.response(self.plan)
        opener = unittest.mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch.object(connect.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(connect.hosted_plan(self.keys), self.plan)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, connect.ORIGIN + '/api/internal/recovery/plan')
        self.assertEqual(request.data, b'{}')
        self.assertEqual(request.headers['Authorization'], 'Bearer ' + self.keys['SARSA_RECOVERY_WORKER_KEY'])

    @staticmethod
    def response(value, *, content_type='application/json'):
        response = unittest.mock.Mock(status=200)
        response.headers.get_content_type.return_value = content_type
        response.read.return_value = json.dumps(value).encode()
        return response

    def test_response_identity_and_lane_limits_required(self):
        for invalid in [{**self.plan, 'application': '003'},
                        {**self.plan, 'version': True},
                        {**self.plan, 'lanes': {**self.plan['lanes'], 'email': 901}},
                        {**self.plan, 'lanes': {**self.plan['lanes'], 'email': True}},
                        {**self.plan, 'secret': 'unexpected'}]:
            opener = unittest.mock.MagicMock()
            opener.open.return_value.__enter__.return_value = self.response(invalid)
            with patch.object(connect.urllib.request, 'build_opener', return_value=opener):
                with self.assertRaises(connect.SafeFailure):
                    connect.hosted_plan(self.keys)

    def test_http_failure_is_safe_and_prevents_configuration(self):
        failure = urllib.error.HTTPError(connect.ORIGIN, 404, 'private body must not be disclosed', {}, io.BytesIO(b'private'))
        with patch.object(connect, 'private_keys', return_value=dict(self.keys)), \
             patch.object(connect, 'hosted_plan', side_effect=connect.SafeFailure('canonical_plan_http_404')), \
             patch.object(connect, 'configure') as configure, \
             patch('sys.argv', ['connect.py', 'configure-worker']), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(connect.main(), 1)
            configure.assert_not_called()
            self.assertNotIn('private body', output.getvalue())
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = failure
        with patch.object(connect.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(connect.SafeFailure, '^canonical_plan_http_404$'):
                connect.hosted_plan(self.keys)

    def test_private_wrangler_input_uses_null_log_sink_not_arguments(self):
        def operation(arguments, **kwargs):
            self.assertNotIn('synthetic-private-input', arguments)
            self.assertEqual(kwargs['input'], 'synthetic-private-input')
            sink = Path(kwargs['env']['WRANGLER_LOG_PATH'])
            self.assertTrue(sink.name.endswith('.log'))
            self.assertTrue(sink.is_symlink())
            self.assertEqual(str(sink.readlink()), '/dev/null')
            self.assertEqual(kwargs['env']['CLOUDFLARE_API_BASE_URL'], 'https://api.cloudflare.com/client/v4')
            self.assertTrue(kwargs['capture_output'])
            return unittest.mock.Mock(returncode=0, stdout='public metadata', stderr='')
        with patch.object(connect.subprocess, 'run', side_effect=operation):
            self.assertEqual(connect.wrangler(['secret', 'bulk'], payload='synthetic-private-input').returncode, 0)

    def test_redirect_never_forwards_authority(self):
        with self.assertRaises(connect.SafeFailure):
            connect.NoRedirect().redirect_request(None, None, None, None, None, None)


if __name__ == '__main__':
    unittest.main()
