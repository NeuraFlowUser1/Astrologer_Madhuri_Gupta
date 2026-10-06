"""Real code encryption and message binding with a synthetic delivery store."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from appointment_system.booking_verification import VerificationSecrets
from appointment_system.booking_verification_delivery import message,seal,open_message,run_booking_code_once
from appointment_system.resend_email import EmailFailure
from appointment_system.access import AccessDenied
from appointment_system.serialization import canonical
from .test_application import protection


class VerificationDeliveryBoundaries(TestCase):
    def setUp(self):
        self.keys=VerificationSecrets.from_environment({'BOOKING_VERIFICATION_DIGEST_KEYS':canonical(protection('booking-verification-digest',11)),
            'BOOKING_VERIFICATION_ENCRYPTION_KEYS':canonical(protection('booking-verification-encryption',12))})
        now=datetime.now(timezone.utc);challenge,context=str(uuid4()),str(uuid4());email='synthetic@example.test'
        _,encrypted=self.keys.challenge(challenge,context,email,1)
        self.job=dict(id=str(uuid4()),challenge_id=challenge,context_id=context,destination=email,generation=1,
            code_ciphertext=encrypted,template_version=1,attempts=1,message_ciphertext=None,message_digest=None,
            first_attempt_at=now.isoformat(),code_expires_at=(now+timedelta(minutes=1)).isoformat())

    def test_saved_code_and_grant_reject_foreign_context_generation_destination_and_format(self):
        self.assertRegex(self.keys.open_code(self.job),r'^[0-9]{6}$')
        for change in ({'destination':'foreign@example.test'},{'context_id':str(uuid4())},{'generation':2}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.keys.open_code(self.job|change)
        for token in (None,'bad','not-bv1.k1.'+'x'*43,'bv1.k1.'+'!'*43):
            with self.assertRaises(AccessDenied):self.keys.grant(token,self.job['context_id'],self.job['destination'])
        with self.assertRaises(ValueError):self.keys.digest('unknown','value')
        with self.assertRaises(ValueError):VerificationSecrets(None,self.keys.cipher)

    def test_frozen_message_binds_destination_job_and_digest_without_plaintext_storage(self):
        payload=message(self.keys,self.job);encrypted,digest=seal(self.keys,self.job,payload)
        saved=self.job|{'message_ciphertext':encrypted,'message_digest':digest}
        self.assertEqual(open_message(self.keys,saved),payload)
        self.assertNotIn(self.keys.open_code(self.job),encrypted)
        for change in ({'destination':'foreign@example.test'},{'message_digest':'a'*64}):
            with self.assertRaises(EmailFailure) as raised:open_message(self.keys,saved|change)
            self.assertEqual(raised.exception.code,'email_snapshot_conflict')
        with self.assertRaises(EmailFailure):message(self.keys,{})

    def store(self,job=None):
        store=Mock();store.claim_booking_code.return_value=deepcopy(self.job if job is None else job);store.finish_booking_code.return_value=True
        store.begin_booking_code.side_effect=lambda saved,encrypted,digest,binding:saved|{'message_ciphertext':encrypted,'message_digest':digest}
        return store

    def test_empty_or_deferred_job_does_not_send_and_expired_code_is_recorded(self):
        sender=Mock();store=self.store();store.claim_booking_code.return_value=None
        self.assertEqual(run_booking_code_once(store,sender,self.keys),{'processed':0});sender.send.assert_not_called()
        store=self.store();store.begin_booking_code.side_effect=None;store.begin_booking_code.return_value=None
        self.assertEqual(run_booking_code_once(store,sender,self.keys),{'processed':0,'deferred':True});sender.send.assert_not_called()
        store=self.store(self.job|{'code_expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()})
        self.assertEqual(run_booking_code_once(store,sender,self.keys),{'processed':1,'retry':False});sender.send.assert_not_called()
        self.assertEqual(store.finish_booking_code.call_args.args[2],'email_deadline_passed')

    def test_retry_uses_identical_saved_message_and_records_provider_uncertainty(self):
        payload=message(self.keys,self.job);encrypted,digest=seal(self.keys,self.job,payload)
        store=self.store(self.job|{'message_ciphertext':encrypted,'message_digest':digest});sender=Mock()
        sender.send.side_effect=EmailFailure('email_configuration_rejected',definitely_rejected=True,retry_after=300)
        self.assertEqual(run_booking_code_once(store,sender,self.keys),{'processed':1,'retry':False})
        self.assertEqual(sender.send.call_args.args[0],payload)
        _,provider,error,review,delay,rejected=store.finish_booking_code.call_args.args
        self.assertIsNone(provider);self.assertEqual(error,'email_configuration_rejected');self.assertTrue(review);self.assertTrue(rejected);self.assertGreaterEqual(delay,300)
        sender.send.side_effect=None;sender.send.return_value='synthetic-provider';store.finish_booking_code.return_value=False
        self.assertEqual(run_booking_code_once(store,sender,self.keys),{'processed':0,'retry':True})
        self.assertEqual(store.finish_booking_code.call_args.args[1],'synthetic-provider')
