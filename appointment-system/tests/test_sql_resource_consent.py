"""Callbacks cannot install grants or grant company authority."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from appointment_system.google_oauth import RESOURCE_SCOPES
from tools.checks.sql_target import literal
from .test_sql_company import CompanyFixture
from .sql_store import IsolatedStore
from .test_google_resources import WEB

class ConsentSQL(CompanyFixture):
    def test_workbook_operations_require_fresh_original_company_parent_and_exact_resource(self):
        query='SELECT appointment_system.authorize_resource_operation(%s,%s,%s,%s)'
        self.assertTrue(self.company._call(query,(self.token,self.csrf,WEB,'agency_sheet')))
        for role,parent,csrf,resource in ((self.staff,self.staff_token,self.csrf,'client_sheet'),
                (self.company,uuid4().hex*2,self.csrf,'client_sheet'),
                (self.company,self.token,uuid4().hex*2,'agency_sheet'),
                (self.company,self.token,self.csrf,'calendar')):
            with self.assertRaises(AssertionError):role._call(query,(parent,csrf,WEB,resource))
        self.db.sql('UPDATE appointment_system.control_company_sessions SET fresh_until=clock_timestamp()-interval \'1 second\' WHERE token_hash='+literal(self.token)+';')
        with self.assertRaises(AssertionError):self.company._call(query,(self.token,self.csrf,WEB,'agency_sheet'))

    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_resources,appointment_system.google_resource_grants CASCADE;')
        for role,purpose in [('abs_staff','staff'),('appointment_system_web','web')]:
            self.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')
        metadata={name:dict(owner_email='agency@example.test' if name=='agency_sheet' else 'practice@example.test',
          active_client=WEB,retained_clients=[WEB]) for name in RESOURCE_SCOPES}
        self.assertEqual(self.db.scalar('SELECT appointment_system.configure_google_resources('+literal(metadata)+'::jsonb);'),'t')
        self.company=IsolatedStore(self.db,'abs_company');self.staff=IsolatedStore(self.db,'abs_staff')
        self.db.sql("INSERT INTO appointment_system.studio_identities(role,subject) VALUES('client','123456789') ON CONFLICT(role) DO UPDATE SET subject=excluded.subject;")
        self.staff_token=uuid4().hex*2
        self.db.sql('INSERT INTO appointment_system.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES ('+
          literal(self.staff_token)+",'client','123456789',"+literal(WEB)+','+literal(self.declared['origin'])+",clock_timestamp()+interval '1 hour');")

    def start(self,resource='calendar',authority='company',store=None,parent=None):
        attempt=dict(id=str(uuid4()),grant=str(uuid4()),state=uuid4().hex*2,browser=uuid4().hex*2,resource=resource,authority=authority)
        result=(store or (self.company if authority=='company' else self.staff))._call(
          'SELECT appointment_system.start_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
          (authority,parent or (self.token if authority=='company' else self.staff_token),self.csrf if authority=='company' else None,
           WEB,attempt['id'],resource,attempt['state'],attempt['browser'],'encrypted-attempt'*20,attempt['grant'],WEB))
        self.assertIsNotNone(result);return attempt

    def consume(self,a,store=None,browser=None):
        return (store or (self.company if a['authority']=='company' else self.staff))._call(
          'SELECT appointment_system.consume_resource_consent(%s,%s,%s)',(a['authority'],a['state'],browser or a['browser']))

    def stage(self,a,owner=None,scopes=None):
        from psycopg.types.json import Jsonb
        return (self.company if a['authority']=='company' else self.staff)._call(
          'SELECT appointment_system.stage_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',
          (a['authority'],a['id'],a['state'],'987654321' if a['resource']=='agency_sheet' else '123456789',
           owner or ('agency@example.test' if a['resource']=='agency_sheet' else 'practice@example.test'),
           'encrypted-grant'*20,Jsonb(scopes or sorted(RESOURCE_SCOPES[a['resource']])),None))

    def finish_consent(self,a,parent=None,csrf=None):
        return (self.company if a['authority']=='company' else self.staff)._call(
          'SELECT appointment_system.finish_resource_consent(%s,%s,%s,%s)',
          (a['authority'],parent or (self.token if a['authority']=='company' else self.staff_token),
           csrf or (self.csrf if a['authority']=='company' else None),a['id']))

    def test_actual_restore_barrier_invalidates_every_unfinished_resource_consent_and_preserves_completed_grants(self):
        self.db.sql('TRUNCATE appointment_system.control_restore_operations CASCADE;')
        # Restore deliberately closes company/staff access until recovery is
        # completed. Always remove this synthetic barrier, including on a
        # failed assertion, so a failed test cannot poison later fixtures.
        self.addCleanup(self.db.sql,'TRUNCATE appointment_system.control_restore_operations CASCADE;')
        self.db.scalar("SELECT appointment_system.provision_login('abs_maintenance','maintenance');")
        unfinished=[]
        for authority in ('company','staff'):
            for stage in ('started','consumed','staged'):
                attempt=self.start(authority=authority)
                if stage!='started':self.assertIsNotNone(self.consume(attempt))
                if stage=='staged':self.assertTrue(self.stage(attempt))
                unfinished.append(attempt)
        completed=self.start(resource='client_sheet')
        self.consume(completed);self.assertTrue(self.stage(completed))
        self.assertEqual(self.finish_consent(completed)['code'],'saved')
        before=self.db.value('SELECT to_jsonb(a) FROM appointment_system.google_resource_attempts a WHERE id='+literal(completed['id'])+';')
        grants=self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;')
        external=self.db.value('SELECT appointment_system.control_snapshot();')
        operation=str(uuid4())
        query='SELECT appointment_system.control_restore_barrier('+literal(operation)+','+literal(external)+'::jsonb);'
        recovered=self.db.value(query,role='abs_maintenance')['snapshot']
        self.assertFalse(recovered['enabled'])
        self.assertNotEqual(recovered['restore_generation'],external['restore_generation'])
        self.assertEqual(int(recovered['generation_sequence']),int(external['generation_sequence'])+1)
        for attempt in unfinished:
            row=self.db.value('SELECT jsonb_build_object(\'result\',result,\'consumed\',consumed_at IS NOT NULL,\'finished\',finished_at IS NOT NULL,\'grant_removed\',encrypted_grant IS NULL) FROM appointment_system.google_resource_attempts WHERE id='+literal(attempt['id'])+';')
            self.assertEqual(row,dict(result='changed',consumed=True,finished=True,grant_removed=True))
        self.assertEqual(self.db.value('SELECT to_jsonb(a) FROM appointment_system.google_resource_attempts a WHERE id='+literal(completed['id'])+';'),before)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),grants)
        self.assertTrue(self.db.value(query,role='abs_maintenance')['replayed'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.control_restore_operations;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.control_company_sessions WHERE revoked_at IS NULL;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.studio_sessions WHERE revoked_at IS NULL;'),'0')
        for attempt in unfinished:
            with self.assertRaisesRegex(AssertionError,'isolated recovery completion required'):
                self.finish_consent(attempt)

    def test_callback_only_stages_and_same_parent_finishes_exactly_once(self):
        a=self.start();self.assertIsNotNone(self.consume(a));self.assertTrue(self.stage(a))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.control_company_sessions WHERE revoked_at IS NULL;'),'1')
        self.assertEqual(self.finish_consent(a,parent=uuid4().hex*2)['code'],'consent_unavailable')
        self.assertEqual(self.finish_consent(a)['code'],'saved');self.assertEqual(self.finish_consent(a)['code'],'saved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'1')

    def test_pending_historical_permission_pins_subject_until_owner_consent_and_parent_confirmation(self):
        from psycopg.types.json import Jsonb
        from tools.conversion.grants import GrantTransfer
        from appointment_system.google_resources import Resources,ResourceCipher
        from appointment_system.settings import Installation
        from .fixtures import installation
        from .test_keys import ring
        from .test_google_resources import spec
        from . import test_conversion_grants as prior
        fixture=prior.HistoricalGoogleGrants();fixture.setUp()
        transfer=GrantTransfer(Installation.parse(installation()),Resources(spec(),ResourceCipher(ring(purpose='google-resource-grant'))),
                              calendar_client=WEB,calendar_reauthorization=True)
        record=transfer.calendar(fixture.calendar(bare=True))['google_resource_grants'][0]
        self.db.sql('INSERT INTO appointment_system.google_resource_grants SELECT * FROM jsonb_populate_record(NULL::appointment_system.google_resource_grants,'+
                    literal(record)+'::jsonb);')
        self.db.sql('UPDATE appointment_system.google_resources SET grant_id='+literal(record['id'])+",revision=1 WHERE resource='calendar';")
        self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false;')
        self.assertEqual(self.company.claim_google_resource_refresh('calendar'),{'code':'google_reconnect_required'})
        a=self.start();saved=self.consume(a)
        self.assertEqual(saved['previous_subject'],record['subject'])
        wrong=self.company._call('SELECT appointment_system.stage_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',
            ('company',a['id'],a['state'],'different-google-subject',record['owner_email'],'encrypted-grant'*20,
             Jsonb(sorted(RESOURCE_SCOPES['calendar'])),None))
        self.assertFalse(wrong)
        self.assertEqual(self.db.scalar("SELECT grant_id FROM appointment_system.google_resources WHERE resource='calendar';"),record['id'])
        b=self.start();self.consume(b);self.assertTrue(self.stage(b))
        # Google's return alone does not install or activate anything.
        self.assertEqual(self.company.claim_google_resource_refresh('calendar'),{'code':'google_reconnect_required'})
        self.assertEqual(self.finish_consent(b)['code'],'saved')
        self.assertEqual(self.db.scalar("SELECT grant_id FROM appointment_system.google_resources WHERE resource='calendar';"),b['grant'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'2')
        self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'f')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.meeting_events;'),'0')

    def test_callback_is_browser_bound_consumed_once_and_never_replayed_under_race(self):
        a=self.start();self.assertIsNone(self.consume(a,browser=uuid4().hex*2))
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:self.consume(a),range(3)))
        self.assertEqual(sum(value is not None for value in results),1)
        self.assertFalse(self.stage(a,owner='foreign@example.test'));self.assertEqual(self.finish_consent(a)['code'],'consent_changed')

    def test_credential_change_between_return_and_finish_does_not_install(self):
        a=self.start();self.consume(a);self.stage(a)
        self.db.scalar("SELECT appointment_system.provision_company_password('company.owner',"+literal(self.hash)+');')
        with self.assertRaisesRegex(AssertionError,'company session rejected'):self.finish_consent(a)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')

    def test_restore_expiry_or_newer_resource_connection_invalidates_the_pending_result(self):
        for kind in ('restore','expired','connection'):
            self.setUp();a=self.start();self.consume(a);self.stage(a)
            if kind=='restore':self.db.sql('UPDATE appointment_system.control_product_state SET restore_generation='+literal(str(uuid4()))+';')
            elif kind=='expired':self.db.sql("UPDATE appointment_system.google_resource_attempts SET expires_at=clock_timestamp()-interval '1 second';")
            else:self.db.sql("UPDATE appointment_system.google_resources SET revision=revision+1 WHERE resource='calendar';")
            if kind=='restore':
                with self.assertRaisesRegex(AssertionError,'company session rejected'):self.finish_consent(a)
            else:self.assertEqual(self.finish_consent(a)['code'],'consent_changed')
            self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')

    def test_staff_can_connect_own_resources_and_never_agency_or_company_authority(self):
        a=self.start('client_sheet','staff');self.consume(a);self.assertTrue(self.stage(a));self.assertEqual(self.finish_consent(a)['code'],'saved')
        with self.assertRaisesRegex(AssertionError,'resource authority denied'):self.start('agency_sheet','staff')
        with self.assertRaisesRegex(AssertionError,'registered caller required'):self.start(store=self.staff)
        self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false;')
        with self.assertRaises(AssertionError):self.start('calendar','staff')

    def test_public_role_cannot_consume_read_or_install_pending_grants(self):
        a=self.start()
        for query in ['SELECT count(*) FROM appointment_system.google_resource_attempts;',
          'SELECT appointment_system.consume_resource_consent(\'company\','+literal(a['state'])+','+literal(a['browser'])+');']:
            with self.assertRaisesRegex(AssertionError,'permission denied'):self.db.scalar(query,role='appointment_system_web')

    def paid_reference(self):
        from .test_sql_booking import BookingFixture
        fixture=BookingFixture();fixture.db=self.db;fixture.setUp()
        booking=fixture.booking();self.assertEqual(fixture.start_order(booking),'t')
        self.assertEqual(fixture.record_order(booking),'ready');self.assertEqual(fixture.capture(booking),'confirmed')
        return booking['request']

    def owner_link(self,reference=None,operation=None):
        link=dict(id=str(operation or uuid4()),access=uuid4().hex*2,body=uuid4().hex*2)
        link['saved']=self.company._call('SELECT appointment_system.issue_resource_owner_link(%s,%s,%s,%s,%s,%s,%s,%s)',
            (self.token,self.csrf,link['id'],'calendar',reference or self.paid_reference(),'Synthetic connection repair',link['access'],link['body']))
        return link

    def test_owner_link_requires_paid_obligation_and_never_grants_company_session(self):
        self.assertIsNone(self.owner_link(reference=str(uuid4()))['saved'])
        link=self.owner_link();self.assertIsNotNone(link['saved'])
        context=self.company._call('SELECT appointment_system.owner_resource_link_context(%s,%s)',(link['id'],link['access']))
        self.assertEqual(context['owner_email'],'practice@example.test')
        self.assertIsNone(self.company._call('SELECT appointment_system.owner_resource_link_context(%s,%s)',(link['id'],uuid4().hex*2)))
        a=dict(id=str(uuid4()),state=uuid4().hex*2,browser=uuid4().hex*2,resource='calendar',authority='company')
        values=(link['id'],link['access'],a['id'],a['state'],a['browser'],'encrypted-attempt'*20,str(uuid4()),WEB)
        result=self.company._call('SELECT appointment_system.start_owner_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',values)
        self.assertIsNotNone(result)
        self.assertIsNone(self.company._call('SELECT appointment_system.start_owner_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',values))
        self.assertTrue(self.consume(a)['delegated']);self.assertTrue(self.stage(a))
        pending=self.company._call('SELECT appointment_system.pending_resource_consents(%s)',(self.token,))
        self.assertEqual([item['attempt_id'] for item in pending],[a['id']])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')
        self.assertEqual(self.finish_consent(a,parent=uuid4().hex*2)['code'],'consent_unavailable')
        self.assertEqual(self.finish_consent(a)['code'],'saved')

    def test_owner_link_expires_and_closed_obligation_cannot_install_staged_permission(self):
        link=self.owner_link();self.db.sql("UPDATE appointment_system.google_resource_owner_links SET expires_at=clock_timestamp()-interval '1 second';")
        self.assertIsNone(self.company._call('SELECT appointment_system.owner_resource_link_context(%s,%s)',(link['id'],link['access'])))
        link=self.owner_link()
        a=dict(id=str(uuid4()),state=uuid4().hex*2,browser=uuid4().hex*2,resource='calendar',authority='company')
        self.company._call('SELECT appointment_system.start_owner_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',
          (link['id'],link['access'],a['id'],a['state'],a['browser'],'encrypted-attempt'*20,str(uuid4()),WEB))
        self.consume(a);self.stage(a)
        self.db.sql("UPDATE appointment_system.delivery_jobs SET state='completed' WHERE recipient_role='calendar';")
        self.assertEqual(self.finish_consent(a)['code'],'consent_changed')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')
