import unittest
from datetime import date, datetime, timedelta, timezone

from backend.booking_engine.policy import (
    IST, InvalidSelection, SERVICES, candidates, policy_snapshot, policy_version,
    quote, validate_start,
)


class SchedulingTests(unittest.TestCase):
    now = datetime(2026, 9, 28, 9, 30, tzinfo=IST)

    def test_approved_catalogue_and_meet(self):
        self.assertEqual({k: v.amount_paise for k, v in SERVICES.items()}, {
            'kundli-matching': 210000, 'kundli-prediction': 250000,
            'vastu-consultation': 450000, 'numerology': 210000})
        for service in SERVICES:
            self.assertEqual(quote(service)['duration_minutes'], 30)
            self.assertEqual(quote(service)['meeting_platform'], 'Google Meet')
        with self.assertRaises(InvalidSelection):
            quote('astroadvice-service')

    def test_all_days_windows_and_half_open_boundaries(self):
        expected = ['10:00','10:30','11:00','11:30','15:00','15:30','16:00','16:30','17:00','17:30']
        for offset in range(6):
            day = self.now.date() + timedelta(days=offset)
            slots = candidates('numerology', day, self.now)
            self.assertEqual([v.strftime('%H:%M') for v in slots], expected)
        self.assertEqual(candidates('numerology', date(2026,10,4), self.now), ())
        for hour, minute in ((9,30), (12,0), (14,30), (18,0), (10,15)):
            with self.subTest(hour=hour, minute=minute), self.assertRaises(InvalidSelection):
                validate_start('numerology', self.now.replace(hour=hour,minute=minute),self.now)

    def test_notice_horizon_and_timezone_boundaries(self):
        start = self.now.replace(hour=10,minute=0)
        self.assertEqual(validate_start('numerology',start,self.now),start+timedelta(minutes=30))
        with self.assertRaises(InvalidSelection):
            validate_start('numerology',start,self.now+timedelta(microseconds=1))
        self.assertEqual(validate_start('numerology',start.astimezone(timezone.utc),self.now),
                         start+timedelta(minutes=30))
        self.assertEqual(len(candidates('numerology',self.now.date()+timedelta(days=10),self.now)),10)
        self.assertEqual(candidates('numerology',self.now.date()+timedelta(days=11),self.now),())
        self.assertEqual(candidates('numerology',self.now.date()-timedelta(days=1),self.now),())
        with self.assertRaises(InvalidSelection):
            validate_start('numerology',start.replace(tzinfo=None),self.now)
        with self.assertRaises(InvalidSelection):
            validate_start('numerology',start.replace(second=1),self.now)

    def test_quote_cannot_mutate_policy(self):
        original = policy_version()
        snapshot = policy_snapshot()
        snapshot['services'][0]['amount_paise'] = 1
        snapshot['weekdays'].append(6)
        self.assertEqual(policy_version(), original)
        self.assertEqual(len(original),64)
        with self.assertRaises(TypeError):
            SERVICES['other'] = SERVICES['numerology']


if __name__ == '__main__':
    unittest.main()
