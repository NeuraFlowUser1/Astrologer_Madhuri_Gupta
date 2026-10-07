"""The real checkout coordinator crosses committed SQL and synthetic provider I/O."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock
from appointment_system.checkout import resume_checkout
from appointment_system.secret_configuration import booking_settings
from appointment_system.serialization import fingerprint
from appointment_system.razorpay import Credentials,RazorpayFailure,order_receipt
from appointment_system.recovery import Accounts
from .test_application import environment
from .test_sql_booking import BookingFixture
from .sql_store import IsolatedStore
from tools.checks.sql_target import literal


class CheckoutFlowSQL(BookingFixture):
    def prepare(self):
        self.settings=booking_settings(environment());self.secret=self.settings.receipt_key.issue()
        self.saved=self.draft();self.saved['receipt']=self.settings.receipt_key.digest(self.saved['request'],self.secret)
        self.saved['payload']['_receipt']={'format':'v1','key_id':'current'}
        self.saved['hash']=fingerprint(self.saved['payload'])
        result=self.reserve(self.saved);self.assertEqual(result['code'],'reserved',result)
        self.saved['booking']=result['booking_id']
        self.assertEqual(self.start_order(self.saved),'t');self.record_order(self.saved)
        self.store=IsolatedStore(self.db,'appointment_system_web')
        self.adapter=Mock();self.adapter.credentials=Credentials('SyntheticMerchant','live','fixture','rzp_live_synthetic','synthetic-secret')
        self.adapter.order.return_value={'id':'order_synthetic','entity':'order','amount':210000,'currency':'INR',
            'receipt':order_receipt(self.saved['booking'],'live'),'partial_payment':False,'status':'created','amount_paid':0,'amount_due':210000}
        self.adapter.order_payments.return_value={'entity':'collection','count':0,'items':[]}
        self.accounts=Accounts([self.adapter],current_versions={('SyntheticMerchant','live'):'fixture'})
        self.wake=Mock()

    def resume(self):
        return resume_checkout(self.store,self.accounts,self.settings,self.saved['request'],self.secret,self.wake)

    def payment(self,**changes):
        return {'entity':'payment','id':'pay_synthetic','order_id':'order_synthetic','amount':210000,'currency':'INR',
            'status':'captured','captured':True,'amount_refunded':0}|changes

    def test_only_current_unpaid_matching_order_can_launch_and_never_creates_another(self):
        self.prepare();result=self.resume()
        self.assertEqual(result['checkout'],{'key_id':'rzp_live_synthetic','order_id':'order_synthetic','amount_paise':210000,'currency':'INR','email_optional':False})
        self.assertNotIn('synthetic-secret',str(result));self.adapter.create_order.assert_not_called()
        self.assertEqual(self.adapter.order.call_count,1);self.assertEqual(self.adapter.order_payments.call_count,1)

    def test_overlapping_second_click_cannot_make_a_second_provider_request(self):
        self.prepare();entered,released=Event(),Event();order=dict(self.adapter.order.return_value)
        def provider(_):
            entered.set()
            if not released.wait(15):raise AssertionError('First provider request was not released')
            return order
        self.adapter.order.side_effect=provider
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.resume)
            try:
                self.assertTrue(entered.wait(10));second=pool.submit(self.resume).result(timeout=10)
                self.assertIsNone(second['checkout']);self.assertEqual(second['retry_after'],15)
            finally:released.set()
            self.assertIsNotNone(first.result(timeout=15)['checkout'])
        self.assertEqual(self.adapter.order.call_count,1)

    def test_fetched_capture_commits_confirmation_without_returning_launch_keys(self):
        self.prepare();self.adapter.order_payments.return_value={'entity':'collection','count':1,'items':[self.payment()]}
        result=self.resume();self.assertIsNone(result['checkout'])
        self.assertEqual(result['receipt']['appointment_state'],'confirmed');self.assertEqual(result['receipt']['captured_paise'],210000)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'),'1')
        self.adapter.create_order.assert_not_called()

    def test_another_appointment_follows_only_after_authoritative_settlement(self):
        self.prepare()
        self.assertNotIn('choose_new_time',self.resume()['receipt']['next_actions'])
        self.adapter.order_payments.return_value={'entity':'collection','count':1,'items':[self.payment()]}
        self.db.sql("UPDATE appointment_system.payment_orders SET resume_started_at=clock_timestamp()-interval '16 seconds';")
        settled=self.resume();self.assertIn('choose_new_time',settled['receipt']['next_actions'])
        other=self.draft(context=self.saved['context'],start=self.starts[1])
        self.assertEqual(self.reserve(other)['code'],'reserved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'2')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'),'1')
        self.adapter.create_order.assert_not_called()

    def test_foreign_order_amount_and_saved_reference_fail_closed(self):
        for changes in ({'id':'order_foreign'},{'amount':1},{'receipt':'foreign-reference'}):
            self.setUp();self.prepare();self.adapter.order.return_value.update(changes)
            with self.subTest(changes=changes):
                self.assertIsNone(self.resume()['checkout']);self.adapter.order_payments.assert_not_called()
                self.assertEqual(self.db.scalar('SELECT last_recovery_error FROM appointment_system.payment_orders;'),'payment_order_mismatch')

    def test_full_collection_and_repeated_payment_identity_never_record_partial_evidence(self):
        for items in ([{}]*100,[self.payment(),self.payment()]):
            self.setUp();self.prepare();self.adapter.order_payments.return_value={'entity':'collection','count':len(items),'items':items}
            with self.subTest(count=len(items)):
                self.assertIsNone(self.resume()['checkout'])
                self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_observations;'),'0')

    def test_provider_timeout_saves_recovery_without_replacing_the_order(self):
        self.prepare();self.adapter.order.side_effect=RazorpayFailure('payment_provider_unavailable')
        self.assertIsNone(self.resume()['checkout']);self.adapter.create_order.assert_not_called()
        self.assertEqual(self.db.scalar('SELECT last_recovery_error FROM appointment_system.payment_orders;'),'payment_provider_unavailable')
        self.wake.publish.assert_called_once()

    def test_cancellation_during_provider_read_prevents_the_old_launch(self):
        self.prepare();order=dict(self.adapter.order.return_value)
        def provider(_):
            # A committed parallel business change, never a provider transaction.
            self.db.sql('UPDATE appointment_system.bookings SET state=\'cancelled\' WHERE id='+literal(self.saved['booking'])+';')
            return order
        self.adapter.order.side_effect=provider
        self.assertIsNone(self.resume()['checkout']);self.adapter.create_order.assert_not_called()

    def test_more_than_two_observations_leave_a_durable_followup_cursor(self):
        self.prepare();items=[self.payment(id='pay_pending'+str(n),status='created',captured=False) for n in range(3)]
        self.adapter.order_payments.return_value={'entity':'collection','count':3,'items':items}
        self.assertIsNone(self.resume()['checkout'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_observations;'),'2')
        self.assertGreaterEqual(int(self.db.scalar('SELECT recovery_cursor FROM appointment_system.payment_orders;')),1)

    def test_customer_finish_cannot_finish_a_worker_owned_claim(self):
        self.prepare();self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        self.db.sql("UPDATE appointment_system.payment_orders SET next_check_at=clock_timestamp()-interval '1 second';")
        jobs=self.db.value('SELECT appointment_system.claim_payment_recovery(1);',role='abs_worker')
        self.assertEqual(len(jobs),1)
        self.assertIs(self.store.finish_checkout_resume(jobs[0],15,0,0),False)
        worker=IsolatedStore(self.db,'abs_worker')
        self.assertIs(worker.finish_payment_recovery(jobs[0],15,0,0),True)
        denied=self.db.sql("SELECT appointment_system.finish_payment_recovery("+literal(self.saved['booking'])+","+
            literal(jobs[0]['lease_token'])+",15,0,0,NULL);",role='appointment_system_web',check=False)
        self.assertNotEqual(denied.returncode,0)

    def test_off_during_provider_read_cannot_return_a_payment_launch(self):
        self.prepare();order=dict(self.adapter.order.return_value)
        def provider(_):
            self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false;')
            return order
        self.adapter.order.side_effect=provider
        result=self.resume();self.assertIsNone(result['checkout'])
        self.assertEqual(result['receipt']['customer_message_code'],'contact_support')
        self.adapter.create_order.assert_not_called()
