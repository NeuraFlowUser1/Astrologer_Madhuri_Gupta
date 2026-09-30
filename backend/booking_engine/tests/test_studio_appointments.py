"""Synthetic staff cancellation HTTP authority and uncertain-commit checks."""
import unittest
from uuid import uuid4
import test_studio_calendar as calendar
from backend.booking_engine.connection import StorageUnavailable

class AppointmentTests(unittest.TestCase):
    setUp=calendar.CalendarTests.setUp
    def post(self,path,body,headers=None):
        return self.client.post('/api/studio/appointments/'+path,json=body,headers=self.headers if headers is None else headers)
    def test_private_detail_and_cancel_contract(self):
        claim=str(uuid4());self.store.studio_appointment_detail.return_value={'code':'ok'}
        result=self.post('detail',{'claim_id':claim});self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')
        body={'claim_id':claim,'operation_id':str(uuid4()),'expected_revision':1,'reason':'Customer requested cancellation'}
        self.store.studio_appointment_cancel.return_value={'code':'cancelled','revision':2}
        self.assertEqual(self.post('cancel',body).status_code,200)
        args=self.store.studio_appointment_cancel.call_args.args
        self.assertEqual(str(args[3]),body['operation_id']);self.assertEqual(args[-2:],(1,body['reason']))
    def test_agency_wrong_origin_and_revoked_denied(self):
        body={'claim_id':str(uuid4()),'operation_id':str(uuid4()),'expected_revision':1,'reason':'Customer request'}
        self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('cancel',body).status_code,403)
        self.assertEqual(self.post('detail',{'claim_id':body['claim_id']}).status_code,403)
        self.store.studio_session.return_value={'role':'client'}
        self.assertEqual(self.post('cancel',body,{'Origin':'https://evil.example'}).status_code,403)
        self.store.studio_session.return_value=None
        self.assertEqual(self.post('cancel',body).status_code,403);self.store.studio_appointment_cancel.assert_not_called()
    def test_invalid_requests_conflicts_and_unknown_commit(self):
        body={'claim_id':str(uuid4()),'operation_id':str(uuid4()),'expected_revision':1,'reason':'Customer request'}
        for change in [{'expected_revision':True},{'expected_revision':0},{'reason':'bad\nline'},{'actor':'client'},{'refund':True}]:
            self.assertEqual(self.post('cancel',dict(body,**change)).status_code,422)
        for code,status in [('revision_changed',409),('appointment_unavailable',409),('request_conflict',409),('access_unavailable',403),('surprise',503)]:
            self.store.studio_appointment_cancel.return_value={'code':code};self.assertEqual(self.post('cancel',body).status_code,status)
        self.store.studio_appointment_cancel.side_effect=StorageUnavailable('private failure')
        result=self.post('cancel',body);self.assertEqual(result.status_code,503);self.assertNotIn('private failure',result.text)
    def test_rate_limit_prevents_mutation(self):
        self.store.consume_limit.return_value={'allowed':False,'retry_after':60}
        self.assertEqual(self.post('cancel',{'claim_id':str(uuid4()),'operation_id':str(uuid4()),'expected_revision':1,'reason':'Customer request'}).status_code,429)
        self.store.studio_appointment_cancel.assert_not_called()

    def test_reschedule_validation_authority_and_conflicts(self):
        body={'claim_id':str(uuid4()),'operation_id':str(uuid4()),'expected_revision':1,'reason':'Customer requested a different time','starts_at':'2026-10-02T10:00:00+05:30'}
        self.store.studio_appointment_reschedule.return_value={'code':'rescheduled','revision':2}
        self.assertEqual(self.post('reschedule',body).status_code,200)
        self.assertEqual(self.store.studio_appointment_reschedule.call_args.args[-1].isoformat(),body['starts_at'])
        for start in ['2026-10-02T10:00:00','2026-10-02T10:00:01+05:30','invalid']:
            self.assertEqual(self.post('reschedule',dict(body,starts_at=start)).status_code,422)
        for code in ['time_unavailable','time_already_reserved','late_reschedule_used','revision_changed']:
            self.store.studio_appointment_reschedule.return_value={'code':code}
            self.assertEqual(self.post('reschedule',body).status_code,409)
        self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('reschedule',body).status_code,403)

    def test_support_lookup_is_private_and_strict(self):
        body={'reference':str(uuid4())};self.store.studio_booking_lookup.return_value={'code':'ok'}
        result=self.post('lookup',body);self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertEqual(self.post('lookup',{'email':'person@example.com'}).status_code,422)
        self.store.studio_session.return_value={'role':'agency'}
        self.assertEqual(self.post('lookup',body).status_code,403)
