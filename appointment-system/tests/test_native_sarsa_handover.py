"""Populated actual 004/31 native format, not a mocked or upgraded source."""
from datetime import datetime,timedelta
from dataclasses import replace
import hashlib,hmac,os,unittest
from uuid import UUID,uuid4
import psycopg
from psycopg.types.json import Jsonb
from tools.checks.sql_target import SQLTarget
from tools.conversion.handover import Handover
from tools.conversion.source import ConversionError
from tools.conversion.mail import MailTransfer
from tools.conversion.resources import ResourceTransfer
from tools.conversion.recovery import RecoveryTransfer
from tools.conversion.support import SupportHistoryTransfer
from appointment_system.credentials import ReceiptKeys
from appointment_system.receipt_recovery import recovery_code
from .test_keys import ring
from .native_legacy_fixture import create
from .test_native_handover import NativeJournal
from . import test_conversion_mail as mail_fixture
from . import test_conversion_grants as grant_fixture
from .test_conversion_mail import declared,job as mail_job,message
from .handover_operations import HandoverOperations
from . import test_conversion_enquiry as enquiry_fixture
from tools.conversion.enquiry import EnquiryTransfer

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET')=='abs-implementation-pg18','Owned PG18 historical 004 target required.')
class NativeSarsaHandover(HandoverOperations,unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.target=SQLTarget('abs-implementation-pg18');cls.target.check_owned()

 def setUp(self):
  self.connection,self.bound,self.database=create(self.target,'legacy-004-31')
  self.addCleanup(self.connection.close);self.socket=self.target.native_socket()
  self.journal=NativeJournal(self.target,self.database)
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  self.context=str(uuid4());self.book=str(uuid4());self.request=str(uuid4());self.claim=str(uuid4());self.observation=str(uuid4())
  policy=self.connection.execute('SELECT policy_version FROM sarsa_booking.intake_settings').fetchone()[0]
  self.connection.execute("INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,created_at,expires_at) "+
   "VALUES(%s,%s,'2026-10-01T10:00:00Z','2026-10-02T10:00:00Z')",(self.context,'a'*64))
  self.connection.execute("INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint,outcome) "+
   "VALUES(%s,%s,%s,%s,'committed')",(self.request,self.context,'b'*64,'c'*64))
  self.connection.execute("""INSERT INTO sarsa_booking.bookings(id,request_id,context_id,state,service_id,policy_version,
   service_snapshot,amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,
   preparation,hold_expires_at,receipt_expires_at,created_at) VALUES(%s,%s,%s,'confirmed','consultation',%s,%s,
    210000,'INR','2031-04-04T10:30:00Z','2031-04-04T11:00:00Z','Asia/Kolkata','Synthetic Customer',
    'fixture@example.test','+919999999999','{}'::jsonb,'2026-10-01T10:10:00Z',
    '2031-04-05T11:00:00Z','2026-10-01T10:00:00Z')""",(self.book,self.request,self.context,policy,
     Jsonb({'id':'consultation','name':'Saved paid appointment','amount_paise':210000,'duration_minutes':30,'currency':'INR'})))
  self.connection.execute('UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=%s WHERE id=%s',(self.book,self.context))
  self.connection.execute("INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version,provider_order_id,state,attempted_at) "+
   "VALUES(%s,'merchant123','test','old_v1','order_fixture','ready','2026-10-01T10:01:00Z')",(self.book,))
  self.connection.execute("INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,amount_paise,currency,captured) "+
   "VALUES(%s,%s,'merchant123','test','pay_fixture','order_fixture',%s,'captured',210000,'INR',true)",(self.observation,self.book,'d'*64))
  self.connection.execute("INSERT INTO sarsa_booking.accepted_payments VALUES(%s,%s,'merchant123','test','pay_fixture')",(self.book,self.observation))
  self.connection.execute("INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at) VALUES(%s,%s,'2031-04-04T10:30:00Z','2031-04-04T11:00:00Z')",(self.claim,self.book))

 def start(self):
  accounts=[{'provider':'razorpay','account_id':'merchant123','mode':'test'}]
  if isinstance(self.bound.mail_mapper,MailTransfer):accounts.append({'provider':'resend','account_id':'synthetic-team','mode':'live'})
  identifier=self.handover.prepare(accounts)
  self.handover.enter_journal_only(identifier,self.journal);return identifier

 def test_live_enquiry_code_finishes_after_handover_with_original_attempts_and_deadline(self):
  _,row,protection,now=enquiry_fixture.fixture()
  for field in ('code_expires_at','resend_after','receipt_expires_at'):
   row[field]=datetime.fromisoformat(row[field]).replace(microsecond=128260).isoformat()
  self.connection.execute('INSERT INTO sarsa_booking.enquiries SELECT * FROM jsonb_populate_record(NULL::sarsa_booking.enquiries,%s)',(Jsonb(row),))
  self.bound=replace(self.bound,enquiry_mapper=EnquiryTransfer(protection,'old-code','old-digest'),receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  identifier=self.start();result=self.handover.convert(identifier)
  self.handover.complete(identifier,result['target_digest'])
  saved=self.connection.execute('SELECT to_jsonb(e) FROM appointment_system.enquiries e WHERE request_id=%s',(row['request_id'],)).fetchone()[0]
  # PostgreSQL JSON omits insignificant trailing fractional-second zeros.
  # Compare exact instants, retaining microseconds, rather than display spelling.
  for field in ('code_expires_at','resend_after','receipt_expires_at'):
   self.assertEqual(datetime.fromisoformat(saved[field]),datetime.fromisoformat(row[field]))
  for field in ('attempts','generation','payload','verified_at'):
   self.assertEqual(saved[field],row[field])
  self.assertIs(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],False)
  web_role=self.bound.installation.document['database_targets']['web']['role']
  with psycopg.connect(host=self.socket,dbname=self.database,user=web_role,autocommit=True) as web:
   def verify(receipt,generation,digest):
    return web.execute('SELECT appointment_system.verify_enquiry(%s,%s,%s,%s)',(row['request_id'],receipt,generation,digest)).fetchone()[0]
   self.assertEqual(verify('f'*64,2,'a'*64)['code'],'access_unavailable')
   self.assertEqual(verify(row['receipt_digest'],1,'a'*64)['code'],'verification_changed')
   self.assertEqual(verify(row['receipt_digest'],2,'a'*64)['code'],'verification_incorrect')
   digest=protection.digest('code',row['request_id'],2,row['payload']['email'],'123456')
   self.assertEqual(verify(row['receipt_digest'],2,digest)['state'],'received')
   self.assertEqual(verify(row['receipt_digest'],2,digest)['state'],'received')
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE request_id=%s',(row['request_id'],)).fetchone()[0],4)
  # Finishing ordinary enquiries is independent of booking OFF and cannot admit
  # a booking or create duplicate acknowledgements on a repeated request.
  self.assertEqual(self.connection.execute('SELECT attempts,code_digest,code_ciphertext FROM appointment_system.enquiries WHERE request_id=%s',(row['request_id'],)).fetchone(),(4,None,None))

 def test_inflight_verification_message_keeps_exact_body_identity_and_original_deadline(self):
  from appointment_system.contact_messages import open_message
  _,row,protection,now=enquiry_fixture.fixture()
  self.connection.execute('INSERT INTO sarsa_booking.enquiries SELECT * FROM jsonb_populate_record(NULL::sarsa_booking.enquiries,%s)',(Jsonb(row),))
  job=mail_job();job.update(kind='verification',request_id=row['request_id'],payload=row['payload'],destination=row['payload']['email'],template_version=1)
  job.pop('booking_id');body=message(job,'004');body['text']='Your saved code is 123456.';body['tags'][-1]['value']='1'
  job=mail_fixture.LegacyMailTransfer().encrypted(job,body)
  self.connection.execute('''INSERT INTO sarsa_booking.enquiry_delivery_jobs
   (id,request_id,kind,generation,state,deadline_at,destination,message_ciphertext,message_digest,first_attempt_at,template_version)
   VALUES(%s,%s,'verification',2,'uncertain',%s,%s,%s,%s,%s,1)''',
   (job['id'],row['request_id'],row['code_expires_at'],job['destination'],job['message_ciphertext'],job['message_digest'],job['first_attempt_at']))
  self.bound=replace(self.bound,enquiry_mapper=EnquiryTransfer(protection,'old-code','old-digest'),
   mail_mapper=MailTransfer(declared('004'),{'004':'k1'},contact=protection,contact_formats={'004':('old-message','old-digest')}),
   receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  identifier=self.start();result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT to_jsonb(j) FROM appointment_system.enquiry_delivery_jobs j WHERE id=%s',(job['id'],)).fetchone()[0]
  self.assertEqual(saved['state'],'delivery_unknown')
  self.assertEqual(datetime.fromisoformat(saved['deadline_at']),datetime.fromisoformat(row['code_expires_at']))
  self.assertEqual(datetime.fromisoformat(saved['first_attempt_at']),datetime.fromisoformat(job['first_attempt_at']))
  self.assertEqual(saved['mail_idempotency_key'],'sarsa004/'+job['id'])
  self.assertEqual(open_message(protection,saved|{'payload':row['payload']}),body)
  self.handover.complete(identifier,result['target_digest'])

 def test_exact_published_commentless_layout_passes_complete_native_handover(self):
  from pathlib import Path
  from tools.conversion.source import detect,catalogue
  definitions=Path(__file__).parent/'legacy_schema/004/live-31-commentless-functions.sql'
  self.connection.execute(definitions.read_text(),prepare=False)
  expected=next(item for item in catalogue() if item.identifier=='legacy-004-31').variants[0]
  self.assertEqual(detect(self.connection).digest,expected.digest)
  preview=self.handover.preview()
  self.assertEqual(preview['structure_digest'],expected.digest)
  identifier=self.start();result=self.handover.convert(identifier)
  self.handover.complete(identifier,result['target_digest'])
  self.assertEqual(self.handover.checkpoint(identifier)['phase'],'complete')
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.accepted_payments').fetchone()[0],1)

 def test_paid_records_pending_calendar_and_notification_during_pause_survive(self):
  identifier=self.start();job=str(uuid4())
  with psycopg.connect(host=self.socket,dbname=self.database,user='sarsa_booking_web',autocommit=True) as old:
   old.execute("UPDATE sarsa_booking.bookings SET preparation='{"+'"notes":"last committed update"'+"}'::jsonb WHERE id=%s",(self.book,))
   old.execute("INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision) VALUES(%s,%s,'booking_calendar','calendar',1)",(job,self.book))
  body=b'owned original notification';digest=hashlib.sha256(body).hexdigest()
  self.journal.save_verified_provider_event('razorpay','merchant123','test','during_pause',digest,
   {'event':'payment.captured','payment_id':'pay_fixture','order_id':'order_fixture'},body)
  result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT preparation,original_starts_at,starts_at FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()
  self.assertEqual(saved[0]['notes'],'last committed update');self.assertEqual(saved[1],saved[2])
  self.assertEqual(self.connection.execute("SELECT service_snapshot->>'meeting' FROM appointment_system.bookings WHERE id=%s",(self.book,)).fetchone()[0],'google_meet')
  self.assertEqual(self.connection.execute('SELECT state FROM appointment_system.delivery_jobs WHERE id=%s',(job,)).fetchone()[0],'pending')
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.accepted_payments').fetchone()[0],1)
  with psycopg.connect(host=self.socket,dbname=self.database,user='sarsa_booking_web',autocommit=True) as old:
   with self.assertRaises(psycopg.errors.InsufficientPrivilege):old.execute('UPDATE sarsa_booking.bookings SET amount_paise=1')
   self.assertEqual(old.execute('SELECT 1').fetchone()[0],1)
  self.handover.complete(identifier,result['target_digest'])
  self.assertIs(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],False)

 def test_accepted_label_with_wrong_saved_amount_rolls_back_the_whole_transfer(self):
  identifier=self.start();self.connection.execute('UPDATE sarsa_booking.payment_observations SET amount_paise=1 WHERE id=%s',(self.observation,))
  with self.assertRaisesRegex(ConversionError,'accepted_payment_conflict'):self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],0)
  with psycopg.connect(host=self.socket,dbname=self.database,user='sarsa_booking_web',autocommit=True) as old:
   old.execute('UPDATE sarsa_booking.bookings SET amount_paise=210000 WHERE id=%s',(self.book,))

 def test_first_move_preserves_original_time(self):
  self.connection.execute("UPDATE sarsa_booking.bookings SET revision=2,starts_at='2031-04-04T11:00:00Z',ends_at='2031-04-04T11:30:00Z' WHERE id=%s",(self.book,))
  self.connection.execute("""INSERT INTO sarsa_booking.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,
   previous_revision,revision,starts_at,notice_seconds,policy_guidance,new_starts_at,new_ends_at)
   VALUES(%s,%s,%s,'reschedule','client:fixture','Earlier move',1,2,'2031-04-04T10:30:00Z',86400,'free_reschedule',
    '2031-04-04T11:00:00Z','2031-04-04T11:30:00Z')""",(str(uuid4()),self.claim,self.book))
  identifier=self.start();result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT original_starts_at,starts_at FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()
  self.assertEqual(saved[1]-saved[0],timedelta(minutes=30))
  self.handover.complete(identifier,result['target_digest'])

 def test_missing_first_revision_keeps_original_time_unknown(self):
  self.connection.execute('UPDATE sarsa_booking.bookings SET revision=3 WHERE id=%s',(self.book,))
  identifier=self.start();result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT original_starts_at,preparation FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()
  self.assertIsNone(saved[0]);self.assertTrue(saved[1]['_legacy_original_time_unknown'])
  self.handover.complete(identifier,result['target_digest'])

 def test_saved_support_code_history_and_throttle_windows_survive_native_transfer(self):
  material=b'Original synthetic recovery protection key';operation=str(uuid4())
  raw=hmac.new(material,f'sarsa:004:support-code:v1:{operation}:{self.request}'.encode(),hashlib.sha256).digest()
  code=str(int.from_bytes(raw,'big')%100000000).zfill(8)
  digest=hmac.new(material,f'sarsa:004:support-code-digest:v1:{self.request}:{code}'.encode(),hashlib.sha256).hexdigest()
  self.connection.execute("""INSERT INTO sarsa_booking.receipt_recoveries(operation_id,request_id,action,actor,reason,
   verified_payment_id,previous_revision,revision,code_digest,attempts,created_at,expires_at)
   VALUES(%s,%s,'receipt_recovery','client:fixture','Original approved support action','pay_fixture',1,1,%s,3,
   clock_timestamp()-interval '2 minutes',clock_timestamp()+interval '13 minutes')""",(operation,self.request,digest))
  self.connection.execute("""INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
   VALUES('receipt',%s,clock_timestamp()-interval '1 minute',clock_timestamp()+interval '1 minute',7)""",('d'*64,))
  old=self.connection.execute('SELECT to_jsonb(r) FROM sarsa_booking.receipt_recoveries r').fetchone()[0]
  window=self.connection.execute('SELECT to_jsonb(r) FROM sarsa_booking.request_limits r').fetchone()[0]
  keys=ReceiptKeys(ring(purpose='receipt'),legacy_keys=(('prior',material),),recovery_readers={'prior-support':{
   'key_id':'prior','code_audience':'sarsa:004:support-code:v1:','digest_audience':'sarsa:004:support-code-digest:v1:'}})
  self.bound=replace(self.bound,history_mapper=SupportHistoryTransfer(RecoveryTransfer(keys,'prior-support')),
   receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  identifier=self.start();result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT to_jsonb(r) FROM appointment_system.receipt_recoveries r').fetchone()[0]
  self.assertEqual({key:saved[key] for key in old},old)
  self.assertEqual(saved['code_format'],'prior-support');self.assertEqual(saved['code_key_id'],'prior')
  self.assertEqual(recovery_code(keys,operation,self.request,format=saved['code_format'],key_id=saved['code_key_id']),code)
  self.assertEqual(self.connection.execute('SELECT to_jsonb(r) FROM appointment_system.request_limits r').fetchone()[0],window)
  self.handover.complete(identifier,result['target_digest'])

 def test_frozen_booking_enquiry_mail_and_spent_quota_survive_native_transfer(self):
  proof=mail_fixture.LegacyMailTransfer();protection,_=proof.protected()
  transfer=MailTransfer(declared('004'),{'004':'k1'},contact=protection,contact_formats={'004':('old-message','old-digest')})
  self.bound=replace(self.bound,mail_mapper=transfer,receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  row=mail_job();row.update(booking_id=self.book,template_version=1)
  body=message(row,'004');body['tags'][-1]['value']='1'
  self.connection.execute("""INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,
   state,first_attempt_at,destination,message_snapshot,template_version) VALUES(%s,%s,'booking_ack','customer',1,
   'uncertain',%s,%s,%s,1)""",(row['id'],self.book,row['first_attempt_at'],row['destination'],Jsonb(body)))
  request=str(uuid4());payload={'request_id':request,'email':'customer@example.com','name':'Synthetic enquiry','message':'Saved question'}
  self.connection.execute("""INSERT INTO sarsa_booking.enquiries(request_id,email_key,receipt_digest,request_fingerprint,
   payload,code_expires_at,resend_after,verified_at) VALUES(%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp(),clock_timestamp())""",
   (request,'a'*64,'b'*64,'c'*64,Jsonb(payload)))
  enquiry=mail_job();enquiry.update(kind='acknowledgement',request_id=request,payload=payload,template_version=1)
  mail=message(enquiry,'004');mail['tags'][-1]['value']='1';enquiry=proof.encrypted(enquiry,mail)
  self.connection.execute("""INSERT INTO sarsa_booking.enquiry_delivery_jobs(id,request_id,kind,generation,state,
   deadline_at,first_attempt_at,destination,message_ciphertext,message_digest) VALUES(%s,%s,'acknowledgement',0,
   'uncertain',clock_timestamp()+interval '1 day',%s,%s,%s,%s)""",(enquiry['id'],request,enquiry['first_attempt_at'],
    enquiry['destination'],enquiry['message_ciphertext'],enquiry['message_digest']))
  self.connection.execute('INSERT INTO sarsa_booking.email_reservations(job_id,reserved_at,enquiry_job_id) VALUES(%s,%s,NULL),(NULL,%s,%s)',
   (row['id'],row['first_attempt_at'],enquiry['first_attempt_at'],enquiry['id']))
  identifier=self.start();result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT message_snapshot,mail_idempotency_key,mail_credential_version,state '+
   'FROM appointment_system.delivery_jobs WHERE id=%s',(row['id'],)).fetchone()
  self.assertEqual(saved,(body,'sarsa004/'+row['id'],'k1','delivery_unknown'))
  saved=self.connection.execute('SELECT mail_idempotency_key,message_format,state FROM appointment_system.enquiry_delivery_jobs WHERE id=%s',(enquiry['id'],)).fetchone()
  self.assertEqual(saved,('sarsa004/'+enquiry['id'],'v1','delivery_unknown'))
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.email_reservations').fetchone()[0],2)
  self.handover.complete(identifier,result['target_digest'])

 def test_owned_workbook_saved_row_and_actual_remote_event_survive_together(self):
  proof=grant_fixture.HistoricalGoogleGrants();proof.setUp();permission=proof.full()
  self.bound=replace(self.bound,resource_mapper=ResourceTransfer(proof.transfer),receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('sarsa_booking_web',))
  self.connection.execute('INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES(%s,%s)',('client',permission['subject']))
  self.connection.execute('''INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at,grant_expires_at)
   SELECT role,subject,client_id,revision,encrypted_grant,connected_at,grant_expires_at
   FROM jsonb_populate_record(NULL::sarsa_booking.google_connections,%s)''',(Jsonb(permission),))
  intent=str(uuid4());job=str(uuid4())
  self.connection.execute("""INSERT INTO sarsa_booking.google_workbooks(role,intent,subject,client_id,spreadsheet_id,state,
   connection_revision,next_row,next_enquiry_row) VALUES('client',%s,%s,%s,'existing_owned_file','ready',7,23,9)""",
   (intent,permission['subject'],permission['client_id']))
  self.connection.execute("INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,state) "+
   "VALUES(%s,%s,'sheet_booking','client_sheet',1,'accepted')",(job,self.book))
  values=['004-sarsa-jyotish-sansthan',job,self.book,'1','confirmed','Saved paid appointment',
   '2031-04-04T10:30:00+00:00','2031-04-04T11:00:00+00:00','Synthetic Customer','fixture@example.test','+919999999999','2100']
  self.connection.execute("INSERT INTO sarsa_booking.sheet_rows(role,job_id,row_number,values_json) VALUES('client',%s,22,%s)",(job,Jsonb(values)))
  external_id='sarsa'+hashlib.sha256(('004-sarsa-jyotish-sansthan:'+self.book+':1').encode()).hexdigest()
  self.connection.execute("INSERT INTO sarsa_booking.meeting_events(booking_id,booking_revision,event_id,state,meet_url) "+
   "VALUES(%s,1,%s,'ready','https://meet.google.com/abc-defg-hij')",(self.book,external_id))
  identifier=self.start();result=self.handover.convert(identifier);self.handover.complete(identifier,result['target_digest'])
  saved=self.connection.execute("SELECT spreadsheet_id,intent,workbook_protocol,grant_id FROM appointment_system.google_workbook_volumes WHERE role='client'").fetchone()
  self.assertEqual(saved[:3],('existing_owned_file',UUID(intent),'legacy-sarsa-workbook-v1'));self.assertIsNotNone(saved[3])
  self.assertEqual(self.connection.execute('SELECT event_id FROM appointment_system.meeting_events WHERE booking_id=%s',(self.book,)).fetchone()[0],external_id)
  worker=self.bound.installation.document['database_targets']['worker']['role']
  with psycopg.connect(host=self.socket,dbname=self.database,user=worker,autocommit=True) as runtime:
   mapped=runtime.execute("SELECT appointment_system.mapped_google_row('client',%s,'booking')",(job,)).fetchone()[0]
   self.assertEqual(mapped['row'],22);self.assertEqual(mapped['values'],values)
   self.assertEqual(mapped['intent'],intent);self.assertEqual(mapped['workbook_protocol'],'legacy-sarsa-workbook-v1')
   next_volume=runtime.execute("SELECT appointment_system.claim_google_workbook_v2('client',%s)",(permission['client_id'],)).fetchone()[0]
   self.assertEqual(next_volume['layout_version'],1);self.assertEqual(next_volume['volume_number'],1)
   self.assertEqual(next_volume['intent'],intent);self.assertEqual(next_volume['action'],'ready')
   self.assertEqual(next_volume['workbook_protocol'],'legacy-sarsa-workbook-v1')
  self.assertEqual(self.connection.execute("SELECT spreadsheet_id,state FROM appointment_system.google_workbook_volumes WHERE role='client' AND volume_number=1").fetchone(),
   ('existing_owned_file','ready'))
