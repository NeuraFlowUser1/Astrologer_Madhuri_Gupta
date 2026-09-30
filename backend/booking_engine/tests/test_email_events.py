import base64
import copy
import hashlib
import json
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from svix.webhooks import Webhook

from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.email_events import EmailWebhook,SENDER,EVENTS
from backend.booking_engine.webhook import InvalidWebhook,EventConflict


class EmailEventTests(unittest.TestCase):
    def setUp(self):
        self.secret='whsec_'+base64.b64encode(b's'*32).decode()
        self.receiver=EmailWebhook((self.secret,))
        self.now=datetime.now(timezone.utc)
        self.store=Mock()
        self.store.save_provider_event.side_effect=lambda *args: args[4]
        self.event={'type':'email.delivered','created_at':self.now.isoformat(), 'data':{
            'email_id':str(uuid4()),'from':SENDER,'to':['private@example.invalid'],'subject':'Private',
            'tags':{'project':'sarsa004','job_id':str(uuid4())}}}

    def signed(self,event=None,*,raw=None,when=None):
        body=raw if raw is not None else json.dumps(event or self.event).encode()
        when=when or self.now
        headers=Headers({'svix-id':'msg_synthetic','svix-timestamp':str(int(when.timestamp())),
            'svix-signature':Webhook(self.secret).sign('msg_synthetic',when,body.decode())})
        return body,headers

    def test_all_supported_events_are_minimized_and_saved_before_acknowledgement(self):
        for kind in EVENTS:
            self.event['type']=kind
            body,headers=self.signed()
            self.assertEqual(self.receiver.receive(self.store,body,headers),{'received':True})
            args=self.store.save_provider_event.call_args.args
            self.assertEqual(args[:3],('resend','bookings@mail.sarsajyotishsansthan.com','live'))
            self.assertEqual(args[4],hashlib.sha256(body).hexdigest())
            self.assertEqual(set(args[5]),{'event','email_id','job_id','occurred_at'})
            self.assertNotIn('private@example.invalid',json.dumps(args[5]))

    def test_tampering_stale_signature_and_duplicate_headers_never_store(self):
        body,headers=self.signed()
        old_body,old_headers=self.signed(when=self.now-timedelta(minutes=10))
        duplicate=Headers(raw=list(headers.raw)+[(b'svix-id',b'msg_other')])
        for payload,h in ((body+b' ',headers),(old_body,old_headers),(body,duplicate),(body,Headers())):
            with self.assertRaises(InvalidWebhook): self.receiver.receive(self.store,payload,h)
        self.store.save_provider_event.assert_not_called()

    def test_signed_duplicate_fields_invalid_identifiers_and_naive_dates_rejected(self):
        raws=[b'{"type":"email.sent","type":"email.delivered"}']
        for change in ('id','time'):
            event=copy.deepcopy(self.event)
            if change=='id':event['data']['email_id']='invalid'
            else:event['created_at']='2026-09-28T10:00:00'
            raws.append(json.dumps(event).encode())
        for raw in raws:
            body,headers=self.signed(raw=raw)
            with self.assertRaises(InvalidWebhook):self.receiver.receive(self.store,body,headers)
        self.store.save_provider_event.assert_not_called()

    def test_signed_other_domain_or_project_and_tracking_are_not_retained(self):
        for change in ('sender','project','tracking'):
            event=copy.deepcopy(self.event)
            if change=='sender':event['data']['from']='other@example.invalid'
            elif change=='project':event['data']['tags']['project']='003'
            else:event['type']='email.opened'
            body,headers=self.signed(event)
            self.assertEqual(self.receiver.receive(self.store,body,headers),{'received':True})
        self.store.save_provider_event.assert_not_called()

    def test_conflicting_event_and_uncertain_commit_are_not_acknowledged(self):
        body,headers=self.signed()
        self.store.save_provider_event.side_effect=None
        self.store.save_provider_event.return_value='different'
        with self.assertRaises(EventConflict):self.receiver.receive(self.store,body,headers)
        self.store.save_provider_event.side_effect=StorageUnavailable('private details')
        with self.assertRaises(StorageUnavailable):self.receiver.receive(self.store,body,headers)

    def test_secret_not_in_repr_and_rotated_key_can_verify(self):
        old='whsec_'+base64.b64encode(b'o'*32).decode()
        self.assertNotIn(self.secret,repr(self.receiver))
        body,headers=self.signed()
        self.assertEqual(EmailWebhook((old,self.secret)).receive(self.store,body,headers),{'received':True})
        for secrets in ((),('wrong',),('whsec_a',)):
            with self.assertRaises(ValueError):EmailWebhook(secrets)

    def test_http_route_needs_signature_not_browser_origin_and_fails_closed(self):
        settings=Settings('https://sarsa.example',b'a'*32,b'b'*32,b'c'*32)
        app=create_application(self.store,settings,verified_client_address=lambda _: '192.0.2.1',email_webhook=self.receiver)
        client=TestClient(app,raise_server_exceptions=False)
        body,headers=self.signed()
        response=client.post('/api/webhooks/resend',content=body,headers=dict(headers,**{'content-type':'application/json'}))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.store.consume_limit.assert_not_called()
        self.store.save_provider_event.side_effect=StorageUnavailable('secret failure')
        response=client.post('/api/webhooks/resend',content=body,headers=dict(headers,**{'content-type':'application/json'}))
        self.assertEqual(response.status_code,503)
        self.assertNotIn('secret failure',response.text)
        bare=create_application(self.store,settings,verified_client_address=lambda _: '192.0.2.1')
        self.assertEqual(TestClient(bare).post('/api/webhooks/resend',json={}).status_code,503)


if __name__=='__main__':unittest.main()
