"""Booking inputs keep explicit retry versions, valid contacts and zoned slots."""
from datetime import date,datetime,timezone
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4
from appointment_system.availability import available_times,IntakeClosed
from appointment_system.connection import StorageUnavailable
from appointment_system.models import BookingInput,BookingRequest
from appointment_system.policy import InvalidSelection

class BookingInputBoundaries(TestCase):
    def body(self):
        return dict(request_id=str(uuid4()),full_name='Synthetic Person',email='MixedCase@Example.com',phone='+919999999999',
            service_id='consultation',quote_version='a'*64,starts_at='2026-10-09T10:00:00+05:30')

    def test_new_mailbox_spelling_and_explicit_legacy_retry_have_distinct_rules(self):
        new=BookingRequest(**self.body());self.assertEqual(new.email,'MixedCase@example.com')
        old=BookingRequest(**self.body(),normalization_version=1);self.assertEqual(old.email,'mixedcase@example.com')
        legacy=BookingInput(**self.body());self.assertEqual(legacy.email,'mixedcase@example.com')
        self.assertEqual(new.starts_at,datetime(2026,10,9,4,30,tzinfo=timezone.utc))
        for version in (True,False,0,4,'1',1.0):
            with self.subTest(version=version),self.assertRaises(ValueError):BookingRequest(**self.body(),normalization_version=version)

    def test_controls_ambiguous_times_and_invalid_mobile_numbers_are_rejected(self):
        for changes in ({'full_name':'bad\x00name'},{'full_name':'bad\x7fname'},{'notes':'bad\x7ftext'},
            {'starts_at':'2026-10-09T10:00:00'},{'starts_at':'2026-10-09T10:00:01Z'},
            {'starts_at':'2026-10-09T10:00:00.000001Z'},{'phone':'9999999999'},{'phone':'+not-a-number'},
            {'phone':'+911123456789'},{'phone':'+919999999999 ext 123'},{'questions':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):BookingRequest(**(self.body()|changes))
        self.assertEqual(BookingRequest(**(self.body()|{'phone':''})).phone,'')

    def test_off_or_unavailable_service_is_not_presented_as_an_empty_schedule(self):
        store=Mock(spec=['available_times']);day=date(2026,10,9)
        for value,error in [(None,StorageUnavailable),({'code':'service_unavailable'},InvalidSelection),({'code':'booking_disabled'},IntakeClosed)]:
            store.available_times.return_value=value
            with self.subTest(value=value),self.assertRaises(error):available_times(store,'consultation',day)
        offered={'code':'ok','times':[]};store.available_times.return_value=offered
        self.assertEqual(available_times(store,'consultation',day),offered)
        store.available_times.assert_called_with('consultation',day,1)
        store.reset_mock()
        for invalid_day,questions in [('2026-10-09',1),(datetime(2026,10,9),1),(day,True)]:
            with self.assertRaises(InvalidSelection):available_times(store,'consultation',invalid_day,questions)
        store.available_times.assert_not_called()

    def test_only_v3_can_omit_email_without_weakening_the_legacy_importer(self):
        for empty in (None,'','   '):
            with self.subTest(empty=empty):
                self.assertIsNone(BookingRequest(**(self.body()|{'email':empty,'normalization_version':3})).email)
                for version in (1,2):
                    with self.assertRaises(ValueError):BookingRequest(**(self.body()|{'email':empty,'normalization_version':version}))
                with self.assertRaises(ValueError):BookingInput(**(self.body()|{'email':empty}))
        body=self.body();body.pop('email')
        self.assertIsNone(BookingRequest(**body,normalization_version=3).email)
        with self.assertRaises(ValueError):BookingRequest(**body)
        for invalid in ('not-an-email',True,12,[]):
            with self.assertRaises(ValueError):BookingRequest(**(self.body()|{'email':invalid,'normalization_version':3}))
        with self.assertRaises(ValueError):BookingRequest(**(self.body()|{'email':None,'normalization_version':3,'verification_grant':'synthetic'}))
