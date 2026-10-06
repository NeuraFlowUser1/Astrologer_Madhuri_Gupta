"""Actual old file markers, grant ownership, rows and remote event IDs."""
from copy import deepcopy
import unittest
from uuid import uuid4
from appointment_system.google_workspace import Workspace,WorkspaceFailure,PROJECT
from tools.conversion.resources import ResourceTransfer
from tools.conversion.source import catalogue,ConversionError
from tools.conversion.calendar import protocol
from tools.conversion.records import Mapper
from .test_conversion_records import bindings,empty
from . import test_conversion_grants as grant_fixtures
from . import test_google_workspace as workspace_fixtures

class HistoricalResources(unittest.TestCase):
 def setUp(self):
  self.proof=grant_fixtures.HistoricalGoogleGrants();self.proof.setUp()
  self.reader=ResourceTransfer(self.proof.transfer)
  self.layout=next(row for row in catalogue() if row.identifier=='legacy-004-31')
  self.permission=self.proof.full()
  self.row=dict(role='client',intent=str(uuid4()),subject=self.permission['subject'],client_id=self.permission['client_id'],
   spreadsheet_id='old_owned_file',state='ready',connection_revision=7,lease=None,lease_until=None,next_row=23,next_enquiry_row=9)
  self.source={'sarsa_booking.google_connections':[self.permission],'sarsa_booking.google_workbooks':[self.row]}

 def test_actual_prefix_file_keeps_intent_owner_rows_and_retained_grant(self):
  converted=self.reader(self.layout,'google_workbooks',[self.row],self.source)
  active=converted['google_workbooks'][0];volume=converted['google_workbook_volumes'][0]
  self.assertEqual(active['next_row'],23);self.assertEqual(active['next_enquiry_row'],9)
  for field in ('role','intent','subject','client_id','spreadsheet_id','state'):
   self.assertEqual(volume[field],self.row[field])
  self.assertEqual(volume['workbook_protocol'],'legacy-sarsa-workbook-v1')
  self.assertEqual(volume['grant_id'],self.proof.transfer.full_grant(self.permission)['google_resource_grants'][0]['id'])
  self.assertNotIn('workbook_protocol',self.row)

 def test_creation_uncertainty_is_preserved_without_a_fresh_creation_attempt(self):
  row=deepcopy(self.row);row.update(state='creating',spreadsheet_id=None,lease=str(uuid4()),lease_until=None)
  result=self.reader(self.layout,'google_workbooks',[row],self.source)['google_workbooks'][0]
  self.assertIsNone(result['lease']);self.assertEqual(result['creation_attempt_at'],self.permission['connected_at'])

 def test_source_volume_markers_and_saved_row_payload_are_not_relabelled(self):
  source=deepcopy(self.source);volume=self.row|dict(volume_number=4,generation=str(uuid4()),layout_version=2,created_at=self.permission['connected_at'])
  converted=self.reader(self.layout,'google_workbook_volumes',[volume],source)['google_workbook_volumes'][0]
  self.assertEqual(converted['generation'],volume['generation']);self.assertEqual(converted['volume_number'],4)
  job_id=str(uuid4());booking=str(uuid4())
  job=dict(id=job_id,booking_id=booking,kind='sheet_booking',recipient_role='client_sheet',booking_revision=2)
  values=['004-sarsa-jyotish-sansthan',job_id,booking,'2','confirmed','Consultation','start','end','Name','email','phone','1']
  source['sarsa_booking.delivery_jobs']=[job]
  mapped=dict(role='client',job_id=job_id,row_number=22,values_json=values,volume_number=4)
  result=self.reader(self.layout,'sheet_rows',[mapped],source)['sheet_rows'][0]
  self.assertEqual(result,mapped)
  mapped['values_json'][2]=str(uuid4())
  with self.assertRaisesRegex(ConversionError,'row_mismatch'):self.reader(self.layout,'sheet_rows',[mapped],source)

 def test_wrong_owner_subject_and_unbound_old_client_are_refused(self):
  for field in ('subject','client_id','role'):
   row=deepcopy(self.row);row[field]='foreign'
   with self.subTest(field=field),self.assertRaisesRegex(ConversionError,'permission_unresolved'):
    self.reader(self.layout,'google_workbooks',[row],self.source)

 def test_old_file_markers_are_exact_while_new_files_include_installation(self):
  proof=workspace_fixtures.WorkspaceTests();proof.setUp()
  workspace=Workspace(proof.access);volume=self.reader.volume(self.layout,self.source,self.row)
  workspace.bind_volume(volume)
  self.assertEqual(workspace.workbook_markers(self.row['intent']),
   {'project':'004-sarsa-jyotish-sansthan','role':'client','intent':self.row['intent']})
  file=deepcopy(proof.file);file['appProperties']=workspace.workbook_markers(self.row['intent'])
  self.assertEqual(workspace.validate_workbook(file,self.row['intent']),file['id'])
  file['appProperties']['project']=PROJECT
  with self.assertRaisesRegex(WorkspaceFailure,'owner_mismatch'):workspace.validate_workbook(file,self.row['intent'])
  workspace.bind_volume(volume|dict(layout_version=3,workbook_protocol='v1'))
  self.assertIn('installation',workspace.workbook_markers(self.row['intent']))
  with self.assertRaisesRegex(WorkspaceFailure,'identity_invalid'):
   workspace.bind_volume(volume|dict(layout_version=3))


