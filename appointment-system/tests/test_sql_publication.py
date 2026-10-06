"""Actual command/job commits and authenticated remote publication/probe boundaries."""
import hashlib,time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import httpx
from appointment_system.configuration import installation,worker_origin
from appointment_system.control_publication import Publisher,PublicationSettings
from appointment_system.projection import signature
from appointment_system.serialization import canonical,decode
from .test_sql_company import CompanyFixture
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal

class PublicationSQL(CompanyFixture):
    def setUp(self):
        super().setUp();self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        self.worker=IsolatedStore(self.db,'abs_worker');self.keys=PublicationSettings(b'P'*32,b'R'*32,worker_origin())
        self.now=int(time.time()*1000);self.remote=None;self.calls=[];self.behaviour='normal'
        self.publisher=Publisher(self.worker,self.keys,transport=httpx.MockTransport(self.provider),clock=lambda:self.now)

    def attest(self,purpose,secret,*,operation=None,nonce=None):
        facts=installation();value={'version':1,'installation_id':facts['installation_id'],'project':facts['project_id'],
          'environment':facts['environment'],'purpose':purpose,'operation_id':operation,
          'issued_at_ms':self.now,'published_at_ms':self.now,'reconcile_pending':False,'snapshot':self.remote,
          'snapshot_hash':hashlib.sha256(canonical(self.remote)).hexdigest()}
        if nonce is not None:value['nonce']=nonce
        value['signature']=signature(secret,purpose,value);return value

    def provider(self,request):
        self.calls.append(request)
        if request.method=='POST':
            body=decode(request.content);self.assertEqual(request.headers['X-Booking-Control-Signature'],signature(self.keys.publish_key,'publish',body))
            self.remote=body['snapshot']
            if self.behaviour=='new-off':self.change(False)
            ack=self.attest('publish-ack',self.keys.publish_key,operation=body['operation_id'])
            if self.behaviour=='bad-ack':ack['signature']='0'*64
            return httpx.Response(200,json=ack)
        self.assertEqual(str(request.url),installation()['origin']+'/api/service-state/probe')
        return httpx.Response(200,json=self.attest('read',self.keys.read_key,nonce=request.headers['X-Booking-State-Nonce']))

    def test_on_off_publish_and_nonce_bound_host_probe_complete_the_same_sql_operation(self):
        for enabled in (False,True,False):
            result,_=self.change(enabled);self.assertEqual(result['progress'],'accepted');self.assertEqual(self.status()['snapshot']['enabled'],enabled)
            self.assertEqual(self.publisher(),{'processed':1,'retry':False})
            self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'t' if enabled else 'f')
            self.assertEqual(self.publisher(),{'processed':0,'retry':False})
        self.assertEqual(len(self.calls),6)

    def test_invalid_ack_does_not_activate_pending_on_and_late_on_cannot_win_new_off(self):
        self.change(False);self.publisher();self.change(True)
        self.behaviour='bad-ack';result=self.publisher();self.assertTrue(result['retry'])
        self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'f')
        self.db.sql("UPDATE appointment_system.control_publications SET next_attempt_at=clock_timestamp() WHERE state='pending';")
        self.behaviour='new-off';result=self.publisher();self.assertTrue(result['retry'])
        self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'f')
        self.behaviour='normal';self.assertFalse(self.publisher()['retry']);self.assertFalse(self.remote['enabled'])

    def test_duplicate_worker_completion_serializes_before_turn_and_publication_locks(self):
        from appointment_system.worker_authority import admitted,Turn
        release='a'*64
        self.db.sql('TRUNCATE appointment_system.worker_runs CASCADE;')
        self.db.scalar('SELECT appointment_system.configure_worker_release('+literal(release)+');')
        self.change(False)
        plan=self.worker.begin_recovery_run(str(uuid4()),release,int(time.time()*1000))
        turn=self.worker.claim_recovery_turn(plan['run_id'],'control_publication',plan['generation'],release)
        self.assertEqual(turn['code'],'ok')
        authority=Turn(plan['run_id'],'control_publication',plan['generation'],release,turn['lease_token'])
        with admitted(authority):job=self.worker.claim_publication()
        self.assertIsNotNone(job)
        start=Barrier(2)
        def finish(_):
            start.wait(timeout=15)
            with admitted(authority):return self.worker.finish_publication(job,job['snapshot'])
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(finish,range(2)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.status()['progress'],'published')
        self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'f')
