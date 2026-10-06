"""Truthful customer notices, bounded provider delays and authenticated reports."""
import base64,hashlib,hmac,json,time
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from starlette.datastructures import Headers
from appointment_system.email_events import EmailWebhook
from appointment_system.email_messages import render_message,REPLY_TO
from appointment_system.mail_identity import tags_for
from appointment_system.mail_outcomes import retry_after,classify,unique_json
from appointment_system.resend_email import EmailFailure
from appointment_system.webhook import InvalidWebhook,EventConflict


class MailFailureBoundaries(TestCase):
    def job(self,kind='booking_ack',role='customer',**payload):
        return dict(id=str(uuid4()),kind=kind,recipient_role=role,
                    destination=REPLY_TO if role=='client' else 'customer@example.com',
                    payload=dict(reference=str(uuid4()),practice_timezone='Asia/Kolkata',
                        starts_at='2026-10-06T10:30:00Z',meeting='google_meet',amount_paise=12345,
                        currency='INR',service='Saved consultation',private_notes='Never publish me')|payload)

    def test_cancel_review_reschedule_contact_correction_and_meet_notices_are_truthful(self):
        for kind,role,fields,required in [
            ('payment_review','client',{},'not an appointment confirmation'),
            ('booking_cancelled','customer',{},'does not confirm a refund'),
            ('booking_ack','customer',{'change_kind':'rescheduled'},'does not request another payment'),
            ('booking_ack','client',{'change_kind':'rescheduled'},'has been rescheduled'),
            ('booking_ack','customer',{'change_kind':'contact_corrected'},'time and fee have not changed'),
            ('booking_ack','client',{'meeting':'internal'},'Arrange this meeting directly'),
            ('booking_ack','client',{},'Open the private studio'),
            ('booking_details','customer',{'meet_url':'https://meet.google.com/abc-defg-hij'},'https://meet.google.com/abc-defg-hij')]:
            with self.subTest(kind=kind,role=role):
                rendered=render_message(self.job(kind,role,**fields))
                self.assertIn(required,rendered['text'])
                self.assertNotIn('Never publish me',json.dumps(rendered))
        self.assertIn('&lt;b&gt;',render_message(self.job(service='<b>Saved service</b>'))['html'])

    def test_incomplete_or_wrong_destination_notice_is_never_rendered_as_a_confirmation(self):
        for changes in ({'recipient_role':'agency'},{'recipient_role':'client','destination':'foreign@example.com'},
                        {'kind':'payment_review'},{'kind':'unknown'}):
            with self.subTest(changes=changes),self.assertRaises(EmailFailure):render_message(self.job()|changes)
        for payload in ({'amount_paise':True},{'amount_paise':0},{'currency':'USD'},{'service':'bad\x00name'},
                        {'meeting':'unknown'},{'service':''},{'service':'x'*201}):
            with self.subTest(fields=list(payload)),self.assertRaises(EmailFailure):render_message(self.job(**payload))
        for payload in ({'meet_url':'https://foreign.example.com/abc-defg-hij'},
                        {'meeting':'internal','meet_url':'https://meet.google.com/abc-defg-hij'}):
            with self.subTest(fields=list(payload)),self.assertRaises(EmailFailure):render_message(self.job('booking_details',**payload))

    def test_retry_advice_is_bounded_and_distinguishes_rejection_from_unknown_delivery(self):
        now=datetime(2026,10,4,12,tzinfo=timezone.utc)
        self.assertEqual(retry_after(format_datetime(now+timedelta(seconds=61)),now=now),61)
        self.assertEqual(retry_after(format_datetime(now-timedelta(seconds=1)),now=now),0)
        self.assertEqual(retry_after('999999',now=now),86400)
        for value in (None,'','x'*81,'bad date','Sun, 04 Oct 2026 12:00:00','١٠'):
            with self.subTest(value=value):self.assertEqual(retry_after(value,now=now),0)
        self.assertEqual(classify(429,{'name':'daily_quota_exceeded'},{}),('daily_quota_exceeded',True,True,86400))
        self.assertEqual(classify(409,{'name':'invalid_idempotent_request'},{}),('email_idempotency_conflict',False,False,0))
        self.assertEqual(classify(409,{'name':'concurrent_idempotent_requests'},{'Retry-After':'60'}),('email_idempotency_in_progress',False,True,60))
        for status in (400,401,403,404,405,422):
            self.assertTrue(classify(status,{}, {})[1]);self.assertFalse(classify(status,{}, {})[2])
        self.assertEqual(classify(503,None,{}),('email_send_unconfirmed',False,True,30))
        self.assertEqual(unique_json([('a',1)]),{'a':1})
        with self.assertRaises(ValueError):unique_json([('a',1),('a',2)])

    def event(self):
        return dict(type='email.delivered',created_at=datetime.now(timezone.utc).isoformat(),data={
            'from':'Example Practice <booking@example.test>','to':['customer@example.com'],
            'email_id':str(uuid4()),'tags':{item['name']:item['value'] for item in tags_for(str(uuid4()))}})

    def signed(self,body):
        stamp=str(int(time.time()));identifier='msg_synthetic_boundaries'
        signature=base64.b64encode(hmac.new(b's'*32,(identifier+'.'+stamp+'.').encode()+body,hashlib.sha256).digest()).decode()
        return Headers({'svix-id':identifier,'svix-timestamp':stamp,'svix-signature':'v1,'+signature})

    def test_signed_but_malformed_reports_never_write_or_wake(self):
        receiver=EmailWebhook(('whsec_'+base64.b64encode(b's'*32).decode(),))
        store=Mock();event=self.event()
        malformed=[b'[]',b'{"type":"email.sent","type":"email.delivered"}',
                   json.dumps(event|{'type':None}).encode(),json.dumps(event|{'data':None}).encode(),
                   json.dumps(event|{'created_at':'2026-10-04T12:00:00'}).encode()]
        for change in ({'to':[]},{'to':['a@example.com','b@example.com']},{'email_id':'invalid'}):
            malformed.append(json.dumps(event|{'data':event['data']|change}).encode())
        for raw in malformed:
            with self.subTest(size=len(raw)),self.assertRaises(InvalidWebhook):receiver.receive(store,raw,self.signed(raw))
        store.save_provider_event.assert_not_called()
        raw=json.dumps(event).encode()
        for headers in (Headers({}),Headers({'svix-id':'invalid space'}),self.signed(raw+b'changed'),
                        Headers(raw=self.signed(raw).raw+[self.signed(raw).raw[0]])):
            with self.assertRaises(InvalidWebhook):receiver.receive(store,raw,headers)
        for body in (b'',b'x'*131073,'not bytes'):
            with self.assertRaises(InvalidWebhook):receiver.receive(store,body,self.signed(raw))

    def test_rotated_signature_is_accepted_but_wake_waits_for_saved_exact_event(self):
        receiver=EmailWebhook(tuple('whsec_'+base64.b64encode(key*32).decode() for key in (b'o',b's')))
        raw=json.dumps(self.event()).encode();headers=self.signed(raw);store=Mock();wake=Mock()
        store.save_provider_event.return_value='different digest'
        with self.assertRaises(EventConflict):receiver.receive(store,raw,headers,on_saved=wake)
        wake.assert_not_called()
        store.save_provider_event.return_value=hashlib.sha256(raw).hexdigest()
        self.assertEqual(receiver.receive(store,raw,headers,on_saved=wake),{'received':True})
        wake.assert_called_once_with()
        for secrets in ((),('invalid',),('whsec_!',),('whsec_'+base64.b64encode(b'short').decode(),)):
            with self.assertRaises(ValueError):EmailWebhook(secrets)
