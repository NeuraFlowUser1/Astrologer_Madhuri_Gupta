import json
import unittest
from copy import deepcopy
from unittest.mock import Mock,patch
from uuid import uuid4
from appointment_system import request_budget as timing

class ProviderObservationTests(unittest.TestCase):
    def test_nested_provider_calls_are_one_bounded_observation_without_private_values(self):
        token=timing._metrics.set({'provider_elapsed_ms':0,'provider_calls':0})
        incident=timing._incident.set(str(uuid4()))
        try:
            with self.assertLogs('booking.operations',level='INFO') as logs:
                with timing.observe_provider('google',clock=Mock(side_effect=[10,10.125])):
                    with timing.observe_provider('google'):
                        private='secret@example.invalid / private receipt and birth data'
            self.assertEqual(len(logs.output),1)
            event=json.loads(logs.records[0].getMessage())
            self.assertEqual(event['elapsed_ms'],125)
            self.assertEqual(event['outcome'],'returned')
            self.assertEqual(event['acceptance'],'not_asserted')
            self.assertEqual(timing._metrics.get(),{'provider_elapsed_ms':125,'provider_calls':1})
            self.assertNotIn(private,logs.output[0])
        finally:timing._incident.reset(incident);timing._metrics.reset(token)
        self.assertFalse(timing._provider_active.get())

    def test_interrupted_transport_preserves_exception_and_does_not_log_exception_text(self):
        error=TimeoutError('private secret, customer phone and provider URL')
        with self.assertLogs('booking.operations',level='INFO') as logs:
            with self.assertRaises(TimeoutError) as raised:
                with timing.observe_provider('razorpay',clock=Mock(side_effect=[1,101])):raise error
        self.assertIs(raised.exception,error)
        event=json.loads(logs.records[0].getMessage())
        self.assertEqual((event['outcome'],event['elapsed_ms']),('interrupted',60000))
        self.assertNotIn(str(error),str(logs.output))
        self.assertFalse(timing._provider_active.get())

    def test_invalid_provider_labels_are_ignored_and_never_enter_logs(self):
        with patch.object(timing.log,'info') as saved:
            for provider in (None,[],{},'google?secret=private'):
                with timing.observe_provider(provider):pass
        saved.assert_not_called()

    def test_logging_failure_and_broken_optional_clock_cannot_stop_provider_work(self):
        for clock in (Mock(side_effect=[10,10.1]),Mock(side_effect=RuntimeError('clock failure'))):
            with patch.object(timing.log,'info',side_effect=RuntimeError('sink unavailable')):
                with timing.observe_provider('resend',clock=clock):pass
            self.assertFalse(timing._provider_active.get())

    def test_negative_clock_delta_is_zero_and_request_totals_are_bounded(self):
        token=timing._metrics.set({'provider_elapsed_ms':60000,'provider_calls':1000})
        try:
            with patch.object(timing.log,'info') as saved:
                with timing.observe_provider('resend',clock=Mock(side_effect=[10,9])):pass
            self.assertEqual(json.loads(saved.call_args.args[0])['elapsed_ms'],0)
            self.assertEqual(timing._metrics.get(),{'provider_elapsed_ms':60000,'provider_calls':1000})
        finally:timing._metrics.reset(token)

