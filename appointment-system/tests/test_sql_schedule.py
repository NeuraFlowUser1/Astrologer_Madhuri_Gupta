"""Real SQL quotation, boundaries, DST and capacity proof on both major versions."""
from copy import deepcopy
import os
import unittest
from .fixtures import installation, business
from appointment_system.serialization import fingerprint
from appointment_system.settings import BusinessSettings
from tools.checks.sql_target import SQLTarget, literal


@unittest.skipUnless(os.environ.get("BOOKING_SQL_TEST_TARGET"), "Owned isolated SQL target required.")
class SchedulingSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SQLTarget(os.environ["BOOKING_SQL_TEST_TARGET"])
        cls.db.check_owned()
        profile = installation()
        profile["database_targets"]["web"]["role"] = "appointment_system_web"
        spec = BusinessSettings.parse(business()).document
        cls.db.value("SELECT appointment_system.configure_installation("+literal(profile)+
                     "::jsonb,"+literal(spec)+"::jsonb,true);")

    def query(self, spec, body, *, rollback=True):
        specification = literal(spec)+"::jsonb"
        statement = "BEGIN;\nSET LOCAL TIME ZONE 'UTC';\n"
        statement += "SELECT " + body.replace("SPEC", specification) + ";\n"
        if rollback:
            statement += "ROLLBACK;"
        return self.db.scalar(statement).splitlines()[-1]

    def test_json_fingerprint_agrees_with_python_for_unicode_and_order(self):
        for value in [{"a":1,"b":True,"c":None,"name":"हिंदी · é","nested":[{"z":"a\nb","x":2}]},
                      business(), installation()]:
            self.assertEqual(self.db.scalar("SELECT appointment_system.settings_digest("+literal(value)+"::jsonb);"),
                             fingerprint(value))

    def test_structural_and_numeric_bad_settings_are_rejected_by_sql(self):
        good = BusinessSettings.parse(business()).document
        self.assertEqual(self.query(good, "appointment_system.validate_business(SPEC)"), "t")
        invalid = []
        for field, value in [("slot_step_minutes",True),("slot_step_minutes",7),("notice_minutes",-1),
                             ("horizon_days",0),("meeting",None),("services",None),("timezone","not/a/zone")]:
            candidate = deepcopy(good); candidate[field] = value; invalid.append(candidate)
        for field, value in [("duration_minutes",31),("enabled",1),("name",123),("id",123)]:
            candidate = deepcopy(good); candidate["services"][0][field]=value; invalid.append(candidate)
        candidate=deepcopy(good);candidate["services"][0]["pricing"]["maximum_questions"]=11;invalid.append(candidate)
        candidate=deepcopy(good);candidate["weekly_windows"].append(candidate["weekly_windows"][0]);invalid.append(candidate)
        for spec in invalid:
            with self.subTest(spec=spec):
                self.assertEqual(self.query(spec,"appointment_system.validate_business(SPEC)"),"f")

    def test_per_question_quote_is_integer_and_bounded(self):
        spec=BusinessSettings.parse(business(per_question=True)).document
        self.assertEqual(self.query(spec,"appointment_system.service_quote(SPEC,'consultation',3)->>'amount_paise'"),"630000")
        for quantity in (0,4,11):
            self.assertEqual(self.query(spec,f"appointment_system.service_quote(SPEC,'consultation',{quantity}) IS NULL"),"t")
        spec["services"][0]["enabled"]=False
        self.assertEqual(self.query(spec,"appointment_system.service_quote(SPEC,'consultation',1) IS NULL"),"t")

    def test_slots_anchor_at_window_start_and_whole_duration_fits(self):
        spec=BusinessSettings.parse(business()).document
        spec["weekly_windows"]=[{"weekday":0,"start":"10:10","end":"11:10"}]
        spec["slot_step_minutes"]=15
        offered=self.query(spec,"coalesce((SELECT jsonb_agg(to_char(starts_at AT TIME ZONE 'Asia/Kolkata','HH24:MI')"
                          " ORDER BY starts_at) FROM appointment_system.schedule_starts(SPEC,40,'2026-10-05',"
                          "'2026-10-05 00:00:00+00')), '[]'::jsonb)::text")
        self.assertEqual(offered,'["10:10", "10:25"]')
        self.assertEqual(self.query(spec,"(SELECT count(*) FROM appointment_system.schedule_starts(SPEC,65,"
                                   "'2026-10-05','2026-10-05 00:00:00+00'))"),"0")

    def test_buffer_range_is_separate_from_appointment_time(self):
        spec=BusinessSettings.parse(business()).document
        spec["buffer_before_minutes"]=10;spec["buffer_after_minutes"]=15
        self.assertEqual(self.query(spec,"(SELECT bool_and(starts_at-occupied_start=interval '10 minutes'"
                                   " AND occupied_end-ends_at=interval '15 minutes') FROM "
                                   "appointment_system.schedule_starts(SPEC,30,'2026-10-05','2026-10-05 00:00+00'))"),"t")

    def test_notice_and_ordinary_horizon_do_not_break_late_move_entitlement(self):
        spec=BusinessSettings.parse(business()).document
        self.assertEqual(self.query(spec,"(SELECT count(*) FROM appointment_system.schedule_starts(SPEC,30,"
                                   "'2026-10-19','2026-10-05 00:00+00'))"),"0")
        self.assertGreater(int(self.query(spec,"(SELECT count(*) FROM appointment_system.schedule_starts(SPEC,30,"
                                         "'2026-10-19','2026-10-05 00:00+00','2026-10-19 13:00+00'))")),0)
        self.assertEqual(self.query(spec,"(SELECT count(*) FROM appointment_system.schedule_starts(SPEC,30,"
                                   "'2026-10-05','2026-10-05 12:59+05:30','2026-10-05 13:00+05:30'))"),"0")

    def test_daylight_saving_skips_nonexistent_and_selects_standard_fold(self):
        spec=BusinessSettings.parse(business()).document
        spec["timezone"]="America/New_York";spec["weekly_windows"]=[{"weekday":6,"start":"01:00","end":"04:00"}]
        spec["horizon_days"]=365
        offered=self.query(spec,"(SELECT jsonb_agg(to_char(starts_at AT TIME ZONE 'America/New_York','HH24:MI')"
                          " ORDER BY starts_at) FROM appointment_system.schedule_starts(SPEC,30,'2027-03-14',"
                          "'2027-03-13 00:00+00'))::text")
        self.assertEqual(offered,'["01:00", "03:00", "03:30"]')
        folded=self.query(spec,"(SELECT to_char(starts_at AT TIME ZONE 'UTC','HH24:MI') FROM "
                          "appointment_system.schedule_starts(SPEC,30,'2026-11-01','2026-10-31 00:00+00')"
                          " WHERE to_char(starts_at AT TIME ZONE 'America/New_York','HH24:MI')='01:00')")
        self.assertEqual(folded,"06:00")
