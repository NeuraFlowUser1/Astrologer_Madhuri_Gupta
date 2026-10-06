"""Historical facts are preserved; labels and retry state cannot invent money."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import os,unittest
from uuid import uuid4
from appointment_system.settings import Installation,BusinessSettings
from appointment_system.razorpay import Credentials
from tools.conversion.source import catalogue,ConversionError,detect,read_rows
from tools.conversion.records import Bindings,Mapper,Translation
from tools.checks.sql_target import literal
from .fixtures import installation,business
from .legacy_store import LegacyTarget

def bindings(**changes):
 return Bindings(Installation.parse(installation()),BusinessSettings.parse(business()),
  datetime.now(timezone.utc),payment_readers=(Credentials('merchant123','test','old_v1','rzp_test_legacy','synthetic-secret'),),
  receipt_formats={'receipt-003':'astro-receipt-v1','context-003':'astro-context-v1',
   'enquiry-003':'astro-inquiry-v1','receipt-004':'sarsa-receipt-v1',
   'context-004':'sarsa-context-v1','enquiry-004':'sarsa-enquiry-v1'},**changes)

def empty(layout):return {key:[] for key in layout.structure['relations']}

class ConversionBoundaries(unittest.TestCase):
 def test_live_customer_verification_is_not_silently_retired_by_handover(self):
  bound=bindings()
  for identifier in ('legacy-003-16','legacy-003-40'):
   layout=next(value for value in catalogue() if value.identifier==identifier)
   for table in ('email_challenges','email_verifications'):
    with self.subTest(layout=identifier,table=table):
     rows=empty(layout)
     row={column['name']:None for column in layout.structure['relations']['public.'+table]}
     row['expires_at']=(bound.now+timedelta(minutes=5)).isoformat()
     rows['public.'+table]=[row];before=deepcopy(rows)
     with self.assertRaisesRegex(ConversionError,'legacy_verification_continuation_required'):
      Mapper(layout,rows,bound).translate()
     self.assertEqual(rows,before)
     row['expires_at']=bound.now.isoformat()
     result=Mapper(layout,rows,bound).translate()
     self.assertNotIn(table,result.tables)
     self.assertEqual(rows['public.'+table],[row])

 def test_enquiry_transfer_preserves_named_service_and_does_not_invent_missing_old_values(self):
  for identifier,interest in [('legacy-003-16',None),('legacy-003-40','prashna-kundali'),('legacy-003-40','')]:
   with self.subTest(layout=identifier,interest=interest):
    layout=next(value for value in catalogue() if value.identifier==identifier);rows=empty(layout)
    row={column['name']:None for column in layout.structure['relations']['public.inquiries']}
    row.update(id=str(uuid4()),request_id=str(uuid4()),request_hash='a'*64,kind='prashna',
     name='Synthetic Customer',email='fixture@example.test',phone='+919999999999',dob='1990-01-01',
     subject='Saved subject',message='Saved question',location='Saved location',source='prashna',
     created_at='2026-10-01T10:00:00Z',receipt_digest='b'*64,receipt_expires_at='2031-04-05T11:00:00Z')
    if 'service_interest' in row:row['service_interest']=interest
    rows['public.inquiries']=[row];before=deepcopy(rows)
    result=Mapper(layout,rows,bindings()).translate();payload=result.tables['enquiries'][0]['payload']
    self.assertEqual(payload['service_interest'],interest)
    for name in ('kind','name','email','phone','dob','subject','message','location','source','request_id'):
     self.assertEqual(payload[name],row[name])
    self.assertEqual(payload['_legacy_reference'],row['id']);self.assertEqual(rows,before)

 def test_input_metadata_and_validated_result_cannot_be_mutated_after_review(self):
  bound=bindings();self.assertIsInstance(bound.now,datetime)
  with self.assertRaises(TypeError):bound.receipt_formats['receipt-003']='different'
  source={'bookings':[{'private':'value'}]};translated=Translation('layout','a'*64,source,{}, {})
  source['bookings'][0]['private']='changed';returned=translated.tables;returned.clear()
  self.assertEqual(translated.tables,{'bookings':[{'private':'value'}]})
  self.assertNotIn('value',repr(translated));self.assertNotIn('value',str(translated.summary()))

 def test_missing_tables_fields_duplicates_and_unprepared_history_are_refused(self):
  layout=catalogue()[0];rows=empty(layout)
  with self.assertRaisesRegex(ConversionError,'source_incomplete'):Mapper(layout,{},bindings())
  rows['public.bookings']=[{}]
  with self.assertRaisesRegex(ConversionError,'row_incomplete'):Mapper(layout,rows,bindings())
  rows=empty(layout);columns=layout.structure['relations']['public.admin_identity']
  rows['public.admin_identity']=[{item['name']:None for item in columns}]
  with self.assertRaisesRegex(ConversionError,'legacy_history_binding_unresolved'):
   Mapper(layout,rows,bindings()).translate()

 def test_callback_result_cannot_silently_discard_nonempty_history_or_add_an_arbitrary_target(self):
  layout=catalogue()[0];rows=empty(layout);columns=layout.structure['relations']['public.admin_identity']
  rows['public.admin_identity']=[{item['name']:None for item in columns}]
  for result in ({},{'staff_reviews':[]},{'../private':[{}]},[],{'staff_reviews':[False]}):
   with self.subTest(result_type=type(result).__name__),self.assertRaisesRegex(ConversionError,'binding_invalid'):
    Mapper(layout,rows,bindings(history_mapper=lambda *_:result)).translate()

 def test_wrong_or_ambiguous_payment_keys_and_reader_names_are_refused(self):
  bound=bindings()
  self.assertEqual(bound.payment(key_id='rzp_test_legacy')['merchant_id'],'merchant123')
  for value in ({'key_id':'rzp_live_foreign'},{'merchant':'foreign'},{'mode':'live'},{'version':'unknown'}):
   with self.subTest(value=value),self.assertRaisesRegex(ConversionError,'payment_binding_unresolved'):bound.payment(**value)
  with self.assertRaisesRegex(ConversionError,'reader_not_prepared'):bound.format('missing')

@unittest.skipUnless(os.environ.get('BOOKING_LEGACY_SQL_PROOF')=='owned','Owned historical native layouts required.')
class NativeLegacyRecords(unittest.TestCase):
 def setUp(self):
  self.target=LegacyTarget('legacy-003-16');self.addCleanup(self.target.close)
  self.layout=detect(self.target);self.book=str(uuid4());self.request=str(uuid4())
  self.target.run('INSERT INTO public.bookings(id,request_id,request_hash,service_id,service_name,question_count,'+
   'amount_paise,currency,duration_minutes,starts_at,full_name,email,phone,birth_details,state,hold_expires_at,created_at,'+
   'receipt_digest,receipt_expires_at) VALUES ('+literal(self.book)+'::uuid,'+literal(self.request)+'::uuid,'+
   literal('a'*64)+",'vedic-astrology','Old accepted consultation',1,210000,'INR',30,'2031-04-04T10:30:00Z',"+
   "'Synthetic Customer','fixture@example.test','+919999999999','historical preparation','confirmed',"+
   "'2026-10-01T10:10:00Z','2026-10-01T10:00:00Z',"+literal('b'*64)+",'2031-04-05T11:00:00Z');")
  self.addCleanup(self.cleanup)
  self.target.run('INSERT INTO public.payment_orders(booking_id,key_id,mode,receipt,amount_paise,state,order_id,'+
   'attempted_at,created_at) VALUES ('+literal(self.book)+"::uuid,'rzp_test_legacy','test','at_"+
   self.book.replace('-','')+"',210000,'ready','order_fixture','2026-10-01T10:01:00Z','2026-10-01T10:00:00Z');")
  self.target.run('INSERT INTO public.slot_claims(starts_at,booking_id) VALUES '+
    "('2031-04-04T10:30:00Z',"+literal(self.book)+'::uuid);')

 def cleanup(self):
  # Only rows created in this labelled synthetic fixture are removed.
  for table in ('payment_observations','payments','slot_claims','payment_orders','bookings'):
   key='id' if table=='bookings' else 'booking_id'
   self.target.run('DELETE FROM public.'+table+' WHERE '+key+'='+literal(self.book)+'::uuid;')

 def translate(self):return Mapper(self.layout,read_rows(self.target,self.layout),bindings()).translate()

 def paid(self,amount=210000):
  self.target.run('INSERT INTO public.payments(payment_id,booking_id,amount_paise,currency,received_at,disposition) '+
   "VALUES ('pay_fixture',"+literal(self.book)+'::uuid,'+str(amount)+",'INR','2026-10-01T10:02:00Z','accepted');")

 def test_saved_payment_proof_preserves_price_time_receipt_and_capacity_without_repricing(self):
  self.paid();result=self.translate();book=result.tables['bookings'][0]
  self.assertEqual(book['id'],self.book);self.assertEqual(book['request_id'],self.request)
  self.assertEqual(book['amount_paise'],210000);self.assertEqual(book['service_snapshot']['name'],'Old accepted consultation')
  self.assertEqual(book['service_snapshot']['meeting'],'google_meet')
  self.assertEqual(book['receipt_format'],'astro-receipt-v1');self.assertEqual(book['state'],'confirmed')
  self.assertEqual(len(result.tables['accepted_payments']),1)
  self.assertEqual(result.tables['slot_claims'][0]['ends_at'],'2031-04-04T11:00:00+00:00')
  self.assertIsNone(book['original_starts_at']);self.assertTrue(book['preparation']['_legacy_original_time_unknown'])
  self.assertNotIn('fixture@example.test',str(result.summary()));self.assertEqual(len(result.source_digest),64)

 def test_confirmation_label_without_saved_capture_stays_a_private_payment_review(self):
  result=self.translate();self.assertEqual(result.tables['bookings'][0]['state'],'payment_review')
  self.assertEqual(result.tables['payment_cases'][0]['reason'],'legacy_confirmation_unverified')
  self.assertNotIn('accepted_payments',result.tables)

 def test_conflicting_saved_capture_is_not_converted_into_accepted_money(self):
  self.paid(amount=1)
  with self.assertRaisesRegex(ConversionError,'accepted_payment_conflict'):self.translate()

 def test_unknown_creation_and_an_inflight_provider_claim_never_become_fresh_order_creation(self):
  self.target.run("UPDATE public.payment_orders SET state='preparing',order_id=NULL WHERE booking_id="+literal(self.book)+'::uuid;')
  result=self.translate();self.assertEqual(result.tables['payment_orders'][0]['state'],'creation_unknown')
  self.assertTrue(result.tables['payment_orders'][0]['recovery_followup'])
  rows=read_rows(self.target,self.layout)
  # A real historical row shape with an active lease is refused before adapters.
  columns={c['name']:None for c in self.layout.structure['relations']['public.delivery_jobs']}
  columns.update(lease_until='2099-01-01T00:00:00Z');rows['public.delivery_jobs']=[columns]
  with self.assertRaisesRegex(ConversionError,'provider_lease_active'):Mapper(self.layout,rows,bindings()).translate()
