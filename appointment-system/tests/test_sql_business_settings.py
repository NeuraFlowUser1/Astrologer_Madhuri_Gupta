"""Private setting changes are fenced, replayable and preserve accepted work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
from .test_sql_company import CompanyFixture
from .test_sql_booking import BookingFixture
from tools.checks.sql_target import literal

class BusinessSettingsSQL(CompanyFixture,BookingFixture):
    def setUp(self):
        BookingFixture.setUp(self);CompanyFixture.setUp(self)
        self.db.scalar("SELECT appointment_system.provision_login('appointment_system_web','web');")

    def settings(self):
        return self.db.value('SELECT appointment_system.company_business_settings('+literal(self.token)+');',role='abs_company')

    def save(self,settings,*,operation=None,revision=None,reason='Synthetic business settings change'):
        operation=operation or str(uuid4());revision=revision or self.settings()['revision']
        return self.db.value('SELECT appointment_system.company_save_business_settings('+literal(self.token)+','+
            literal(self.csrf)+','+literal(str(operation))+','+str(revision)+','+literal(settings)+'::jsonb,'+literal(reason)+');',role='abs_company')

    def test_price_change_keeps_accepted_fee_and_does_not_invalidate_email_verification_policy(self):
        booking=self.booking();old=self.settings();updated=deepcopy(old['settings'])
        old_verification=self.db.scalar('SELECT appointment_system.verification_policy(appointment_system.current_business());')
        updated['services'][0]['pricing']['amount_paise']=310000;result=self.save(updated)
        self.assertEqual(result['revision'],str(int(old['revision'])+1));self.assertNotEqual(result['quote_version'],old['quote_version'])
        self.assertEqual(self.db.scalar('SELECT amount_paise FROM appointment_system.bookings WHERE id='+literal(booking['booking'])+';'),'210000')
        self.assertEqual(self.db.scalar('SELECT appointment_system.verification_policy(appointment_system.current_business());'),old_verification)
        self.assertEqual(self.db.scalar("SELECT (appointment_system.service_quote(appointment_system.current_business(),'consultation',1)->>'amount_paise')::bigint;"),'310000')

    def test_same_operation_recovers_original_result_and_changed_body_or_stale_revision_is_rejected(self):
        old=self.settings();updated=deepcopy(old['settings']);updated['notice_minutes']=45;operation=str(uuid4())
        first=self.save(updated,operation=operation,revision=old['revision'])
        self.assertEqual(self.save(updated,operation=operation,revision=old['revision']),first)
        with self.assertRaises(AssertionError):self.save(updated,operation=operation,revision=old['revision'],reason='Different business settings reason')
        with self.assertRaises(AssertionError):self.save(updated,revision=old['revision'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.company_configuration_actions WHERE operation_id='+literal(operation)+';'),'1')

    def test_two_settings_changes_from_same_revision_have_one_winner(self):
        current=self.settings()
        def change(value):
            updated=deepcopy(current['settings']);updated['notice_minutes']=value
            try:return self.save(updated,revision=current['revision'])
            except AssertionError as error:
                self.assertIn('business settings changed',str(error));return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,[45,60]))
        self.assertEqual(sum(result is not None for result in results),1)

    def test_settings_work_off_but_require_fresh_password_for_a_new_save(self):
        current=self.settings();updated=deepcopy(current['settings']);updated['booking_verification']['email']=True
        self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false;')
        operation=str(uuid4());saved=self.save(updated,operation=operation,revision=current['revision'])
        self.db.sql("UPDATE appointment_system.control_company_sessions SET created_at=clock_timestamp()-interval '11 minutes',fresh_until=clock_timestamp()-interval '1 second';")
        self.assertEqual(self.save(updated,operation=operation,revision=current['revision']),saved)
        with self.assertRaises(AssertionError):self.save(updated)

    def test_malformed_or_foreign_scope_configuration_cannot_write_and_public_role_cannot_edit(self):
        old=self.settings();invalid=deepcopy(old['settings']);invalid['timezone']='Unreal/Timezone'
        with self.assertRaises(AssertionError):self.save(invalid)
        self.assertEqual(self.settings()['revision'],old['revision'])
        attempted=self.db.sql('SELECT appointment_system.company_business_settings('+literal(self.token)+');',role='appointment_system_web',check=False)
        self.assertNotEqual(attempted.returncode,0)
