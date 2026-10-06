"""Committed synthetic payment/refund ordering on the two owned SQL targets."""
import hashlib
import json
from uuid import uuid4
from .test_sql_staff import StaffFixture, CLIENT, ORIGIN
from tools.checks.sql_target import literal


class PaymentOutcomes(StaffFixture):
    def resource(self, saved, *, status, updated, parent_refunded, provenance='provider_fetch'):
        self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        fact = dict(version=1, kind='refund', id='rfnd_synthetic', payment_id='pay_synthetic',
                    status=status, amount=210000, currency='INR', created_at=1700000000,
                    updated_at=updated, respond_by=None, speed_requested='normal', speed_processed=None)
        parent = dict(entity='payment', id='pay_synthetic', order_id='order_synthetic',
                      status='refunded' if parent_refunded == 210000 else 'captured', amount=210000,
                      currency='INR', amount_refunded=parent_refunded, captured=True)
        evidence = hashlib.sha256(json.dumps([fact, parent, provenance], sort_keys=True).encode()).hexdigest()
        values = [saved['booking'], 'SyntheticMerchant', 'live', 'fixture', fact, provenance, evidence, parent]
        return self.db.value('SELECT appointment_system.observe_financial_resource(' + ','.join(map(literal, values)) + ');',
                             role='abs_worker')

    def observe(self, saved, *, payment='pay_synthetic', order='order_synthetic',
                status='captured', amount=210000, refunded=0, captured=True):
        values = [saved['context'], saved['booking'], 'SyntheticMerchant', 'live', 'fixture',
                  payment, order, hashlib.sha256(json.dumps([payment, order, status, amount, refunded, captured]).encode()).hexdigest(),
                  status, amount, 'INR', refunded, captured]
        return self.db.scalar('SELECT appointment_system.observe_payment(' + ','.join(map(literal, values)) + ');',
                              role='appointment_system_web')

    def receipt(self, saved):
        return self.db.value('SELECT appointment_system.api_receipt_snapshot(' + literal(saved['request']) + ');',
                             role='appointment_system_web')['booking']

    def test_uncaptured_authorization_never_confirms_or_sends_booking_jobs(self):
        saved = self.booking(); self.start_order(saved); self.record_order(saved)
        self.assertEqual(self.observe(saved, status='authorized', captured=False), 'observed')
        self.assertEqual(self.receipt(saved)['state'], 'held')
        self.assertEqual(self.receipt(saved)['payment_state'], 'pending')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.delivery_jobs;'), '0')

    def test_wrong_amount_retains_evidence_without_accepting_or_occupying_slot(self):
        saved = self.booking(); self.start_order(saved); self.record_order(saved)
        self.assertEqual(self.observe(saved, amount=210001), 'payment_needs_review')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_observations;'), '1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'), '0')
        self.assertEqual(self.db.scalar('SELECT reason FROM appointment_system.payment_cases;'), 'payment_mismatch')

    def test_wrong_order_cannot_confirm_the_booking(self):
        saved = self.booking(); self.start_order(saved); self.record_order(saved)
        self.assertEqual(self.observe(saved, order='order_foreign'), 'payment_needs_review')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '0')
        self.assertEqual(self.db.scalar('SELECT reason FROM appointment_system.payment_cases;'), 'payment_mismatch')

    def test_second_payment_is_reviewed_without_replacing_first_or_releasing_appointment(self):
        saved = self.confirmed()
        self.assertEqual(self.observe(saved, payment='pay_second'), 'payment_needs_review')
        self.assertEqual(self.observe(saved, payment='pay_second'), 'payment_needs_review')
        self.assertEqual(self.db.scalar('SELECT payment_id FROM appointment_system.accepted_payments;'), 'pay_synthetic')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'), '1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_cases;'), '1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='payment_review';"), '1')
        self.assertEqual(self.receipt(saved)['state'], 'confirmed')

    def test_partial_full_duplicate_and_stale_refund_observations_never_reduce_saved_total(self):
        saved = self.confirmed()
        self.assertEqual(self.observe(saved, refunded=100000), 'payment_needs_review')
        self.assertEqual(self.receipt(saved)['refunded_paise'], 100000)
        self.assertEqual(self.observe(saved, refunded=210000, status='refunded'), 'payment_needs_review')
        self.assertEqual(self.observe(saved, refunded=210000, status='refunded'), 'payment_needs_review')
        self.assertEqual(self.observe(saved, refunded=50000), 'payment_needs_review')
        self.assertEqual(self.observe(saved), 'confirmed')
        receipt = self.receipt(saved)
        self.assertEqual((receipt['captured_paise'], receipt['refunded_paise']), (210000, 210000))
        self.assertEqual(receipt['payment_state'], 'needs_attention')
        self.assertEqual(receipt['state'], 'confirmed')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_cases;'), '1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='payment_review';"), '1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'), '1')

    def test_refund_before_confirmation_does_not_create_a_confirmed_appointment(self):
        saved = self.booking(); self.start_order(saved); self.record_order(saved)
        self.assertEqual(self.observe(saved, status='refunded', refunded=210000), 'payment_needs_review')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'), '0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'), '0')
        self.assertEqual(self.receipt(saved)['state'], 'payment_review')

    def test_full_refund_review_requires_cancelled_appointment_and_retries_do_not_send_money(self):
        saved = self.confirmed()
        self.observe(saved, refunded=100000)
        item = 'payment:' + self.db.scalar('SELECT id::text FROM appointment_system.payment_cases;')
        operation = uuid4()
        def close():
            return self.staff.studio_inbox_refund_verified(self.session, CLIENT, ORIGIN, operation,
                                                         item, 0, 'Synthetic refund verification')
        self.assertEqual(close()['code'], 'refund_not_verified')
        self.observe(saved, status='refunded', refunded=210000)
        self.assertEqual(close()['code'], 'refund_not_verified')
        cancelled = self.staff.studio_appointment_cancel(self.session, CLIENT, ORIGIN, uuid4(),
                                                        saved['claim'], 1, 'Synthetic cancellation')
        self.assertEqual(cancelled['code'], 'cancelled')
        observations = self.db.scalar('SELECT count(*) FROM appointment_system.payment_observations;')
        first = close(); self.assertEqual(first['code'], 'refund_verified'); self.assertEqual(close(), first)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_observations;'), observations)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.staff_reviews WHERE action='verified_refund';"), '1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_cases WHERE resolved_at IS NULL;'), '0')
        self.assertEqual(self.receipt(saved)['payment_state'], 'refunded')
        self.assertEqual(self.receipt(saved)['state'], 'cancelled')

    def test_older_verified_refund_fact_cannot_reopen_a_completed_refund_review(self):
        saved = self.confirmed()
        self.resource(saved, status='processed', updated=1700000020, parent_refunded=210000)
        item = 'payment:' + self.db.scalar('SELECT id::text FROM appointment_system.payment_cases;')
        self.assertEqual(self.staff.studio_appointment_cancel(self.session, CLIENT, ORIGIN, uuid4(),
                         saved['claim'], 1, 'Synthetic cancellation')['code'], 'cancelled')
        self.assertEqual(self.staff.studio_inbox_refund_verified(self.session, CLIENT, ORIGIN, uuid4(),
                         item, 0, 'Synthetic verified full refund')['code'], 'refund_verified')
        before = self.db.value('SELECT jsonb_build_object(\'resolved_at\',resolved_at,\'actor\',resolution_actor,\'note\',resolution_note) FROM appointment_system.payment_cases;')
        observed = self.resource(saved, status='pending', updated=1700000010, parent_refunded=0)
        self.assertEqual(observed['status'], 'processed')
        self.assertIsNone(observed['attention_reason'])
        after = self.db.value('SELECT jsonb_build_object(\'resolved_at\',resolved_at,\'actor\',resolution_actor,\'note\',resolution_note) FROM appointment_system.payment_cases;')
        self.assertEqual(after, before)
        self.assertEqual(self.receipt(saved)['payment_state'], 'refunded')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.financial_resource_facts;'), '2')

    def test_newer_regressive_refund_still_raises_attention(self):
        saved = self.confirmed()
        self.resource(saved, status='processed', updated=1700000020, parent_refunded=210000)
        observed = self.resource(saved, status='pending', updated=1700000030, parent_refunded=210000)
        self.assertEqual(observed['status'], 'processed')
        self.assertEqual(observed['attention_reason'], 'financial_resource_conflict')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_cases WHERE resolved_at IS NULL;'), '1')

    def test_missing_timestamp_cannot_claim_that_conflicting_refund_is_old(self):
        saved = self.confirmed()
        self.resource(saved, status='processed', updated=1700000020, parent_refunded=210000)
        observed = self.resource(saved, status='pending', updated=None, parent_refunded=210000)
        self.assertEqual(observed['status'], 'processed')
        self.assertEqual(observed['attention_reason'], 'financial_resource_conflict')

    def test_unfetched_notification_does_not_override_an_authoritative_provider_read(self):
        saved = self.confirmed()
        self.resource(saved, status='pending', updated=1700000030, parent_refunded=0, provenance='signed_webhook')
        observed = self.resource(saved, status='processed', updated=1700000020, parent_refunded=210000)
        self.assertEqual(observed['status'], 'processed')
        self.assertTrue(observed['verified'])
        self.assertIsNone(observed['attention_reason'])
