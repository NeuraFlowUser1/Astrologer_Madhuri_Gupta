"""No network or money: account isolation, retired writers and signed event identity."""
from copy import deepcopy
import hashlib,hmac,json
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from appointment_system.configuration import installation
from appointment_system.errors import Rejected
from appointment_system.payment_configuration import payment_accounts,payment_webhook
from appointment_system.razorpay import RazorpayFailure,order_receipt,saved_order_receipt
from appointment_system.webhook import accept_webhook,InvalidWebhook,EventConflict

def accounts_document():
    facts=installation()
    return {'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
      'provider':'razorpay','active_account_version':'new', 'accounts':[
       {'account_version':'old','merchant_id':'SyntheticOldMID','mode':'live','key_id':'rzp_live_old',
        'key_secret':'SyntheticOldAPISecret001','state':'retired'},
       {'account_version':'new','merchant_id':'SyntheticNewMID','mode':'live','key_id':'rzp_live_new',
        'key_secret':'SyntheticNewAPISecret002','state':'active'}]}

def webhook_document():
    facts=installation()
    return {'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
      'provider':'razorpay','purpose':'razorpay-webhook','key_map':{
       'old':{'merchant_id':'SyntheticOldMID','keys':[{'key_id':'old-hook','secret':'SyntheticOldWebhookSecret001'}]},
       'new':{'merchant_id':'SyntheticNewMID','keys':[{'key_id':'new-hook','secret':'SyntheticNewWebhookSecret002'}]}}}

class RegistryTests(TestCase):
    def parse(self,value):return payment_accounts(json.dumps(value))

    def test_scoped_document_has_one_writer_and_retired_accounts_only_read_pinned_history(self):
        accounts=self.parse(accounts_document())
        self.assertEqual(accounts.current('SyntheticNewMID','live').credentials.version,'new')
        old=accounts.pinned('SyntheticOldMID','live','old')
        with self.assertRaises(RazorpayFailure):accounts.current('SyntheticOldMID','live')
        with patch.object(old,'_request') as network:
            with self.assertRaises(RazorpayFailure):old.create_order(uuid4(),100)
            network.assert_not_called()
        with self.assertRaises(RazorpayFailure):accounts.pinned('UnrelatedMID','live','old')
        with self.assertRaises(TypeError):accounts.versions['other']=old

    def test_scope_type_duplicate_fields_and_active_selection_are_rejected(self):
        original=accounts_document()
        for key,value in [('version',True),('installation_id',str(uuid4())),('environment','production'),('provider','other'),('active_account_version','old')]:
            bad=deepcopy(original);bad[key]=value
            with self.assertRaises((ValueError,Rejected,RazorpayFailure)):self.parse(bad)
        with self.assertRaises(Rejected):payment_accounts(json.dumps(original).replace('"version": 1','"version": 1,"version": 1'))
        with self.assertRaises((ValueError,Rejected)):payment_accounts(' '*65537)
        bad=deepcopy(original);bad['accounts'][0]['state']='active'
        with self.assertRaises(ValueError):self.parse(bad)

    def test_duplicate_account_and_api_identity_and_malformed_secret_are_rejected(self):
        original=accounts_document()
        for key,value in [('account_version','new'),('key_id','rzp_live_new'),('key_secret',' '),('key_id',{})]:
            bad=deepcopy(original);bad['accounts'][0][key]=value
            with self.assertRaises((ValueError,Rejected,RazorpayFailure)):self.parse(bad)
        bad=deepcopy(original);bad['accounts'][1]['key_id']='rzp_test_new'
        with self.assertRaises(RazorpayFailure):self.parse(bad)

    def test_test_writer_allowed_only_outside_production(self):
        value=accounts_document();value['accounts'][1].update(mode='test',key_id='rzp_test_new')
        self.assertEqual(self.parse(value).current('SyntheticNewMID','test').mode,'test')
        facts=deepcopy(installation());facts['environment']='production';value['environment']='production'
        with patch('appointment_system.payment_configuration.installation',return_value=facts):
            with self.assertRaises(ValueError):self.parse(value)

    def registry(self):return payment_webhook(json.dumps(webhook_document()),self.parse(accounts_document()))

    def event(self,account='SyntheticOldMID'):
        return json.dumps({'entity':'event','account_id':'acc_'+account,'event':'payment.captured',
             'payload':{'payment':{'entity':{'id':'pay_synthetic','order_id':'order_synthetic'}}}}).encode()

    def test_signed_retired_account_event_is_saved_under_its_original_account(self):
        body=self.event();signature=hmac.new(b'SyntheticOldWebhookSecret001',body,hashlib.sha256).hexdigest()
        class Store:
            def save_provider_event(inner,*args):inner.args=args;return args[4]
        store=Store();self.assertEqual(accept_webhook(store,self.registry(),body,signature,'event1'),{'received':True})
        self.assertEqual(store.args[:4],('razorpay','SyntheticOldMID','live','event1'))
        forged=self.event('SyntheticNewMID');signature=hmac.new(b'SyntheticOldWebhookSecret001',forged,hashlib.sha256).hexdigest()
        with self.assertRaises(InvalidWebhook):accept_webhook(store,self.registry(),forged,signature,'event2')
        with self.assertRaises(InvalidWebhook):accept_webhook(store,self.registry(),body,'0'*64,'event3')
        with self.assertRaises(InvalidWebhook):accept_webhook(store,self.registry(),b'x'*131073,'0'*64,'event4')

    def test_webhook_scope_key_reuse_and_account_mismatch_are_rejected(self):
        accounts=self.parse(accounts_document());original=webhook_document()
        for key,value in [('purpose','other'),('key_map',{}),('installation_id',str(uuid4()))]:
            bad=deepcopy(original);bad[key]=value
            with self.assertRaises((ValueError,Rejected)):payment_webhook(json.dumps(bad),accounts)
        for field,value in [('merchant_id','OtherMID'),('keys',original['key_map']['new']['keys'])]:
            bad=deepcopy(original);bad['key_map']['old'][field]=value
            with self.assertRaises(ValueError):payment_webhook(json.dumps(bad),accounts)

    def test_repeated_event_with_a_different_saved_body_cannot_replace_evidence(self):
        class Store:
            def save_provider_event(self,*args):return '0'*64
        body=self.event();signature=hmac.new(b'SyntheticOldWebhookSecret001',body,hashlib.sha256).hexdigest()
        with self.assertRaises(EventConflict):accept_webhook(Store(),self.registry(),body,signature,'event1')

    def test_external_reference_formats_are_explicit_and_old_prefixes_are_preserved(self):
        booking=uuid4()
        self.assertEqual(order_receipt(booking,'live'),'bl_'+booking.hex)
        self.assertEqual(order_receipt(booking,'test','astro-order-receipt-v1'),'at_'+booking.hex)
        self.assertEqual(saved_order_receipt({'booking_id':booking,'mode':'live','provider_receipt_format':'sarsa-order-receipt-v1'}),'s4l_'+booking.hex)
        with self.assertRaises(ValueError):order_receipt(booking,'live','unknown')
        with self.assertRaises(RazorpayFailure):saved_order_receipt({'booking_id':booking,'mode':'live'})
