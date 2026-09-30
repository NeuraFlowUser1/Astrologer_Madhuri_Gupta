import json
import unittest
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import httpx

from backend.booking_engine.email_events import SENDER,PROJECT_TAG
from backend.booking_engine.resend_email import ResendSender,EmailFailure,REPLY_TO


class ResendTests(unittest.TestCase):
    def setUp(self):
        self.job=str(uuid4());self.provider=str(uuid4());self.now=datetime.now(timezone.utc)
        self.payload={'from':SENDER,'to':['person@example.com'],'reply_to':REPLY_TO,'subject':'Appointment',
            'text':'Appointment details','html':'<p>Appointment details</p>',
            'tags':[{'name':'project','value':PROJECT_TAG},{'name':'job_id','value':self.job}]}
        self.requests=[]

    def sender(self,response):
        def handle(request):
            self.requests.append(request)
            if isinstance(response,Exception):raise response
            return response
        return ResendSender('re_synthetic_test_only',httpx.MockTransport(handle))

    def test_accepted_reference_and_same_frozen_key_and_body_on_retry(self):
        sender=self.sender(httpx.Response(200,json={'id':self.provider}))
        for _ in range(2):self.assertEqual(sender.send(self.payload,self.job,self.now,now=self.now),self.provider)
        self.assertEqual(self.requests[0].content,self.requests[1].content)
        self.assertEqual(self.requests[0].headers['idempotency-key'],'sarsa004/'+self.job)
        self.assertEqual(self.requests[0].url.host,'api.resend.com')
        self.assertNotIn('re_synthetic_test_only',repr(sender))

    def test_expired_or_missing_committed_attempt_never_contacts_provider(self):
        sender=self.sender(httpx.Response(200,json={'id':self.provider}))
        for first in (None,self.now-timedelta(hours=23),self.now+timedelta(seconds=6)):
            with self.assertRaisesRegex(EmailFailure,'email_retry_window_closed'):
                sender.send(self.payload,self.job,first,now=self.now)
        self.assertEqual(self.requests,[])

    def test_small_database_clock_skew_does_not_strand_a_new_send(self):
        sender=self.sender(httpx.Response(200,json={'id':self.provider}))
        self.assertEqual(sender.send(self.payload,self.job,self.now+timedelta(seconds=1),now=self.now),self.provider)

    def test_sender_reply_recipient_and_job_binding_checked_before_send(self):
        sender=self.sender(httpx.Response(200,json={'id':self.provider}))
        for change in ({'from':'Other <other@example.com>'},{'reply_to':'other@example.com'},
                       {'to':['one@example.com','two@example.com']},{'tags':[]},{'bcc':['other@example.com']},
                       {'subject':'Subject\r\nInjected: true'}):
            with self.assertRaises(EmailFailure):sender.send(dict(self.payload,**change),self.job,self.now,now=self.now)
        self.assertEqual(self.requests,[])

    def test_rejection_is_distinct_from_ambiguous_send_and_never_retried(self):
        for status,rejected in ((400,True),(401,True),(422,True),(429,True),(409,False),(500,False),(302,False)):
            self.requests=[]
            with self.assertRaises(EmailFailure) as error:
                self.sender(httpx.Response(status,json={'private':'detail'})).send(self.payload,self.job,self.now,now=self.now)
            self.assertEqual(error.exception.definitely_rejected,rejected)
            self.assertNotIn('detail',str(error.exception))
            self.assertEqual(len(self.requests),1)

    def test_timeout_and_malformed_success_remain_uncertain(self):
        for response in (httpx.ReadTimeout('private'),httpx.Response(200,json={'id':'bad'}),
                         httpx.Response(200,json={'padding':'x'*17000}),httpx.Response(200,text='not json')):
            with self.assertRaises(EmailFailure) as error:
                self.sender(response).send(self.payload,self.job,self.now,now=self.now)
            self.assertFalse(error.exception.definitely_rejected)


if __name__=='__main__':unittest.main()
