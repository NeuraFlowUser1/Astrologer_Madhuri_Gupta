"""Deadline exhaustion and diagnostic failure must not undo saved responses."""
import asyncio
from http.client import HTTPResponse
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, patch, AsyncMock
from appointment_system import request_budget as rb


class RequestBoundaryTests(unittest.TestCase):
    def test_invalid_time_budgets_do_not_replace_the_outer_context(self):
        for seconds in (0,-1,rb.CEILING+1):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):
                with rb.budget(seconds):
                    self.fail('Invalid budget admitted')
        self.assertEqual(rb.remaining(),rb.CEILING)

    def test_real_http_read1_and_wrapped_stream_respect_byte_limits(self):
        class Socket:
            def __init__(self,data):self.data=data
            def makefile(self,*args):return BytesIO(self.data)
        def response(body):
            result=HTTPResponse(Socket(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body))
            result.begin()
            return result
        self.assertEqual(rb.read_bounded(response(b'owned'),5),b'owned')
        self.assertEqual(rb.read_bounded(Mock(fp=response(b'owned')),5),b'owned')
        with self.assertRaises(ValueError):
            rb.read_bounded(response(b'too long'),3)
        for data in (None,'text instead of bytes',b'too long'):
            with self.subTest(data=data),self.assertRaises(ValueError):
                rb.read_bounded(Mock(read=Mock(return_value=data)),3)
        self.assertEqual(rb.read_bounded(Mock(read=Mock(return_value=b'ok')),2),b'ok')

    def test_all_server_owned_operation_categories_are_bounded(self):
        for path,expected in [('/api/company/support/private','control'),('/company/sign-in','control'),
          ('/api/webhooks/provider','provider_event'),('/api/internal/recovery','recovery'),
          ('/api/auth/private','verification'),('/api/contact/private','enquiry'),
          ('/api/studio/calendar','staff'),('/api/admin/settings','staff'),
          ('/api/checkout/begin','checkout'),('/api/booking/status','booking'),
          ('/api/availability','availability'),('/arbitrary/private','site')]:
            with self.subTest(path=path):
                self.assertEqual(rb.operation_kind(path),expected)

    def test_non_http_calls_pass_through_without_an_observation(self):
        called=[]
        async def app(scope,receive,send):called.append(scope['type'])
        with patch.object(rb.log,'info') as output:
            asyncio.run(rb.BudgetMiddleware(app)({'type':'websocket'},None,None))
        self.assertEqual(called,['websocket'])
        output.assert_not_called()

    def test_spoofed_response_reference_replaced_and_first_request_reported_once(self):
        sent=[]
        async def app(scope,receive,send):
            await send({'type':'http.response.start','status':409,'headers':[(b'X-Booking-Reference',b'private-spoof'),(b'content-type',b'application/json')]})
            await send({'type':'http.response.body','body':b'conflict'})
        async def send(message):sent.append(message)
        handler=rb.BudgetMiddleware(app)
        with patch.object(rb.log,'info') as output:
            for _ in range(2):
                asyncio.run(handler({'type':'http','path':'/api/company/control','state':{}},None,send))
        headers=sent[0]['headers']
        self.assertEqual(sum(k.lower()==b'x-booking-reference' for k,v in headers),1)
        self.assertNotIn(b'private-spoof',[v for k,v in headers])
        records=[json.loads(call.args[0]) for call in output.call_args_list]
        self.assertEqual([r['first_request'] for r in records],[True,False])
        self.assertTrue(all(r['outcome']=='rejected' for r in records))
        self.assertIsNone(rb.reference())

    def test_unexpected_application_failure_gets_safe_correlation_without_raw_error(self):
        async def app(*args):raise RuntimeError('private-provider-body')
        scope={'type':'http','path':'/api/internal/work','state':{}}
        diagnostic=AsyncMock(return_value='unavailable')
        with patch('appointment_system.diagnostics.record_optional',diagnostic),patch.object(rb.log,'info') as output,self.assertRaises(RuntimeError):
            asyncio.run(rb.BudgetMiddleware(app)(scope,None,None))
        record=json.loads(output.call_args.args[0])
        self.assertEqual(record['status'],503)
        self.assertEqual(record['outcome'],'recoverable')
        self.assertNotIn('private-provider-body',str(record))
        self.assertEqual(scope['state']['booking_failure_code'],'unexpected_failure')
        self.assertIsNone(rb.reference())

    def test_broken_optional_diagnostic_cannot_break_or_change_the_sent_response(self):
        sent=[]
        async def app(scope,receive,send):
            await send({'type':'http.response.start','status':503,'headers':[]})
            await send({'type':'http.response.body','body':b'safe failure'})
        async def send(message):sent.append(message)
        for failure in ('database','logger'):
            with self.subTest(failure=failure):
                diagnostic=AsyncMock(side_effect=RuntimeError('private database') if failure=='database' else None,return_value='unavailable')
                with patch('appointment_system.diagnostics.record_optional',diagnostic),patch.object(rb.log,'info',side_effect=RuntimeError('logger unavailable') if failure=='logger' else None):
                    asyncio.run(rb.BudgetMiddleware(app)({'type':'http','path':'/api/internal/run','state':{'booking_failure_code':'private untrusted value'}},None,send))
        self.assertEqual([m['status'] for m in sent if m['type']=='http.response.start'],[503,503])
        self.assertIsNone(rb.reference())

