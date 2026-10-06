"""Frozen retry/account identity and real bounded provider transport, without mail."""
import base64,hashlib,hmac,json,time
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest import TestCase
from uuid import uuid4
import httpx
from starlette.datastructures import Headers

from appointment_system.configuration import installation
from appointment_system.email_configuration import connection,webhook
from appointment_system.errors import Rejected
from appointment_system.email_messages import render_message
from appointment_system.mail_identity import MailIdentity,new_key,retained_key,tags_for
from appointment_system.resend_email import ResendSender,EmailFailure
from appointment_system.webhook import InvalidWebhook


def document():
    facts=installation()
    return {'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
      'provider':'resend','purpose':'email-send','account_id':'synthetic-team','active_key_id':'k2',
      'keys':[{'key_id':'k1','secret':'re_'+'a'*24},{'key_id':'k2','secret':'re_'+'b'*24}],
      'legacy_identities':[{'format':'resend-legacy-job-v1','project':'historical-project',
       'sender':'Historical Practice <old@example.com>','address':'old@example.com',
       'reply_to':'help@example.com','event_account_id':'old@example.com'}]}


def payload(job=None):
    return {'from':'Example Practice <booking@example.test>','to':['customer@example.com'],
      'reply_to':'practice@example.test','subject':'A synthetic notice','text':'Synthetic content.',
      'html':'<p>Synthetic content.</p>','tags':tags_for(job or str(uuid4()))}


