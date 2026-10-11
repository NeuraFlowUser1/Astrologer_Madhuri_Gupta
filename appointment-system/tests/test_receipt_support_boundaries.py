"""Authorized direct corrections preserve audit and expose no customer secret."""
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from appointment_system.access import AccessDenied
from appointment_system.connection import StorageUnavailable
from appointment_system.contact_correction import add_staff_correction_routes

class ReceiptSupportBoundaries(TestCase):
 def setUp(self):
  self.operation,self.reference=uuid4(),uuid4()
  self.store=Mock(spec=['studio_support_change'])
  self.value={'code':'contact_corrected','operation_id':str(self.operation),'reference':str(self.reference),'revision':2}
  self.store.studio_support_change.return_value=self.value
  self.actor=Mock(return_value=('saved-session',{'role':'client'}));self.boundary,self.limit,self.wake=Mock(),Mock(),Mock(spec=['publish'])
  self.body={'operation_id':str(self.operation),'reference':str(self.reference),'expected_revision':1,'action':'contact_correction',
   'phone':'+919999999999','verified_payment_id':'pay_Synthetic','verification_confirmed':True,'reason':'Synthetic approved verification'}
  app=FastAPI()
  @app.exception_handler(AccessDenied)
  async def denied(request,error):return JSONResponse({'code':'access_unavailable'},403)
  @app.exception_handler(StorageUnavailable)
  async def unavailable(request,error):return JSONResponse({'code':'temporarily_unavailable'},503)
  add_staff_correction_routes(app,self.store,'synthetic-google-client','https://practice.example.test',self.actor,self.boundary,self.limit,self.wake)
  self.client=TestClient(app);self.addCleanup(self.client.close)
 def post(self,body=None):return self.client.post('/api/studio/appointments/support',json=self.body if body is None else body)
 def test_verified_correction_completes_directly_and_wake_failure_preserves_it(self):
  self.wake.publish.side_effect=RuntimeError('Synthetic wake failure')
  response=self.post();self.assertEqual(response.status_code,200);self.assertEqual(response.json(),self.value)
  self.store.studio_support_change.assert_called_once_with('saved-session','synthetic-google-client','https://practice.example.test',
   self.operation,self.reference,1,'contact_correction','Synthetic approved verification','pay_Synthetic',None,'+919999999999')
  for retired in ('activation_code','secret','code_digest'):self.assertNotIn(retired,response.json())
 def test_unauthorized_unverified_or_invalid_corrections_never_reach_storage(self):
  self.actor.return_value=('saved-session',{'role':'agency'});self.assertEqual(self.post().status_code,403)
  self.actor.return_value=('saved-session',{'role':'client'});self.boundary.side_effect=AccessDenied();self.assertEqual(self.post().status_code,403);self.boundary.side_effect=None
  for changes in ({'verification_confirmed':False},{'verification_confirmed':1},{'expected_revision':True},{'action':'receipt_recovery'},
   {'phone':None},{'phone':'+not-a-number'},{'email':'invalid'}):
   with self.subTest(changes=changes):self.assertEqual(self.post(self.body|changes).status_code,422)
  self.store.studio_support_change.assert_not_called();self.wake.publish.assert_not_called()
 def test_conflicts_and_unknown_replies_do_not_claim_success(self):
  for code in ('booking_unavailable','revision_changed','request_conflict','support_verification_unavailable','support_wait','invalid_change'):
   self.store.studio_support_change.return_value={'code':code};response=self.post()
   self.assertEqual(response.status_code,422 if code=='invalid_change' else 409)
  for value,status in ((None,503),({'code':'access_unavailable'},403),({'code':'unexpected'},503)):
   self.store.studio_support_change.return_value=value;self.assertEqual(self.post().status_code,status)
  self.wake.publish.assert_not_called()
