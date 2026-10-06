"""Original-event durability, audience binding and the dedicated journal login."""
import base64,hashlib,hmac,json,os,time,unittest
from datetime import datetime,timezone
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4
from appointment_system.errors import Rejected
from appointment_system.provider_ingress import JournalCipher,JournalStore,persist_verified
from appointment_system.webhook import accept_webhook,WebhookAccount,InvalidWebhook,EventConflict
from appointment_system.settings import BusinessSettings
from tools.checks.sql_target import SQLTarget,literal
from .fixtures import installation,business
from .test_keys import ring
from .sql_store import IsolatedStore
from starlette.datastructures import Headers
from appointment_system.configuration import installation as current_installation
from appointment_system.mail_identity import MailIdentity,tags_for
from appointment_system.email_events import EmailWebhook

class OriginalEventCipher(unittest.TestCase):
 def setUp(self):self.cipher=JournalCipher(ring(purpose='provider-journal'))

 def test_all_body_boundaries_are_bound_to_account_event_environment_and_chunk_order(self):
  for size in (1,65535,65536,65537,131072):
   body=b'x'*size;hashed=hashlib.sha256(body).hexdigest()
   envelope=self.cipher.seal('razorpay','merchant','test','event',body)
   self.assertEqual(self.cipher.open('razorpay','merchant','test','event',envelope,hashed),body)
   for binding in [('resend','merchant','test','event'),('razorpay','other','test','event'),
      ('razorpay','merchant','live','event'),('razorpay','merchant','test','other')]:
    with self.subTest(size=size,binding=binding),self.assertRaises(Rejected):
     self.cipher.open(*binding,envelope,hashed)
   wrong=deepcopy(envelope);wrong['chunks'].reverse()
   if len(wrong['chunks'])>1:
    with self.assertRaises(Rejected):self.cipher.open('razorpay','merchant','test','event',wrong,hashed)

 def test_empty_oversized_and_malformed_envelopes_are_rejected_without_original_data(self):
  with self.assertRaises(Rejected):JournalCipher(ring())
  for body in (b'',b'x'*131073,'private customer data'):
   with self.assertRaises(Rejected):self.cipher.seal('razorpay','merchant','test','event',body)
  body=b'private customer data';hashed=hashlib.sha256(body).hexdigest()
  envelope=self.cipher.seal('razorpay','merchant','test','event',body)
  for field,value in [('version',True),('bytes',True),('bytes',0),('sha256','0'*64),('chunks',[]),('chunks',[None])]:
   broken=deepcopy(envelope);broken[field]=value
   with self.subTest(field=field),self.assertRaises(Rejected) as error:
    self.cipher.open('razorpay','merchant','test','event',broken,hashed)
   self.assertNotIn('private customer data',str(error.exception))
  with self.assertRaises(Rejected):self.cipher.open('razorpay','merchant','test','event',{},hashed)

 def test_a_mock_or_missing_marker_cannot_accidentally_choose_the_journal(self):
  store=Mock();store.save_provider_event.return_value='saved'
  self.assertEqual(persist_verified(store,'razorpay','merchant','test','id','hash',{},b'body'),'saved')
  store.save_verified_provider_event.assert_not_called()
  store.buffers_original_events=True;store.save_verified_provider_event.return_value='journal'
  self.assertEqual(persist_verified(store,'razorpay','merchant','test','id','hash',{},b'body'),'journal')

class IsolatedJournal(JournalStore):
 def __init__(self,target):
  self.bridge=IsolatedStore(target,'abs_journal');self.cipher=JournalCipher(ring(purpose='provider-journal'))
 def _call(self,statement,parameters=(),**kwargs):return self.bridge._call(statement,parameters,**kwargs)

