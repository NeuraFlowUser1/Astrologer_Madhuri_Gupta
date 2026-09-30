import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
from uuid import uuid4

from backend.booking_engine.razorpay import RazorpayFailure,order_receipt
from backend.booking_engine.recovery import run_payment_recovery_once,run_payment_event_once


class RecoveryTests(unittest.TestCase):
    def flow(self):
        now=datetime.now(timezone.utc)
        job=dict(booking_id=str(uuid4()),context_id=str(uuid4()),lease_token=str(uuid4()),attempts=1,
            merchant_id='sarsaTest',mode='test',credential_version='v1',provider_order_id='order_test',
            state='ready',amount_paise=210000,currency='INR',hold_expires_at=now-timedelta(days=2),
            server_now=now,recovery_cursor=0,order_search_skip=0)
        store,accounts=Mock(),Mock()
        store.claim_payment_recovery.return_value=[job]
        adapter=accounts.pinned.return_value
        adapter.order_payments.return_value={'entity':'collection','count':0,'items':[]}
        return store,accounts,adapter,job

    def test_empty_remote_list_after_old_hold_never_allows_new_order(self):
        store,accounts,adapter,job=self.flow()
        run_payment_recovery_once(store,accounts)
        store.abandon_unattempted.assert_not_called()
        adapter.create_order.assert_not_called()
        store.finish_payment_recovery.assert_called_once()

    def test_two_item_cursor_eventually_covers_odd_number_of_payments(self):
        store,accounts,adapter,job=self.flow()
        adapter.order_payments.return_value={'entity':'collection','count':3,'items':[
            {'entity':'payment','id':f'pay_{i}','order_id':'order_test'} for i in range(3)]}
        with patch('backend.booking_engine.recovery.fetch_and_record') as record:
            run_payment_recovery_once(store,accounts)
            self.assertEqual([call.args[-1] for call in record.call_args_list],['pay_0','pay_1'])
            self.assertEqual(store.finish_payment_recovery.call_args.args[2],2)
            job['recovery_cursor']=2
            record.reset_mock()
            run_payment_recovery_once(store,accounts)
            self.assertEqual([call.args[-1] for call in record.call_args_list],['pay_2'])
            self.assertEqual(store.finish_payment_recovery.call_args.args[2],0)

    def test_unknown_order_can_recover_but_never_repeat_create(self):
        store,accounts,adapter,job=self.flow()
        job.update(provider_order_id=None,state='creation_unknown')
        adapter.orders_page.return_value={'entity':'collection','count':1,'items':[
            dict(entity='order',id='order_recovered',receipt=order_receipt(job['booking_id'],'test'),
                 amount=210000,currency='INR',partial_payment=False)]}
        run_payment_recovery_once(store,accounts)
        store.record_order_creation.assert_called_once_with(job['context_id'],job['booking_id'],job,'order_recovered')
        adapter.create_order.assert_not_called()

    def test_missing_credentials_retain_job_with_nonsecret_reason(self):
        store,accounts,adapter,job=self.flow()
        accounts.pinned.side_effect=RazorpayFailure('payment_configuration_missing')
        run_payment_recovery_once(store,accounts)
        self.assertEqual(store.finish_payment_recovery.call_args.kwargs['error'],'payment_configuration_missing')
        store.abandon_unattempted.assert_not_called()

    def test_only_expired_never_attempted_hold_is_abandoned(self):
        store,accounts,adapter,job=self.flow()
        job['state']='not_attempted'
        run_payment_recovery_once(store,accounts)
        store.abandon_unattempted.assert_called_once_with(job['context_id'],job['booking_id'])
        accounts.pinned.assert_not_called()

    def test_provider_event_resolves_saved_pinned_account(self):
        store,accounts=Mock(),Mock()
        event=dict(account_id='sarsaTest',environment='test',event_id='evt_test',lease_token=str(uuid4()),
                   attempts=1,payload=dict(payment_id='pay_test',order_id='order_test'))
        store.claim_payment_events.return_value=[event]
        booking=dict(merchant_id='sarsaTest',mode='test',credential_version='old-version',
                     context_id=str(uuid4()),booking_id=str(uuid4()))
        store.find_order.return_value=booking
        with patch('backend.booking_engine.recovery.fetch_and_record') as record:
            run_payment_event_once(store,accounts)
            accounts.pinned.assert_called_once_with('sarsaTest','test','old-version')
            record.assert_called_once()
        self.assertTrue(store.finish_payment_event.call_args.kwargs['done'])
        store.find_order.return_value=None
        run_payment_event_once(store,accounts)
        self.assertFalse(store.finish_payment_event.call_args.kwargs['done'])


class RecoveryCompletionTests(unittest.TestCase):
    def test_lost_payment_lease_is_not_reported_as_committed_work(self):
        store,accounts,adapter,job=RecoveryTests().flow()
        for value in (False,True):
            store.finish_payment_recovery.return_value=value
            result=run_payment_recovery_once(store,accounts)
            self.assertEqual(result,{'processed':int(value),'retry':not value})

    def test_lost_event_lease_is_not_reported_as_committed_work(self):
        store,accounts=Mock(),Mock()
        store.claim_payment_events.return_value=[{'account_id':'sarsaTest','environment':'test',
            'payload':{'order_id':'order_test'},'attempts':1}]
        store.find_order.return_value={'merchant_id':'sarsaTest','mode':'test','credential_version':'v1','booking_id':'synthetic'}
        for value in (False,True):
            store.finish_payment_event.return_value=value
            result=run_payment_event_once(store,accounts)
            self.assertEqual(result,{'processed':int(value),'retry':not value})


if __name__=='__main__':
    unittest.main()
