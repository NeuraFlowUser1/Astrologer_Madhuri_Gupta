"""Later default changes cannot rewrite an accepted appointment's meeting choice."""
from uuid import uuid4
from tools.checks.sql_target import literal
from .test_sql_staff import StaffFixture, CLIENT, ORIGIN


class SavedMeetingSQL(StaffFixture):
    def accepted(self, original, current):
        self.spec['meeting'] = original
        self.set_policy(self.spec)
        booking = self.confirmed()
        self.spec['meeting'] = current
        self.set_policy(self.spec)
        return booking

    def calendar_jobs(self, booking):
        return self.db.value("SELECT coalesce(jsonb_agg(jsonb_build_object('kind',kind,'revision',booking_revision)"
            " ORDER BY booking_revision,kind),'[]') FROM appointment_system.delivery_jobs WHERE booking_id="
            + literal(booking['booking']) + " AND recipient_role='calendar';")

    def assert_preserved(self, booking, choice, state):
        saved = self.db.value("SELECT jsonb_build_object('meeting',service_snapshot->>'meeting','state',state,"
            "'revision',revision,'amount',amount_paise,'reference',request_id) FROM appointment_system.bookings WHERE id="
            + literal(booking['booking']) + ';')
        self.assertEqual(saved, {'meeting': choice, 'state': state, 'revision': 2,
                                'amount': 210000, 'reference': booking['request']})
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_observations WHERE status='refunded';"), '0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND recipient_role IN (\'client_sheet\',\'agency_sheet\');'), '2')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision=2 AND recipient_role IN (\'customer\',\'client\');'), '2')

    def test_google_move_retains_old_cleanup_and_new_meeting_after_default_becomes_internal(self):
        booking = self.accepted('google_meet', 'internal')
        operation = uuid4()
        result = self.move(booking, self.starts[2], operation=operation)
        self.assertEqual(result['code'], 'rescheduled')
        self.assertEqual(self.move(booking, self.starts[2], operation=operation), result)
        self.assertEqual(self.calendar_jobs(booking), [
            {'kind': 'booking_calendar', 'revision': 1}, {'kind': 'booking_cancelled', 'revision': 1},
            {'kind': 'booking_calendar', 'revision': 2}])
        self.assert_preserved(booking, 'google_meet', 'confirmed')

    def test_internal_move_never_invents_google_work_after_default_becomes_google(self):
        booking = self.accepted('internal', 'google_meet')
        self.assertEqual(self.move(booking, self.starts[2])['code'], 'rescheduled')
        self.assertEqual(self.calendar_jobs(booking), [])
        self.assert_preserved(booking, 'internal', 'confirmed')

    def cancel(self, booking):
        operation = uuid4()
        def perform():
            return self.staff.studio_appointment_cancel(self.session, CLIENT, ORIGIN,
                operation, booking['claim'], 1, 'Synthetic saved-choice cancellation')
        result = perform()
        self.assertEqual(result['code'], 'cancelled')
        self.assertEqual(perform(), result)

    def test_google_cancel_keeps_its_cleanup_after_default_becomes_internal(self):
        booking = self.accepted('google_meet', 'internal')
        self.cancel(booking)
        self.assertEqual(self.calendar_jobs(booking), [
            {'kind': 'booking_calendar', 'revision': 1}, {'kind': 'booking_cancelled', 'revision': 1}])
        self.assert_preserved(booking, 'google_meet', 'cancelled')

    def test_internal_cancel_never_invents_google_work_after_default_becomes_google(self):
        booking = self.accepted('internal', 'google_meet')
        self.cancel(booking)
        self.assertEqual(self.calendar_jobs(booking), [])
        self.assert_preserved(booking, 'internal', 'cancelled')
