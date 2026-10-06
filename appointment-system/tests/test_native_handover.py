"""Same-connection final snapshot, permission fence and atomic native import."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib,os,unittest
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from appointment_system.provider_ingress import JournalStore,JournalCipher
from appointment_system.settings import Installation
from tools.checks.sql_target import SQLTarget,ROOT
from tools.conversion.source import catalogue,ConversionError
from tools.conversion.handover import Handover
from tools.conversion.transport import TransportTransfer
from tools.conversion.mail import MailTransfer
from tools.conversion.mail_events import MailEventTransfer
from tools.conversion.allowance import AllowanceTransfer
from tools.conversion.resources import ResourceTransfer
from tools.conversion.support import SupportHistoryTransfer
from . import test_conversion_grants as grant_fixture
from tools.conversion import verification
from .test_conversion_mail import declared,message,job
from .test_contact_protection import keys
from .test_keys import ring
from .test_conversion_records import bindings
from .handover_operations import HandoverOperations

SOURCE=ROOT/'tests/legacy_schema/003'
DATABASE='abs_handover_003'

class NativeJournal(JournalStore):
 def __init__(self,target,database):
  self.target=target;self.database=database;self.cipher=JournalCipher(ring(purpose='provider-journal'))
 def _call(self,statement,parameters=(),**kwargs):
  self.target.check_owned()
  with psycopg.connect(host=self.target.native_socket(),dbname=self.database,user='abs_journal',autocommit=True) as connection:
   return connection.execute(statement,parameters).fetchone()[0]

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET')=='abs-implementation-pg16','Owned PG16 historical 003 target required.')
class NativeHandover(HandoverOperations,unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.target=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET']);cls.target.check_owned();cls.socket=cls.target.native_socket()
  cls.layout=next(item for item in catalogue() if item.identifier=='legacy-003-16')

 def setUp(self):
  with psycopg.connect(host=self.socket,dbname='postgres',user='postgres',autocommit=True) as admin:
   admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(DATABASE)))
   admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DATABASE)))
   if admin.execute("SELECT 1 FROM pg_roles WHERE rolname='astro_booking_app'").fetchone() is None:
    admin.execute('CREATE ROLE astro_booking_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
  self.connection=psycopg.connect(host=self.socket,dbname=DATABASE,user='postgres',autocommit=True)
  self.addCleanup(self.connection.close)
  for name,digest in self.layout.ledger.items():
   path=SOURCE/name;self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
   self.connection.execute(path.read_text(),prepare=False)
  self.connection.execute('CREATE TABLE public.schema_migrations(name text PRIMARY KEY,checksum text NOT NULL)')
  for name,digest in self.layout.ledger.items():self.connection.execute('INSERT INTO public.schema_migrations VALUES(%s,%s)',(name,digest))
  self.connection.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO astro_booking_app')
  for path in sorted((ROOT/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql')):
   self.connection.execute(path.read_text(),prepare=False)
   self.connection.execute('INSERT INTO appointment_system.schema_migrations(version,sha256) VALUES(%s,%s)',
    (path.name,hashlib.sha256(path.read_bytes()).hexdigest()))
  bound=bindings();profile=bound.installation.document
  for target in profile['database_targets'].values():target['database']=DATABASE
  profile['database_targets']['migration']=dict(profile['database_targets']['web'],role='postgres',pooling=False)
  self.bound=replace(bound,installation=Installation.parse(profile),receipt_formats=dict(bound.receipt_formats))
  self.connection.execute('SELECT appointment_system.configure_installation(%s,%s,false)',(Jsonb(profile),Jsonb(self.bound.business.document)))
  for purpose,target in profile['database_targets'].items():
   if purpose!='migration':self.connection.execute('SELECT appointment_system.provision_login(%s,%s)',(target['role'],purpose))
  self.journal=NativeJournal(self.target,DATABASE)
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  self.book=str(uuid4());self.request=str(uuid4())
  self.connection.execute("""INSERT INTO public.bookings(id,request_id,request_hash,service_id,service_name,question_count,
   amount_paise,currency,duration_minutes,starts_at,full_name,email,phone,birth_details,state,hold_expires_at,created_at,
   receipt_digest,receipt_expires_at) VALUES(%s,%s,%s,'vedic-astrology','Original paid service',1,210000,'INR',30,
    '2031-04-04T10:30:00Z','Synthetic Customer','fixture@example.test','+919999999999','preparation','confirmed',
    '2026-10-01T10:10:00Z','2026-10-01T10:00:00Z',%s,'2031-04-05T11:00:00Z')""",(self.book,self.request,'b'*64,'c'*64))
  self.connection.execute("""INSERT INTO public.payment_orders(booking_id,key_id,mode,receipt,amount_paise,state,order_id,
    attempted_at,created_at) VALUES(%s,'rzp_test_legacy','test',%s,210000,'ready','order_fixture',
    '2026-10-01T10:01:00Z','2026-10-01T10:00:00Z')""",(self.book,'at_'+self.book.replace('-','')))
  self.connection.execute("INSERT INTO public.payments VALUES('pay_fixture',%s,210000,'INR','2026-10-01T10:02:00Z','accepted')",(self.book,))
  self.connection.execute("INSERT INTO public.slot_claims VALUES('2031-04-04T10:30:00Z',%s,NULL)",(self.book,))

 def start(self):
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
  self.handover.enter_journal_only(identifier,self.journal);return identifier

 def test_live_verification_refuses_import_without_losing_source_or_writer_access(self):
  for table in ('email_challenges','email_verifications'):
   expires=self.bound.now+timedelta(minutes=5)
   if table=='email_challenges':
    self.connection.execute("INSERT INTO public.email_challenges VALUES('verify@example.test','contact',%s,%s,%s,2,true)",
     (str(uuid4()),'d'*64,expires))
   else:
    self.connection.execute("INSERT INTO public.email_verifications VALUES(%s,'verify@example.test','booking',%s)",('e'*64,expires))
  with self.assertRaisesRegex(ConversionError,'legacy_verification_continuation_required'):self.handover.preview()
  identifier=self.start()
  with self.assertRaisesRegex(ConversionError,'legacy_verification_continuation_required'):self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],0)
  self.assertEqual(self.connection.execute('SELECT phase FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()[0],'journal_only')
  with psycopg.connect(host=self.socket,dbname=DATABASE,user='astro_booking_app',autocommit=True) as old:
   self.assertEqual(old.execute("SELECT attempts FROM public.email_challenges WHERE email='verify@example.test'").fetchone()[0],2)
   old.execute("UPDATE public.bookings SET notes='old writer remains authoritative' WHERE id=%s",(self.book,))
  # Model natural expiry in synthetic source data, without changing the
  # production customer's lifetime or inventing a new verification grant.
  for table in ('email_challenges','email_verifications'):
   self.connection.execute(sql.SQL('UPDATE public.{} SET expires_at=%s').format(sql.Identifier(table)),(self.bound.now,))
  result=self.handover.convert(identifier);self.handover.complete(identifier,result['target_digest'])

 def test_pinned_staff_identity_calendar_permission_and_existing_event_survive_together(self):
  proof=grant_fixture.HistoricalGoogleGrants();proof.setUp();grant=proof.calendar(bare=True)
  self.connection.execute('INSERT INTO public.admin_identity VALUES(true,%s,%s)',(grant['google_subject'],grant['connected_at']))
  self.connection.execute('INSERT INTO public.google_connection(singleton,google_subject,calendar_id,refresh_token_encrypted,scopes,connected_at) VALUES(true,%s,%s,%s,%s,%s)',
   tuple(grant[field] for field in ('google_subject','calendar_id','refresh_token_encrypted','scopes','connected_at')))
  event='astro'+self.book.replace('-','');meet='https://meet.google.com/abc-defg-hij'
  self.connection.execute("INSERT INTO public.booking_calendar_events VALUES(%s,%s,%s,'ready',%s,clock_timestamp(),clock_timestamp())",(self.book,grant['calendar_id'],event,meet))
  self.bound=replace(self.bound,resource_mapper=ResourceTransfer(proof.transfer),history_mapper=SupportHistoryTransfer(),receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  identifier=self.start();result=self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT role,subject FROM appointment_system.studio_identities').fetchall(),[('client',grant['google_subject'])])
  self.assertEqual(self.connection.execute('SELECT event_id,state,meet_url FROM appointment_system.meeting_events WHERE booking_id=%s',(self.book,)).fetchone(),(event,'ready',meet))
  self.assertEqual(self.connection.execute('SELECT calendar_protocol FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()[0],'legacy-astro003-unversioned')
  owner=self.connection.execute('SELECT owner_email,grant_format,last_error_code FROM appointment_system.google_resource_grants').fetchone()
  self.assertEqual(owner,(grant['calendar_id'],'astro-calendar-bare','legacy_owner_verification_required'))
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.delivery_jobs').fetchone()[0],0)
  self.handover.complete(identifier,result['target_digest'])

 def test_explicit_reauthorization_preserves_calendar_event_without_unreadable_old_key(self):
  proof=grant_fixture.HistoricalGoogleGrants();proof.setUp();grant=proof.calendar(bare=True)
  self.connection.execute('INSERT INTO public.admin_identity VALUES(true,%s,%s)',(grant['google_subject'],grant['connected_at']))
  self.connection.execute('INSERT INTO public.google_connection(singleton,google_subject,calendar_id,refresh_token_encrypted,scopes,connected_at) VALUES(true,%s,%s,%s,%s,%s)',
   tuple(grant[field] for field in ('google_subject','calendar_id','refresh_token_encrypted','scopes','connected_at')))
  from tools.conversion.grants import GrantTransfer
  from appointment_system.google_resources import Resources,ResourceCipher
  from .test_google_resources import spec,WEB
  proof.transfer=GrantTransfer(self.bound.installation,Resources(spec(),ResourceCipher(ring(purpose='google-resource-grant'))),
    calendar_client=WEB,calendar_reauthorization=True)
  event='astro'+self.book.replace('-','');meet='https://meet.google.com/abc-defg-hij'
  self.connection.execute("INSERT INTO public.booking_calendar_events VALUES(%s,%s,%s,'ready',%s,clock_timestamp(),clock_timestamp())",(self.book,grant['calendar_id'],event,meet))
  self.bound=replace(self.bound,resource_mapper=ResourceTransfer(proof.transfer),history_mapper=SupportHistoryTransfer(),receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  identifier=self.start();result=self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT role,subject FROM appointment_system.studio_identities').fetchall(),[('client',grant['google_subject'])])
  self.assertEqual(self.connection.execute('SELECT event_id,state,meet_url FROM appointment_system.meeting_events WHERE booking_id=%s',(self.book,)).fetchone(),(event,'ready',meet))
  self.assertEqual(self.connection.execute('SELECT calendar_protocol FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()[0],'legacy-astro003-unversioned')
  owner=self.connection.execute('SELECT owner_email,grant_format,last_error_code FROM appointment_system.google_resource_grants').fetchone()
  self.assertEqual(owner,(grant['calendar_id'],'reauthorization-required','google_reconnect_required'))
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.delivery_jobs').fetchone()[0],0)
  self.handover.complete(identifier,result['target_digest'])
  self.assertFalse(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0])
  self.connection.execute("SELECT appointment_system.provision_login('abs_worker','worker')")
  with psycopg.connect(host=self.socket,dbname=DATABASE,user='abs_worker',autocommit=True) as worker:
   self.assertEqual(worker.execute("SELECT appointment_system.claim_google_resource_refresh('calendar')").fetchone()[0],
     {'code':'google_reconnect_required'})
  self.assertEqual(self.connection.execute('SELECT refresh_token_encrypted FROM public.google_connection').fetchone()[0],grant['refresh_token_encrypted'])

 def test_final_delta_paid_facts_and_callback_are_preserved_then_old_writer_is_denied(self):
  identifier=self.start()
  with psycopg.connect(host=self.socket,dbname=DATABASE,user='astro_booking_app',autocommit=True) as old:
   old.execute("UPDATE public.bookings SET notes='last committed legacy change' WHERE id=%s",(self.book,))
  body=b'{"synthetic":"signed provider notification fixture"}';digest=hashlib.sha256(body).hexdigest()
  self.assertEqual(self.journal.save_verified_provider_event('razorpay','merchant123','test','during_pause',digest,
    {'event':'payment.captured','payment_id':'pay_fixture','order_id':'order_fixture'},body),digest)
  result=self.handover.convert(identifier)
  converted=self.connection.execute('SELECT preparation,state,amount_paise FROM appointment_system.bookings WHERE id=%s',(self.book,)).fetchone()
  self.assertEqual(converted[0]['notes'],'last committed legacy change');self.assertEqual(converted[1:],('confirmed',210000))
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.accepted_payments').fetchone()[0],1)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.provider_inbox WHERE event_id=%s',('during_pause',)).fetchone()[0],1)
  with psycopg.connect(host=self.socket,dbname=DATABASE,user='astro_booking_app',autocommit=True) as old:
   with self.assertRaises(psycopg.errors.InsufficientPrivilege):old.execute('UPDATE public.bookings SET amount_paise=1')
   # Login remains available; no cluster-wide disable was used.
   self.assertEqual(old.execute('SELECT 1').fetchone()[0],1)
  self.handover.complete(identifier,result['target_digest'])
  self.assertEqual(self.connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],False)
  with self.assertRaisesRegex(ConversionError,'rollback_forbidden'):self.handover.abort_before_import(identifier)

 def test_bad_record_rolls_back_permissions_and_target_rows_together(self):
  identifier=self.start();self.connection.execute("UPDATE public.payments SET amount_paise=1 WHERE booking_id=%s",(self.book,))
  with self.assertRaisesRegex(ConversionError,'accepted_payment_conflict'):self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],0)
  self.assertEqual(self.connection.execute('SELECT phase FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()[0],'journal_only')
  with psycopg.connect(host=self.socket,dbname=DATABASE,user='astro_booking_app',autocommit=True) as old:
   old.execute('UPDATE public.bookings SET notes=%s WHERE id=%s',('still sole old writer',self.book))

 def test_pause_requires_actual_journal_login_and_abort_cannot_discard_new_notifications(self):
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
  with self.assertRaisesRegex(ConversionError,'journal_not_ready'):self.handover.enter_journal_only(identifier,object())
  self.handover.enter_journal_only(identifier,self.journal)
  body=b'owned notification';digest=hashlib.sha256(body).hexdigest()
  self.journal.save_verified_provider_event('razorpay','merchant123','test','pending',digest,{'event':'unknown','unmapped':True},body)
  with self.assertRaisesRegex(ConversionError,'pending_notifications'):self.handover.abort_before_import(identifier)

 def test_legacy_object_owner_or_schema_creator_is_refused_before_pause_or_revocation(self):
  self.connection.execute('GRANT CREATE ON SCHEMA public TO astro_booking_app')
  with self.assertRaisesRegex(ConversionError,'can_change_schema'):
   self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.conversion_handover').fetchone()[0],0)

 def test_completion_rechecks_actual_rows_and_never_accepts_a_saved_digest_alone(self):
  identifier=self.start();result=self.handover.convert(identifier)
  manifest=self.connection.execute('SELECT verification_manifest FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()[0]
  self.assertNotIn('fixture@example.test',str(manifest));self.assertNotIn('Synthetic Customer',str(manifest))
  self.connection.execute("UPDATE appointment_system.bookings SET full_name='Altered after import' WHERE id=%s",(self.book,))
  with self.assertRaisesRegex(ConversionError,'verification_content_changed'):
   self.handover.complete(identifier,result['target_digest'])

  self.connection.execute("UPDATE appointment_system.conversion_handover SET verification_manifest='{}'::jsonb WHERE id=%s",(identifier,))
  with self.assertRaisesRegex(ConversionError,'result_mismatch'):
   self.handover.complete(identifier,result['target_digest'])
  self.assertEqual(self.connection.execute('SELECT phase FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()[0],'imported')

 def test_completion_detects_a_missing_payment_record(self):
  identifier=self.start();result=self.handover.convert(identifier)
  self.connection.execute('DELETE FROM appointment_system.accepted_payments WHERE booking_id=%s',(self.book,))
  with self.assertRaisesRegex(ConversionError,'verification_content_changed'):
   self.handover.complete(identifier,result['target_digest'])

 def test_completion_rechecks_final_saved_source_records_after_import(self):
  identifier=self.start();result=self.handover.convert(identifier)
  self.connection.execute("UPDATE public.bookings SET notes='unexpected owner change' WHERE id=%s",(self.book,))
  with self.assertRaisesRegex(ConversionError,'source_records_changed'):
   self.handover.complete(identifier,result['target_digest'])
  self.assertEqual(self.connection.execute('SELECT phase FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()[0],'imported')

 def test_retired_verification_and_unmatched_reports_never_become_current_authority(self):
  mail=MailTransfer(declared('003'),{'003':'k1'},contact=keys());transport=TransportTransfer(self.bound,mail)
  self.bound=replace(self.bound,transport_mapper=transport,mail_mapper=mail,
   history_mapper=SupportHistoryTransfer(mail_events=MailEventTransfer(transport)),receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  challenge=str(uuid4());provider=str(uuid4());orphan=str(uuid4());when=self.bound.now.isoformat()
  self.connection.execute("INSERT INTO public.verification_emails VALUES(%s,%s,'contact',%s)",(challenge,provider,when))
  for identifier,reference in [('evt_retired_code',provider),('evt_unmatched',orphan)]:
   self.connection.execute("INSERT INTO public.email_events VALUES(%s,%s,'email.delivered',%s,%s)",(identifier,reference,when,when))
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'},
   {'provider':'resend','account_id':'synthetic-team','mode':'live'}])
  self.handover.enter_journal_only(identifier,self.journal);result=self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT challenge_id::text,provider_id::text,purpose,mail_account_id FROM appointment_system.historical_verification_receipts').fetchall(),
   [(challenge,provider,'contact','synthetic-team')])
  self.assertEqual(self.connection.execute('SELECT classification,challenge_id::text FROM appointment_system.historical_email_observations ORDER BY event_id').fetchall(),
   [('verification',challenge),('unmatched',None)])
  for table in ('booking_verification_challenges','booking_verification_grants','booking_verification_mail','delivery_jobs','mail_acceptance_claims'):
   self.assertEqual(self.connection.execute(sql.SQL('SELECT count(*) FROM appointment_system.{}').format(sql.Identifier(table))).fetchone()[0],0)
  for purpose in ('web','staff','worker','company','backup'):
   role=self.bound.installation.document['database_targets'][purpose]['role']
   for table in ('historical_verification_receipts','historical_email_observations'):
    self.assertIs(self.connection.execute("SELECT has_table_privilege(%s,%s,'SELECT')",(role,'appointment_system.'+table)).fetchone()[0],purpose=='backup')
  self.handover.complete(identifier,result['target_digest'])
  # Even a correctly frozen new message cannot claim a retired code's
  # provider reference as its own successful send.
  new_job=str(uuid4())
  self.connection.execute("INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,first_attempt_at,message_hash) VALUES(%s,%s,'booking_ack','customer',1,clock_timestamp(),%s)",
   (new_job,self.book,'b'*64))
  outcome=self.connection.execute("SELECT appointment_system.append_mail_acceptance('booking',%s,%s,%s)",(new_job,'b'*64,provider)).fetchone()[0]
  self.assertEqual(outcome,'conflict')
  self.assertEqual(self.connection.execute('SELECT result FROM appointment_system.mail_acceptance_claims WHERE job_id=%s',(new_job,)).fetchone()[0],'conflict')

 def test_old_delivery_reports_preserve_acceptance_and_bounce_suppression(self):
  mail=MailTransfer(declared('003'),{'003':'k1'},contact=keys());transport=TransportTransfer(self.bound,mail)
  history=SupportHistoryTransfer(mail_events=MailEventTransfer(transport))
  self.bound=replace(self.bound,transport_mapper=transport,mail_mapper=mail,history_mapper=history,receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  row=job();row.update(booking_id=self.book,template_version=1)
  body=message(row,'003');body.pop('tags');provider=str(uuid4())
  self.connection.execute("""INSERT INTO public.delivery_jobs(id,dedupe_key,kind,record_id,state,attempts,created_at,
   recipient_role,message_version,next_attempt_at,first_attempt_at,send_uncertain,message_payload,provider_id)
   VALUES(%s,%s,'booking_confirmed',%s,'processing',1,%s,'customer',1,%s,%s,true,%s,%s)""",
   (row['id'],'confirmation:'+self.book,self.book,row['first_attempt_at'],row['first_attempt_at'],row['first_attempt_at'],Jsonb(body),provider))
  self.connection.execute("INSERT INTO public.email_events VALUES('evt_old_bounce',%s,'email.bounced',%s,%s)",
   (provider,row['first_attempt_at'],row['first_attempt_at']))
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'},
    {'provider':'resend','account_id':'synthetic-team','mode':'live'}])
  self.handover.enter_journal_only(identifier,self.journal);result=self.handover.convert(identifier)
  facts=self.connection.execute('SELECT event_id,job_id::text,provider_id::text,event_type FROM appointment_system.email_observations').fetchall()
  self.assertEqual(facts,[('evt_old_bounce',row['id'],provider,'email.bounced')])
  claims=self.connection.execute('SELECT kind,job_id::text,provider_id::text,result FROM appointment_system.mail_acceptance_claims').fetchall()
  self.assertEqual(claims,[('booking',row['id'],provider,'accepted')])
  self.assertIs(self.connection.execute('SELECT appointment_system.email_recipient_suppressed(%s)',(row['destination'],)).fetchone()[0],True)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.delivery_jobs').fetchone()[0],1)
  self.handover.complete(identifier,result['target_digest'])
  worker=self.bound.installation.document['database_targets']['worker']['role']
  with psycopg.connect(host=self.socket,dbname=DATABASE,user=worker,autocommit=True) as runtime:
   self.assertIsNone(runtime.execute('SELECT appointment_system.claim_email_delivery()').fetchone()[0])
  self.assertEqual(self.connection.execute('SELECT state FROM appointment_system.delivery_jobs WHERE id=%s',(row['id'],)).fetchone()[0],'completed')

 def test_completed_enquiry_sheet_copies_transfer_without_new_writes_or_mail(self):
  transport=TransportTransfer(self.bound)
  self.bound=replace(self.bound,transport_mapper=transport,receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  enquiry=str(uuid4());request=str(uuid4());jobs=[]
  self.connection.execute("""INSERT INTO public.inquiries(id,request_id,request_hash,kind,name,email,phone,
   subject,message,created_at,receipt_digest,receipt_expires_at,source)
   VALUES(%s,%s,%s,'contact','Synthetic Enquirer','fixture@example.test','+919999999999',
   'Synthetic subject','Synthetic message','2026-10-01T10:00:00Z',%s,'2031-04-05T11:00:00Z','contact')""",
   (enquiry,request,'d'*64,'e'*64))
  for role in ('client_sheet','agency_sheet'):
   identifier=str(uuid4());jobs.append((identifier,role))
   self.connection.execute("""INSERT INTO public.delivery_jobs(id,dedupe_key,kind,record_id,state,attempts,created_at,
    recipient_role,message_version,next_attempt_at,first_attempt_at)
    VALUES(%s,%s,'sheet_inquiry',%s,'sent',1,'2026-10-01T10:00:00Z',%s,1,
    '2026-10-01T10:00:00Z','2026-10-01T10:00:00Z')""",(identifier,role+':'+enquiry,enquiry,role))
  identifier=self.start();result=self.handover.convert(identifier)
  self.handover.complete(identifier,result['target_digest'])
  for job_id,role in jobs:
   saved=self.connection.execute('SELECT request_id,kind,state,attempts,destination FROM appointment_system.enquiry_delivery_jobs WHERE id=%s',(job_id,)).fetchone()
   self.assertEqual(tuple(str(item) if index==0 else item for index,item in enumerate(saved)),
    (request,role,'completed',1,None))
  for table in ('email_reservations','mail_acceptance_claims','enquiry_sheet_rows','google_resource_grants'):
   self.assertEqual(self.connection.execute(sql.SQL('SELECT count(*) FROM appointment_system.{}').format(sql.Identifier(table))).fetchone()[0],0)

 def test_original_frozen_booking_mail_survives_native_transfer_without_new_identity(self):
  mail=MailTransfer(declared('003'),{'003':'k1'},contact=keys())
  transport=TransportTransfer(self.bound,mail)
  self.bound=replace(self.bound,transport_mapper=transport,mail_mapper=mail,receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  row=job();row.update(booking_id=self.book,template_version=1)
  body=message(row,'003');body.pop('tags')
  provider=str(uuid4())
  self.connection.execute("""INSERT INTO public.delivery_jobs(id,dedupe_key,kind,record_id,state,attempts,created_at,
   recipient_role,message_version,next_attempt_at,first_attempt_at,send_uncertain,message_payload)
   VALUES(%s,%s,'booking_confirmed',%s,'processing',1,%s,'customer',1,%s,%s,true,%s)""",
   (row['id'],'confirmation:'+self.book,self.book,row['first_attempt_at'],row['first_attempt_at'],row['first_attempt_at'],Jsonb(body)))
  self.connection.execute('UPDATE public.delivery_jobs SET provider_id=%s WHERE id=%s',(provider,row['id']))
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'},
    {'provider':'resend','account_id':'synthetic-team','mode':'live'}])
  self.handover.enter_journal_only(identifier,self.journal);result=self.handover.convert(identifier)
  saved=self.connection.execute('SELECT kind,message_snapshot,mail_idempotency_key,state,payload FROM appointment_system.delivery_jobs WHERE id=%s',(row['id'],)).fetchone()
  self.assertEqual(saved[:4],('booking_details',body,'booking/'+self.book+'/booking_confirmed/customer/v1','delivery_unknown'))
  self.assertEqual(saved[4]['service_snapshot']['name'],'Original paid service')
  self.handover.complete(identifier,result['target_digest'])
  configuration=declared('003')
  metadata={'account_id':configuration.account_id,'active_key_id':configuration.active_key_id,
   'retained_keys':list(configuration.keys),'legacy_identities':[
    dict(format=item.format,project=item.project,sender=item.sender,address=item.address,reply_to=item.reply_to,event_account_id=item.event_account_id)
    for item in configuration.identities if item.format!='resend-v1']}
  self.connection.execute('SELECT appointment_system.configure_mail_connection(%s,20,600)',(Jsonb(metadata),))
  report={'event':'email.delivered','email_id':provider,'occurred_at':self.bound.now.isoformat(),'binding_version':2,
   'mail_format':'resend-legacy-untagged-job-v1','recipient_hash':hashlib.sha256(row['destination'].strip().lower().encode()).hexdigest()}
  identity=next(item for item in configuration.identities if item.format==report['mail_format'])
  for name,value in [('wrong-account',report),('wrong-recipient',report|{'recipient_hash':'f'*64}),('owned-report',report)]:
   self.connection.execute('INSERT INTO appointment_system.provider_inbox(provider,account_id,environment,event_id,body_hash,payload) '+
    "VALUES('resend',%s,'live',%s,%s,%s)",(('foreign' if name=='wrong-account' else identity.event_account_id),name,'f'*64,Jsonb(value)))
  worker=self.bound.installation.document['database_targets']['worker']['role']
  with psycopg.connect(host=self.socket,dbname=DATABASE,user=worker,autocommit=True) as runtime:
   self.assertIs(runtime.execute('SELECT appointment_system.reconcile_email_event()').fetchone()[0],False)
   self.assertIs(runtime.execute('SELECT appointment_system.reconcile_email_event()').fetchone()[0],True)
  self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.email_observations WHERE job_id=%s',(row['id'],)).fetchone()[0],1)
  self.assertEqual(self.connection.execute("SELECT event_id FROM appointment_system.provider_inbox WHERE provider='resend' AND processed_at IS NOT NULL").fetchall(),[('owned-report',)])

 def test_real_daily_spending_and_existing_job_reservation_do_not_reset_or_count_twice(self):
  from datetime import timedelta
  mail=MailTransfer(declared('003'),{'003':'k1'},contact=keys());transport=TransportTransfer(self.bound,mail)
  quota=AllowanceTransfer(self.bound)
  self.bound=replace(self.bound,transport_mapper=transport,mail_mapper=mail,quota_mapper=quota,receipt_formats=dict(self.bound.receipt_formats))
  self.handover=Handover(self.connection,self.bound,'a'*64,('astro_booking_app',))
  row=job();row.update(booking_id=self.book,template_version=1);body=message(row,'003');body.pop('tags')
  self.connection.execute("""INSERT INTO public.delivery_jobs(id,dedupe_key,kind,record_id,state,attempts,created_at,
   recipient_role,message_version,next_attempt_at,first_attempt_at,send_uncertain,message_payload)
   VALUES(%s,%s,'booking_confirmed',%s,'pending',1,%s,'customer',1,%s,%s,true,%s)""",
   (row['id'],'confirmation:'+self.book,self.book,row['first_attempt_at'],row['first_attempt_at'],row['first_attempt_at'],Jsonb(body)))
  reset=self.bound.now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
  for name,count,expiry in [('resend:daily:all',20,reset),('resend:daily:verification',5,reset),
    ('resend:rolling31:'+self.bound.now.date().isoformat(),20,reset+timedelta(days=31))]:
   self.connection.execute('INSERT INTO public.rate_limits VALUES(%s,%s,%s)',(name,count,expiry))
  identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'},
    {'provider':'resend','account_id':'synthetic-team','mode':'live'}])
  self.handover.enter_journal_only(identifier,self.journal);result=self.handover.convert(identifier)
  self.assertEqual(self.connection.execute('SELECT total_count,verification_count FROM appointment_system.email_allowance_baselines').fetchone(),(20,5))
  self.assertIs(self.connection.execute('SELECT counted_in_legacy_baseline FROM appointment_system.email_reservations WHERE job_id=%s',(row['id'],)).fetchone()[0],True)
  metadata={'account_id':'synthetic-team','active_key_id':'k2','retained_keys':['k1','k2'],'legacy_identities':[]}
  self.connection.execute('SELECT appointment_system.configure_mail_connection(%s,20,600)',(Jsonb(metadata),))
  self.connection.execute("SET TIME ZONE 'Pacific/Kiritimati'")
  self.assertIsNone(self.connection.execute("SELECT appointment_system.reserve_delivery_budget('booking_notification',%s)",(row['id'],)).fetchone()[0])
  self.assertEqual(self.connection.execute("SELECT appointment_system.reserve_delivery_budget('booking_notification',%s)",(str(uuid4()),)).fetchone()[0],'email_budget_exhausted')
  self.handover.complete(identifier,result['target_digest'])

 def test_bounded_native_verification_checks_a_changed_record_in_the_last_batch(self):
  rows=[dict(id=str(uuid4()),role='client',action='signin',at=self.bound.now.isoformat()) for _ in range(123)]
  for row in rows:self.connection.execute('INSERT INTO appointment_system.studio_audit(id,role,action,at) VALUES(%s,%s,%s,%s)',
    (row['id'],row['role'],row['action'],row['at']))
  manifest=verification.capture(self.connection,{'studio_audit':rows})
  self.assertEqual(manifest['studio_audit']['count'],123);verification.verify(self.connection,manifest)
  self.connection.execute("UPDATE appointment_system.studio_audit SET action='connect' WHERE id=%s",(rows[-1]['id'],))
  with self.assertRaisesRegex(ConversionError,'verification_content_changed'):verification.verify(self.connection,manifest)
