"""Adversarial historical facts cannot silently gain authority during translation."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import unittest
from uuid import uuid4
from tools.conversion import records
from tools.conversion.source import catalogue,ConversionError
from .test_conversion_records import bindings,empty

class HistoricalRecordBoundaries(unittest.TestCase):
 def test_saved_sarsa_meeting_survives_a_different_new_business_default(self):
  mapper=self.mapper();document=deepcopy(mapper.bindings.business.document);document['meeting']='internal'
  from appointment_system.settings import BusinessSettings
  mapper.bindings=replace(mapper.bindings,business=BusinessSettings.parse(document),receipt_formats=dict(mapper.bindings.receipt_formats))
  row={'id':str(uuid4()),'state':'cancelled','revision':1,'starts_at':'2031-01-01T00:00:00Z',
       'preparation':{},'service_snapshot':{'meeting_platform':'Google Meet','name':'Saved consultation'}}
  original=deepcopy(row);saved=mapper._direct('bookings',row)
  self.assertEqual(saved['service_snapshot'],original['service_snapshot']|{'meeting':'google_meet'})
  self.assertEqual(row,original)
  for unsupported in (None,[],True,'Google Meet',{'meeting_platform':'Other provider'},{'meeting':'internal'}):
   with self.subTest(value=unsupported),self.assertRaisesRegex(ConversionError,'legacy_meeting_contract_invalid'):
    mapper._direct('bookings',row|{'service_snapshot':unsupported})

 def mapper(self,project='004',**changes):
  layout=next(row for row in catalogue() if row.identifier==('legacy-004-31' if project=='004' else 'legacy-003-16'))
  return records.Mapper(layout,empty(layout),bindings(**changes))
 def test_timestamp_and_binding_validation_never_invents_timezone_or_reader(self):
  for value in [None,1,'invalid','2031-01-01T00:00:00',datetime(2031,1,1)]:
   with self.assertRaisesRegex(ConversionError,'timestamp_invalid'):records.stamp(value)
  bound=bindings()
  for changes in [{'installation':None},{'business':None},{'payment_readers':[]},{'payment_readers':(object(),)},{'payment_readers':bound.payment_readers*2},{'receipt_formats':{'x':'v1'}},{'receipt_formats':{'x':None}},{'resource_mapper':False}]:
   updated={'receipt_formats':dict(bound.receipt_formats),**changes}
   with self.subTest(changes=list(changes)),self.assertRaises(ConversionError):replace(bound,**updated)
 def test_configuration_retirement_requires_exact_table_digest_and_reason(self):
  mapper=self.mapper();rows=[{'limit':20}]
  for proof in [records.ConfigurationOnly('other',records.digest(rows),'historical_limits_replaced'),records.ConfigurationOnly('email_policy','a'*64,'historical_limits_replaced'),records.ConfigurationOnly('email_policy',records.digest(rows),'arbitrary')]:
   with self.assertRaisesRegex(ConversionError,'binding_invalid'):mapper.adapter(lambda *_:proof,'email_policy',rows,'legacy_binding')
  mapper.adapter(lambda *_:records.ConfigurationOnly('email_policy',records.digest(rows),'historical_limits_replaced'),'email_policy',rows,'legacy_binding');self.assertEqual(mapper.output,{})
 def test_duplicate_remote_event_identity_must_have_identical_content(self):
  mapper=self.mapper();row={'provider':'razorpay','account_id':'merchant','environment':'test','event_id':'event_one','payload_hash':'a'*64}
  mapper.add('provider_inbox',row);mapper.add('provider_inbox',deepcopy(row));self.assertEqual(len(mapper.output['provider_inbox']),1)
  with self.assertRaisesRegex(ConversionError,'provider_event_collision'):mapper.add('provider_inbox',row|{'payload_hash':'b'*64})
 def test_payment_ownership_and_quota_binding_cannot_be_guessed(self):
  mapper=self.mapper();booking=str(uuid4())
  with self.assertRaisesRegex(ConversionError,'payment_ownership_conflict'):mapper._direct('payment_observations',{'booking_id':booking,'merchant_id':'merchant123','mode':'test'})
  with self.assertRaisesRegex(ConversionError,'quota_binding_missing'):mapper._direct('email_reservations',{'job_id':None,'enquiry_job_id':None})
  mapper.rows['sarsa_booking.enquiry_delivery_jobs']=[{'id':'synthetic','kind':'verification'}]
  self.assertTrue(mapper._direct('email_reservations',{'job_id':None,'enquiry_job_id':'synthetic'})['verification'])
 def test_two_claimed_original_times_cannot_choose_one_arbitrarily(self):
  mapper=self.mapper();booking=str(uuid4());row={'id':booking,'state':'cancelled','revision':3,'starts_at':'2031-01-01T00:00:00Z','preparation':{},'service_snapshot':{'meeting_platform':'Google Meet'}}
  mapper.rows['sarsa_booking.staff_appointment_actions']=[{'booking_id':booking,'previous_revision':1,'starts_at':'2030-01-01T00:00:00Z'}]*2
  with self.assertRaisesRegex(ConversionError,'original_time_conflict'):mapper._direct('bookings',row)
 def test_unexpired_enquiry_adapter_may_change_only_protection_fields(self):
  mapper=self.mapper(enquiry_mapper=lambda row,now:row|{'payload':{'changed':'customer question'}})
  row={'request_id':str(uuid4()),'verified_at':None,'code_expires_at':(mapper.bindings.now+timedelta(minutes=5)).isoformat(),'code_digest':'a'*64,'payload':{'message':'Saved customer question'}}
  with self.assertRaisesRegex(ConversionError,'enquiry_binding_invalid'):mapper._direct('enquiries',row)
  mapper=self.mapper()
  with self.assertRaisesRegex(ConversionError,'enquiry_binding_unresolved'):mapper._direct('enquiries',row)
 def test_capacity_preserves_contiguous_half_hours_and_refuses_discontinuous_booking(self):
  mapper=self.mapper('003');booking=str(uuid4());closure=str(uuid4())
  mapper.rows['public.slot_claims']=[{'booking_id':booking,'closure_id':None,'starts_at':'2031-01-01T10:00:00Z'},{'booking_id':booking,'closure_id':None,'starts_at':'2031-01-01T10:30:00Z'}]
  mapper._capacity003();self.assertEqual(len(mapper.output['slot_claims']),1);self.assertEqual(mapper.output['slot_claims'][0]['ends_at'],'2031-01-01T11:00:00+00:00')
  mapper.rows['public.slot_claims'][1]['starts_at']='2031-01-01T11:00:00Z'
  with self.assertRaisesRegex(ConversionError,'capacity_discontinuous'):mapper._capacity003()
  mapper.output={};mapper.rows['public.closures']=[{'id':closure,'reason':'Saved holiday'}];mapper.rows['public.slot_claims']=[{'booking_id':None,'closure_id':closure,'starts_at':'2031-01-01T10:00:00Z'},{'booking_id':None,'closure_id':closure,'starts_at':'2031-01-01T11:00:00Z'}];mapper._capacity003();self.assertEqual(len(mapper.output['slot_claims']),2);self.assertTrue(all(row['closure_reason']=='Saved holiday' for row in mapper.output['slot_claims']))
 def test_missing_payment_parent_or_saved_enquiry_receipt_stops_conversion(self):
  mapper=self.mapper('003');mapper.rows['public.payments']=[{'booking_id':str(uuid4()),'payment_id':'pay_synthetic'}]
  with self.assertRaisesRegex(ConversionError,'payment_order_missing'):mapper._payments003()
  enquiry=dict.fromkeys(('name','email','phone','dob','subject','message','location','kind'),'synthetic');enquiry.update(request_id=str(uuid4()),id=str(uuid4()))
  with self.assertRaisesRegex(ConversionError,'enquiry_receipt_missing'):mapper._enquiry003(enquiry)