class SignedMailJournal(unittest.TestCase):
 def setUp(self):
  self.receiver=EmailWebhook(('whsec_'+base64.b64encode(b's'*32).decode(),),(MailIdentity.current('synthetic-team'),))
  self.store=Mock();self.store.buffers_original_events=True
  self.store.save_verified_provider_event.side_effect=lambda *args:args[4]

 def event(self,**changes):
  identity=MailIdentity.current('synthetic-team')
  value={'type':'email.future_event','created_at':datetime.now(timezone.utc).isoformat(),
   'data':{'from':identity.sender,'to':['fixture@example.test'],'email_id':str(uuid4()),
    'tags':{item['name']:item['value'] for item in tags_for(str(uuid4()))}}}
  value.update(changes);return value

 def receive(self,value):
  body=json.dumps(value,separators=(',',':')).encode();timestamp=str(int(time.time()));event='msg_synthetic'
  signature=base64.b64encode(hmac.new(b's'*32,(event+'.'+timestamp+'.').encode()+body,hashlib.sha256).digest()).decode()
  return self.receiver.receive(self.store,body,Headers({'svix-id':event,'svix-timestamp':timestamp,'svix-signature':'v1,'+signature}))

 def test_owned_unknown_event_and_owned_unmapped_tags_are_saved_before_ack(self):
  for partial in (False,True):
   self.setUp();event=self.event()
   if partial:event['data']['tags'].pop('job_id')
   self.assertTrue(self.receive(event)['received'])
   args=self.store.save_verified_provider_event.call_args.args
   self.assertTrue(args[5]['unmapped']);self.assertEqual(args[0:3],('resend','synthetic-team','live'))
   self.assertNotIn('fixture@example.test',json.dumps(args[5]));self.assertEqual(json.loads(args[6]),event)

 def test_shared_account_foreign_project_environment_installation_or_sender_is_never_buffered(self):
  for name,value in [('project','foreign'),('environment','production'),('installation',str(uuid4())),('sender','other@example.com')]:
   self.setUp();event=self.event()
   if name=='sender':event['data']['from']=value
   else:event['data']['tags'][name]=value
   self.assertTrue(self.receive(event)['received']);self.store.save_verified_provider_event.assert_not_called()

 def test_durable_collision_does_not_get_a_successful_ack(self):
  self.store.save_verified_provider_event.side_effect=None;self.store.save_verified_provider_event.return_value='different'
  with self.assertRaises(EventConflict):self.receive(self.event())

