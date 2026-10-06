"""Saved external event identities and marker protocols at the old boundary."""
from copy import deepcopy
import re
from appointment_system.google_workspace import event_id,WorkspaceFailure
from .source import ConversionError


def protocol(layout,source,booking_id,revision):
 if layout.project!='003':raise ConversionError('legacy_calendar_layout_invalid')
 records=source.get(layout.schema+'.booking_event_revisions',[])
 matches=[item for item in records if item['booking_id']==booking_id and item['revision']==revision]
 if len(matches)>1:raise ConversionError('legacy_calendar_event_mismatch')
 if matches:
  version=matches[0]['protocol_version']
  if type(version) is not int or version not in (1,2) or version==1 and revision!=1:
   raise ConversionError('legacy_calendar_protocol_invalid')
  return 'legacy-astro003-unversioned' if version==1 else 'legacy-astro003'
 # An existing pre-revision event is the original unversioned protocol. New
 # unsent work under the versioned schema uses that source's versioned writer.
 if layout.schema+'.booking_event_revisions' in layout.structure['relations']:
  return 'legacy-astro003'
 if revision!=1:raise ConversionError('legacy_calendar_protocol_invalid')
 return 'legacy-astro003-unversioned'


def events(installation,layout,table,rows,source):
 if layout.project!='003' or table not in ('booking_calendar_events','booking_event_revisions'):
  raise ConversionError('legacy_calendar_table_unprepared')
 books={row['id']:row for row in source.get(layout.schema+'.bookings',[])}
 versions=source.get(layout.schema+'.booking_event_revisions',[]);result=[]
 for original in rows:
  row=deepcopy(original);revision=row.get('revision',1);book=books.get(row['booking_id'])
  if book is None or type(revision) is not int or not 1<=revision<=book.get('revision',1):
   raise ConversionError('legacy_calendar_event_mismatch')
  current=protocol(layout,source,row['booking_id'],revision)
  try:expected=event_id(row['booking_id'],revision,current)
  except (WorkspaceFailure,ValueError,TypeError):raise ConversionError('legacy_calendar_event_mismatch') from None
  if row['calendar_id']!=installation.document['owners']['client_email'] or row['event_id']!=expected:
   raise ConversionError('legacy_calendar_owner_or_event_mismatch')
  if table=='booking_calendar_events' and layout.schema+'.booking_event_revisions' in layout.structure['relations']:
   saved=[item for item in versions if item['booking_id']==row['booking_id'] and item['revision']==revision]
   if len(saved)!=1 or any(saved[0][field]!=row[field] for field in ('calendar_id','event_id')):
    raise ConversionError('legacy_calendar_revision_conflict')
   # The old writer can finish an obsolete remote event after the booking has
   # moved. It then updates the versioned fact, leaving the current pointer
   # stale until cancellation. Preserve the authoritative versioned fact; do
   # not mistake that normal race for a foreign event or create a replacement.
   row=deepcopy(saved[0])
  state=row['state'];meet=row['meet_url']
  if state not in ('preparing','waiting','ready','cancelled','failed') or ((state=='ready')!=(meet is not None)):
   raise ConversionError('legacy_calendar_state_invalid')
  if meet is not None and (type(meet) is not str or not re.fullmatch(r'https://meet[.]google[.]com/[a-z]{3}-[a-z]{4}-[a-z]{3}',meet)):
   raise ConversionError('legacy_calendar_state_invalid')
  # Waiting means no verified meeting link. This does not schedule a create;
  # the separately transferred job keeps any failed/uncertain attempt state.
  result.append(dict(booking_id=row['booking_id'],booking_revision=revision,event_id=row['event_id'],
   state='waiting' if state in ('preparing','failed') else state,meet_url=meet))
 return result