class MailContracts(TestCase):
    def sender(self,handler):
        declared=connection(json.dumps(document()))
        return ResendSender(declared.pinned('k2'),transport=httpx.MockTransport(handler),declared=declared)

    def test_scoped_settings_current_writer_and_retained_key(self):
        declared=connection(json.dumps(document()))
        self.assertEqual(declared.pinned('k1'),'re_'+'a'*24)
        self.assertEqual(declared.identity('resend-v1').event_account_id,'synthetic-team')
        with self.assertRaises(ValueError):declared.pinned('missing')
        with self.assertRaises(ValueError):declared.identity('missing')
        with self.assertRaises(TypeError):declared.keys['other']='re_'+'c'*24

    def test_wrong_scope_duplicate_credentials_and_implicit_old_setting_fail(self):
        for key,value in [('version',True),('installation_id',str(uuid4())),('environment','production'),
                          ('purpose','email-webhook'),('provider','other'),('account_id',''),('active_key_id','missing')]:
            bad=deepcopy(document());bad[key]=value
            with self.assertRaises((ValueError,Rejected)):connection(json.dumps(bad))
        for key,value in [('key_id','k2'),('secret','re_'+'b'*24),('secret','bad')]:
            bad=deepcopy(document());bad['keys'][0][key]=value
            with self.assertRaises(ValueError):connection(json.dumps(bad))
        with self.assertRaises(KeyError):ResendSender.from_environment({'BOOKING_RESEND_API_KEY':'re_'+'a'*24})

    def test_tags_require_exact_installation_environment_unique_names_and_version(self):
        identity=MailIdentity.current();job=str(uuid4());tags=tags_for(job)
        self.assertEqual(identity.binding(tags),(job,'1'))
        for name,value in [('project','foreign'),('installation',str(uuid4())),('environment','production'),('message_version','0'),('job_id','bad')]:
            bad=deepcopy(tags);next(item for item in bad if item['name']==name)['value']=value
            self.assertIsNone(identity.binding(bad))
        self.assertIsNone(identity.binding(tags+tags[:1]));self.assertIsNone(identity.binding({}))
        self.assertIsNone(identity.binding(None));self.assertIsNone(identity.binding([{'name':'x'}]))
        for version in (True,0,10000):
            with self.assertRaises(ValueError):tags_for(job,version)

    def test_new_send_uses_scoped_key_and_account_key_only_after_binding(self):
        requests=[];job=str(uuid4());body=payload(job);provider=str(uuid4())
        def handler(request):requests.append(request);return httpx.Response(200,json={'id':provider})
        sender=self.sender(handler);binding=sender.binding({'id':job},body)
        self.assertEqual(sender.send(body,job,datetime.now(timezone.utc),binding=binding),provider)
        self.assertEqual(requests[0].headers['idempotency-key'],new_key(job))
        self.assertEqual(requests[0].headers['authorization'],'Bearer re_'+'b'*24)

    def test_frozen_historical_message_and_exact_saved_key_are_not_rewritten(self):
        requests=[];job=str(uuid4());booking=str(uuid4());body=payload(job)
        body.update({'from':'Historical Practice <old@example.com>','reply_to':'help@example.com',
          'tags':[{'name':'project','value':'historical-project'},{'name':'job_id','value':job},
                  {'name':'message_version','value':'2'}]})
        key='booking/'+booking+'/confirmation/customer/v2'
        saved={'id':job,'booking_id':booking,'mail_format':'resend-legacy-job-v1','mail_account_id':'synthetic-team',
          'mail_credential_version':'k1','mail_idempotency_key':key,'mail_key_kind':'confirmation','mail_key_role':'customer',
          'first_attempt_at':datetime.now(timezone.utc)}
        sender=self.sender(lambda request:(requests.append(request) or httpx.Response(200,json={'id':str(uuid4())})))
        binding=sender.binding(saved,body)
        sender.send(body,job,saved['first_attempt_at'],expected_reply_to='help@example.com',binding=binding)
        self.assertEqual(json.loads(requests[0].content),body)
        self.assertEqual(requests[0].headers['idempotency-key'],key)
        self.assertEqual(requests[0].headers['authorization'],'Bearer re_'+'a'*24)
        for bad in [saved|{'mail_account_id':'foreign'},saved|{'mail_idempotency_key':key.replace(booking,str(uuid4()))},
                    saved|{'mail_idempotency_key':None},saved|{'mail_credential_version':'missing'}]:
            with self.assertRaises(EmailFailure):sender.binding(bad,body)

    def test_missing_legacy_reader_or_attempt_key_never_makes_another_send(self):
        sender=self.sender(lambda request:self.fail('Provider should not be called.'))
        job=str(uuid4());body=payload(job)
        for saved in [{'id':job,'first_attempt_at':datetime.now(timezone.utc)},
                      {'id':job,'mail_format':'unregistered'}]:
            with self.assertRaises(EmailFailure):sender.binding(saved,body)

    def test_actual_sarsa_retry_namespace_is_retained_only_for_its_exact_project(self):
        job=str(uuid4());key='sarsa004/'+job
        identity=MailIdentity('resend-legacy-flat-job-v1','sarsa004',
            'Sarsa <old@example.com>','old@example.com','help@example.com','historical-account')
        self.assertEqual(retained_key(key,job,identity),key)
        for bad in ['sarsa004/'+str(uuid4()),key+'/v1',key+' ', 'sarsa003/'+job]:
            with self.assertRaises(ValueError):retained_key(bad,job,identity)
        foreign=MailIdentity('resend-legacy-job-v1','historical-project',identity.sender,
            identity.address,identity.reply_to,identity.event_account_id)
        with self.assertRaises(ValueError):retained_key(key,job,foreign)

    def test_retry_boundary_and_provider_response_are_conservative(self):
        sender=self.sender(lambda request:httpx.Response(200,json={'id':'bad'}));job=str(uuid4());body=payload(job)
        instant=datetime.now(timezone.utc)
        for first in [instant-timedelta(hours=23),instant+timedelta(seconds=6)]:
            with self.assertRaises(EmailFailure) as raised:sender.send(body,job,first,now=instant)
            self.assertEqual(raised.exception.code,'email_retry_window_closed')
        with self.assertRaises(EmailFailure) as raised:sender.send(body,job,instant,now=instant)
        self.assertEqual(raised.exception.code,'email_send_unconfirmed')
        rejected=self.sender(lambda request:httpx.Response(429,json={'name':'rate_limit_exceeded'}))
        with self.assertRaises(EmailFailure) as raised:rejected.send(body,job,instant)
        self.assertTrue(raised.exception.retryable)

    def test_payload_change_foreign_tags_multi_recipient_and_big_body_never_send(self):
        sender=self.sender(lambda request:self.fail('Invalid payload reached provider.'));job=str(uuid4());body=payload(job)
        for change in [{'from':'Other <other@example.com>'},{'to':['a@example.com','b@example.com']},
                       {'text':'a'*20000},{'subject':'line\nbreak'},{'reply_to':'foreign@example.com'},
                       {'tags':tags_for(str(uuid4()))}]:
            with self.assertRaises(EmailFailure):sender.send(body|change,job,datetime.now(timezone.utc))

    def test_accepted_timezone_and_internal_meeting_use_correct_brand_and_words(self):
        job={'id':str(uuid4()),'kind':'booking_ack','recipient_role':'customer','destination':'customer@example.com',
             'payload':{'reference':str(uuid4()),'practice_timezone':'Europe/London','starts_at':'2026-10-20T12:00:00Z',
                        'meeting':'internal','amount_paise':12345,'currency':'INR','service':'Synthetic consultation'}}
        rendered=render_message(job)
        self.assertIn('Example Practice',rendered['subject']);self.assertIn('01:00 PM',rendered['text'])
        self.assertIn('London time (BST)',rendered['text']);self.assertNotIn('will follow',rendered['text'])
        self.assertIn('123.45',rendered['text']);self.assertNotIn('birth',rendered['text'])
        with self.assertRaises(EmailFailure):render_message(job|{'kind':'booking_details'})

    def test_signed_notification_is_committed_and_wrong_project_is_ignored(self):
        declared=connection(json.dumps(document()));secret='whsec_'+base64.b64encode(b's'*32).decode()
        setup={'version':1,'installation_id':installation()['installation_id'],'environment':installation()['environment'],
          'provider':'resend','purpose':'email-webhook','key_map':{'synthetic-team':{'keys':[{'key_id':'hook','secret':secret}]}}}
        receiver=webhook(json.dumps(setup),declared);job=str(uuid4());provider=str(uuid4());saved=[]
        class Store:
            def save_provider_event(self,*args):saved.append(args);return args[4]
        event={'type':'email.delivered','created_at':datetime.now(timezone.utc).isoformat(),
               'data':{'from':'Example Practice <booking@example.test>','to':['customer@example.com'],
                       'email_id':provider,'tags':{item['name']:item['value'] for item in tags_for(job)}}}
        def receive(value):
            raw=json.dumps(value,separators=(',',':')).encode();stamp=str(int(time.time()));event_id='msg_synthetic'
            signature=base64.b64encode(hmac.new(b's'*32,(event_id+'.'+stamp+'.').encode()+raw,hashlib.sha256).digest()).decode()
            return receiver.receive(Store(),raw,Headers({'svix-id':event_id,'svix-timestamp':stamp,'svix-signature':'v1,'+signature}))
        self.assertEqual(receive(event),{'received':True});self.assertEqual(saved[0][1],'synthetic-team')
        self.assertEqual(saved[0][5]['job_id'],job);self.assertNotIn('customer@example.com',json.dumps(saved[0][5]))
        wrong=deepcopy(event);wrong['data']['tags']['installation']=str(uuid4())
        receive(wrong);self.assertEqual(len(saved),1)
        setup['key_map']={'foreign':setup['key_map']['synthetic-team']}
        with self.assertRaises(ValueError):webhook(json.dumps(setup),declared)

    def test_signed_historical_untagged_report_is_saved_without_guessing_a_job(self):
        from .test_conversion_mail import declared
        selected=declared('003');secret='whsec_'+base64.b64encode(b's'*32).decode()
        setup={'version':1,'installation_id':installation()['installation_id'],'environment':installation()['environment'],
          'provider':'resend','purpose':'email-webhook','key_map':{'synthetic-team':{'keys':[{'key_id':'hook','secret':secret}]}}}
        receiver=webhook(json.dumps(setup),selected);saved=[]
        class Store:
            def save_provider_event(self,*args):saved.append(args);return args[4]
        legacy=next(item for item in receiver.identities if item.format=='resend-legacy-untagged-job-v1')
        event={'type':'email.delivered','created_at':datetime.now(timezone.utc).isoformat(),
          'data':{'from':legacy.sender,'to':['customer@example.com'],'email_id':str(uuid4())}}
        def receive(value):
            raw=json.dumps(value,separators=(',',':')).encode();stamp=str(int(time.time()));event_id='msg_historical'
            signature=base64.b64encode(hmac.new(b's'*32,(event_id+'.'+stamp+'.').encode()+raw,hashlib.sha256).digest()).decode()
            return receiver.receive(Store(),raw,Headers({'svix-id':event_id,'svix-timestamp':stamp,'svix-signature':'v1,'+signature}))
        self.assertEqual(receive(event),{'received':True});self.assertEqual(len(saved),1)
        self.assertEqual(saved[0][1],legacy.event_account_id);self.assertNotIn('job_id',saved[0][5])
        self.assertEqual(saved[0][5]['mail_format'],'resend-legacy-untagged-job-v1')
        self.assertNotIn('customer@example.com',json.dumps(saved[0][5]))
        event['data']['from']='foreign@example.com';receive(event);self.assertEqual(len(saved),1)
        event['data']['from']=legacy.sender;event['data']['tags']={'project':'foreign'}
        receive(event);self.assertEqual(len(saved),1)
