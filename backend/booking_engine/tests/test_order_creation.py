import unittest
from unittest.mock import Mock
from uuid import uuid4

from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.order_creation import create_once
from backend.booking_engine.razorpay import Credentials,RazorpayFailure


class CreationTests(unittest.TestCase):
    def setup_flow(self):
        store=Mock()
        store.order_intent.return_value=dict(merchant_id='sarsaTest',mode='test',credential_version='v1',
                                            amount_paise=210000,currency='INR')
        store.start_order_creation.return_value=True
        adapter=Mock()
        adapter.credentials=Credentials('sarsaTest','test','v1','rzp_test_synthetic','synthetic-secret')
        adapter.create_order.return_value={'id':'order_synthetic'}
        return store,adapter,uuid4(),uuid4()

    def test_durable_claim_precedes_external_call(self):
        store,adapter,context,booking=self.setup_flow()
        trace=[]
        store.start_order_creation.side_effect=lambda *args: trace.append('committed') or True
        adapter.create_order.side_effect=lambda *args: trace.append('provider') or {'id':'order_synthetic'}
        store.record_order_creation.side_effect=lambda *args: trace.append('saved')
        self.assertEqual(create_once(store,adapter,context,booking),'check_saved_status')
        self.assertEqual(trace,['committed','provider','saved'])

    def test_duplicate_or_uncertain_claim_never_contacts_provider(self):
        for uncertain in (False,True):
            store,adapter,context,booking=self.setup_flow()
            if uncertain:
                store.start_order_creation.side_effect=StorageUnavailable('uncertain')
                with self.assertRaises(StorageUnavailable):
                    create_once(store,adapter,context,booking)
            else:
                store.start_order_creation.return_value=False
                create_once(store,adapter,context,booking)
            adapter.create_order.assert_not_called()

    def test_wrong_credential_version_never_claims_or_creates(self):
        store,adapter,context,booking=self.setup_flow()
        store.order_intent.return_value['credential_version']='old-version'
        with self.assertRaises(RazorpayFailure):
            create_once(store,adapter,context,booking)
        store.start_order_creation.assert_not_called()
        adapter.create_order.assert_not_called()

    def test_lost_provider_response_saved_as_unknown_without_retry(self):
        store,adapter,context,booking=self.setup_flow()
        adapter.create_order.side_effect=RazorpayFailure('timeout',uncertain=True)
        create_once(store,adapter,context,booking)
        self.assertEqual(adapter.create_order.call_count,1)
        self.assertIsNone(store.record_order_creation.call_args.args[-1])

    def test_lost_local_save_never_repeats_provider_request(self):
        store,adapter,context,booking=self.setup_flow()
        store.record_order_creation.side_effect=StorageUnavailable('uncertain')
        with self.assertRaises(StorageUnavailable):
            create_once(store,adapter,context,booking)
        self.assertEqual(adapter.create_order.call_count,1)


if __name__=='__main__':
    unittest.main()
