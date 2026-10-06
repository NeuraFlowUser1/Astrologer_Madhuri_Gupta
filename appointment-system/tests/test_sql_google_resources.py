"""Actual SQL resource bindings, least privilege and renewal races."""
from copy import deepcopy
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from appointment_system.google_oauth import RESOURCE_SCOPES,scopes_for
from tools.checks.sql_target import literal
from .test_sql_booking import BookingFixture
from .sql_store import IsolatedStore
from .test_google_resources import WEB,DESKTOP

class ResourceSQL(BookingFixture):
    def setUp(self):
        super().setUp()
        self.db.sql('TRUNCATE appointment_system.google_workbooks,appointment_system.google_resources,appointment_system.google_resource_grants CASCADE;')
        for role,purpose in [('abs_worker','worker'),('abs_staff','staff'),('abs_company','company'),('abs_backup','backup')]:
            self.db.scalar('SELECT appointment_system.provision_login('+literal(role)+','+literal(purpose)+');')
        self.metadata={name:dict(owner_email='agency@example.test' if name=='agency_sheet' else 'practice@example.test',
          active_client=WEB,retained_clients=[WEB,DESKTOP]) for name in RESOURCE_SCOPES}
        self.assertEqual(self.configure(),True)
        self.worker=IsolatedStore(self.db,'abs_worker');self.staff=IsolatedStore(self.db,'abs_staff')

    def configure(self,spec=None):
        return self.db.scalar('SELECT appointment_system.configure_google_resources('+literal(spec or self.metadata)+'::jsonb);')=='t'

    def install(self,resource='calendar',*,resources=None,client=WEB,revision=0,subject=None,scopes=None,owner=None):
        identifier=str(uuid4());group=resources or [resource]
        email=owner or ('agency@example.test' if resource=='agency_sheet' else 'practice@example.test')
        scope=scopes or sorted(scopes_for('client') if len(group)==2 else RESOURCE_SCOPES[resource])
        result=self.db.scalar('SELECT appointment_system.install_resource_grant('+','.join(literal(x) for x in (
            resource,revision,identifier,subject or ('987654321' if resource=='agency_sheet' else '123456789'),email,client))+
            ',ARRAY['+','.join(literal(x) for x in group)+']::text[],'+literal(scope)+'::jsonb,'+literal('ciphertext'*20)+',NULL,\'v1\');')
        return identifier,result=='t'

    def finish(self,saved,**changes):
        return self.worker.finish_google_resource_refresh(saved,changes.get('encrypted','replacement'*20),None,
            changes.get('scopes',saved['scopes']),changes.get('error'))

    def test_shared_grant_serializes_calendar_and_client_sheet_renewal(self):
        identifier,ok=self.install(resources=['calendar','client_sheet']);self.assertTrue(ok)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.worker.claim_google_resource_refresh,['calendar','client_sheet']))
        selected=[value for value in results if value is not None];self.assertEqual(len(selected),1)
        saved=selected[0];self.assertEqual(saved['grant_id'],identifier);self.assertTrue(self.finish(saved))
        second='client_sheet' if saved['resource']=='calendar' else 'calendar'
        renewed=self.worker.claim_google_resource_refresh(second);self.assertEqual(renewed['revision'],2)

    def test_desktop_workbook_client_is_preserved_instead_of_replaced_with_website_client(self):
        _,ok=self.install('client_sheet',client=DESKTOP);self.assertTrue(ok)
        saved=self.worker.claim_google_resource_refresh('client_sheet');self.assertEqual(saved['client_id'],DESKTOP)
        changed=deepcopy(self.metadata);changed['client_sheet']['retained_clients']=[WEB]
        with self.assertRaisesRegex(AssertionError,'must be retained'):self.configure(changed)
        self.assertEqual(self.db.scalar('SELECT client_id FROM appointment_system.google_sheet_connections;'),DESKTOP)

    def workbook(self,client):
        from uuid import UUID
        saved=self.worker.claim_google_workbook('client',client)
        self.assertEqual(saved['action'],'create')
        self.assertTrue(self.worker.begin_google_workbook_create('client',UUID(saved['lease']),UUID(saved['intent'])))
        self.assertTrue(self.worker.finish_google_workbook('client',UUID(saved['lease']),'owned-'+str(uuid4())))
        return saved

    def test_resource_permission_never_creates_or_replaces_staff_identity(self):
        agency_before=self.db.scalar("SELECT coalesce(max(subject),'') FROM appointment_system.studio_identities WHERE role='agency';")
        self.db.sql("INSERT INTO appointment_system.studio_identities(role,subject) VALUES('client','website-subject') ON CONFLICT(role) DO UPDATE SET subject=excluded.subject;")
        self.assertTrue(self.install('client_sheet',client=DESKTOP,subject='drive-permission-id')[1])
        self.assertEqual(self.db.scalar("SELECT subject FROM appointment_system.studio_identities WHERE role='client';"),'website-subject')
        self.assertTrue(self.install('agency_sheet')[1])
        self.assertEqual(self.db.scalar("SELECT coalesce(max(subject),'') FROM appointment_system.studio_identities WHERE role='agency';"),agency_before)
        self.assertIsNotNone(self.worker.claim_google_workbook('agency',WEB))

    def test_new_client_rotates_workbook_and_old_volume_keeps_exact_old_grant(self):
        old,ok=self.install('client_sheet',client=DESKTOP,subject='drive-permission-id');self.assertTrue(ok)
        first=self.workbook(DESKTOP)
        new,ok=self.install('client_sheet',revision=1,subject='website-subject');self.assertTrue(ok)
        next_volume=self.worker.claim_google_workbook('client',WEB)
        self.assertEqual(next_volume['volume_number'],first['volume_number']+1)
        self.assertEqual(next_volume['subject'],'website-subject')
        pinned=self.worker.claim_google_resource_refresh('client_sheet',old)
        self.assertEqual(pinned['grant_id'],old);self.assertEqual(pinned['client_id'],DESKTOP)
        self.assertTrue(self.finish(pinned));self.assertIsNone(self.worker.claim_google_resource_refresh('calendar',old))
        changed=deepcopy(self.metadata);changed['client_sheet']['retained_clients']=[WEB]
        with self.assertRaisesRegex(AssertionError,'must be retained'):self.configure(changed)
        unpinned,_=self.install('client_sheet',revision=2,subject='another-valid-subject')
        current,_=self.install('client_sheet',revision=3)
        self.assertIsNone(self.worker.claim_google_resource_refresh('client_sheet',unpinned))
        self.assertIsNotNone(self.worker.claim_google_resource_refresh('client_sheet',current))

    def test_unresolved_creation_is_not_replaced_and_same_client_reconsent_can_renew_old_volume(self):
        old,_=self.install('client_sheet');first=self.worker.claim_google_workbook('client',WEB)
        self.install('client_sheet',client=DESKTOP,revision=1,subject='drive-permission-id')
        saved=self.worker.claim_google_workbook('client',DESKTOP)
        self.assertEqual(saved['action'],'review');self.assertEqual(saved['code'],'google_workbook_client_changed_unresolved')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_workbook_volumes;'),'1')
        current,_=self.install('client_sheet',revision=2)
        renewed=self.worker.claim_google_resource_refresh('client_sheet',old)
        self.assertEqual(renewed['grant_id'],current)

    def test_wrong_owner_unknown_client_and_shared_scope_escalation_do_not_save(self):
        for options in [dict(owner='agency@example.test'),dict(client='111-foreign.apps.googleusercontent.com'),
                        dict(resources=['calendar','client_sheet'],scopes=sorted(RESOURCE_SCOPES['calendar']))]:
            self.assertFalse(self.install(**options)[1])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.google_resource_grants;'),'0')

    def test_only_matching_lease_connection_revision_and_existing_permissions_can_finish(self):
        self.install();saved=self.worker.claim_google_resource_refresh('calendar')
        for field,value in [('lease',str(uuid4())),('resource_revision',2),('revision',2)]:
            changed=saved|{field:value};self.assertFalse(self.finish(changed))
        self.assertFalse(self.finish(saved,scopes=sorted(scopes_for('client'))))
        self.assertTrue(self.finish(saved));self.assertFalse(self.finish(saved))

    def test_reconnect_error_retains_ciphertext_and_is_reported_without_repeated_provider_calls(self):
        self.install();saved=self.worker.claim_google_resource_refresh('calendar');self.assertTrue(self.finish(saved,error='google_reconnect_required'))
        self.assertEqual(self.worker.claim_google_resource_refresh('calendar'),{'code':'google_reconnect_required'})
        self.assertEqual(self.db.scalar('SELECT encrypted_grant FROM appointment_system.google_resource_grants;'),'ciphertext'*20)
        self.assertIsNone(self.db.value('SELECT refresh_lease FROM appointment_system.google_resource_grants;'))

    def test_public_role_cannot_read_mutate_or_renew_and_staff_cannot_renew_agency(self):
        self.install('agency_sheet')
        for query in ['SELECT count(*) FROM appointment_system.google_resource_grants;',
                      "SELECT appointment_system.claim_google_resource_refresh('calendar');",
                      'SELECT appointment_system.configure_google_resources('+literal(self.metadata)+'::jsonb);']:
            with self.assertRaisesRegex(AssertionError,'permission denied'):self.db.value(query,role='appointment_system_web')
        with self.assertRaisesRegex(AssertionError,'resource access denied'):self.staff.claim_google_resource_refresh('agency_sheet')
        self.assertIsNotNone(self.worker.claim_google_resource_refresh('agency_sheet'))
