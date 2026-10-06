"""Actual old mail bytes and retry identities, without sending any mail."""
from dataclasses import replace
from datetime import datetime,timezone
from copy import deepcopy
import hashlib,hmac,json,unittest
from uuid import uuid4
from cryptography.fernet import Fernet
import httpx
from appointment_system.contact import ContactSecrets
from appointment_system.contact_messages import open_message
from appointment_system.email_configuration import connection
from appointment_system.email_messages import message_hash
from appointment_system.resend_email import ResendSender
from appointment_system.keys import encode
from appointment_system.serialization import canonical
from tools.conversion.source import catalogue,ConversionError
from tools.conversion.mail import MailTransfer,FORMATS,PROJECTS
from .test_contact_protection import keys
from .test_mail_contracts import document

def declared(project):
 value=document();record=value['legacy_identities'][0]
 record.update(format=FORMATS[project],project=PROJECTS[project],sender='Historical Practice <old@example.com>',
  address='old@example.com',reply_to='practice@example.test')
 if project=='003':value['legacy_identities'].append(record|{'format':'resend-legacy-untagged-job-v1'})
 return connection(json.dumps(value))

def job():
 return {'id':str(uuid4()),'booking_id':str(uuid4()),'kind':'booking_ack','recipient_role':'customer',
  'template_version':2,'first_attempt_at':datetime.now(timezone.utc).isoformat(),'state':'delivery_unknown',
  'destination':'customer@example.com','message_snapshot':None,'message_hash':None,
  'mail_key_kind':'booking_confirmed','mail_key_role':'customer'}

def message(row,project):
 return {'from':'Historical Practice <old@example.com>','to':[row['destination']],
  'reply_to':'practice@example.test','subject':'Saved subject','text':'नमस्ते — saved exactly.',
  'html':'<p>नमस्ते — saved exactly.</p>','tags':[{'name':'project','value':PROJECTS[project]},
   {'name':'job_id','value':row['id']},{'name':'message_version','value':'2'}]}

