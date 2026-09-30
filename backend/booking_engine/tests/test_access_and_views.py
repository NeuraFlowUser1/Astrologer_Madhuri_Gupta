import unittest
from datetime import date,datetime,timedelta,timezone
from unittest.mock import Mock
from uuid import uuid4

from backend.booking_engine.access import AccessDenied,authorize_context,new_context,parse_context
from backend.booking_engine.availability import IntakeClosed,available_times
from backend.booking_engine.connection import StorageUnavailable
from backend.booking_engine.policy import IST,policy_snapshot,policy_version
from backend.booking_engine.receipt_view import receipt_view
from backend.booking_engine.security import new_secret,receipt_digest,receipt_matches


class AccessTests(unittest.TestCase):
    def test_context_separate_from_receipt_and_exact_expiry(self):
        key=b'a'*32
        context,token,digest=new_context(key)
        self.assertEqual(parse_context(token,key),(context,digest))
        secret=token.split('.')[1]
        self.assertNotEqual(digest,receipt_digest(context,secret,key))
        now=datetime.now(timezone.utc)
        row=dict(credential_digest=digest,expires_at=now+timedelta(seconds=1))
        authorize_context(row,digest,now)
        for expiry in (now,now-timedelta(seconds=1)):
            with self.assertRaises(AccessDenied):
                authorize_context(dict(row,expires_at=expiry),digest,now)
        with self.assertRaises(AccessDenied):
            authorize_context(row,'b'*64,now)
        for bad in (None,'',token+'suffix','invalid.'+secret):
            with self.assertRaises(AccessDenied):
                parse_context(bad,key)
        self.assertFalse(receipt_matches(context,secret,key,'é'*64))


class ReceiptViewTests(unittest.TestCase):
    def fixture(self):
        now=datetime(2026,9,28,4,tzinfo=timezone.utc)
        request=uuid4(); secret=new_secret(); key=b'a'*32
        row=dict(request_id=str(request),receipt_digest=receipt_digest(request,secret,key),
                 receipt_expires_at=now+timedelta(days=2),receipt_revoked_at=None,
                 state='confirmed',order_state='ready',attempted_at=now-timedelta(minutes=1),
                 provider_order_id='order_synthetic',resolution='confirmed',resolved_at=now,
                 hold_expires_at=now+timedelta(minutes=9),service_name='Numerology',amount_paise=210000,
                 currency='INR',starts_at=now+timedelta(hours=1),ends_at=now+timedelta(minutes=90),
                 captured_paise=210000,refunded_paise=0,practice_timezone='Asia/Kolkata',payment_state='captured',payment_checked_at=now.isoformat(),
                 meeting_state='preparing',acknowledgement_state='pending',meeting_email_state='not_queued',
                 email='private@example.invalid',phone='+919876543210',notes='private',
                 context_id=str(uuid4()),merchant_id='private-merchant')
        return dict(server_now=now,booking=row),request,secret,key

    def test_minimal_projection_and_confirmed_resolution(self):
        snapshot,request,secret,key=self.fixture()
        view=receipt_view(snapshot,request,secret,key)
        self.assertEqual(view['appointment_state'],'confirmed')
        self.assertEqual(view['next_actions'],['check_status'])
        for private in ('email','phone','notes','context_id','merchant_id','receipt_digest','provider_order_id'):
            self.assertNotIn(private,view)
        self.assertNotIn(secret,str(view))
        self.assertEqual(view['acknowledgement_state'],'pending')
        self.assertEqual(view['meeting_state'],'preparing')

    def test_partial_refund_amounts_are_separate_from_confirmation(self):
        snapshot,request,secret,key=self.fixture()
        snapshot['booking'].update(payment_state='partially_refunded',refunded_paise=10000)
        result=receipt_view(snapshot,request,secret,key)
        self.assertEqual(result['payment_state'],'partially_refunded')
        self.assertEqual(result['refunded_paise'],10000)
        self.assertEqual(result['appointment_state'],'confirmed')
        snapshot['booking']['refunded_paise']=210001
        with self.assertRaises(ValueError):receipt_view(snapshot,request,secret,key)

    def test_meeting_link_only_for_current_ready_confirmed_receipt(self):
        snapshot,request,secret,key=self.fixture()
        snapshot['booking'].update(meeting_state='ready',meet_url='https://meet.google.com/abc-defg-hij')
        self.assertEqual(receipt_view(snapshot,request,secret,key)['meet_url'],'https://meet.google.com/abc-defg-hij')
        snapshot['booking']['meeting_state']='preparing'
        self.assertIsNone(receipt_view(snapshot,request,secret,key)['meet_url'])
        snapshot['booking'].update(meeting_state='ready',state='cancelled')
        self.assertIsNone(receipt_view(snapshot,request,secret,key)['meet_url'])
        snapshot['booking'].update(state='confirmed',meet_url='https://other.example/meeting')
        with self.assertRaises(ValueError): receipt_view(snapshot,request,secret,key)

    def test_wrong_missing_revoked_and_expired_credentials_same_error(self):
        snapshot,request,secret,key=self.fixture()
        for changed in (dict(snapshot,booking=None),
                        dict(snapshot,booking=dict(snapshot['booking'],receipt_revoked_at=snapshot['server_now'])),
                        dict(snapshot,booking=dict(snapshot['booking'],receipt_expires_at=snapshot['server_now']))):
            with self.assertRaises(AccessDenied):
                receipt_view(changed,request,secret,key)
        for wrong in ('',new_secret(),None):
            with self.assertRaises(AccessDenied):
                receipt_view(snapshot,request,wrong,key)

    def test_expired_hold_does_not_offer_another_payment(self):
        snapshot,request,secret,key=self.fixture()
        snapshot['booking'].update(state='held',resolution=None,resolved_at=None,payment_state='unobserved',
                                   hold_expires_at=snapshot['server_now']-timedelta(seconds=1))
        view=receipt_view(snapshot,request,secret,key)
        self.assertEqual(view['appointment_state'],'expired')
        self.assertNotIn('choose_new_time',view['next_actions'])
        self.assertNotIn('resume_payment',view['next_actions'])


