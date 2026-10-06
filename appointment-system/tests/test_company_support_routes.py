"""Company support keeps private session authority separate from public booking."""
import hashlib
import hmac
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.company_support import router
from appointment_system.credentials import ReceiptKeys
from appointment_system.errors import Rejected
from appointment_system.service_control import COOKIE,ORIGIN,ControlError
from appointment_system.receipt_recovery import recovery_code,code_digest
from .test_keys import ring

class CompanySupportRoutes(TestCase):
    def setUp(self):
        self.store=Mock(spec=['_call','studio_time_context','studio_resolve_time','studio_action_result','recovery_protection'])
        self.database=Mock(spec=['call']);self.database.call.return_value=True
        self.settings=SimpleNamespace(digest=lambda purpose,value:hmac.new(b'C'*32,(purpose+':'+value).encode(),hashlib.sha256).hexdigest(),google_client_id='synthetic-client')
        self.receipt=ReceiptKeys(ring());self.wake=Mock(spec=['publish']);self.token='x'*43
        self.headers={'Origin':ORIGIN,'X-Company-CSRF':self.settings.digest('csrf',self.token)}
        self.client=self.client_for();self.reference=str(uuid4());self.operation=str(uuid4());self.claim=str(uuid4())
        self.store._call.return_value={'code':'ok'}
        self.store.recovery_protection.return_value=None

    def client_for(self,**changes):
        values=dict(settings=self.settings,store=self.store,receipt_key=self.receipt,wake=self.wake,database=self.database)|changes
        app=FastAPI();app.include_router(router(**values))
        @app.exception_handler(ControlError)
        async def control_error(request,error):return JSONResponse({'code':error.code},error.status)
        @app.exception_handler(Rejected)
        async def rejected(request,error):return JSONResponse(error.public(),error.status)
        client=TestClient(app,base_url=ORIGIN);client.cookies.set(COOKIE,self.token);return client

    def post(self,name,body,headers=None):
        return self.client.post('/api/company/support/'+name,json=body,headers=self.headers if headers is None else headers)

    def test_sessions_missing_configuration_and_forged_browser_requests_cannot_reach_actions(self):
        for client,status in [(self.client_for(settings=None),503),(self.client_for(database=None),503)]:
            self.assertEqual(client.get('/api/company/support/status').status_code,status)
        anonymous=self.client_for();anonymous.cookies.clear()
        self.assertEqual(anonymous.get('/api/company/support/status').status_code,401)
        self.database.call.return_value=False
        self.assertEqual(self.client.get('/api/company/support/status').status_code,401)
        self.database.call.return_value=True
        for headers in ({},self.headers|{'Origin':'https://foreign.example.test'},self.headers|{'X-Company-CSRF':'wrong'},
            self.headers|{'X-Company-CSRF':'f'*64},self.headers|{'Content-Encoding':'gzip'},self.headers|{'Content-Type':'text/plain'}):
            response=self.post('lookup',{'reference':self.reference},headers)
            self.assertIn(response.status_code,(403,422),response.text)
        self.store._call.assert_not_called();self.wake.publish.assert_not_called()

    def test_status_and_operation_results_are_private_and_recheck_the_session(self):
        self.store._call.return_value={'code':'ok','items':[]}
        result=self.client.get('/api/company/support/status');self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['csrf_token'],self.headers['X-Company-CSRF']);self.assertIn('no-store',result.headers['cache-control'])
        self.database.call.assert_called()
        for value,expected in [(None,503),({'code':'access_unavailable'},401),({'code':'please_wait'},409)]:
            self.store._call.return_value=value;response=self.client.get('/api/company/support/status')
            self.assertEqual(response.status_code,expected)
        for value,expected in [(None,503),({'code':'access_unavailable'},401),({'code':'unexpected'},503),({'code':'operation_not_found'},200)]:
            self.store.studio_action_result.return_value=value
            self.assertEqual(self.client.get('/api/company/support/actions/'+self.operation).status_code,expected)

    def test_lookup_and_detail_never_wake_or_create_customer_work(self):
        for name,body in [('lookup',{'reference':self.reference}),('detail',{'claim_id':self.claim})]:
            result=self.post(name,body);self.assertEqual(result.status_code,200)
            statement,args=self.store._call.call_args.args
            self.assertIn('control_obligation_action',statement);self.assertEqual(args[2:4],('synthetic-client',name));self.assertEqual(args[4].obj,body)
        self.wake.publish.assert_not_called()
        for route in ('create','checkout','refund','booking'):
            self.assertEqual(self.post(route,{}).status_code,404)

    def test_accepted_actions_keep_operation_revision_and_reason_and_wake_failures_do_not_undo_them(self):
        base={'operation_id':self.operation,'expected_revision':1,'reason':'Synthetic reviewed obligation'}
        cases=[('cancel',base|{'claim_id':self.claim},'cancelled'),
          ('reschedule',base|{'claim_id':self.claim,'starts_at':'2026-10-09T10:00:00+05:30'},'rescheduled'),
          ('verified-refund',base|{'case_id':str(uuid4())},'refund_verified'),
          ('resource-reviewed',base|{'case_id':str(uuid4())},'resource_reviewed')]
        self.wake.publish.side_effect=RuntimeError('Private failure must not erase saved action')
        for name,body,code in cases:
            self.store._call.return_value={'code':code};response=self.post(name,body)
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json(),{'code':code})
            saved=self.store._call.call_args.args[1][4].obj
            self.assertEqual(saved['operation_id'],self.operation);self.assertEqual(saved['expected_revision'],1);self.assertEqual(saved['reason'],base['reason'])
        self.assertEqual(self.wake.publish.call_count,4)
        self.store._call.return_value={'code':'revision_changed'};self.wake.reset_mock()
        self.assertEqual(self.post('cancel',cases[0][1]).status_code,409);self.wake.publish.assert_not_called()

    def test_time_context_uses_private_company_audience(self):
        self.store.studio_time_context.return_value={'code':'ok','timezone':'Asia/Kolkata'}
        self.assertEqual(self.post('time-context',{}).status_code,200)
        token,client,audience=self.store.studio_time_context.call_args.args
        self.assertEqual((token,client,audience),(self.settings.digest('session',self.token),'synthetic-client',ORIGIN+'/company/booking-support'))
        self.store.studio_resolve_time.return_value={'code':'ok','starts_at':'2026-10-09T04:30:00Z'}
        self.assertEqual(self.post('resolve-time',{'local':'2026-10-09T10:00','timezone':'Asia/Kolkata'}).status_code,200)
        self.store.studio_resolve_time.assert_called_once_with(token,client,audience,'2026-10-09T10:00','Asia/Kolkata')

    def support(self):
        return {'operation_id':self.operation,'reference':self.reference,'expected_revision':1,'action':'receipt_recovery',
            'verified_payment_id':'pay_Synthetic','verification_confirmed':True,'reason':'Synthetic verified customer support'}

    def test_recovery_code_is_reproducible_without_saving_or_returning_receipt_secrets(self):
        self.store._call.return_value={'code':'support_saved','active':True,'reference':self.reference}
        result=self.post('support',self.support());self.assertEqual(result.status_code,200,result.text)
        code=recovery_code(self.receipt,self.operation,self.reference,key_id=self.receipt.ring.active)
        self.assertEqual(result.json()['activation_code'],code)
        data=self.store._call.call_args.args[1][4].obj
        self.assertEqual(data['code_digest'],code_digest(self.receipt,self.reference,code,key_id=self.receipt.ring.active))
        self.assertNotIn('activation_code',data);self.assertNotIn('secret',data)
        self.store.recovery_protection.return_value={'format':'v1','key_id':self.receipt.ring.active}
        self.store.studio_action_result.return_value={'code':'support_saved','active':True,'reference':self.reference}
        replay=self.client.get('/api/company/support/actions/'+self.operation)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['activation_code'],code)
        self.store.studio_action_result.return_value={'code':'support_saved','active':False,'reference':self.reference}
        self.assertNotIn('activation_code',self.client.get('/api/company/support/actions/'+self.operation).json())
        self.store._call.return_value={'code':'support_saved','active':False}
        self.assertIsNone(self.post('support',self.support()).json()['activation_code'])
        self.store._call.return_value={'code':'revision_changed'}
        self.assertEqual(self.post('support',self.support()).status_code,409)

    def test_unverified_support_and_invalid_changes_do_not_generate_codes(self):
        for changed in ({'verification_confirmed':False},{'verification_confirmed':1},{'verified_payment_id':'wrong'},
            {'action':'contact_correction'}, {'email':'synthetic@example.test'},{'expected_revision':True}):
            self.assertEqual(self.post('support',self.support()|changed).status_code,422)
        self.store.recovery_protection.assert_not_called();self.store._call.assert_not_called()

    def test_company_shell_and_script_have_no_customer_content_or_cache(self):
        for path in ('/company/booking-support','/api/company/support.js'):
            response=self.client.get(path);self.assertEqual(response.status_code,200)
            self.assertIn('no-store',response.headers['cache-control']);self.assertNotIn(self.token,response.text)

    def test_company_support_label_uses_this_installation_and_escapes_markup(self):
        for project in ('003','004'):
            with patch('appointment_system.company_support.label',return_value='Practice <script>'),patch('appointment_system.company_support.project_id',return_value=project):
                response=self.client.get('/company/booking-support')
            self.assertEqual(response.status_code,200)
            self.assertIn('Practice &lt;script&gt;',response.text)
            self.assertIn('Project '+project,response.text)
            self.assertNotIn('Practice <script>',response.text)
            self.assertNotIn('CLIENT_NAME',response.text)
