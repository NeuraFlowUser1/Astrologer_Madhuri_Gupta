"""Complete missing identity and payment failure paths with synthetic providers."""
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
import httpx
from cryptography.fernet import Fernet
from backend.booking_engine import google_oauth as google
from backend.booking_engine import razorpay as razor
from backend.booking_engine import recovery
from backend.booking_engine.payment_policy import CheckoutEvidence,Appointment,Order,Payment,Resolution,customer_actions
from backend.booking_engine.tests import test_google_oauth as oauth_fixtures
from backend.booking_engine.tests import test_recovery as recovery_fixtures

class IdentityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):oauth_fixtures.GoogleOAuthTests.setUpClass()
    def setUp(self):self.f=oauth_fixtures.GoogleOAuthTests();self.f.setUp()

    def test_invalid_attempt_grant_and_encryption_shapes_cannot_be_sealed(self):
        for values in [('client','bad','x'*43,'x'*43),('client','x'*43,'bad','x'*43)]:
            with self.assertRaises(google.GoogleFailure):google.Attempt(*values)
        for changes in ({'email':'other@example.invalid'},{'subject':''},{'refresh_token':''},{'refresh_expires_at':datetime.now()}):
            base=dict(role='client',subject='synthetic',email=google.OWNERS['client'],refresh_token='synthetic',scopes=google.scopes_for('client'));base.update(changes)
            with self.assertRaises(google.GoogleFailure):google.Grant(**base)
        for keys in (None,[],['broken']):
            with self.assertRaises(google.GoogleFailure):google.GrantCipher(oauth_fixtures.CLIENT,keys)
        cipher=google.GrantCipher(oauth_fixtures.CLIENT,[Fernet.generate_key()])
        with self.assertRaises(google.GoogleFailure):cipher.seal(None)
        with self.assertRaises(google.GoogleFailure):cipher.seal_attempt(self.f.attempt,'other')
        for raw in ('','private-but-invalid'):
            with self.assertRaises(google.GoogleFailure):cipher.open_attempt(raw,state=self.f.attempt.state,role='client',purpose='signin')
            with self.assertRaises(google.GoogleFailure):cipher.open(raw,role='client',subject='synthetic',now=self.f.now)
        sealed=cipher.seal_attempt(self.f.attempt,'signin')
        with self.assertRaises(google.GoogleFailure):cipher.open_attempt(sealed,state='different',role='client',purpose='signin')

    def test_transport_certificate_time_and_code_guards_precede_identity_acceptance(self):
        with self.assertRaises(google.GoogleFailure):google.GoogleOAuth(None)
        oauth=self.f.provider()
        with self.assertRaises(google.GoogleFailure):oauth._request('https://evil.invalid')
        with self.assertRaises(google.GoogleFailure):oauth.exchange(self.f.attempt,'',now=self.f.now)
        self.assertEqual(self.f.calls,[])
        with patch.object(oauth,'_request',return_value={'synthetic':'not a certificate'}),self.assertRaises(google.GoogleFailure):oauth._certificates(google.CERTS)
        with self.assertRaises(google.GoogleFailure):google._time(datetime.now())
        bad=httpx.Response(200,content=b'{}',headers={'content-type':'text/html'})
        with self.assertRaises(google.GoogleFailure):self.f.provider(bad).exchange(self.f.attempt,'code',now=self.f.now)
        bad=self.f.token_response(id_token=None)
        with self.assertRaises(google.GoogleFailure):self.f.provider(bad).exchange(self.f.attempt,'code',now=self.f.now)

    def test_refresh_rechecks_scope_expiry_and_replacement_identity(self):
        grant=google.Grant('client',self.f.claims['sub'],google.OWNERS['client'],'synthetic',google.scopes_for('client'))
        for changes in ({'scope':'openid'},{'refresh_token_expires_in':True},{'refresh_token_expires_in':0},{'access_token':''}):
            tokens={'token_type':'Bearer','expires_in':3600,'access_token':'synthetic',**changes}
            with self.assertRaises(google.GoogleFailure):self.f.provider(tokens).refresh(grant,now=self.f.now)
        with self.assertRaises(google.GoogleFailure):self.f.provider().refresh(None,now=self.f.now)