class AvailabilityTests(unittest.TestCase):
    def snapshot(self):
        return dict(server_now=datetime(2026,9,28,9,tzinfo=IST),schedule_browsing_open=True,public_open=True,
                    policy_version=policy_version(),specification=policy_snapshot(),claims=[])

    def test_real_claims_exclude_overlap_but_allow_adjacency(self):
        store=Mock(); snapshot=self.snapshot()
        snapshot['claims']=[dict(starts_at='2026-09-28T10:00:00+05:30',ends_at='2026-09-28T10:45:00+05:30')]
        store.scheduling_snapshot.return_value=snapshot
        view=available_times(store,'numerology',date(2026,9,28))
        self.assertEqual(len(view['slots']),8)
        self.assertTrue(view['slots'][0]['starts_at'].endswith('11:00:00+05:30'))
        self.assertNotIn('claims',view)

    def test_out_of_range_date_is_rejected_before_database_access(self):
        from backend.booking_engine.policy import InvalidSelection
        store=Mock()
        with self.assertRaises(InvalidSelection):
            available_times(store,'numerology',date.max)
        store.scheduling_snapshot.assert_not_called()

    def test_closed_and_failed_storage_are_not_empty_available_days(self):
        store=Mock(); store.scheduling_snapshot.return_value=dict(self.snapshot(),schedule_browsing_open=False,public_open=False)
        with self.assertRaises(IntakeClosed):
            available_times(store,'numerology',date(2026,9,28))
        store.scheduling_snapshot.return_value=dict(self.snapshot(),policy_version='0'*64)
        with self.assertRaises(StorageUnavailable):
            available_times(store,'numerology',date(2026,9,28))
        store.scheduling_snapshot.side_effect=StorageUnavailable('offline')
        with self.assertRaises(StorageUnavailable):
            available_times(store,'numerology',date(2026,9,28))


if __name__=='__main__':
    unittest.main()
