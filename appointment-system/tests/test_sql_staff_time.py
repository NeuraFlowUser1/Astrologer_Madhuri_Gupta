"""Configured civil times use database rules, including daylight-saving edges."""
from datetime import datetime,timezone
from uuid import uuid4
from .test_sql_staff import StaffFixture,CLIENT,ORIGIN
from .sql_store import IsolatedStore

class StaffTimeSQL(StaffFixture):
    def test_current_zone_resolution_and_changed_setting_are_explicit(self):
        context=self.staff.studio_time_context(self.session,CLIENT,ORIGIN)
        self.assertEqual(context['code'],'ok');self.assertEqual(context['timezone'],'Asia/Kolkata')
        value=self.staff.studio_resolve_time(self.session,CLIENT,ORIGIN,'2026-11-03T16:30','Asia/Kolkata')
        self.assertEqual(value['local'],'2026-11-03T16:30')
        self.assertEqual(datetime.fromisoformat(value['instant']).astimezone(timezone.utc).isoformat(),'2026-11-03T11:00:00+00:00')
        self.spec['timezone']='America/New_York';self.set_policy(self.spec)
        self.assertEqual(self.staff.studio_resolve_time(self.session,CLIENT,ORIGIN,'2026-11-03T16:30','Asia/Kolkata')['code'],'timezone_changed')
        self.assertEqual(self.staff.studio_time_context(self.session,CLIENT,ORIGIN)['timezone'],'America/New_York')
        self.assertEqual(self.staff.studio_time_context('wrong',CLIENT,ORIGIN)['code'],'access_unavailable')
        with self.assertRaises(Exception):IsolatedStore(self.db,'appointment_system_web').studio_time_context(self.session,CLIENT,ORIGIN)

    def test_nonexistent_and_normalized_times_are_rejected_and_repeated_time_matches_slot_rules(self):
        self.spec['timezone']='America/New_York';self.set_policy(self.spec)
        for local in ['2026-03-08T02:30','2026-02-31T10:00','2026-01-01T24:00','2026-01-01T10:60','2026-01-01','0000-01-01T10:00']:
            with self.subTest(local=local):self.assertEqual(self.staff.studio_resolve_time(self.session,CLIENT,ORIGIN,local,'America/New_York')['code'],'invalid_local_time')
        value=self.staff.studio_resolve_time(self.session,CLIENT,ORIGIN,'2026-11-01T01:30','America/New_York')
        self.assertEqual(value['code'],'ok')
        self.assertEqual(datetime.fromisoformat(value['instant']).astimezone(timezone.utc).isoformat(),'2026-11-01T06:30:00+00:00')
        self.assertNotIn('notes',value)