@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned isolated target required.')
class JournalSQL(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET']);cls.db.check_owned();cls.profile=installation()
  cls.db.scalar('SELECT appointment_system.configure_installation('+literal(cls.profile)+'::jsonb,'+
    literal(BusinessSettings.parse(business()).document)+'::jsonb,true);')
  for purpose,target in cls.profile['database_targets'].items():
   cls.db.scalar('SELECT appointment_system.provision_login('+literal(target['role'])+','+literal(purpose)+');')
  cls.store=IsolatedJournal(cls.db)

 def setUp(self):
  self.db.sql('DELETE FROM appointment_system.conversion_handover; DELETE FROM appointment_system.provider_inbox;')
  # This is private historical ingress, not a public test-mode checkout.
  self.db.sql("UPDATE appointment_system.intake_settings SET public_open=false,merchant_id='merchant123',payment_mode='test',credential_version='fixture';")
  self.account=WebhookAccount('merchant123','test',('synthetic-signing-secret',))
  self.saved=[]

 def event(self,event='payment.captured',**extra):
  body=json.dumps(dict(entity='event',account_id='merchant123',event=event,
    payload={'payment':{'entity':{'id':'pay_fixture','order_id':'order_fixture'}}},**extra)).encode()
  signature=hmac.new(b'synthetic-signing-secret',body,hashlib.sha256).hexdigest()
  return body,signature

 def accept(self,body,signature,identifier='event_fixture'):
  return accept_webhook(self.store,self.account,body,signature,identifier,on_saved=lambda:self.saved.append(True))

 def row(self):return self.db.value('SELECT to_jsonb(p) FROM appointment_system.provider_inbox p;')

 def test_valid_supported_and_unmapped_notifications_are_committed_before_acknowledgement(self):
  for name in ('payment.captured','future.event'):
   self.setUp();body,signature=self.event(name,private={'contact':'fixture@example.test'})
   self.assertTrue(self.accept(body,signature)['received']);self.assertEqual(self.saved,[True])
   row=self.row();self.assertNotIn('fixture@example.test',json.dumps(row['payload']))
   self.assertNotIn('fixture@example.test',json.dumps(row['journal_envelope']))
   self.assertEqual(self.store.cipher.open('razorpay','merchant123','test','event_fixture',
    row['journal_envelope'],row['body_hash']),body)
   self.assertEqual(row['payload'].get('unmapped'),True if name=='future.event' else None)

 def test_duplicate_is_recoverable_collision_is_not_acknowledged_and_bad_signature_is_not_saved(self):
  body,signature=self.event();self.accept(body,signature);self.accept(body,signature)
  self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.provider_inbox;'),'1')
  other,signed=self.event(extra=1)
  with self.assertRaises(EventConflict):self.accept(other,signed)
  with self.assertRaises(InvalidWebhook):self.accept(body,'invalid')
  self.assertEqual(self.saved,[True,True]);self.assertEqual(self.row()['body_hash'],hashlib.sha256(body).hexdigest())

 def test_unregistered_account_and_malformed_envelope_cannot_enter_the_journal(self):
  body,signature=self.event()
  self.account=WebhookAccount('othermerchant','test',('synthetic-signing-secret',))
  with self.assertRaises(InvalidWebhook):self.accept(body,signature)
  args=['razorpay','unknown','test','event',hashlib.sha256(body).hexdigest(),{},self.store.cipher.seal('razorpay','unknown','test','event',body)]
  statement='SELECT appointment_system.journal_provider_event('+','.join(literal(item)+('::jsonb' if isinstance(item,dict) else '') for item in args)+');'
  self.assertNotEqual(self.db.sql(statement,role='abs_journal',check=False).returncode,0)
  for envelope in ({},{'version':1,'sha256':args[4],'bytes':None,'chunks':[]},
    {'version':1,'sha256':args[4],'bytes':1,'chunks':[None]}):
   args[1]='merchant123';args[-1]=envelope
   statement='SELECT appointment_system.journal_provider_event('+','.join(literal(item)+('::jsonb' if isinstance(item,dict) else '') for item in args)+');'
   self.assertNotEqual(self.db.sql(statement,role='abs_journal',check=False).returncode,0)
  self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.provider_inbox;'),'0')

 def test_handover_blocks_normal_work_but_keeps_exact_journal_authority(self):
  self.db.sql('INSERT INTO appointment_system.conversion_handover(id,installation_id,source_layout,source_digest,'+
    'phase,writer_roles,provider_accounts,source_counts,release_digest) VALUES ('+
    literal(str(uuid4()))+'::uuid,'+literal(self.profile['installation_id'])+"::uuid,'legacy-004-31',"+
    literal('a'*64)+",'journal_only',ARRAY['old_fixture'], '[]'::jsonb,'{}'::jsonb,"+literal('b'*64)+');')
  try:
   result=self.db.sql('SELECT appointment_system.public_policy();',role='appointment_system_web',check=False)
   self.assertNotEqual(result.returncode,0);self.assertIn('handover',result.stderr)
   body,signature=self.event();self.assertTrue(self.accept(body,signature)['received'])
   for query in ('SELECT * FROM appointment_system.provider_inbox;',
     'SELECT appointment_system.public_policy();','SELECT appointment_system.claim_payment_events(1);'):
    self.assertNotEqual(self.db.sql(query,role='abs_journal',check=False).returncode,0)
  finally:self.db.sql('DELETE FROM appointment_system.conversion_handover;')
