"""Carry real old spending without inventing messages or renewing counters."""
from datetime import datetime,timedelta,timezone,date
from .records import Bindings,ConfigurationOnly,digest,stamp
from .source import ConversionError

ROLLING='resend:rolling31:'
DAILY='resend:daily:all'
VERIFICATION='resend:daily:verification'

def baselines(bindings,rows):
 now=bindings.now;today=now.date();current={};daily=None;verification=None
 for row in rows:
  if set(row)!={'key','count','resets_at'} or type(row['key']) is not str or type(row['count']) is not int or row['count']<1:
   raise ConversionError('legacy_allowance_counter_invalid')
  expiry=stamp(row['resets_at']);key=row['key']
  if key.startswith('resend:') and key not in (DAILY,VERIFICATION) and not key.startswith(ROLLING):
   raise ConversionError('legacy_allowance_format_unprepared')
  if expiry<=now:continue
  if key.startswith(ROLLING):
   try:day=date.fromisoformat(key[len(ROLLING):])
   except ValueError:raise ConversionError('legacy_allowance_counter_invalid') from None
   if (day>today or day.isoformat()!=key[len(ROLLING):] or day in current
       or expiry<=datetime.combine(day,datetime.min.time(),timezone.utc)):
    raise ConversionError('legacy_allowance_counter_invalid')
   current[day]=dict(installation_id=bindings.installation.installation_id,bucket_date=day.isoformat(),
    total_count=row['count'],verification_count=None,expires_at=row['resets_at'],source_digest=digest(row))
  elif key in (DAILY,VERIFICATION):
   if expiry!=datetime.combine(today+timedelta(days=1),datetime.min.time(),timezone.utc):
    raise ConversionError('legacy_allowance_counter_invalid')
   if key==DAILY:daily=row
   else:verification=row
 if daily:
  entry=current.get(today)
  if entry is None:
   entry=dict(installation_id=bindings.installation.installation_id,bucket_date=today.isoformat(),
    total_count=daily['count'],verification_count=None,
    expires_at=(stamp(daily['resets_at'])+timedelta(days=31)).isoformat(),source_digest=digest(daily))
   current[today]=entry
  elif entry['total_count']<daily['count']:
   entry['total_count']=daily['count'];entry['source_digest']=digest([entry['source_digest'],daily])
 if verification:
  entry=current.get(today)
  if entry is None or verification['count']>entry['total_count']:raise ConversionError('legacy_allowance_counter_invalid')
  entry['verification_count']=verification['count'];entry['source_digest']=digest([entry['source_digest'],verification])
 return list(current.values())

class AllowanceTransfer:
 def __init__(self,bindings):
  if not isinstance(bindings,Bindings):raise ConversionError('legacy_allowance_configuration_invalid')
  self.bindings=bindings
 def __call__(self,layout,table,rows,source=None):
  if layout.project!='003' or table!='rate_limits':raise ConversionError('legacy_allowance_table_unprepared')
  result=baselines(self.bindings,rows)
  if result:return {'email_allowance_baselines':result}
  return ConfigurationOnly(table,digest(rows),'historical_throttles_retired')
