"""Real staff capacity changes, idempotency, configured hours and private OFF settlement."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4
from appointment_system.company_auth import password_hash
from .test_sql_booking import BookingFixture
from tools.checks.sql_target import literal
from .sql_store import IsolatedStore

CLIENT='123456789-syntheticclient.apps.googleusercontent.com'
ORIGIN='https://practice.example.test'

class StaffFixture(BookingFixture):
    def setUp(self):
        super().setUp()
        for role,purpose in [('abs_staff','staff'),('abs_company','company')]:
            self.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')
        self.db.sql("TRUNCATE appointment_system.studio_sessions CASCADE;"
            "INSERT INTO appointment_system.studio_identities(role,subject) VALUES('client','123456789') ON CONFLICT(role) DO UPDATE SET subject=excluded.subject;")
        self.session=uuid4().hex*2
        self.db.sql('INSERT INTO appointment_system.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES ('+
            literal(self.session)+",'client','123456789',"+literal(CLIENT)+','+literal(ORIGIN)+",clock_timestamp()+interval '1 hour');")
        self.staff=IsolatedStore(self.db,'abs_staff')

    def confirmed(self,**changes):
        booking=self.booking(**changes);self.assertEqual(self.start_order(booking),'t');self.assertEqual(self.record_order(booking),'ready')
        self.assertEqual(self.capture(booking),'confirmed')
        booking['claim']=self.db.scalar('SELECT id::text FROM appointment_system.slot_claims WHERE booking_id='+literal(booking['booking'])+';')
        return booking

    def move(self,booking,start,*,operation=None,revision=1,store=None,session=None,origin=ORIGIN):
        return (store or self.staff).studio_appointment_reschedule(session or self.session,CLIENT,origin,
            uuid4() if operation is None else operation,booking['claim'],revision,'Synthetic reschedule',datetime.fromisoformat(start))

class StaffSQL(StaffFixture):
    def test_reschedule_uses_accepted_duration_and_preserves_all_record_fields_after_service_retirement(self):
        booking=self.confirmed(notes='Saved preparation',birth_place='Saved location')
        self.spec['services'][0]['enabled']=False;self.spec['services'][0]['duration_minutes']=60;self.set_policy(self.spec)
        changed=self.move(booking,self.starts[2]);self.assertEqual(changed['code'],'rescheduled')
        snapshot=self.db.value('SELECT appointment_system.booking_snapshot('+literal(booking['booking'])+');')
        self.assertEqual((datetime.fromisoformat(snapshot['ends_at'])-datetime.fromisoformat(snapshot['starts_at'])).total_seconds(),1800)
        self.assertEqual(snapshot['preparation']['notes'],'Saved preparation');self.assertEqual(snapshot['payment_reference'],'pay_synthetic')
        self.assertEqual(snapshot['request_id'],booking['request']);self.assertEqual(snapshot['currency'],'INR')

    def test_two_moves_from_same_revision_cannot_both_win_and_replay_keeps_same_result(self):
        booking=self.confirmed();operation=uuid4();first=self.move(booking,self.starts[2],operation=operation)
        self.assertEqual(first['code'],'rescheduled');self.assertEqual(self.move(booking,self.starts[2],operation=operation),first)
        self.assertEqual(self.move(booking,self.starts[3],operation=operation)['code'],'request_conflict')
        self.assertEqual(self.move(booking,self.starts[3])['code'],'revision_changed')

    def test_blocked_hours_and_expired_claims_are_handled_without_clearing_foreign_contexts(self):
        booking=self.confirmed();held=self.booking(start=self.starts[2])
        self.assertEqual(self.move(booking,self.starts[2])['code'],'time_already_reserved')
        self.db.sql('UPDATE appointment_system.bookings SET created_at=clock_timestamp()-interval \'15 minutes\',hold_expires_at=clock_timestamp()-interval \'1 second\' WHERE id='+literal(held['booking'])+';')
        self.assertEqual(self.move(booking,self.starts[2])['code'],'rescheduled')
        self.assertEqual(self.db.scalar('SELECT active_checkout_id::text FROM appointment_system.checkout_contexts WHERE id='+literal(held['context'])+';'),held['booking'])

    def test_cancel_replay_releases_capacity_once_and_never_creates_a_refund(self):
        booking=self.confirmed();operation=uuid4()
        def cancel():return self.staff.studio_appointment_cancel(self.session,CLIENT,ORIGIN,operation,booking['claim'],1,'Synthetic cancellation')
        first=cancel();self.assertEqual(first['code'],'cancelled');self.assertEqual(cancel(),first)
        self.assertEqual(self.db.scalar('SELECT cancelled_at IS NOT NULL FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'t')
        self.assertEqual(self.db.scalar('SELECT released_at IS NOT NULL FROM appointment_system.slot_claims WHERE id='+literal(booking['claim'])+';'),'t')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'),'1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_observations WHERE status='refunded';"),'0')

    def test_month_marks_confirmed_days_and_day_view_uses_appointment_time_not_buffer_time(self):
        self.spec['buffer_before_minutes']=15;self.set_policy(self.spec)
        booking=self.confirmed();start=datetime.fromisoformat(self.starts[0]);day=start.date()
        result=self.staff.studio_calendar_month(self.session,CLIENT,ORIGIN,day)
        marker=next(row for row in result['days'] if row['date']==str(day));self.assertEqual(marker['appointments'],1)
        row=self.staff.studio_calendar_list(self.session,CLIENT,ORIGIN,day,None)['items'][0]
        self.assertEqual(datetime.fromisoformat(row['starts_at']),start)

    def test_closure_race_has_one_winner_and_cannot_overlap_confirmed_appointment(self):
        booking=self.confirmed();start=datetime.fromisoformat(self.starts[0]);end=datetime.fromisoformat(self.starts[1])
        result=self.staff.studio_calendar_close(self.session,CLIENT,ORIGIN,uuid4(),'Synthetic absence',start,end)
        self.assertEqual(result['code'],'time_already_reserved')
        start=datetime.fromisoformat(self.starts[4]);end=datetime.fromisoformat(self.starts[5])
        def close(_):return self.staff.studio_calendar_close(self.session,CLIENT,ORIGIN,uuid4(),'Synthetic absence',start,end)
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(close,range(8)))
        self.assertEqual(sum(row['code']=='closed' for row in results),1)
        claim=next(row['claim_id'] for row in results if row['code']=='closed');operation=uuid4()
        opened=self.staff.studio_calendar_reopen(self.session,CLIENT,ORIGIN,operation,claim,'Synthetic reopening')
        self.assertEqual(opened['code'],'reopened')
        self.assertEqual(self.staff.studio_calendar_reopen(self.session,CLIENT,ORIGIN,operation,claim,'Synthetic reopening')['code'],'existing')

    def test_password_company_can_resolve_paid_appointment_off_but_client_cannot(self):
        booking=self.confirmed();token=uuid4().hex*2;csrf=uuid4().hex*2
        self.db.sql('TRUNCATE appointment_system.company_login_attempts;TRUNCATE appointment_system.control_company_sessions;')
        self.db.scalar("SELECT appointment_system.provision_company_password('company.owner',"+literal(password_hash('Synthetic company password for tests'))+');')
        attempt=self.db.value("SELECT appointment_system.company_login_begin('company.owner',"+literal(uuid4().hex*2)+','+literal(hashlib.sha256(b'company.owner').hexdigest())+');',role='abs_company')
        self.assertEqual(self.db.scalar('SELECT appointment_system.company_login_finish('+literal(attempt['attempt_id'])+','+str(attempt['credential_revision'])+',true,'+literal(token)+','+literal(csrf)+');',role='abs_company'),'t')
        self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false;')
        with self.assertRaises(AssertionError):self.move(booking,self.starts[2])
        company=IsolatedStore(self.db,'abs_company')
        result=self.move(booking,self.starts[2],store=company,session=token,origin=ORIGIN+'/company/booking-support')
        self.assertEqual(result['code'],'rescheduled')

    def test_late_move_keeps_original_deadline_and_does_not_apply_new_booking_horizon(self):
        booking=self.confirmed()
        self.db.sql('UPDATE appointment_system.bookings SET starts_at=clock_timestamp()+interval \'6 hours\','
            'ends_at=clock_timestamp()+interval \'6 hours 30 minutes\',original_starts_at=clock_timestamp()+interval \'6 hours\' WHERE id='+literal(booking['booking'])+';'
            'UPDATE appointment_system.slot_claims SET starts_at=(SELECT starts_at FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+'),'
            'ends_at=(SELECT ends_at FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+') WHERE id='+literal(booking['claim'])+';')
        # A fixed today+13 lands on the closed Sunday once every week. Select
        # an open day beyond the ordinary horizon and within the saved allowance.
        # Keep the real current-hours rule; do not open Sunday to satisfy a test.
        start=self.db.scalar("WITH observed AS (SELECT clock_timestamp() AS instant), candidate AS ("
            "SELECT offered.starts_at FROM observed CROSS JOIN generate_series(11,13) AS offset_day "
            "CROSS JOIN LATERAL appointment_system.schedule_starts(appointment_system.current_business(),30,"
            "(instant AT TIME ZONE 'Asia/Kolkata')::date+offset_day,instant,instant+interval '14 days 6 hours') offered) "
            "SELECT starts_at::text FROM candidate ORDER BY starts_at LIMIT 1;")
        self.assertTrue(start)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.schedule_starts(appointment_system.current_business(),30,"
            "("+literal(start)+"::timestamptz AT TIME ZONE 'Asia/Kolkata')::date,clock_timestamp());"),'0')
        result=self.move(booking,start);self.assertEqual(result['code'],'rescheduled')
        self.assertEqual(self.db.scalar('SELECT reschedule_deadline_at=original_starts_at+interval \'14 days\' FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'t')
        self.assertEqual(self.db.scalar('SELECT late_exception FROM appointment_system.staff_appointment_actions WHERE booking_id='+literal(booking['booking'])+';'),'t')

    def test_current_business_hours_and_notice_apply_to_moves_as_well_as_new_bookings(self):
        booking=self.confirmed();self.spec['weekly_windows']=[];self.set_policy(self.spec)
        self.assertEqual(self.move(booking,self.starts[2])['code'],'time_unavailable')
        self.assertEqual(self.db.scalar('SELECT revision FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'1')

    def test_unknown_original_time_cannot_create_a_new_late_move_entitlement(self):
        booking=self.confirmed()
        self.db.sql('UPDATE appointment_system.bookings SET starts_at=clock_timestamp()+interval \'6 hours\','
            'ends_at=clock_timestamp()+interval \'6 hours 30 minutes\',original_starts_at=NULL WHERE id='+literal(booking['booking'])+';')
        self.assertEqual(self.move(booking,self.starts[2])['code'],'original_time_review_required')
        self.assertEqual(self.db.scalar('SELECT revision FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'1')
        self.db.sql('UPDATE appointment_system.bookings SET reschedule_deadline_at=clock_timestamp()+interval \'13 days\' WHERE id='+literal(booking['booking'])+';')
        self.assertEqual(self.move(booking,self.starts[2])['code'],'rescheduled')

    def test_saved_used_late_allowance_cannot_be_reset_by_missing_legacy_history(self):
        booking=self.confirmed()
        self.db.sql('UPDATE appointment_system.bookings SET starts_at=clock_timestamp()+interval \'6 hours\','
            'ends_at=clock_timestamp()+interval \'6 hours 30 minutes\','
            'preparation=preparation||\'{"_legacy_late_reschedule_used":true}\'::jsonb WHERE id='+literal(booking['booking'])+';')
        self.assertEqual(self.move(booking,self.starts[2])['code'],'late_reschedule_used')
        self.assertEqual(self.db.scalar('SELECT revision FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'1')
