"""Focused real SQL acceptance for optional contacts and strict preparation."""
from copy import deepcopy
from .test_sql_booking import BookingFixture
from tools.checks.sql_target import literal

class BookingExperienceSQL(BookingFixture):
    def test_optional_email_preserves_calendar_staff_and_both_record_jobs(self):
        draft=self.booking(email=None,normalization_version=3)
        self.assertEqual(self.reserve(draft)['booking_id'],draft['booking'])
        self.assertEqual(self.db.scalar('SELECT email IS NULL FROM appointment_system.bookings WHERE id='+literal(draft['booking'])+';'),'t')
        self.start_order(draft);self.record_order(draft);self.capture(draft)
        jobs=self.db.value('SELECT jsonb_agg(jsonb_build_array(kind,recipient_role) ORDER BY kind,recipient_role) FROM appointment_system.delivery_jobs WHERE booking_id='+literal(draft['booking'])+';')
        self.assertEqual(jobs,[['booking_ack','client'],['booking_calendar','calendar'],['sheet_booking','agency_sheet'],['sheet_booking','client_sheet']])

    def test_missing_email_remains_invalid_for_old_versions_and_verification_on(self):
        for version in (None,1,2,True,'3',4):
            changes={'email':None}
            if version is not None:changes['normalization_version']=version
            result=self.reserve(self.draft(**changes));self.assertEqual(result['code'],'invalid_details',version)
        spec=deepcopy(self.spec);spec['booking_verification']['email']=True;spec['required_contacts']=['email','phone'];self.set_policy(spec)
        self.assertEqual(self.reserve(self.draft(email=None,normalization_version=3))['code'],'invalid_details')

    def test_invalid_birth_dates_and_times_are_rejected_without_cast_errors_or_bookings(self):
        for changes in ({'birth_date':'2026-02-30'},{'birth_date':'2026-13-01'},{'birth_date':'0000-01-01'},
                        {'birth_date':'9999-01-01'},{'birth_date':True},{'birth_time':'24:00'},
                        {'birth_time':None},{'birth_place':['not a string']},{'notes':'x'*4001}):
            with self.subTest(changes=changes):
                draft=self.draft(normalization_version=3,**changes)
                self.assertEqual(self.reserve(draft)['code'],'invalid_details')
                self.assertEqual(self.db.scalar('SELECT outcome FROM appointment_system.checkout_admissions WHERE request_id='+literal(draft['request'])+';'),'rejected')
                self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings WHERE request_id='+literal(draft['request'])+';'),'0')

    def test_existing_commitment_is_returned_before_current_policy_rejection(self):
        draft=self.booking(email=None,normalization_version=3)
        spec=deepcopy(self.spec);spec['booking_verification']['email']=True;spec['required_contacts']=['email','phone'];self.set_policy(spec)
        self.assertEqual(self.reserve(draft),{'code':'existing','booking_id':draft['booking']})

    def test_public_policy_uses_independent_verification_binding_and_rejects_contradictory_rules(self):
        public=self.db.value('SELECT appointment_system.public_policy();',role='appointment_system_web')
        saved=self.db.scalar('SELECT appointment_system.verification_policy(appointment_system.current_business());')
        self.assertEqual(public['booking_verification_policy_hash'],saved)
        changed=deepcopy(self.spec);changed['required_contacts']=['email','phone']
        self.assertEqual(self.db.scalar('SELECT appointment_system.validate_business('+literal(changed)+'::jsonb);'),'f')
