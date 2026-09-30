"""Synthetic session/role/contract checks; no external traffic."""
import unittest
from uuid import uuid4
from backend.booking_engine.tests import test_studio_calendar as calendar_fixture

class InboxTests(unittest.TestCase):
    def setUp(self):
        fixture=calendar_fixture.CalendarTests();fixture.setUp()
        self.store,self.client,self.headers=fixture.store,fixture.client,fixture.headers
        self.item='enquiry:'+str(uuid4())
    def post(self,path,body,headers=None):
        return self.client.post('/api/studio/inbox/'+path,json=body,headers=self.headers if headers is None else headers)
    def test_client_list_and_detail_use_authenticated_session(self):
        self.store.studio_inbox_list.return_value={'code':'ok','items':[]}
        self.assertEqual(self.post('list',{'view':'enquiries'}).status_code,200)
        self.store.studio_inbox_detail.return_value={'code':'ok','item':{}}
        result=self.post('detail',{'item_key':self.item});self.assertEqual(result.status_code,200)
        self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertEqual(self.store.studio_inbox_detail.call_args.args[0],self.store.studio_inbox_list.call_args.args[0])
    def test_agency_cannot_access_customer_enquiries_or_finance(self):
        self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('list',{'view':'enquiries'}).status_code,403)
        for key in [self.item,'payment:'+str(uuid4())]:
            self.assertEqual(self.post('detail',{'item_key':key}).status_code,403)
            self.assertEqual(self.post('review',{'item_key':key,'operation_id':str(uuid4()),'expected_revision':0,'note':'Checked'}).status_code,403)
        self.store.studio_inbox_detail.assert_not_called();self.store.studio_inbox_review.assert_not_called()
        self.store.studio_inbox_list.return_value={'code':'ok','items':[]}
        self.assertEqual(self.post('list',{'view':'issues'}).status_code,200)
    def test_rechecks_session_and_unknown_results_fail_closed(self):
        for code,status in [('access_unavailable',403),('surprise',503),('revision_changed',409)]:
            self.store.studio_inbox_detail.return_value={'code':code}
            self.assertEqual(self.post('detail',{'item_key':self.item}).status_code,status)
        self.assertEqual(self.post('list',{'view':'issues'},headers={'Origin':'https://evil.example'}).status_code,403)
    def test_notes_use_operation_revision_and_reject_unknown_actor_controls(self):
        body={'item_key':self.item,'operation_id':str(uuid4()),'expected_revision':0,'note':'Checked with the practice'}
        self.store.studio_inbox_review.return_value={'code':'review_saved','revision':1}
        self.assertEqual(self.post('review',body).status_code,200)
        args=self.store.studio_inbox_review.call_args.args
        self.assertEqual(str(args[3]),body['operation_id']);self.assertEqual(args[-2:],(0,body['note']))
        for change in [{'actor':'agency'},{'note':'bad\nline'},{'expected_revision':True},{'expected_revision':-1},{'note':'a'*1001}]:
            self.assertEqual(self.post('review',dict(body,**change)).status_code,422)
    def test_limits_and_revoked_session_prevent_database_call(self):
        self.store.consume_limit.return_value={'allowed':False,'retry_after':60}
        self.assertEqual(self.post('list',{'view':'issues'}).status_code,429)
        self.store.studio_inbox_list.assert_not_called()
        self.store.consume_limit.return_value={'allowed':True}
        self.store.studio_session.return_value=None
        self.assertEqual(self.post('list',{'view':'issues'}).status_code,403)

    def test_retry_does_not_allow_enquiry_or_agency_finance(self):
        body={'item_key':self.item,'operation_id':str(uuid4()),'expected_revision':0,'note':'Fixed the saved connection'}
        self.assertEqual(self.post('retry',body).status_code,403)
        body['item_key']='payment:'+str(uuid4());self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('retry',body).status_code,403)
        self.store.studio_inbox_retry.assert_not_called()
        self.store.studio_session.return_value={'role':'client'};self.store.studio_inbox_retry.return_value={'code':'retry_queued','revision':1}
        self.assertEqual(self.post('retry',body).status_code,200)
        for code in ['retry_unavailable','retry_wait','revision_changed']:
            self.store.studio_inbox_retry.return_value={'code':code};self.assertEqual(self.post('retry',body).status_code,409)

    def test_refund_resolution_requires_client_and_provider_evidence(self):
        body={'item_key':'payment:'+str(uuid4()),'operation_id':str(uuid4()),'expected_revision':0,'note':'Checked full refund evidence'}
        self.store.studio_inbox_refund_verified.return_value={'code':'refund_not_verified'}
        self.assertEqual(self.post('refund-verified',body).status_code,409)
        self.store.studio_inbox_refund_verified.return_value={'code':'refund_verified','revision':1}
        self.assertEqual(self.post('refund-verified',body).status_code,200)
        self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('refund-verified',body).status_code,403)