class HistoricalAstroCalendar(unittest.TestCase):
 def setUp(self):
  self.proof=grant_fixtures.HistoricalGoogleGrants();self.proof.setUp();self.reader=ResourceTransfer(self.proof.transfer)
  self.layout=next(row for row in catalogue() if row.identifier=='legacy-003-16')
  self.full=next(row for row in catalogue() if row.identifier=='legacy-003-40')
  self.booking=str(uuid4());self.row=dict(booking_id=self.booking,calendar_id='practice@example.test',event_id='astro'+self.booking.replace('-',''),
   state='ready',meet_url='https://meet.google.com/abc-defg-hij',created_at='2026-10-01T10:00:00Z',updated_at='2026-10-01T10:00:00Z')
  self.source={'public.bookings':[{'id':self.booking}],'public.booking_calendar_events':[self.row]}

 def test_original_event_keeps_its_id_link_and_unversioned_markers(self):
  result=self.reader(self.layout,'booking_calendar_events',[self.row],self.source)['meeting_events'][0]
  self.assertEqual(result,{'booking_id':self.booking,'booking_revision':1,'event_id':self.row['event_id'],'state':'ready','meet_url':self.row['meet_url']})
  self.assertEqual(protocol(self.layout,self.source,self.booking,1),'legacy-astro003-unversioned')
  self.assertNotIn('booking_revision',self.row)

 def test_old_first_event_and_later_versioned_event_keep_distinct_protocols(self):
  first=self.row|{'revision':1,'protocol_version':1}
  second=self.row|{'revision':2,'protocol_version':2,'event_id':self.row['event_id']+'r2'}
  source=self.source|{'public.bookings':[{'id':self.booking,'revision':2}],'public.booking_event_revisions':[first,second]}
  self.assertEqual(protocol(self.full,source,self.booking,1),'legacy-astro003-unversioned')
  self.assertEqual(protocol(self.full,source,self.booking,2),'legacy-astro003')
  self.assertEqual(protocol(self.full,source,self.booking,3),'legacy-astro003')
  versions=self.reader(self.full,'booking_event_revisions',[first,second],source)['meeting_events']
  current=self.reader(self.full,'booking_calendar_events',[second],source)['meeting_events'][0]
  mapper=Mapper(self.full,empty(self.full),bindings())
  for row in versions+[current]:mapper.add('meeting_events',row)
  self.assertEqual(len(mapper.output['meeting_events']),2)
  with self.assertRaisesRegex(ConversionError,'calendar_event_collision'):mapper.add('meeting_events',current|{'state':'cancelled','meet_url':None})
  stale=self.reader(self.full,'booking_calendar_events',[second|{'state':'preparing','meet_url':None}],source)
  self.assertEqual(stale['meeting_events'][0],current,'An obsolete provider reply can leave the old current pointer behind its authoritative versioned fact')
  with self.assertRaisesRegex(ConversionError,'revision_conflict'):
   self.reader(self.full,'booking_calendar_events',[self.row],self.source|{'public.booking_event_revisions':[]})

 def test_wrong_owner_event_revision_and_invalid_meeting_state_are_rejected(self):
  for change in ({'calendar_id':'foreign@example.test'},{'event_id':'foreign'}, {'revision':2},
   {'meet_url':'https://foreign.test/abc-defg-hij'},{'state':'cancelled'}):
   with self.subTest(change=change),self.assertRaises(ConversionError):
    self.reader(self.layout,'booking_calendar_events',[self.row|change],self.source)
  for state in ('preparing','failed'):
   result=self.reader(self.layout,'booking_calendar_events',[self.row|{'state':state,'meet_url':None}],self.source)
   self.assertEqual(result['meeting_events'][0]['state'],'waiting')
   self.assertEqual(set(result),{'meeting_events'},'An uncertain old event cannot create a fresh job')
