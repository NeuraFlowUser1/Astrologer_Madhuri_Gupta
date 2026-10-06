"""First display setup retains SQL state and proves the signed OFF result."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
import httpx
from appointment_system.control_recovery import ProjectionInitialization
from appointment_system.configuration import worker_origin
from appointment_system.service_control import ControlError
from appointment_system.serialization import decode
from appointment_system.projection import signature
from . import test_restore_reconciliation as restoration

class ProjectionInitializationTests(TestCase):
    attest=restoration.RestoreReconciliationTests.attest
    def setUp(self):
        restoration.RestoreReconciliationTests.setUp(self)
        self.current=self.external|{'enabled':False,'generation_sequence':'1','revision':'3'}
        self.database.current.return_value=self.current
        self.remote=None;self.saved_body=None;self.lose=False;self.change=False;self.bad=None
        self.initializer=ProjectionInitialization(self.database,self.keys,transport=httpx.MockTransport(self.provider),clock=lambda:self.restore.clock())
    def provider(self,request):
        self.calls.append(request.url.path)
        self.assertEqual(str(request.url).split('/service-')[0],worker_origin())
        if request.method=='GET':
            return httpx.Response(200,json=self.attest('read',self.keys.read_key,nonce=request.headers['X-Booking-State-Nonce']))
        body=decode(request.content)
        self.assertEqual(body['action'],'initialize');self.assertIsNone(body['expected_generation'])
        self.assertEqual(body['snapshot'],self.current)
        self.assertEqual(request.headers['X-Booking-Control-Signature'],signature(self.keys.reconcile_key,'reconcile',body))
        if self.saved_body is not None and body!=self.saved_body:return httpx.Response(409,json={'code':'state_operation_conflict'})
        self.saved_body=deepcopy(body);self.remote=deepcopy(body['snapshot'])
        if self.lose:self.lose=False;raise httpx.ReadTimeout('Synthetic lost reply')
        if self.change:self.database.current.return_value=self.current|{'revision':'4'}
        value=self.attest('reconcile-ack',self.keys.reconcile_key,operation=body['operation_id'])
        if self.bad:value.update(self.bad)
        return httpx.Response(200,json=value)
    def test_initial_off_setting_retains_first_later_and_large_revisions(self):
        for revision in ('1','3','9007199254740993'):
            with self.subTest(revision=revision):
                self.current=self.current|{'revision':revision};self.database.current.return_value=self.current;self.saved_body=None
                self.assertEqual(self.initializer.run(self.operation),{'operation_id':self.operation,'verified':True,'enabled':False})
                self.assertEqual(self.remote,self.current)
        self.database.barrier.assert_not_called();self.database.confirm.assert_not_called();self.privacy.assert_not_called()
        self.database.claim_publication.assert_not_called()
    def test_lost_reply_reuses_exact_operation_and_never_resets_the_generation(self):
        self.lose=True
        with self.assertRaisesRegex(ControlError,'restore_external_state_unavailable'):self.initializer.run(self.operation)
        self.assertTrue(self.initializer.run(self.operation)['verified'])
        self.assertEqual(self.remote,self.current)
        with self.assertRaises(ControlError):self.initializer.run(str(uuid4()))
    def test_on_later_generation_foreign_identity_and_invalid_operations_refuse_before_network(self):
        for value in (self.current|{'enabled':True},self.current|{'generation_sequence':'2'},self.current|{'installation_id':str(uuid4())}):
            self.database.current.return_value=value
            with self.assertRaises(ControlError):self.initializer.run(self.operation)
        for operation in (None,True,'bad','00000000-0000-0000-0000-000000000000',self.operation.upper()):
            with self.assertRaises(ControlError):self.initializer.run(operation)
        self.assertEqual(self.calls,[])
    def test_tampered_pending_and_foreign_acknowledgements_never_confirm(self):
        for change in ({'signature':'0'*64},{'reconcile_pending':True},{'operation_id':str(uuid4())}):
            self.bad=change
            with self.assertRaises(ControlError):self.initializer.run(self.operation)
    def test_concurrent_sql_change_is_reported_without_overwriting_it(self):
        self.change=True
        with self.assertRaisesRegex(ControlError,'initial_projection_state_changed'):self.initializer.run(self.operation)
        self.assertEqual(self.database.current.return_value['revision'],'4')
        self.assertFalse(self.remote['enabled']);self.database.barrier.assert_not_called()
    def test_unknown_http_result_or_transport_error_is_never_reported_as_success(self):
        self.initializer.transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'code':'private'}))
        with self.assertRaisesRegex(ControlError,'restore_external_state_unavailable'):self.initializer.run(self.operation)
