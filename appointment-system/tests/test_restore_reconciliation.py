"""Restored records cannot resume serving before fresh OFF and privacy proof."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
import httpx
from appointment_system.control_recovery import RecoverySettings,RestoreReconciliation
from appointment_system.configuration import installation,worker_origin
from appointment_system.service_control import ControlError
from appointment_system.projection import signature
from appointment_system.serialization import canonical,decode
from .test_projection import state,NOW

class RestoreReconciliationTests(TestCase):
    def setUp(self):
        self.keys=RecoverySettings(b'R'*32,b'C'*32,b'P'*32,worker_origin())
        self.operation=str(uuid4());self.external=state(True)
        self.recovered=self.external|{'enabled':False,'revision':'1','restore_generation':str(uuid4()),
            'generation_sequence':'2','activation_epoch':str(uuid4())}
        self.saved={'operation_id':self.operation,'external_snapshot':self.external,'snapshot':self.recovered}
        self.database=Mock(spec=['saved','barrier','current','claim_publication','finish_publication','claim_probe','record_probe','probe_retry','confirm'])
        self.database.saved.return_value=None;self.database.current.return_value=self.recovered
        self.database.claim_publication.return_value={'operation_id':self.operation,'lease_token':str(uuid4()),'snapshot':self.recovered}
        self.database.finish_publication.return_value=True;self.database.record_probe.return_value=True;self.database.claim_probe.return_value=None
        def barrier(operation,external):
            self.assertEqual((operation,external),(self.operation,self.external))
            self.database.saved.return_value=deepcopy(self.saved);return deepcopy(self.saved)
        self.database.barrier.side_effect=barrier
        self.database.confirm.return_value={'operation_id':self.operation,'verified':True}
        facts=installation();self.proof={'project':facts['project_id'],'environment':facts['environment'],
            'restore_generation':self.recovered['restore_generation'],'sequence':0,'head_hash':'0'*64,'unresolved':0}
        self.privacy=Mock(return_value=self.proof);self.remote=deepcopy(self.external);self.calls=[];self.lose=False
        self.restore=RestoreReconciliation(self.database,self.keys,self.privacy,transport=httpx.MockTransport(self.provider),clock=lambda:NOW)

    def attest(self,purpose,secret,*,operation=None,nonce=None,pending=False,snapshot=None):
        facts=installation();snapshot=self.remote if snapshot is None else snapshot
        body={'version':1,'installation_id':facts['installation_id'],'project':facts['project_id'],'environment':facts['environment'],
            'purpose':purpose,'operation_id':operation,'issued_at_ms':NOW,'published_at_ms':NOW,'snapshot':snapshot,
            'snapshot_hash':hashlib.sha256(canonical(snapshot)).hexdigest(),'reconcile_pending':pending}
        if nonce is not None:body['nonce']=nonce
        return body|{'signature':signature(secret,purpose,body)}

    def provider(self,request):
        self.calls.append(request.url.path)
        if request.method=='GET':
            self.assertIn(str(request.url),(worker_origin()+'/service-state',installation()['origin']+'/api/service-state/probe'))
            return httpx.Response(200,json=self.attest('read',self.keys.read_key,nonce=request.headers['X-Booking-State-Nonce']))
        body=decode(request.content);purpose=body['purpose'];self.assertIn(purpose,('reconcile','publish'))
        secret=self.keys.reconcile_key if purpose=='reconcile' else self.keys.publish_key
        self.assertEqual(request.headers['X-Booking-Control-Signature'],signature(secret,purpose,body))
        self.assertFalse(body['snapshot']['enabled']);self.remote=body['snapshot']
        if purpose=='reconcile':
            self.assertEqual(body['expected_generation'],self.external['restore_generation'])
            if self.lose:self.lose=False;raise httpx.ReadTimeout('Synthetic lost reply')
        return httpx.Response(200,json=self.attest(purpose+'-ack',secret,operation=body['operation_id'],pending=purpose=='reconcile'))

    def test_complete_restore_publishes_only_off_then_replays_privacy_before_confirmation(self):
        self.assertEqual(self.restore.run(self.operation),{'operation_id':self.operation,'verified':True,'enabled':False})
        self.assertEqual(self.calls,['/service-state','/service-control/reconcile','/service-control/publish','/api/service-state/probe','/service-state'])
        self.privacy.assert_called_once_with(self.operation,self.recovered['restore_generation'])
        self.database.confirm.assert_called_once_with(self.operation,self.recovered,self.proof);self.assertFalse(self.remote['enabled'])

    def test_lost_reconciliation_reply_resumes_the_saved_operation_and_generation(self):
        self.lose=True
        with self.assertRaisesRegex(ControlError,'restore_external_state_unavailable'):self.restore.run(self.operation)
        self.database.confirm.assert_not_called();self.privacy.assert_not_called()
        self.assertFalse(self.remote['enabled']);self.assertEqual(self.remote['revision'],'0')
        self.assertTrue(self.restore.run(self.operation)['verified']);self.database.barrier.assert_called_once()
        self.assertEqual(self.calls.count('/service-control/reconcile'),2)

    def test_shared_credentials_missing_privacy_and_invalid_operation_are_rejected_before_work(self):
        for changes in ({'read_key':b'short'},{'read_key':'x'*32},{'reconcile_key':b'R'*32},{'origin':'https://foreign.example.test'}):
            with self.subTest(changes=changes),self.assertRaises(ControlError):replace(self.keys,**changes)
        with self.assertRaisesRegex(ControlError,'restore_privacy_replay_required'):RestoreReconciliation(self.database,self.keys,None)
        for identifier in (None,True,'not-a-uuid',self.operation.upper(),'00000000-0000-0000-0000-000000000000'):
            with self.subTest(identifier=identifier),self.assertRaisesRegex(ControlError,'restore_operation_invalid'):self.restore.run(identifier)
        self.database.saved.assert_not_called()

    def test_bad_http_body_and_timeout_never_reach_a_restore_barrier(self):
        responses=[httpx.Response(403,json={}),httpx.Response(200,text='wrong content type'),
            httpx.Response(200,content=b'x'*4097,headers={'content-type':'application/json'}),
            httpx.Response(200,content=b'{"version":1,"version":1}',headers={'content-type':'application/json'}),
            httpx.Response(200,content=b'bad-json',headers={'content-type':'application/json'})]
        for response in responses:
            self.restore.transport=httpx.MockTransport(lambda request:response)
            with self.subTest(response=response.status_code),self.assertRaises(ControlError):self.restore.run(self.operation)
        def timeout(request):raise httpx.ReadTimeout('Synthetic private transport error')
        self.restore.transport=httpx.MockTransport(timeout)
        with self.assertRaisesRegex(ControlError,'restore_external_state_unavailable'):self.restore.run(self.operation)
        self.database.barrier.assert_not_called()
        self.restore.transport=httpx.MockTransport(lambda request:httpx.Response(200,json={}))
        with patch('appointment_system.control_recovery.time.monotonic',side_effect=[0,4]):
            with self.assertRaises(ControlError):self.restore.exchange('/service-state',nonce='a'*64)

    def test_signature_scope_nonce_age_and_pending_generation_are_all_checked(self):
        nonce='a'*64;good=self.attest('read',self.keys.read_key,nonce=nonce)
        self.assertEqual(self.restore.checked(good,'read',None,None,nonce),self.external)
        changes={'version':True,'installation_id':str(uuid4()),'project':'foreign','environment':'production','purpose':'publish-ack',
            'operation_id':str(uuid4()),'issued_at_ms':NOW-60001,'published_at_ms':NOW+1,'reconcile_pending':1,
            'nonce':'b'*64,'signature':'0'*64,'snapshot_hash':'0'*64}
        for name,value in changes.items():
            with self.subTest(field=name),self.assertRaises(ControlError):self.restore.checked(good|{name:value},'read',None,None,nonce)
        with self.assertRaises(ControlError):self.restore.checked(good,'read',None,self.recovered,nonce)
        with self.assertRaises(ControlError):self.restore.checked([], 'read',None,None)
        pending=self.attest('reconcile-ack',self.keys.reconcile_key,operation=self.operation,pending=True,snapshot=self.recovered|{'revision':'0'})
        self.assertEqual(self.restore.checked(pending,'reconcile-ack',self.operation,None)['revision'],'0')
        for raw in (None,self.recovered,self.recovered|{'revision':'0','enabled':True}):
            with self.subTest(snapshot=raw),self.assertRaises(ControlError):self.restore.checked(pending|{'snapshot':raw},'reconcile-ack',self.operation,None)
        bad=self.attest('read',self.keys.read_key,nonce=nonce,pending=True,snapshot=self.recovered|{'revision':'0'})
        with self.assertRaises(ControlError):self.restore.checked(bad,'read',None,None,nonce)
        completed=self.attest('reconcile-ack',self.keys.reconcile_key,operation=self.operation,snapshot=self.recovered)
        self.assertEqual(self.restore.checked(completed,'reconcile-ack',self.operation,self.recovered),self.recovered)

    def test_changed_saved_state_never_publishes_or_confirms(self):
        for mutation in ({'operation_id':str(uuid4())},{'snapshot':self.recovered|{'enabled':True}},
            {'snapshot':self.recovered|{'revision':'2'}},{'snapshot':self.recovered|{'generation_sequence':'4'}},
            {'snapshot':self.recovered|{'restore_generation':self.external['restore_generation']}}):
            self.database.saved.return_value=self.saved|mutation
            with self.subTest(mutation=mutation),self.assertRaises(ControlError):self.restore.run(self.operation)
        self.database.saved.return_value=self.saved;self.database.current.return_value=self.external
        with self.assertRaisesRegex(ControlError,'restore_saved_state_changed'):self.restore.run(self.operation)
        self.assertEqual(self.calls,[]);self.database.confirm.assert_not_called()

    def test_unconfirmed_remote_state_or_privacy_cannot_complete_restore(self):
        self.database.saved.return_value=self.saved
        with patch.object(self.restore,'exchange',return_value=[]):
            with self.assertRaisesRegex(ControlError,'restore_external_proof_invalid'):self.restore.run(self.operation)
        with patch.object(self.restore,'read',return_value=self.external):
            with self.assertRaisesRegex(ControlError,'restore_publication_unconfirmed'):self.restore.run(self.operation)
        self.database.confirm.assert_not_called()
        for proof in (None,self.proof|{'unresolved':1},self.proof|{'sequence':True},self.proof|{'head_hash':'invalid'},
                      self.proof|{'restore_generation':str(uuid4())},self.proof|{'extra':'field'}):
            self.privacy.return_value=proof
            with self.subTest(proof=proof),self.assertRaisesRegex(ControlError,'restore_privacy_replay_unconfirmed'):self.restore.run(self.operation)
        self.database.confirm.assert_not_called();self.privacy.return_value=self.proof
        for confirmation in (None,{}, {'verified':True,'operation_id':str(uuid4())}):
            self.database.confirm.return_value=confirmation
            with self.assertRaisesRegex(ControlError,'restore_completion_unconfirmed'):self.restore.run(self.operation)
