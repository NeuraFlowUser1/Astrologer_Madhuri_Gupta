"""Worker dispatch preserves lane identity, failure state and independent keys."""
import base64
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import UUID,uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from appointment_system import recovery_contract as contract
from appointment_system.configuration import installation
from appointment_system.worker_access import WorkerKey
from appointment_system.worker_authority import current

RELEASE='a'*64

class RecoveryDispatch(TestCase):
    def setUp(self):
        self.store=Mock();self.options={name:Mock() for name in ('sender','code_keys','contact_keys','google','accounts','publisher')}
        self.options['publisher'].return_value={'processed':1}

    def call(self,lane,resource,**changes):
        return contract.operation(self.store,lane,resource,**(self.options|changes))

    def test_each_resource_uses_its_own_delivery_path(self):
        cases=[('verification_email','booking_code','booking_verification_delivery.run_booking_code_once',('sender','code_keys'),{}),
          ('verification_email','enquiry_code','contact_delivery.run_contact_email_once',('sender','contact_keys'),{'kind':'verification'}),
          ('notification_email','booking','email_delivery.run_email_delivery_once',('sender',),{}),
          ('notification_email','enquiry','contact_delivery.run_contact_email_once',('sender','contact_keys'),{'kind':'notification'}),
          ('payment_events','inbox','recovery.run_payment_event_once',('accounts',),{'source':'inbox'}),
          ('payment','order','recovery.run_payment_recovery_once',('accounts',),{})]
        for lane,resource,path,names,kwargs in cases:
            with self.subTest(lane=lane,resource=resource),patch('appointment_system.'+path,return_value={'processed':1}) as action:
                self.assertEqual(self.call(lane,resource),{'processed':1})
                action.assert_called_once_with(self.store,*(self.options[name] for name in names),**kwargs)

    def test_missing_provider_authority_does_not_dispatch(self):
        cases=[('verification_email','booking_code','sender'),('verification_email','booking_code','code_keys'),
          ('verification_email','enquiry_code','contact_keys'),('notification_email','booking','sender'),
          ('notification_email','enquiry','contact_keys'),('payment_events','inbox','accounts'),('payment','order','accounts'),
          ('booking_records','calendar','google'),('enquiry_records','client_sheet','google'),('control_publication','display','publisher')]
        for lane,resource,name in cases:
            with self.subTest(lane=lane,name=name),self.assertRaises(ValueError):self.call(lane,resource,**{name:None})
        self.assertEqual(self.store.mock_calls,[])

    def test_each_email_event_keeps_its_resource(self):
        for resource,name in [('booking','reconcile_email_event'),('enquiry','reconcile_enquiry_email_event'),('verification','reconcile_booking_code_email_event')]:
            for available in (False,True):
                self.store.reset_mock();getattr(self.store,name).return_value=available
                self.assertEqual(self.call('email_events',resource),{'processed':int(available)})
                getattr(self.store,name).assert_called_once_with();self.assertEqual(len(self.store.mock_calls),1)
        with self.assertRaises(KeyError):self.call('email_events','unknown')

    def test_sheet_projection_runs_before_delivery_and_prevents_duplicate_work(self):
        for lane,audience,path in [('booking_records','booking','google_delivery.run_google_delivery_once'),('enquiry_records','enquiry','contact_delivery.run_contact_google_once')]:
            for resource in ('client_sheet','agency_sheet'):
                with self.subTest(lane=lane,resource=resource),patch('appointment_system.sheet_projection.run_projection_once',return_value={'processed':1}) as projection,patch('appointment_system.'+path,return_value={'processed':0}) as delivery:
                    self.assertEqual(self.call(lane,resource),{'processed':1});delivery.assert_not_called()
                    projection.assert_called_once_with(self.store,self.options['google'],audience,resource)
                    projection.return_value=None
                    self.assertEqual(self.call(lane,resource),{'processed':0});delivery.assert_called_once_with(self.store,self.options['google'],resource=resource)
        with patch('appointment_system.google_delivery.run_google_delivery_once',return_value={'processed':1}) as delivery:
            self.assertEqual(self.call('booking_records','calendar'),{'processed':1})
            delivery.assert_called_once_with(self.store,self.options['google'],resource='calendar')

    def test_maintenance_and_publication_remain_separate(self):
        self.assertEqual(self.call('control_publication','display'),{'processed':1});self.assertEqual(self.store.mock_calls,[])
        self.options['publisher'].assert_called_once_with()
        self.store.cleanup_temporary_records.return_value={'processed':1}
        self.assertEqual(self.call('maintenance','temporary'),{'processed':1});self.store.expire_enquiry_codes.assert_called_once_with()
        for result in (None,{}, {'processed':True},{'processed':2}):
            self.store.cleanup_temporary_records.return_value=result
            with self.subTest(result=result),self.assertRaisesRegex(ValueError,'maintenance_result_invalid'):self.call('maintenance','temporary')