class LegacyMailTransfer(unittest.TestCase):
 def layout(self,project):return next(item for item in catalogue() if item.project==project)

 def transfer(self,project,**options):return MailTransfer(declared(project),{project:'k1'},**options)

 def test_sarsa_frozen_body_credential_and_flat_key_are_exact_on_actual_transport(self):
  row=job();body=message(row,'004');row.update(message_snapshot=body,message_hash=message_hash(body))
  translated=self.transfer('004')(self.layout('004'),'delivery_jobs',row)
  self.assertEqual(translated['first_attempt_at'],row['first_attempt_at']);self.assertEqual(translated['message_snapshot'],body)
  calls=[];sender=ResendSender('re_'+'b'*24,declared=declared('004'),
   transport=httpx.MockTransport(lambda request:(calls.append(request) or httpx.Response(200,json={'id':str(uuid4())}))))
  binding=sender.binding(translated,body);sender.send(body,row['id'],row['first_attempt_at'],binding=binding)
  self.assertEqual(calls[0].headers['idempotency-key'],'sarsa004/'+row['id'])
  self.assertEqual(calls[0].headers['authorization'],'Bearer re_'+'a'*24)
  self.assertEqual(json.loads(calls[0].content),body)

 def test_astro_versioned_and_untagged_frozen_bodies_never_gain_new_tags(self):
  row=job();body=message(row,'003');row['message_snapshot']=body
  translated=self.transfer('003')(self.layout('003'),'delivery_jobs',row)
  self.assertEqual(translated['mail_idempotency_key'],'booking/'+row['booking_id']+'/booking_confirmed/customer/v2')
  body.pop('tags');row['message_snapshot']=body;translated=self.transfer('003')(self.layout('003'),'delivery_jobs',row)
  self.assertEqual(translated['mail_format'],'resend-legacy-untagged-job-v1')
  calls=[];sender=ResendSender('re_'+'b'*24,declared=declared('003'),
   transport=httpx.MockTransport(lambda request:(calls.append(request) or httpx.Response(200,json={'id':str(uuid4())}))))
  binding=sender.binding(translated,body);sender.send(body,row['id'],row['first_attempt_at'],binding=binding)
  self.assertEqual(json.loads(calls[0].content),body);self.assertNotIn('tags',json.loads(calls[0].content))

 def test_changed_job_sender_recipient_version_hash_and_saved_key_refuse(self):
  row=job();body=message(row,'004');row.update(message_snapshot=body,message_hash=message_hash(body))
  for changes in [{'id':str(uuid4())},{'destination':'foreign@example.com'},{'template_version':3},
   {'message_hash':'a'*64},{'mail_idempotency_key':'sarsa004/'+str(uuid4())},
   {'message_snapshot':body|{'from':'Other <other@example.com>'}}]:
   with self.subTest(field=list(changes)),self.assertRaisesRegex(ConversionError,'snapshot_invalid'):
    self.transfer('004')(self.layout('004'),'delivery_jobs',row|changes)

 def test_missing_old_body_is_private_review_or_saved_completion_never_a_new_send(self):
  row=job();translated=self.transfer('004')(self.layout('004'),'delivery_jobs',row)
  self.assertEqual(translated['state'],'needs_review');self.assertIsNone(translated['message_snapshot'])
  self.assertEqual(translated['last_error_code'],'legacy_mail_snapshot_unavailable')
  for state in ('completed','suppressed'):
   translated=self.transfer('004')(self.layout('004'),'delivery_jobs',row|{'state':state})
   self.assertEqual(translated['state'],state)

 def protected(self):
  legacy_key=encode(b'L'*32);base=keys(legacy={'old-message':{'algorithm':'fernet-json',
   'keys':[legacy_key],'purpose':'sarsa004-contact-message-v1'}})
  return ContactSecrets(base.digest_key,base.cipher,legacy_digests=(('old-digest',b'D'*32,'sarsa004'),)),legacy_key

 def encrypted(self,row,payload):
  raw=json.dumps({'purpose':'sarsa004-contact-message-v1','job_id':row['id'],'payload':payload},sort_keys=True,separators=(',',':'))
  digest=hmac.new(b'D'*32,canonical(['sarsa004','contact-v1','message',raw]),hashlib.sha256).hexdigest()
  return row|{'message_ciphertext':Fernet(encode(b'L'*32)).encrypt(raw.encode()).decode(),'message_digest':digest}

 def test_actual_sarsa_protected_enquiry_reencrypts_without_changing_the_message_or_first_attempt(self):
  protection,_=self.protected();row=job();row.update(kind='acknowledgement',request_id=str(uuid4()),payload={'email':row['destination']})
  row.pop('booking_id');body=message(row,'004');row=self.encrypted(row,body)
  translated=self.transfer('004',contact=protection,contact_formats={'004':('old-message','old-digest')})(self.layout('004'),'enquiry_delivery_jobs',row)
  self.assertEqual(open_message(protection,translated),body)
  self.assertEqual(translated['first_attempt_at'],row['first_attempt_at']);self.assertNotIn('message_snapshot',translated)
  self.assertTrue(translated['message_ciphertext'].startswith('e1.'));self.assertNotEqual(translated['message_digest'],row['message_digest'])

 def test_protected_enquiry_swaps_and_missing_reader_never_become_valid_mail(self):
  protection,_=self.protected();row=job();row.update(kind='acknowledgement',request_id=str(uuid4()),payload={'email':row['destination']})
  row.pop('booking_id');row=self.encrypted(row,message(row,'004'))
  transfer=self.transfer('004',contact=protection,contact_formats={'004':('old-message','old-digest')})
  for change in [{'id':str(uuid4())},{'message_digest':'a'*64},{'message_ciphertext':'invalid'},
    {'destination':'foreign@example.com'}]:
   with self.subTest(field=list(change)),self.assertRaisesRegex(ConversionError,'snapshot_invalid'):
    transfer(self.layout('004'),'enquiry_delivery_jobs',row|change)
  with self.assertRaises(ConversionError):self.transfer('004')(self.layout('004'),'enquiry_delivery_jobs',row)

 def test_wrong_project_key_version_table_and_mutated_reader_are_refused(self):
  with self.assertRaises(ConversionError):MailTransfer(declared('003'),{'004':'k1'})
  with self.assertRaises(ConversionError):MailTransfer(declared('004'),{'004':'missing'})
  transfer=self.transfer('004')
  with self.assertRaises(TypeError):transfer.key_versions['004']='k2'
  with self.assertRaises(ConversionError):transfer(self.layout('004'),'provider_inbox',job())
