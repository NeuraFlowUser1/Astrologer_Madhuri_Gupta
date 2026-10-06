"""Deadline, slow-stream and diagnostic privacy contracts, no external I/O."""
import json
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from appointment_system.request_budget import budget,remaining,provider_timeout,chunks,BudgetExpired,operation_kind,BudgetMiddleware
from appointment_system.mail_outcomes import retry_after,classify

class BudgetTests(unittest.TestCase):
    def test_nested_budget_never_extends_parent_and_provider_reserves_result_time(self):
        with patch('time.monotonic',return_value=100):
            with budget(clock=lambda:100):
                self.assertEqual(provider_timeout(50).connect,3)
                self.assertEqual(provider_timeout(50).read,1.5)
                with patch('time.monotonic',return_value=119):
                    with self.assertRaises(BudgetExpired):provider_timeout()
                    with budget(clock=lambda:119):
                        self.assertEqual(remaining(),1)
                with patch('time.monotonic',return_value=120):
                    with self.assertRaises(BudgetExpired):remaining()
        self.assertEqual(remaining(),20)
    def test_small_continuous_chunks_cannot_bypass_elapsed_limit(self):
        class Stream:
            def iter_bytes(self):
                yield b'a'
                yield b'b'
        with budget(clock=lambda:100),patch('time.monotonic',side_effect=[101,119]):
            data=chunks(Stream());self.assertEqual(next(data),b'a')
            with self.assertRaises(BudgetExpired):next(data)
    def test_retry_advice_and_quota_categories_are_bounded_and_distinct(self):
        now=datetime(2030,1,1,tzinfo=timezone.utc)
        for value,seconds in [('600',600),('999999',86400),('Tue, 01 Jan 2030 00:02:00 GMT',120),('untrusted',0),('-10',0),('',0)]:
            self.assertEqual(retry_after(value,now=now),seconds)
        daily=classify(429,{'name':'daily_quota_exceeded'},{})
        self.assertEqual(daily,('daily_quota_exceeded',True,True,86400))
        self.assertEqual(classify(429,{'name':'rate_limit_exceeded'},{})[0],'provider_rate_limited')
        self.assertFalse(classify(409,{'name':'invalid_idempotent_request'},{})[2])
        self.assertTrue(classify(409,{'name':'concurrent_idempotent_requests'},{})[2])
    def test_observation_ignores_private_path_and_untrusted_reference(self):
        import asyncio
        sent=[]
        async def app(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):sent.append(message)
        with patch('appointment_system.request_budget.log.info') as observe:
            asyncio.run(BudgetMiddleware(app)({'type':'http','path':'/api/contact/private@example.com','query_string':b'code=123456','headers':[(b'x-booking-reference',b'caller-value')]},receive,send))
        value=observe.call_args.args[0]
        self.assertNotIn('private',value);self.assertNotIn('123456',value);self.assertNotIn('caller-value',value)
        self.assertEqual(json.loads(value)['operation'],'enquiry')
        self.assertTrue(dict(sent[0]['headers']).get(b'x-booking-reference'))
