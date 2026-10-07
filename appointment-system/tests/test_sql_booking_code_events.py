"""Actual signed booking-code notifications through the native worker operation."""
import base64
from datetime import datetime,timezone
import hashlib
import hmac
import json
import time
from uuid import uuid4
from starlette.datastructures import Headers
from .test_sql_booking_verification import BookingCodeFixture
from appointment_system.configuration import installation
from appointment_system.email_configuration import webhook
from appointment_system.recovery_contract import operation
from tools.checks.sql_target import literal


class BookingCodeEventsSQL(BookingCodeFixture):
    def signed_event(self,payload,provider,event_id,event):
        facts=installation();secret='whsec_'+base64.b64encode(b's'*32).decode()
        configured=dict(version=1,installation_id=facts['installation_id'],environment=facts['environment'],
            provider='resend',purpose='email-webhook',key_map={self.sender.declared.account_id:
                {'keys':[{'key_id':'hook','secret':secret}]}})
        receiver=webhook(json.dumps(configured),self.sender.declared)
        created=datetime.now(timezone.utc).isoformat()
        raw=json.dumps({'type':'email.'+event,'created_at':created,'data':{
            'from':payload['from'],'to':payload['to'],'email_id':provider,
            'tags':{item['name']:item['value'] for item in payload['tags']}}},separators=(',',':')).encode()
        stamp=str(int(time.time()))
        signature=base64.b64encode(hmac.new(b's'*32,(event_id+'.'+stamp+'.').encode()+raw,hashlib.sha256).digest()).decode()
        headers=Headers({'svix-id':event_id,'svix-timestamp':stamp,'svix-signature':'v1,'+signature})
        self.assertEqual(receiver.receive(self.worker,raw,headers),{'received':True})
        self.assertEqual(receiver.receive(self.worker,raw,headers),{'received':True})

    def consume(self):
        return operation(self.worker,'email_events','verification',sender=None,code_keys=None,
                         contact_keys=None,google=None,accounts=None,publisher=None)

    def joined(self,event):
        self.start();self.assertEqual(len(self.requests),1)
        payload=json.loads(self.requests[0].content)
        before=self.db.value('SELECT to_jsonb(j) FROM appointment_system.booking_verification_mail j;')
        self.assertEqual(before['state'],'completed');self.assertIsNotNone(before['first_attempt_at'])
        event_id='msg_synthetic_'+uuid4().hex
        self.signed_event(payload,before['provider_id'],event_id,event)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.provider_inbox WHERE event_id='+literal(event_id)+' AND processed_at IS NULL;'),'1')
        self.assertEqual(self.consume(),{'processed':1})
        self.assertEqual(self.consume(),{'processed':0})
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.booking_verification_email_observations WHERE job_id='+literal(before['id'])+' AND event_type='+literal('email.'+event)+';'),'1')
        self.assertEqual(self.db.scalar('SELECT attempts FROM appointment_system.provider_inbox WHERE event_id='+literal(event_id)+';'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.mail_acceptance_claims WHERE kind=\'verification\' AND job_id='+literal(before['id'])+" AND result='accepted';"),'1')
        after=self.db.value('SELECT to_jsonb(j) FROM appointment_system.booking_verification_mail j;')
        for field in ('provider_id','first_attempt_at','message_ciphertext','message_digest','mail_account_id',
                      'mail_event_account_id','mail_credential_version','mail_idempotency_key','template_version'):
            self.assertEqual(after[field],before[field],field)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.email_reservations;'),'1')

    def test_signed_sent_worker_consumes_exact_duplicate_once_without_resending(self):
        self.joined('sent')

    def test_signed_delivered_worker_consumes_exact_duplicate_once_without_resending(self):
        self.joined('delivered')

    def test_event_function_keeps_fixed_identity_security_and_worker_only_permissions(self):
        metadata=self.db.value("SELECT jsonb_build_object('arguments',pg_get_function_identity_arguments(p.oid),"
            "'owner',pg_get_userbyid(p.proowner),'security_definer',p.prosecdef,'settings',p.proconfig,"
            "'worker_execute',has_function_privilege('abs_worker',p.oid,'EXECUTE'),"
            "'web_execute',has_function_privilege('appointment_system_web',p.oid,'EXECUTE'),"
            "'public_execute',EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE'),"
            "'body',p.prosrc) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='appointment_system' AND p.proname='reconcile_booking_code_email_event';")
        self.assertEqual(metadata['arguments'],'');self.assertEqual(metadata['owner'],'appointment_system_owner')
        self.assertTrue(metadata['security_definer'])
        self.assertEqual(metadata['settings'],['search_path=pg_catalog, appointment_system, pg_temp'])
        self.assertTrue(metadata['worker_execute']);self.assertFalse(metadata['web_execute']);self.assertFalse(metadata['public_execute'])
        self.assertEqual(metadata['body'].count('WHERE provider_inbox.provider='),3)
        self.assertNotIn('WHERE provider=',metadata['body'])
        self.assertIn('provider uuid;',metadata['body'])
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.schema_migrations WHERE version='035_booking_code_event_provider_column.sql';"),'1')
