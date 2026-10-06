"""Simultaneous staff changes compete with real independent checkout sessions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

from tools.checks.sql_target import literal
from .test_sql_staff import StaffFixture


class StaffRacesSQL(StaffFixture):
    def saved(self, booking):
        return self.db.value("SELECT jsonb_build_object('start',starts_at::text,'revision',revision,"
            "'state',state,'amount',amount_paise) FROM appointment_system.bookings WHERE id="
            + literal(booking['booking']) + ';')

    def assert_moved_obligations(self, booking, previous_start, new_start, operation):
        audit = self.db.value("SELECT jsonb_build_object('operation',operation_id,'reason',reason,"
            "'previous',previous_revision,'revision',revision,'start',new_starts_at::text)"
            " FROM appointment_system.staff_appointment_actions WHERE booking_id=" + literal(booking['booking']) + ';')
        self.assertEqual(audit['operation'], str(operation))
        self.assertEqual(audit['reason'], 'Synthetic reschedule')
        self.assertEqual((audit['previous'], audit['revision']), (1, 2))
        self.assertEqual(datetime.fromisoformat(audit['start']), datetime.fromisoformat(new_start))
        rows = self.db.value("SELECT jsonb_agg(jsonb_build_object('kind',kind,'role',recipient_role,"
            "'revision',booking_revision,'start',payload->>'starts_at')) FROM appointment_system.delivery_jobs"
            " WHERE booking_id=" + literal(booking['booking']) + " AND (booking_revision=2 OR kind='booking_cancelled');")
        expected = {('booking_cancelled', 'calendar', 1), ('sheet_booking', 'client_sheet', 2),
            ('sheet_booking', 'agency_sheet', 2), ('booking_calendar', 'calendar', 2),
            ('booking_ack', 'customer', 2), ('booking_ack', 'client', 2)}
        self.assertEqual(len(rows), len(expected))
        self.assertEqual({(row['kind'], row['role'], row['revision']) for row in rows}, expected)
        for row in rows:
            self.assertEqual(datetime.fromisoformat(row['start']),
                datetime.fromisoformat(previous_start if row['revision'] == 1 else new_start))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_observations WHERE status='refunded';"), '0')

    def test_simultaneous_moves_have_one_revision_winner_and_one_complete_obligation_set(self):
        booking = self.confirmed()
        operations = [uuid4(), uuid4()]
        starts = self.starts[2:4]
        barrier = Barrier(2, timeout=15)
        def move(index):
            barrier.wait()
            return self.move(booking, starts[index], operation=operations[index])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(move, range(2)))
        self.assertCountEqual([row['code'] for row in results], ['rescheduled', 'revision_changed'])
        winner = next(index for index, row in enumerate(results) if row['code'] == 'rescheduled')
        state = self.saved(booking)
        self.assertEqual((state['revision'], state['state'], state['amount']), (2, 'confirmed', 210000))
        self.assertEqual(datetime.fromisoformat(state['start']), datetime.fromisoformat(starts[winner]))
        self.assertEqual(self.move(booking, starts[winner], operation=operations[winner]), results[winner])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.staff_appointment_actions;'), '1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'), '1')
        self.assert_moved_obligations(booking, self.starts[0], starts[winner], operations[winner])

    def test_new_reservation_and_staff_move_cannot_both_take_the_same_time(self):
        booking = self.confirmed()
        destination = self.starts[2]
        draft = self.draft(start=destination)
        operation = uuid4()
        barrier = Barrier(2, timeout=15)
        def compete(kind):
            barrier.wait()
            return self.move(booking, destination, operation=operation) if kind == 'move' else self.reserve(draft)
        with ThreadPoolExecutor(max_workers=2) as pool:
            moved, reserved = list(pool.map(compete, ['move', 'reserve']))
        self.assertIn((moved['code'], reserved['code']),
            [('rescheduled', 'time_unavailable'), ('time_already_reserved', 'reserved')])
        owners = self.db.value('SELECT jsonb_agg(booking_id) FROM appointment_system.slot_claims WHERE released_at IS NULL'
            ' AND starts_at=' + literal(destination) + '::timestamptz;')
        state = self.saved(booking)
        self.assertEqual((state['state'], state['amount']), ('confirmed', 210000))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '1')
        if moved['code'] == 'rescheduled':
            self.assertEqual(owners, [booking['booking']])
            self.assertEqual(state['revision'], 2)
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'), '1')
            self.assert_moved_obligations(booking, self.starts[0], destination, operation)
        else:
            self.assertEqual(owners, [reserved['booking_id']])
            self.assertEqual(state['revision'], 1)
            self.assertEqual(datetime.fromisoformat(state['start']), datetime.fromisoformat(self.starts[0]))
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.staff_appointment_actions;'), '0')
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'), '2')
            self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_revision<>1 OR kind='booking_cancelled';"), '0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_orders WHERE provider_order_id IS NOT NULL;'), '1')
