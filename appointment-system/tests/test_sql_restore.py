"""Real recovered-authority barrier; existing money and occupancy are preserved."""
from copy import deepcopy
from uuid import uuid4
from .test_sql_company import CompanyFixture
from .test_sql_booking import BookingFixture
from tools.checks.sql_target import literal

class RestoreSQL(CompanyFixture,BookingFixture):
    @classmethod
    def setUpClass(cls):
        BookingFixture.setUpClass.__func__(cls);CompanyFixture.setUpClass.__func__(cls)

    def setUp(self):
        self.db.sql('TRUNCATE appointment_system.control_restore_operations CASCADE;')
        CompanyFixture.setUp(self);BookingFixture.setUp(self)
        self.db.scalar("SELECT appointment_system.provision_login('abs_maintenance','maintenance');")
        self.db.scalar("SELECT appointment_system.provision_login('abs_worker','worker');")
        self.operation=str(uuid4());self.external=self.db.value('SELECT appointment_system.control_snapshot();')

    def tearDown(self):
        # Only the declared disconnected proof target is reset between cases.
        self.db.sql('TRUNCATE appointment_system.control_restore_operations CASCADE;')

    def restore(self,external=None,operation=None,role='abs_maintenance'):
        return self.db.value('SELECT appointment_system.control_restore_barrier('+literal(operation or self.operation)+','+
                            literal(external or self.external)+'::jsonb);',role=role)

    def test_restore_disables_all_old_authority_but_retains_payment_booking_and_claim(self):
        b=self.booking();self.assertEqual(self.start_order(b),'t');self.assertEqual(self.record_order(b),'ready')
        self.assertEqual(self.capture(b),'confirmed')
        self.db.sql("UPDATE appointment_system.delivery_jobs SET state='processing',attempts=attempts+1,lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds' WHERE booking_id="+literal(b['booking'])+';')
        self.db.sql("INSERT INTO appointment_system.studio_identities(role,subject) VALUES('client','123456789') ON CONFLICT(role) DO UPDATE SET subject=excluded.subject;")
        staff_token=uuid4().hex*2
        self.db.sql('INSERT INTO appointment_system.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES ('+
            literal(staff_token)+",'client','123456789','synthetic-client',"+literal(self.declared['origin'])+",clock_timestamp()+interval '1 hour');")
        before=self.db.value('SELECT jsonb_build_object(\'bookings\',(SELECT count(*) FROM appointment_system.bookings),\'payments\',(SELECT count(*) FROM appointment_system.accepted_payments),\'claims\',(SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL));')
        result=self.restore();state=result['snapshot']
        self.assertFalse(state['enabled']);self.assertEqual(state['generation_sequence'],str(int(self.external['generation_sequence'])+1))
        self.assertNotEqual(state['restore_generation'],self.external['restore_generation']);self.assertNotEqual(state['activation_epoch'],self.external['activation_epoch'])
        self.assertEqual(before,self.db.value('SELECT jsonb_build_object(\'bookings\',(SELECT count(*) FROM appointment_system.bookings),\'payments\',(SELECT count(*) FROM appointment_system.accepted_payments),\'claims\',(SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL));'))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.control_company_sessions WHERE revoked_at IS NULL;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.studio_sessions WHERE revoked_at IS NULL;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.checkout_contexts WHERE expires_at>clock_timestamp();'),'0')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE state='processing' OR lease_token IS NOT NULL;"),'0')
        self.assertEqual(self.db.scalar('SELECT requested_enabled OR enabled FROM appointment_system.control_product_state WHERE singleton;'),'f')
        with self.assertRaises(AssertionError):self.db.sql('UPDATE appointment_system.control_product_state SET enabled=true WHERE singleton;')
        self.assertTrue(self.restore()['replayed'])

    def test_foreign_snapshot_stale_generation_and_serving_roles_cannot_restore(self):
        for mutation in ({'installation_id':str(uuid4())},{'project':'foreign-practice'},{'environment':'production'},
                         {'version':True},{'revision':1},{'unknown':'field'},
                         {'generation_sequence':str(2**63-1)},{'restore_generation':'00000000-0000-0000-0000-000000000000'}):
            external=deepcopy(self.external);external.update(mutation)
            with self.assertRaises(AssertionError):self.restore(external)
            self.assertEqual(self.db.value('SELECT appointment_system.control_snapshot();'),self.external)
        for role in ('appointment_system_web','abs_worker','abs_company'):
            with self.assertRaises(AssertionError):self.restore(role=role)
        self.restore()
        with self.assertRaises(AssertionError):self.restore(operation=str(uuid4()))
