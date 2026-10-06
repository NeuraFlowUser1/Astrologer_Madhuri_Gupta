"""Historical resource preservation refuses mismatched ownership and remote identities."""
from copy import deepcopy
import unittest
from uuid import uuid4
from appointment_system.google_workspace import event_id
from tools.conversion.resources import ResourceTransfer
from tools.conversion.source import ConversionError
from . import test_conversion_resources as fixtures

class ResourceBoundaries(unittest.TestCase):
 setUp=fixtures.HistoricalResources.setUp

 def test_configuration_source_layout_and_file_identity_are_strict(self):
  with self.assertRaisesRegex(ConversionError,'configuration_invalid'):ResourceTransfer(None)
  for source in (None,{}, {'sarsa_booking.google_connections':{}}):
   with self.subTest(source=source),self.assertRaises(ConversionError):
    self.reader(self.layout,'google_workbooks',[self.row],source)
  for change,code in [({'layout_version':True},'layout_invalid'),({'layout_version':3},'layout_invalid'),({'volume_number':0},'volume_invalid'),({'volume_number':True},'volume_invalid'),({'spreadsheet_id':None},'file_missing')]:
   with self.subTest(change=change),self.assertRaisesRegex(ConversionError,code):self.reader.volume(self.layout,self.source,self.row|change)
  with self.assertRaisesRegex(ConversionError,'table_unprepared'):self.reader(self.layout,'unregistered',[],self.source)

 def test_existing_volume_must_match_exactly_before_keeping_active_pointer(self):
  row=self.row|dict(volume_number=1,layout_version=1)
  source=self.source|{'sarsa_booking.google_workbook_volumes':[row]}
  result=self.reader(self.layout,'google_workbooks',[row],source)
  self.assertEqual(result['google_workbook_volumes'],[]);self.assertEqual(result['google_workbooks'][0]['spreadsheet_id'],row['spreadsheet_id'])
  for volumes in [[row|{'spreadsheet_id':'another'}],[row,row]]:
   with self.assertRaisesRegex(ConversionError,'active_volume_mismatch'):
    self.reader(self.layout,'google_workbooks',[row],source|{'sarsa_booking.google_workbook_volumes':volumes})

 def test_sheet_row_has_exact_job_role_identity_revision_and_value_types(self):
  job_id=str(uuid4());booking=str(uuid4());job=dict(id=job_id,booking_id=booking,kind='sheet_booking',recipient_role='client_sheet',booking_revision=2)
  values=['004-sarsa-jyotish-sansthan',job_id,booking,'2']+['synthetic']*8
  row=dict(role='client',job_id=job_id,row_number=22,values_json=values)
  source=self.source|{'sarsa_booking.delivery_jobs':[job]}
  for changed,changed_source,code in [(row|{'role':'unknown'},source,'role_invalid'),(row,source|{'sarsa_booking.delivery_jobs':[]},'job_missing'),(row,source|{'sarsa_booking.delivery_jobs':[job|{'recipient_role':'agency_sheet'}]},'job_mismatch'),(row|{'values_json':None},source,'row_mismatch'),(row|{'values_json':values[:3]},source,'row_mismatch'),(row|{'values_json':values[:4]+[1]*8},source,'row_mismatch')]:
   with self.subTest(code=code),self.assertRaisesRegex(ConversionError,code):self.reader(self.layout,'sheet_rows',[changed],changed_source)
  enquiry=dict(id=job_id,request_id=booking,kind='client_sheet');source=self.source|{'sarsa_booking.enquiry_delivery_jobs':[enquiry]}
  result=self.reader(self.layout,'enquiry_sheet_rows',[row|{'values_json':values[:10]}],source)
  self.assertEqual(result['enquiry_sheet_rows'][0]['volume_number'],1)
  with self.assertRaisesRegex(ConversionError,'job_mismatch'):
   self.reader(self.layout,'enquiry_sheet_rows',[row],source|{'sarsa_booking.enquiry_delivery_jobs':[enquiry|{'kind':'email'}]})

 def test_sarsa_calendar_events_keep_provider_ids_and_refuse_missing_parent_or_future_revision(self):
  booking=str(uuid4());row=dict(booking_id=booking,booking_revision=2,event_id=event_id(booking,2,'legacy-sarsa004'),state='ready',meet_url='https://meet.google.com/abc-defg-hij')
  source=self.source|{'sarsa_booking.bookings':[{'id':booking,'revision':2}]}
  self.assertEqual(self.reader(self.layout,'meeting_events',[row],source),{'meeting_events':[row]})
  for changed,changed_source in [(row|{'event_id':'foreign'},source),(row|{'booking_revision':3},source),(row,source|{'sarsa_booking.bookings':[]})]:
   with self.assertRaisesRegex(ConversionError,'calendar_event_mismatch'):self.reader(self.layout,'meeting_events',[changed],changed_source)
