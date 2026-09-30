import unittest
from uuid import uuid4
from backend.booking_engine.tests import test_studio_calendar as calendar
from backend.booking_engine.receipt_recovery import recovery_code,code_digest
from backend.booking_engine.security import receipt_digest

class RecoveryTests(unittest.TestCase):
    setUp=calendar.CalendarTests.setUp
    def post(self,path,body):return self.client.post(path,json=body,headers=self.headers)
    def support_body(self):return {'operation_id':str(uuid4()),'reference':str(uuid4()),'expected_revision':1,'action':'receipt_recovery','reason':'Verified original phone callback','verified_payment_id':'pay_fixture','verification_confirmed':True}
    def test_staff_attestation_and_role_are_required(self):
        body=self.support_body();self.store.studio_support_change.return_value={'code':'support_saved','revision':1,'active':True,'expires_at':'2030-01-01T10:00:00Z'}
        first=self.post('/api/studio/appointments/support',body);again=self.post('/api/studio/appointments/support',body)
        self.assertEqual(first.status_code,200);self.assertEqual(first.json()['activation_code'],again.json()['activation_code']);self.assertRegex(first.json()['activation_code'],r'^[0-9]{8}$')
        self.assertEqual(first.headers['cache-control'],'no-store')
        for bad in [False,1,'true',None]:self.assertEqual(self.post('/api/studio/appointments/support',dict(body,verification_confirmed=bad)).status_code,422)
        self.store.studio_session.return_value={'role':'agency'};self.assertEqual(self.post('/api/studio/appointments/support',body).status_code,403)
    def test_correction_requires_valid_email_and_mobile(self):
        body=dict(self.support_body(),action='contact_correction')
        for fields in [{},{'email':'not-email','phone':'+919876543210'},{'email':'Valid@example.com','phone':'123'}]:
            self.assertEqual(self.post('/api/studio/appointments/support',dict(body,**fields)).status_code,422)
        self.store.studio_support_change.return_value={'code':'support_saved','revision':2,'active':True,'expires_at':'2030-01-01T10:00:00Z'}
        self.assertEqual(self.post('/api/studio/appointments/support',dict(body,email='Valid@example.com',phone='+919876543210')).status_code,200)
        self.assertEqual(self.store.studio_support_change.call_args.args[-3],'Valid@example.com')
    def test_public_redemption_is_strict_rate_limited_and_passes_only_digests(self):
        ref=str(uuid4());body={'request_id':ref,'code':'12345678','secret':'a'*43}
        self.store.redeem_receipt_recovery.return_value={'code':'receipt_restored'}
        result=self.post('/api/checkout/recover-receipt',body);self.assertEqual(result.status_code,200)
        args=self.store.redeem_receipt_recovery.call_args.args;self.assertNotIn(body['code'],args);self.assertNotIn(body['secret'],args)
        self.assertEqual(args[1],code_digest(b'a'*32,ref,body['code']));self.assertEqual(args[2],receipt_digest(ref,body['secret'],b'a'*32))
        self.store.redeem_receipt_recovery.return_value={'code':'access_unavailable'}
        self.assertEqual(self.post('/api/checkout/recover-receipt',body).status_code,403)
        result=self.post('/api/checkout/recover-receipt',dict(body,code='PRIVATE_INVALID_CODE'))
        self.assertEqual(result.status_code,422);self.assertNotIn('PRIVATE_INVALID_CODE',result.text)
        self.store.consume_limit.return_value={'allowed':False,'retry_after':60}
        self.assertEqual(self.post('/api/checkout/recover-receipt',body).status_code,429)
    def test_code_is_bound_to_operation_and_reference(self):
        op,ref=uuid4(),uuid4();code=recovery_code(b'a'*32,op,ref)
        self.assertEqual(len(code),8);self.assertEqual(code,recovery_code(b'a'*32,op,ref))
        self.assertNotEqual(code_digest(b'a'*32,ref,code),code_digest(b'a'*32,uuid4(),code))
