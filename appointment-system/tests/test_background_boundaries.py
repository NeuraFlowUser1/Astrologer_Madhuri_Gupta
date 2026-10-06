"""Wake and optional diagnostics cannot invent success or expose private failures."""
import asyncio
import base64
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
import httpx
from starlette.requests import Request
from appointment_system import diagnostics
from appointment_system.configuration import project_id
from appointment_system.request_budget import BudgetExpired
from appointment_system.wake import WakePublisher,WAKE_URL

WAKE_KEY=base64.urlsafe_b64encode(b"W"*32).decode()

class WakeBoundaries(TestCase):
    def publisher(self,handler):
        return WakePublisher(WAKE_URL,WAKE_KEY,transport=httpx.MockTransport(handler))

    def test_exact_wake_is_posted_without_customer_information(self):
        def provider(request):
            self.assertEqual(request.method,'POST');self.assertEqual(str(request.url),WAKE_URL)
            self.assertEqual(request.content,b'{}');self.assertEqual(request.headers['authorization'],'Bearer '+WAKE_KEY)
            return httpx.Response(202,json={'application':project_id(),'queued':True})
        self.assertTrue(self.publisher(provider).publish())
        self.assertNotIn(WAKE_KEY,repr(self.publisher(provider)))

    def test_only_the_dedicated_address_is_accepted(self):
        for address in ('https://foreign.example.test/wake',WAKE_URL+'?other=1'):
            with self.subTest(address=address),self.assertRaises(ValueError):WakePublisher(address,WAKE_KEY)
        with self.assertRaises(ValueError):WakePublisher(WAKE_URL,'short')

    def test_ambiguous_or_malformed_acknowledgements_remain_pending(self):
        import json
        values=[httpx.Response(200,json={'application':project_id(),'queued':True}),
            httpx.Response(302,headers={'location':'https://foreign.example.test'}),
            httpx.Response(202,text='not json'),httpx.Response(202,content=b'x'*1025,headers={'content-type':'application/json'}),
            httpx.Response(202,content=b'not json',headers={'content-type':'application/json'}),
            httpx.Response(202,json={'application':project_id(),'queued':True},headers={'content-type':'application/json-invalid'}),
            httpx.Response(202,json={'application':'other','queued':True}),
            httpx.Response(202,json={'application':project_id(),'queued':False}),
            httpx.Response(202,json={'application':project_id(),'queued':1}),
            httpx.Response(202,json={'application':project_id(),'queued':True,'extra':1}),
            httpx.Response(202,content=('{"application":'+json.dumps(project_id())+',"queued":false,"queued":true}').encode(),headers={'content-type':'application/json'})]
        for response in values:
            with self.subTest(body=response.content):
                with self.assertLogs('appointment_system.wake',level='WARNING') as logs:
                    self.assertFalse(self.publisher(lambda request:response).publish())
                self.assertEqual(logs.output,['WARNING:appointment_system.wake:appointment_wake_pending_rescue'])

    def test_network_and_budget_failures_do_not_replace_saved_work(self):
        def provider(request):raise httpx.ReadTimeout('private diagnostic detail')
        with self.assertLogs('appointment_system.wake',level='WARNING') as logs:self.assertFalse(self.publisher(provider).publish())
        self.assertNotIn('private diagnostic',str(logs.output))
        with patch('appointment_system.wake.provider_timeout',side_effect=BudgetExpired()),self.assertLogs('appointment_system.wake'):
            self.assertFalse(self.publisher(provider).publish())

class OptionalDiagnostics(TestCase):
    def test_only_approved_codes_and_valid_references_are_recorded(self):
        request=Request({'type':'http'})
        diagnostics.note(request,'private content');self.assertNotIn('state',request.scope)
        diagnostics.note(request,'provider_rejected');self.assertEqual(request.state.booking_failure_code,'provider_rejected')
        self.assertIsNone(diagnostics.request_reference(request))
        identifier=str(uuid4());request.state.booking_reference=identifier
        self.assertEqual(diagnostics.request_reference(request),identifier)
        for value in ('private',None,True):
            request.state.booking_reference=value;self.assertIsNone(diagnostics.request_reference(request))

    def test_database_is_not_touched_after_storage_failure_or_for_private_paths(self):
        store=Mock(spec=['record_operation_incident']);base={'path':'/api/booking','app':SimpleNamespace(state=SimpleNamespace(operational_store=store))}
        cases=[(base|{'state':{'booking_failure_code':'storage_unavailable'}},1),(base,15001),
            (base|{'state':{'booking_diagnostic_skip':True}},1)]
        cases.extend((base|{'path':path},1) for path in ('/api/internal/worker/plan','/api/webhooks/payment','/api/auth/redeem','/api/company/sign-in'))
        for scope,elapsed in cases:self.assertEqual(asyncio.run(diagnostics.record_optional(scope,'identity','booking',elapsed)),'host_only')
        store.record_operation_incident.assert_not_called()
        self.assertEqual(asyncio.run(diagnostics.record_optional({},'identity','booking',1)),'host_only')

    def test_saved_diagnostics_use_bounded_time_and_allowlisted_details(self):
        from appointment_system.request_budget import remaining
        store=Mock(spec=['record_operation_incident']);identifier=str(uuid4())
        def save(*args):
            self.assertEqual(args,(identifier,'booking','request','service_unavailable',15000))
            self.assertGreater(remaining(),0);self.assertLessEqual(remaining(),3.5);return True
        store.record_operation_incident.side_effect=save
        scope={'path':'/api/booking','state':{'booking_failure_code':'private text'},'app':SimpleNamespace(state=SimpleNamespace(operational_store=store))}
        self.assertEqual(asyncio.run(diagnostics.record_optional(scope,identifier,'booking',15000)),'saved')
        store.record_operation_incident.side_effect=None;store.record_operation_incident.return_value=False
        self.assertEqual(asyncio.run(diagnostics.record_optional(scope,identifier,'booking',12)),'host_only')
        store.record_operation_incident.side_effect=RuntimeError('private detail')
        with self.assertLogs('booking.operations') as logs:
            self.assertEqual(asyncio.run(diagnostics.record_optional(scope,identifier,'booking',12)),'host_only')
        self.assertNotIn('private detail',str(logs.output))
