"""Native role-protected outcomes for browser refreshes; no private note replay."""
from datetime import datetime, timedelta
from uuid import uuid4
from .test_sql_staff import StaffFixture,CLIENT,ORIGIN
from tools.checks.sql_target import literal
from .sql_store import IsolatedStore

class PendingActionsSQL(StaffFixture):
    def test_closure_result_survives_reopen_but_requires_same_actor_and_on(self):
        operation=uuid4();start=datetime.fromisoformat(self.starts[0]);end=start+timedelta(minutes=20)
        saved=self.staff.studio_calendar_close(self.session,CLIENT,ORIGIN,operation,'Synthetic private reason',start,end)
        self.assertEqual(saved['code'],'closed');claim=saved['claim_id']
        first=self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'calendar')
        self.assertEqual(first,{'code':'closed','operation_id':str(operation)})
        opened=uuid4();self.assertEqual(self.staff.studio_calendar_reopen(self.session,CLIENT,ORIGIN,opened,claim,'Synthetic reopen')['code'],'reopened')
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,opened,'calendar')['code'],'reopened')
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'calendar'),first)
        self.assertEqual(self.staff.studio_pending_result(self.session,'wrong',ORIGIN,operation,'calendar')['code'],'access_unavailable')
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,uuid4(),'calendar')['code'],'operation_not_found')
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'unknown')['code'],'invalid_request')
        self.db.sql("UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false;")
        with self.assertRaises(Exception):self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'calendar')

    def test_review_results_are_actor_bound_and_enquiry_purpose_does_not_reveal_booking_actions(self):
        operation=uuid4();item='payment:'+str(uuid4());actor="client:"+__import__('hashlib').sha256(b'123456789').hexdigest()
        self.db.sql('INSERT INTO appointment_system.staff_reviews(operation_id,item_key,revision,actor,note) VALUES ('+
            ','.join([literal(str(operation)),literal(item),'1',literal(actor),literal('Private review note')])+');')
        result=self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'inbox')
        self.assertEqual(result,{'code':'review_saved','operation_id':str(operation),'revision':1})
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'enquiry')['code'],'operation_not_found')
        self.db.sql('UPDATE appointment_system.staff_reviews SET actor='+literal('client:someone-else')+';')
        self.assertEqual(self.staff.studio_pending_result(self.session,CLIENT,ORIGIN,operation,'inbox')['code'],'operation_not_found')
        with self.assertRaises(Exception):IsolatedStore(self.db,'appointment_system_web').studio_pending_result(self.session,CLIENT,ORIGIN,operation,'inbox')
        with self.assertRaises(Exception):IsolatedStore(self.db,'abs_company').studio_pending_result(self.session,CLIENT,ORIGIN,operation,'inbox')