class RecoveryRoutes(TestCase):
    def setUp(self):
        self.store=Mock();self.run=str(uuid4());self.generation=str(uuid4());self.lease=str(uuid4())
        self.runtime=contract.RecoveryRuntime(RELEASE);self.body=contract.TurnInput(run_id=self.run,generation=self.generation,release_digest=RELEASE)
        self.keys={name:WorkerKey(base64.urlsafe_b64encode(bytes([n])*32).decode()) for name,n in [('recovery',1),('email',2),('google',3)]}
        self.store.claim_recovery_turn.return_value={'code':'ok','resource':'booking','lease_token':self.lease}
        self.store.complete_recovery_turn.side_effect=lambda run,lane,lease,generation,release,processed,retry,attention:self.ack(lane,processed=processed,attention=attention)
        self.client=self.client_for()

    def ack(self,lane,**changes):
        f=installation()
        return dict(contract=1,application=f['project_id'],environment=f['environment'],installation_id=f['installation_id'],
            generation=self.generation,release_digest=RELEASE,run_id=self.run,lane=lane,code='evaluated-empty',evaluated_at=1,
            processed=0,remaining_due=0,next_due_at=None,attention=False)|changes

    def client_for(self,**changes):
        app=FastAPI();arguments=dict(recovery_key=self.keys['recovery'],email_key=self.keys['email'],google_key=self.keys['google'],
          sender=None,code_keys=None,contact_keys=None,google=None,accounts=None,publisher=None)|changes
        runtime=arguments.pop('runtime',self.runtime)
        contract.add_routes(app,self.store,runtime,**arguments)
        return TestClient(app,base_url=installation()['origin'])

    def post(self,lane,body=None,key='recovery',client=None):
        headers={'Authorization':'Bearer '+self.keys[key].value}
        return (client or self.client).post('/api/internal/worker/'+lane,json=body or self.body.model_dump(),headers=headers)

    def test_each_lane_requires_the_right_independent_key_and_carries_authority(self):
        def operation(store,lane,resource,**kwargs):
            self.assertEqual(current().parameters(),(self.run,lane,self.generation,RELEASE,self.lease));return {'processed':0}
        with patch.object(contract,'operation',side_effect=operation):
            for lane in contract.LANES:
                expected='email' if lane in ('verification_email','notification_email','email_events') else 'google' if lane in ('booking_records','enquiry_records') else 'recovery'
                for key in self.keys:
                    self.store.claim_recovery_turn.reset_mock();response=self.post(lane,key=key)
                    self.assertEqual(response.status_code,200 if key==expected else 401,response.text)
                    if key!=expected:self.store.claim_recovery_turn.assert_not_called()
                self.assertIsNone(current())

    def test_unavailable_invalid_or_old_authority_does_not_claim_work(self):
        for client in (self.client_for(runtime=None),self.client_for(recovery_key=None)):
            self.assertEqual(self.post('payment',client=client).status_code,503)
        for body in (self.body.model_dump()|{'run_id':'invalid'},self.body.model_dump()|{'generation':str(uuid4()).upper()},self.body.model_dump()|{'run_id':str(UUID(int=0))}):
            self.assertEqual(self.post('payment',body).status_code,422)
        self.assertEqual(self.post('payment',self.body.model_dump()|{'release_digest':'b'*64}).status_code,409)
        self.store.claim_recovery_turn.assert_not_called()
        for digest in (None,True,'a'*63,'A'*64):
            with self.assertRaises(ValueError):contract.RecoveryRuntime(digest)

    def test_plan_end_and_rejected_claim_preserve_database_response(self):
        plan={'run_id':self.run,'release_digest':RELEASE,'scheduled_at':1}
        self.store.begin_recovery_run.return_value={'run_id':self.run,'lanes':[]}
        self.assertEqual(self.post('plan',plan).json(),{'run_id':self.run,'lanes':[]})
        self.store.begin_recovery_run.return_value={'code':'run_busy'}
        self.assertEqual(self.post('plan',plan).status_code,409)
        self.store.end_recovery_run.return_value={'ended':True}
        self.assertEqual(self.post('end',{'run_id':self.run,'release_digest':RELEASE}).json(),{'ended':True})
        for chosen,expected in [({'code':'lease_busy'},'lease_busy'),({},'turn_unavailable')]:
            self.store.claim_recovery_turn.return_value=chosen
            with patch.object(contract,'operation') as operation:
                response=self.post('payment');self.assertEqual(response.status_code,409);self.assertEqual(response.json()['code'],expected);operation.assert_not_called()

    def test_retry_attention_and_saved_facts_survive_failed_turns(self):
        for result,retry,attention in [({'processed':1},False,False),({'processed':0,'state':'waiting'},True,False),
          ({'processed':1,'deferred':True},True,False),({'processed':1,'state':'attention'},False,True),({'processed':1,'attention':True},False,True)]:
            with patch.object(contract,'operation',return_value=result):
                self.assertEqual(self.post('payment').status_code,200)
                self.store.complete_recovery_turn.assert_called_with(self.run,'payment',self.lease,self.generation,RELEASE,result['processed'],retry,attention)
        for result in (None,{}, {'processed':True},{'processed':2},{'processed':0,'retry':1},{'processed':0,'attention':'yes'}):
            with self.subTest(result=result),patch.object(contract,'operation',return_value=result):
                with self.assertRaisesRegex(ValueError,'worker_result_invalid'):self.post('payment')
                self.store.complete_recovery_turn.assert_called_with(self.run,'payment',self.lease,self.generation,RELEASE,0,True,True)
                self.assertIsNone(current())
        self.store.complete_recovery_turn.side_effect=RuntimeError('secondary diagnostic failure')
        with patch.object(contract,'operation',side_effect=ValueError('original failure')):
            with self.assertRaisesRegex(ValueError,'original failure'):self.post('payment')
        self.assertIsNone(current())

    def test_malformed_or_foreign_acknowledgement_never_reports_completion(self):
        good=self.ack('payment');self.assertEqual(contract.checked_ack(good,self.body,'payment',self.runtime),good)
        invalid={'contract':True,'application':'other','environment':'other','installation_id':str(uuid4()),'release_digest':'b'*64,
          'run_id':str(uuid4()),'generation':str(uuid4()),'lane':'email_events','code':'invented','processed':True,
          'evaluated_at':-1,'remaining_due':10001,'next_due_at':True,'attention':1}
        for name,value in invalid.items():
            with self.subTest(field=name),self.assertRaisesRegex(ValueError,'worker_result_invalid'):
                contract.checked_ack(good|{name:value},self.body,'payment',self.runtime)
        with self.assertRaises(ValueError):contract.checked_ack({},self.body,'payment',self.runtime)
        self.assertEqual(contract.checked_ack(good|{'next_due_at':1},self.body,'payment',self.runtime)['next_due_at'],1)
        self.store.complete_recovery_turn.side_effect=None;self.store.complete_recovery_turn.return_value=good|{'application':'other'}
        with patch.object(contract,'operation',return_value={'processed':1}),self.assertRaisesRegex(ValueError,'worker_result_invalid'):self.post('payment')
        self.assertEqual(self.store.complete_recovery_turn.call_count,2)
