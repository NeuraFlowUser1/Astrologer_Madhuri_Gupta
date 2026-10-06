"""Historical counters do not become fictitious sends or fresh allowance."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import unittest
from tools.conversion.allowance import baselines,AllowanceTransfer,DAILY,VERIFICATION,ROLLING
from tools.conversion.records import ConfigurationOnly
from tools.conversion.source import catalogue,ConversionError
from .test_conversion_records import bindings

class HistoricalAllowance(unittest.TestCase):
 def setUp(self):self.bound=replace(bindings(),now=datetime(2026,10,3,12,tzinfo=timezone.utc),receipt_formats=dict(bindings().receipt_formats))
 def row(self,key,count,expiry):return {'key':key,'count':count,'resets_at':expiry.isoformat()}
 def test_total_daily_and_rolling_records_count_the_same_day_once_and_keep_real_expiry(self):
  reset=self.bound.now.replace(hour=0)+timedelta(days=1)
  rows=[self.row(DAILY,23,reset),self.row(VERIFICATION,10,reset),
   self.row(ROLLING+'2026-10-03',20,reset+timedelta(days=31)),
   self.row(ROLLING+'2026-10-02',8,reset+timedelta(days=30))]
  result={row['bucket_date']:row for row in baselines(self.bound,rows)}
  self.assertEqual(result['2026-10-03']['total_count'],23);self.assertEqual(result['2026-10-03']['verification_count'],10)
  self.assertIsNone(result['2026-10-02']['verification_count']);self.assertEqual(len(result),2)
  self.assertEqual(result['2026-10-03']['expires_at'],rows[2]['resets_at'])
 def test_active_daily_without_a_rolling_bucket_is_carried_and_expired_spending_stays_expired(self):
  reset=self.bound.now.replace(hour=0)+timedelta(days=1)
  result=baselines(self.bound,[self.row(DAILY,3,reset),self.row(ROLLING+'2026-09-01',70,self.bound.now-timedelta(seconds=1))])
  self.assertEqual(len(result),1);self.assertEqual(result[0]['total_count'],3)
  self.assertEqual(result[0]['expires_at'],(reset+timedelta(days=31)).isoformat())
 def test_unknown_sender_namespace_future_bucket_missing_total_and_bad_counts_refuse(self):
  reset=self.bound.now.replace(hour=0)+timedelta(days=1)
  for rows in [[self.row('resend:monthly:unknown',3,reset)],
   [self.row(ROLLING+'2026-10-04',3,reset+timedelta(days=32))],[self.row(VERIFICATION,3,reset)],
   [self.row(DAILY,2,reset),self.row(VERIFICATION,3,reset)],[self.row(DAILY,True,reset)],
   [self.row(DAILY,3,reset+timedelta(hours=1))]]:
   with self.subTest(keys=[row['key'] for row in rows]),self.assertRaises(ConversionError):baselines(self.bound,rows)
 def test_retired_non_sender_throttle_does_not_create_any_message_or_sender_budget(self):
  layout=next(item for item in catalogue() if item.identifier=='legacy-003-16')
  result=AllowanceTransfer(self.bound)(layout,'rate_limits',[self.row('old-private-rate-key',3,self.bound.now+timedelta(hours=1))])
  self.assertIsInstance(result,ConfigurationOnly);self.assertEqual(result.reason,'historical_throttles_retired')
