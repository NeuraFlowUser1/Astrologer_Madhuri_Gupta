"""Owned SQL contention proof; no HTTP-rate, live latency or provider claim.

Each submission uses its own committed restricted-role database sessions. The
fixture contains synthetic contacts only. Verification uses the exact protected
challenge digest, as the separately tested HTTP verification boundary does.
"""
from concurrent.futures import ThreadPoolExecutor
from time import monotonic,sleep
from uuid import uuid4

import psycopg

from appointment_system.contact import EnquiryInput,enquiry_payload
from .sql_store import IsolatedStore
from .test_contact_protection import keys
from .test_sql_booking import BookingFixture


class MixedWorkloadSQL(BookingFixture):
    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.enquiries CASCADE;'
                    'TRUNCATE appointment_system.request_limits;'
                    'UPDATE appointment_system.contact_intake SET public_open=true;')
        self.protection=keys()
        self.public=IsolatedStore(self.db,'appointment_system_web')

    def enquiry(self,index):
        reference=uuid4()
        body=EnquiryInput(request_id=reference,name='Synthetic Customer',
            email=f'workload{index}@example.com',subject='Synthetic enquiry',
            message='An isolated database workload enquiry.',source='contact')
        payload,fingerprint=enquiry_payload(body)
        secret=self.protection.receipt_keys.issue()
        metadata=self.protection.receipt_keys.metadata(secret)
        receipt=self.protection.receipt(reference,secret,key_id=metadata['key_id'])
        digest,encrypted=self.protection.challenge(reference,payload['email'],1)
        return (reference,receipt,fingerprint,payload,digest,encrypted,
                self.protection.digest('email-quota',payload['email'].casefold()),
                metadata['key_id'],self.protection.digest_key.active)

    def test_one_hundred_mixed_submissions_preserve_capacity_and_all_enquiries(self):
        bookings=[self.draft() for _ in range(40)]
        enquiries=[self.enquiry(index) for index in range(60)]
        # Alternate the two sources before filling the remaining enquiry tail.
        # This is a bounded 20-session mixed workload, not a claim that 100
        # customers bypass the real per-address HTTP admission limits.
        work=[]
        for index in range(60):
            if index<40:work.append(('booking',bookings[index]))
            work.append(('enquiry',enquiries[index]))
        self.assertEqual(len(work),100)
        def submit(item):
            kind,value=item
            return kind,(self.reserve(value) if kind=='booking' else self.public.start_enquiry(*value))
        with ThreadPoolExecutor(max_workers=20) as pool:
            results=list(pool.map(submit,work))
        appointments=[value for kind,value in results if kind=='booking']
        contacts=[value for kind,value in results if kind=='enquiry']
        self.assertEqual(sum(value['code']=='reserved' for value in appointments),1)
        self.assertEqual(sum(value['code']=='time_unavailable' for value in appointments),39)
        self.assertEqual(len(contacts),60)
        self.assertTrue(all(value['code']=='ok' and value['state']=='awaiting_verification' for value in contacts))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiries WHERE verified_at IS NOT NULL;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiry_delivery_jobs;'),'60')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_orders WHERE attempted_at IS NOT NULL OR provider_order_id IS NOT NULL;'),'0')
        def verify(value):return self.public.verify_enquiry(value[0],value[1],1,value[4])
        with ThreadPoolExecutor(max_workers=20) as pool:
            verified=list(pool.map(verify,enquiries))
            repeated=list(pool.map(verify,enquiries))
        self.assertTrue(all(value['state']=='received' for value in verified+repeated))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiries WHERE verified_at IS NOT NULL;'),'60')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification';"),'240')

    def test_enquiry_commits_while_booking_mode_and_settings_are_locked(self):
        self.db.check_owned()
        values=self.enquiry(0)
        with psycopg.connect(host=self.db.native_socket(),dbname='postgres',user='postgres') as blocker:
            blocker.execute('SELECT pg_advisory_xact_lock(83124,4)')
            blocker.execute('SELECT 1 FROM appointment_system.control_product_state FOR UPDATE')
            blocker.execute('SELECT 1 FROM appointment_system.intake_settings FOR UPDATE')
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(self.public.start_enquiry,*values)
                try:
                    saved=pending.result(timeout=8)
                    self.assertEqual(saved['state'],'awaiting_verification')
                    # This read also completes before the booking locks release.
                    self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiries;'),'1')
                finally:
                    # Release only this fixture transaction even if the test
                    # finds an unwanted dependency, allowing the child to exit.
                    blocker.rollback()
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'0')

    def test_installation_maintenance_still_fences_enquiry_until_commit(self):
        values=self.enquiry(0)
        with psycopg.connect(host=self.db.native_socket(),dbname='postgres',user='postgres') as blocker:
            blocker.execute('SELECT pg_advisory_xact_lock(83124,5)')
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(self.public.start_enquiry,*values)
                try:
                    deadline=monotonic()+8
                    while monotonic()<deadline:
                        # PostgreSQL otherwise retains the first activity
                        # snapshot for this still-open blocker transaction.
                        blocker.execute('SELECT pg_stat_clear_snapshot()')
                        waiting=blocker.execute("SELECT EXISTS(SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
                            "WHERE l.locktype='advisory' AND NOT l.granted AND l.classid=83124 AND l.objid=5 "
                            "AND a.datname=current_database() AND a.usename='appointment_system_web')").fetchone()[0]
                        if waiting:break
                        sleep(.02)
                    self.assertTrue(waiting,'The enquiry did not reach the actual maintenance fence.')
                    self.assertFalse(pending.done())
                    self.assertEqual(blocker.execute('SELECT count(*) FROM appointment_system.enquiries').fetchone()[0],0)
                finally:
                    blocker.rollback()
                self.assertEqual(pending.result(timeout=8)['state'],'awaiting_verification')
