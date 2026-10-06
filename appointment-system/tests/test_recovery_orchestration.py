"""Saved money recovery is bounded, account-pinned and never creates a new order."""
from datetime import datetime,timezone,timedelta
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from appointment_system import recovery
from appointment_system.razorpay import Credentials,Razorpay,RazorpayFailure,saved_order_receipt
from appointment_system.financial_resources import resource_fact


def collection(items):return {'entity':'collection','count':len(items),'items':items}


class RecoveryOrchestration(TestCase):
    def setUp(self):
        self.now=datetime(2030,1,1,tzinfo=timezone.utc)
        self.job=dict(booking_id=str(uuid4()),context_id=str(uuid4()),merchant_id='SyntheticMerchant',mode='live',
            credential_version='original',provider_receipt_format='provider-receipt-v1',provider_order_id='order_saved',
            state='ready',recovery_cursor=0,order_search_skip=0,attempts=1,amount_paise=100,currency='INR',
            hold_expires_at=self.now+timedelta(minutes=5),server_now=self.now,created_at=self.now,
            order_search_from=self.now-timedelta(minutes=2),order_search_until=self.now)
        self.adapter=Mock()
        self.adapter.credentials=Credentials('SyntheticMerchant','live','original','rzp_live_synthetic','synthetic secret')
        self.adapter.order_payments.return_value=collection([])
        self.accounts=recovery.Accounts([self.adapter],current_versions={('SyntheticMerchant','live'):'original'})
        self.store=Mock(spec=['claim_payment_recovery','finish_payment_recovery','abandon_unattempted',
            'advance_order_search','record_order_creation','order_intent','observe_payment','claim_financial_resources',
            'finish_financial_resource','observe_financial_resource','claim_payment_events','find_order',
            'wake_payment_recovery','finish_payment_event'])
        self.store.claim_payment_recovery.return_value=[self.job]
        self.store.finish_payment_recovery.return_value=True
        self.store.order_intent.return_value=self.job
        self.store.claim_financial_resources.return_value=[]
        self.store.claim_payment_events.return_value=[]
        self.store.finish_financial_resource.return_value=True
        self.store.finish_payment_event.return_value=True
        self.store.observe_financial_resource.return_value={}
        self.store.find_order.return_value=self.job
        self.adapter.payment.side_effect=lambda identifier:self.payment(identifier)
        self.event=dict(account_id='acc_SyntheticMerchant',environment='live',attempts=1,
            payload={'payment_id':'pay_saved','order_id':'order_saved'},body_hash='a'*64)

    def payment(self,identifier='pay_saved',**changes):
        return dict(entity='payment',id=identifier,order_id='order_saved',amount=100,currency='INR',
            status='captured',captured=True,amount_refunded=0)|changes

    def order(self,identifier='order_saved',**changes):
        return dict(entity='order',id=identifier,receipt=saved_order_receipt(self.job),amount=100,currency='INR',partial_payment=False)|changes

    def resource(self,kind='refund',**changes):
        return dict(entity=kind,id='rfnd_saved' if kind=='refund' else 'disp_saved',payment_id='pay_saved',
            amount=100,currency='INR',status='processed' if kind=='refund' else 'open',created_at=1700000000)|changes

    def run_recovery(self):return recovery.run_payment_recovery_once(self.store,self.accounts)
    def run_event(self,**options):return recovery.run_payment_event_once(self.store,self.accounts,**options)

    def test_idle_and_unattempted_work_never_call_the_payment_provider(self):
        self.store.claim_payment_recovery.return_value=[]
        self.assertEqual(self.run_recovery(),{'processed':0});self.store.finish_payment_recovery.assert_not_called()
        self.store.claim_payment_recovery.return_value=[self.job];self.job['state']='not_attempted'
        for expired in (False,True):
            self.job['hold_expires_at']=self.now+timedelta(minutes=-1 if expired else 1)
            self.assertEqual(self.run_recovery(),{'processed':1,'retry':False})
            self.assertEqual(self.store.abandon_unattempted.call_count,int(expired))
            self.assertEqual(self.store.finish_payment_recovery.call_args.args[1],15)
        self.assertEqual(self.adapter.method_calls,[])

    def test_missing_or_rotated_credentials_keep_the_original_account_job_pending(self):
        with self.assertRaises(ValueError):recovery.Accounts([self.adapter,self.adapter],current_versions={})
        for mode,version in [('test','original'),('live','new')]:
            with self.assertRaises(RazorpayFailure):self.accounts.pinned('SyntheticMerchant',mode,version)
        self.job['credential_version']='removed'
        self.assertEqual(self.run_recovery(),{'processed':1,'retry':True})
        self.assertEqual(self.store.finish_payment_recovery.call_args.kwargs['error'],'payment_configuration_missing')
        self.adapter.create_order.assert_not_called();self.adapter.order_payments.assert_not_called()

    def test_saved_order_recovery_deduplicates_and_rotates_a_bounded_payment_batch(self):
        self.adapter.order_payments.return_value=collection([self.payment('pay_c'),self.payment('pay_a'),self.payment('pay_b'),self.payment('pay_a')])
        self.assertEqual(self.run_recovery(),{'processed':1,'retry':False})
        self.assertEqual([c.args[0] for c in self.adapter.payment.call_args_list],['pay_a','pay_b'])
        self.assertEqual(self.store.finish_payment_recovery.call_args.args[2],2)
        self.job['recovery_cursor']=2;self.adapter.payment.reset_mock();self.run_recovery()
        self.assertEqual([c.args[0] for c in self.adapter.payment.call_args_list],['pay_c'])
        self.assertEqual(self.store.finish_payment_recovery.call_args.args[2],0)
        self.adapter.create_order.assert_not_called();self.adapter.orders_page.assert_not_called()

    def test_empty_or_malformed_payment_results_never_confirm_or_recreate_an_order(self):
        invalid=[None,{},collection([None]),{'entity':'collection','items':[],'count':True},
            collection([{}]),
            collection([self.payment(order_id='order_other')]),collection([self.payment(id='bad')]),
            collection([self.payment(entity='order')]),collection([self.payment()]*101)]
        self.run_recovery();self.store.observe_payment.assert_not_called()
        for response in invalid:
            with self.subTest(response=response):
                self.adapter.order_payments.return_value=response
                self.assertTrue(self.run_recovery()['retry'])
                self.assertEqual(self.store.finish_payment_recovery.call_args.kwargs['error'],'payment_response_invalid')
        self.store.observe_payment.assert_not_called();self.adapter.create_order.assert_not_called()

    def test_search_pages_overlap_and_persist_without_guessing_that_no_order_exists(self):
        self.job.update(provider_order_id=None,order_search_skip=90)
        self.adapter.orders_page.return_value=collection([self.order('order_'+str(i),receipt='unrelated') for i in range(100)])
        self.store.advance_order_search.return_value={'code':'continue'}
        self.run_recovery()
        self.store.advance_order_search.assert_called_with(self.job,[],False)
        self.assertEqual(self.store.finish_payment_recovery.call_args.args[3],180)
        self.adapter.orders_page.return_value=collection([]);self.run_recovery()
        self.store.advance_order_search.assert_called_with(self.job,[],True)
        self.assertEqual(self.store.finish_payment_recovery.call_args.args[3],0)
        self.adapter.create_order.assert_not_called();self.store.record_order_creation.assert_not_called()

    def test_one_matching_order_is_fetched_and_bound_before_any_payment_observation(self):
        self.job['provider_order_id']=None
        self.adapter.orders_page.return_value=collection([self.order()]);self.adapter.order.return_value=self.order()
        self.store.advance_order_search.return_value={'code':'match','order_id':'order_saved'}
        self.run_recovery()
        self.store.record_order_creation.assert_called_once_with(self.job['context_id'],self.job['booking_id'],self.job,'order_saved')
        self.adapter.order_payments.assert_called_once_with('order_saved');self.adapter.create_order.assert_not_called()
        self.adapter.order.return_value=self.order(amount=99);self.assertTrue(self.run_recovery()['retry'])
        self.assertEqual(self.store.record_order_creation.call_count,1)

    def test_ambiguous_or_conflicting_search_evidence_stays_a_review_not_a_fresh_order(self):
        self.job['provider_order_id']=None
        for items,outcome,error in [([self.order('order_a'),self.order('order_b')],{},'payment_order_mismatch'),
            ([self.order(amount=99)],{},'payment_order_mismatch'),([{'receipt':saved_order_receipt(self.job),'id':None}],{},'payment_order_mismatch'),
            ([],None,'payment_response_invalid'),([],{'code':'conflict'},'payment_order_mismatch')]:
            with self.subTest(items=items,outcome=outcome):
                self.adapter.orders_page.return_value=collection(items);self.store.advance_order_search.return_value=outcome
                self.assertTrue(self.run_recovery()['retry'])
                self.assertEqual(self.store.finish_payment_recovery.call_args.kwargs['error'],error)
        self.store.record_order_creation.assert_not_called();self.adapter.create_order.assert_not_called()

    def test_real_adapter_search_receives_the_saved_time_window_and_bounded_retry(self):
        self.job['provider_order_id']=None
        provider=Razorpay(self.adapter.credentials);provider.orders_page=Mock(return_value=collection([]))
        self.accounts=recovery.Accounts([provider],current_versions={});self.store.advance_order_search.return_value={'code':'continue'}
        self.run_recovery();kwargs=provider.orders_page.call_args.kwargs
        self.assertEqual(kwargs['from_time'],int(self.job['order_search_from'].timestamp()))
        self.assertEqual(kwargs['to_time'],int(self.now.timestamp()))
        self.assertEqual(kwargs['receipt_format'],'provider-receipt-v1')
        self.store.finish_payment_recovery.return_value=False
        self.assertEqual(self.run_recovery(),{'processed':0,'retry':True})
        self.job.pop('server_now');self.job['attempts']=3;self.run_recovery()
        self.assertEqual(self.store.finish_payment_recovery.call_args.args[1],60)
        self.assertEqual(recovery.delay_for(10000),3600)

    def test_empty_event_lanes_and_invalid_lane_do_not_take_other_work(self):
        self.assertEqual(self.run_event(),{'processed':0})
        self.store.claim_payment_events.reset_mock()
        self.assertEqual(self.run_event(source='resource'),{'processed':0});self.store.claim_payment_events.assert_not_called()
        self.store.claim_financial_resources.reset_mock();self.run_event(source='inbox');self.store.claim_financial_resources.assert_not_called()
        with self.assertRaises(ValueError):self.run_event(source='arbitrary')

    def test_order_only_event_wakes_saved_recovery_and_missing_order_remains_unresolved(self):
        self.event['payload']={'order_id':'order_saved'};self.store.claim_payment_events.return_value=[self.event]
        self.assertEqual(self.run_event(),{'processed':1,'retry':False})
        self.store.wake_payment_recovery.assert_called_once_with(self.job['booking_id']);self.store.observe_payment.assert_not_called()
        self.store.find_order.return_value=None
        self.assertTrue(self.run_event()['retry']);self.assertFalse(self.store.finish_payment_event.call_args.kwargs['done'])
        self.store.finish_payment_event.return_value=False
        self.assertEqual(self.run_event(),{'processed':0,'retry':True})

    def test_payment_only_event_fetches_parent_then_uses_the_original_pinned_account(self):
        self.event['payload']={'payment_id':'pay_saved'};self.store.claim_payment_events.return_value=[self.event]
        self.assertEqual(self.run_event(),{'processed':1,'retry':False})
        self.store.find_order.assert_called_once_with('acc_SyntheticMerchant','live','order_saved')
        self.store.observe_payment.assert_called_once()
        for payment in (None,self.payment(id='pay_other'),self.payment(order_id=None)):
            self.adapter.payment.side_effect=None;self.adapter.payment.return_value=payment
            self.assertTrue(self.run_event()['retry'])
            self.assertEqual(self.store.finish_payment_event.call_args.kwargs['error'],'payment_response_invalid')
        self.event['payload']={};self.assertTrue(self.run_event()['retry'])

    def test_signed_refund_is_not_finished_until_fetched_money_reflects_it(self):
        self.store.claim_payment_events.return_value=[self.event]
        self.event['payload'].update(resource_fact=resource_fact(self.resource(),'refund'))
        self.adapter.refund.return_value=self.resource()
        self.assertTrue(self.run_event()['retry'])
        self.assertEqual(self.store.finish_payment_event.call_args.kwargs['error'],'refund_not_reflected')
        self.adapter.payment.side_effect=lambda identifier:self.payment(identifier,amount_refunded=100,status='refunded')
        self.assertEqual(self.run_event(),{'processed':1,'retry':False})
        self.assertEqual([c.args[3] for c in self.store.observe_financial_resource.call_args_list],['signed_webhook','provider_fetch']*2)
        self.store.observe_payment.assert_called_once();self.adapter.create_order.assert_not_called()
        self.store.observe_financial_resource.return_value={'attention_reason':'refund_totals_conflict'}
        self.assertTrue(self.run_event()['retry']);self.assertEqual(self.store.observe_payment.call_count,1)

    def test_dispute_notifications_and_resource_polling_never_reconfirm_appointments(self):
        fact=resource_fact(self.resource('dispute'),'dispute');self.adapter.dispute.return_value=self.resource('dispute')
        self.event['payload']['resource_fact']=fact;self.store.claim_payment_events.return_value=[self.event]
        self.assertFalse(self.run_event()['retry']);self.store.observe_payment.assert_not_called()
        for kind in ('dispute','refund'):
            self.job.update(fact=resource_fact(self.resource(kind),kind),payment_id='pay_saved',order_id='order_saved')
            self.adapter.refund.return_value=self.resource();self.store.claim_financial_resources.return_value=[self.job]
            self.assertEqual(self.run_event(),{'processed':1,'retry':False})
        self.assertEqual(self.store.observe_payment.call_count,1)
        self.store.observe_financial_resource.return_value={'attention_reason':'financial_resource_conflict'}
        self.assertTrue(self.run_event()['retry']);self.assertEqual(self.store.observe_payment.call_count,1)
        self.store.finish_financial_resource.return_value=False
        self.assertEqual(self.run_event(),{'processed':0,'retry':True})

    def test_provider_failure_keeps_durable_work_retryable_without_private_response_details(self):
        self.adapter.order_payments.side_effect=RazorpayFailure('payment_provider_unavailable')
        self.assertTrue(self.run_recovery()['retry'])
        self.assertEqual(self.store.finish_payment_recovery.call_args.kwargs['error'],'payment_provider_unavailable')
        self.event['payload']['event']='refund.processed';self.store.claim_payment_events.return_value=[self.event]
        self.assertTrue(self.run_event()['retry'])
        self.assertEqual(self.store.finish_payment_event.call_args.kwargs['error'],'refund_not_reflected')
        self.adapter.payment.side_effect=lambda identifier:self.payment(identifier,amount_refunded=100)
        self.event.update(server_now=self.now,received_at=self.now-timedelta(days=10))
        self.assertFalse(self.run_event()['retry']);self.assertEqual(self.store.finish_payment_event.call_args.kwargs['delay'],86400)
