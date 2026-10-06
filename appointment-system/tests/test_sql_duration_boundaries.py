"""Real capacity exclusion across configurable durations and window edges."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta
from threading import Barrier

from tools.checks.sql_target import literal
from .test_sql_booking import BookingFixture


class DurationBoundariesSQL(BookingFixture):
    def variable_policy(self):
        template=deepcopy(self.spec['services'][0])
        self.spec['services']=[dict(template,id='duration-'+str(minutes),
            name='Synthetic '+str(minutes),duration_minutes=minutes) for minutes in (45,60,90)]
        self.spec['slot_step_minutes']=15
        self.spec['weekly_windows']=[{'weekday':day,'start':'10:00','end':'14:00'} for day in range(6)]
        self.set_policy(self.spec)

    def test_three_partly_overlapping_durations_have_one_owner_and_exact_end_remains_available(self):
        self.variable_policy()
        start=datetime.fromisoformat(self.starts[0])
        drafts=[self.draft(start=(start+timedelta(minutes=offset)).isoformat(),service_id='duration-'+str(minutes))
            for minutes,offset in ((45,0),(60,15),(90,30))]
        barrier=Barrier(3,timeout=15)
        def compete(draft):
            barrier.wait()
            return self.reserve(draft)
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(compete,drafts))
        self.assertEqual([value['code'] for value in results].count('reserved'),1)
        self.assertEqual([value['code'] for value in results].count('time_unavailable'),2)
        winner=next(index for index,value in enumerate(results) if value['code']=='reserved')
        saved=self.db.value("SELECT jsonb_build_object('start',starts_at::text,'end',ends_at::text,"
            "'minutes',extract(epoch from ends_at-starts_at)/60,'service',service_id) FROM appointment_system.bookings;")
        self.assertEqual(datetime.fromisoformat(saved['start']),datetime.fromisoformat(drafts[winner]['payload']['starts_at']))
        self.assertEqual(saved['minutes'],(45,60,90)[winner])
        self.assertEqual(saved['service'],drafts[winner]['payload']['service_id'])
        adjacent=self.reserve(self.draft(start=datetime.fromisoformat(saved['end']).isoformat(),service_id='duration-45'))
        self.assertEqual(adjacent['code'],'reserved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'2')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;'),'2')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.payment_orders WHERE attempted_at IS NOT NULL OR provider_order_id IS NOT NULL;'),'0')

    def test_each_duration_cannot_overrun_the_closing_window_or_create_financial_work(self):
        self.variable_policy()
        self.spec['weekly_windows']=[{'weekday':day,'start':'10:00','end':'11:00'} for day in range(6)]
        self.set_policy(self.spec)
        start=datetime.fromisoformat(self.starts[0])+timedelta(minutes=30)
        for minutes in (45,60,90):
            with self.subTest(minutes=minutes):
                value=self.reserve(self.draft(start=start.isoformat(),service_id='duration-'+str(minutes)))
                self.assertEqual(value['code'],'time_unavailable')
        for table in ('bookings','slot_claims','payment_orders','delivery_jobs'):
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.'+table+';'),'0')

    def test_buffers_on_both_sides_prevent_overlap_but_allow_exact_occupied_adjacency(self):
        self.spec['slot_step_minutes']=15
        self.spec['buffer_before_minutes']=15
        self.spec['buffer_after_minutes']=15
        self.set_policy(self.spec)
        start=datetime.fromisoformat(self.starts[0])
        first=self.booking()
        self.assertEqual(self.reserve(self.draft(start=(start+timedelta(minutes=30)).isoformat()))['code'],'time_unavailable')
        second=self.booking(start=(start+timedelta(minutes=60)).isoformat())
        rows=self.db.value("SELECT jsonb_agg(jsonb_build_object('id',b.id,"
            "'appointment_minutes',extract(epoch from b.ends_at-b.starts_at)/60,"
            "'before_minutes',extract(epoch from b.starts_at-c.starts_at)/60,"
            "'after_minutes',extract(epoch from c.ends_at-b.ends_at)/60) ORDER BY b.starts_at)"
            " FROM appointment_system.bookings b JOIN appointment_system.slot_claims c ON c.booking_id=b.id WHERE c.released_at IS NULL;")
        self.assertEqual([row['id'] for row in rows],[first['booking'],second['booking']])
        for row in rows:
            self.assertEqual((row['appointment_minutes'],row['before_minutes'],row['after_minutes']),(30,15,15))

    def test_notice_now_and_last_permitted_day_have_explicit_inclusive_edges(self):
        self.spec['slot_step_minutes']=15
        self.spec['horizon_days']=3
        def starts(day,now):
            rows=self.db.value('SELECT to_jsonb(ARRAY(SELECT starts_at::text FROM appointment_system.schedule_starts('
                +literal(self.spec)+'::jsonb,30,'+literal(day)+'::date,'+literal(now)+'::timestamptz)));')
            return [datetime.fromisoformat(value) for value in rows]
        opening=datetime.fromisoformat('2026-10-05T10:00:00+05:30')
        self.assertIn(opening,starts('2026-10-05','2026-10-05T09:30:00+05:30'))
        self.assertNotIn(opening,starts('2026-10-05','2026-10-05T09:30:00.000001+05:30'))
        self.spec['notice_minutes']=0
        self.assertIn(opening,starts('2026-10-05','2026-10-05T10:00:00+05:30'))
        self.assertNotIn(opening,starts('2026-10-05','2026-10-05T10:00:00.000001+05:30'))
        self.assertTrue(starts('2026-10-08','2026-10-05T09:00:00+05:30'))
        self.assertEqual(starts('2026-10-09','2026-10-05T09:00:00+05:30'),[])
        self.assertEqual(starts('2026-10-03','2026-10-05T09:00:00+05:30'),[])
