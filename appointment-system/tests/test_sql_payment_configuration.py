"""Account retirement never drops ambiguous money; meetings follow the saved choice."""
from concurrent.futures import ThreadPoolExecutor
from .test_sql_booking import BookingFixture
from tools.checks.sql_target import literal

class PaymentConfigurationSQL(BookingFixture):
    def change_account(self):
        self.db.scalar("SELECT appointment_system.configure_payment_account('ReplacementSyntheticMerchant','live','replacement');")

    def test_account_change_releases_only_unattempted_intents_and_their_own_context_pointer(self):
        booking=self.booking();self.change_account()
        self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'expired')
        self.assertEqual(self.db.scalar('SELECT active_checkout_id IS NULL FROM appointment_system.checkout_contexts WHERE id='+literal(booking['context'])+';'),'t')
        self.assertEqual(self.db.scalar('SELECT resolution FROM appointment_system.payment_orders WHERE booking_id='+literal(booking['booking'])+';'),'never_attempted_abandoned')
        self.assertEqual(self.start_order(booking),'f')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE booking_id='+literal(booking['booking'])+' AND released_at IS NULL;'),'0')

    def test_attempted_unknown_order_keeps_identity_and_capacity_for_read_only_recovery(self):
        booking=self.booking();self.assertEqual(self.start_order(booking),'t');self.record_order(booking,None)
        self.change_account()
        self.assertEqual(self.db.scalar('SELECT state FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'held')
        saved=self.db.value('SELECT to_jsonb(p) FROM appointment_system.payment_orders p WHERE booking_id='+literal(booking['booking'])+';')
        self.assertEqual((saved['merchant_id'],saved['credential_version'],saved['state']),('SyntheticMerchant','fixture','creation_unknown'))
        self.assertIsNone(saved['resolved_at']);self.assertEqual(self.start_order(booking),'f')
        self.assertEqual(self.db.scalar('SELECT active_checkout_id::text FROM appointment_system.checkout_contexts WHERE id='+literal(booking['context'])+';'),booking['booking'])

    def test_reapplying_same_owned_account_preserves_an_unattempted_intent(self):
        booking=self.booking();self.db.scalar("SELECT appointment_system.configure_payment_account('SyntheticMerchant','live','fixture');")
        self.assertEqual(self.start_order(booking),'t')

    def test_internal_meeting_confirms_without_a_google_calendar_obligation(self):
        spec=self.spec;spec['meeting']='internal';self.set_policy(spec)
        booking=self.booking();self.assertEqual(self.start_order(booking),'t');self.record_order(booking)
        self.assertEqual(self.capture(booking),'confirmed')
        self.assertEqual(self.db.scalar('SELECT service_snapshot->>\'meeting\' FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'internal')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_id='+literal(booking['booking'])+';'),'4')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs WHERE booking_id='+literal(booking['booking'])+" AND kind='booking_calendar';"),'0')

    def test_pinned_external_reference_format_is_returned_to_order_and_receipt_readers(self):
        booking=self.booking()
        for format in ('provider-receipt-v1','astro-order-receipt-v1','sarsa-order-receipt-v1'):
            self.db.sql('UPDATE appointment_system.bookings SET provider_receipt_format='+literal(format)+' WHERE id='+literal(booking['booking'])+';')
            intent=self.db.value('SELECT appointment_system.api_order_intent('+literal(booking['booking'])+','+literal(booking['context'])+');',role='appointment_system_web')
            receipt=self.db.value('SELECT appointment_system.api_receipt_snapshot('+literal(booking['request'])+');',role='appointment_system_web')
            self.assertEqual(intent['provider_receipt_format'],format);self.assertEqual(receipt['booking']['provider_receipt_format'],format)

    def test_eight_independent_requests_for_same_empty_time_have_one_capacity_winner(self):
        drafts=[self.draft() for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(self.reserve,drafts))
        self.assertEqual(sum(row['code']=='reserved' for row in results),1)
        self.assertTrue(all(row['code'] in ('reserved','time_unavailable') for row in results))