class FinancialEvidenceBoundaryTests(unittest.TestCase):
    def test_incomplete_or_contradictory_evidence_never_allows_another_booking(self):
        now=datetime.now(timezone.utc);base=dict(appointment=Appointment.HELD,order=Order.NOT_ATTEMPTED,payment=Payment.UNOBSERVED,hold_expires_at=now+timedelta(minutes=10))
        changes=[{'appointment':'held'},{'resolution':'unknown'},{'resolution':Resolution.NEVER_ATTEMPTED},
          {'hold_expires_at':datetime.now()},{'order_id':'order_synthetic'}, {'order':Order.READY,'order_attempted_at':now},
          {'order':Order.FAILED},{'resolution':Resolution.CONFIRMED,'resolved_at':now},
          {'order':Order.READY,'order_id':'order_synthetic','order_attempted_at':now,'resolution':Resolution.NEVER_ATTEMPTED,'resolved_at':now},
          {'resolution':Resolution.REJECTED,'resolved_at':now}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):CheckoutEvidence(**{**base,**change})
        evidence=CheckoutEvidence(**base)
        with self.assertRaises(ValueError):customer_actions(evidence,datetime.now())
        evidence=CheckoutEvidence(**{**base,'resolution':Resolution.NEVER_ATTEMPTED,'resolved_at':now+timedelta(minutes=1)})
        with self.assertRaises(ValueError):customer_actions(evidence,now)

    def test_provider_input_and_transport_failures_preserve_uncertainty(self):
        credentials=razor.Credentials('sarsaSynthetic','test','v1','rzp_test_synthetic','synthetic')
        with self.assertRaises(razor.RazorpayFailure):razor.Razorpay(None)
        self.assertIsNone(razor.merchant_identity(None))
        with self.assertRaises(ValueError):razor.order_receipt(uuid4(),'other')
        for args in [(b'body',None,'secret'),(b'body','a'*64,''),('body','a'*64,'secret')]:self.assertFalse(razor.verify_signature(*args))
        for response in [httpx.Response(404),httpx.Response(200,content=b'{}',headers={'content-type':'text/html'}),httpx.Response(200,json=[]),httpx.Response(200,content=b'x'*(razor.MAX_RESPONSE+1),headers={'content-type':'application/json'})]:
            calls=[];adapter=razor.Razorpay(credentials,transport=httpx.MockTransport(lambda request:(calls.append(request) or response)))
            with self.assertRaises(razor.RazorpayFailure) as error:adapter.create_order(uuid4(),100)
            self.assertTrue(error.exception.uncertain);self.assertEqual(len(calls),1)
        adapter=razor.Razorpay(credentials,transport=httpx.MockTransport(lambda request:httpx.Response(200,json={})))
        for amount in (0,True):
            with self.assertRaises(ValueError):adapter.create_order(uuid4(),amount)
        for value,method in [('bad',adapter.payment),('bad',adapter.order_payments),('bad',adapter.order)]:
            with self.assertRaises(ValueError):method(value)
        with self.assertRaises(ValueError):adapter.orders_page(uuid4(),skip=-1)
        self.assertEqual(adapter.order('order_synthetic'),{})

class RecoveryBoundaryTests(unittest.TestCase):
    def test_empty_jobs_and_unexpired_unattempted_hold_do_not_call_provider(self):
        store,accounts,adapter,job=recovery_fixtures.RecoveryTests().flow();store.claim_payment_recovery.return_value=[]
        self.assertEqual(recovery.run_payment_recovery_once(store,accounts),{'processed':0})
        job.update(state='not_attempted',hold_expires_at=job['server_now']+timedelta(minutes=5));store.claim_payment_recovery.return_value=[job]
        recovery.run_payment_recovery_once(store,accounts);accounts.pinned.assert_not_called();store.abandon_unattempted.assert_not_called()
        store.claim_payment_events.return_value=[];self.assertEqual(recovery.run_payment_event_once(store,accounts),{'processed':0})

    def test_recovery_rejects_invalid_and_duplicate_remote_collections_without_recreating_order(self):
        store,accounts,adapter,job=recovery_fixtures.RecoveryTests().flow()
        for response in [[],{'entity':'collection','items':['not-payment'],'count':1},{'entity':'collection','items':[{'entity':'order'}],'count':1},{'entity':'collection','items':[{'entity':'payment','id':'bad','order_id':'order_test'}],'count':1},{'entity':'collection','items':[{'entity':'payment','id':'pay_same','order_id':'order_test'}]*2,'count':2}]:
            adapter.order_payments.return_value=response;recovery.run_payment_recovery_once(store,accounts);self.assertEqual(store.finish_payment_recovery.call_args.kwargs['error'],'payment_response_invalid');adapter.create_order.assert_not_called()
        job.update(provider_order_id=None,state='creation_unknown');order=dict(entity='order',id='order_test',receipt=razor.order_receipt(job['booking_id'],'test'),amount=job['amount_paise'],currency='INR',partial_payment=False)
        for items in [[{**order,'amount':1}],[order,order]]:
            adapter.orders_page.return_value={'entity':'collection','items':items,'count':len(items)};recovery.run_payment_recovery_once(store,accounts);self.assertEqual(store.finish_payment_recovery.call_args.kwargs['error'],'payment_order_mismatch')
        adapter.orders_page.return_value={'entity':'collection','items':[{'entity':'order','receipt':'other'}]*100,'count':100};recovery.run_payment_recovery_once(store,accounts);self.assertEqual(store.finish_payment_recovery.call_args.args[3],100)
        self.assertFalse(recovery._matching_order({},job));self.assertFalse(recovery._matching_order(None,job))

    def test_payment_only_and_order_only_events_lookup_existing_account_and_wake_saved_work(self):
        store,accounts=Mock(),Mock();job={'account_id':'sarsaSynthetic','environment':'test','attempts':1,'payload':{'payment_id':'pay_synthetic'}};store.claim_payment_events.return_value=[job];store.find_order.return_value={'merchant_id':'sarsaSynthetic','mode':'test','credential_version':'v1','booking_id':'synthetic','context_id':'synthetic'}
        accounts.current.return_value.payment.return_value={'id':'pay_synthetic','order_id':'order_synthetic'}
        with patch.object(recovery,'fetch_and_record') as record:recovery.run_payment_event_once(store,accounts);record.assert_called_once()
        job['payload']={'order_id':'order_synthetic'};recovery.run_payment_event_once(store,accounts);store.wake_payment_recovery.assert_called_once_with('synthetic')
        for payload,response in [({},{}),({'payment_id':'pay_synthetic'},{'id':'wrong'})]:
            job['payload']=payload;accounts.current.return_value.payment.return_value=response;recovery.run_payment_event_once(store,accounts);self.assertEqual(store.finish_payment_event.call_args.kwargs['error'],'payment_response_invalid')

if __name__=='__main__':unittest.main()
