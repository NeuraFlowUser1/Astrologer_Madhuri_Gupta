"""The same read-only preview and lost-response proofs run on both native layouts."""
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
from appointment_system.serialization import canonical
from tools.conversion.handover import Handover
from tools.conversion.source import ConversionError
from tools.handover import run
from .handover_configuration import protected
from .test_application import protection


class HandoverOperations:
    def test_operating_commands_use_real_configuration_and_native_saved_checkpoints(self):
        project='003' if self.handover.writer_roles==('astro_booking_app',) else '004'
        selected,environment=protected(project)
        profile=SimpleNamespace(installation=self.bound.installation,initial_business=self.bound.business)
        def command(action,**kwargs):
            return run(action,self.connection,profile,'a'*64,selected,environment,**kwargs)
        baseline=command('preview')
        self.assertEqual(baseline['target_counts']['bookings'],1)
        self.assertEqual(command('diff',baseline=baseline)['source_changes'],[])
        prepared=command('prepare')['checkpoint'];identifier=prepared['id']
        self.assertEqual(prepared['phase'],'prepared')
        # Replace only the network connector; readiness and all mutations use
        # the real restricted native journal login and actual SQL functions.
        environment['BOOKING_JOURNAL_DATABASE_URL']='synthetic-local-connector'
        environment['BOOKING_JOURNAL_KEYS']=canonical(protection('provider-journal',12))
        with patch('appointment_system.provider_ingress.JournalStore',return_value=self.journal):
            self.assertEqual(command('journal-only',identifier=identifier)['checkpoint']['phase'],'journal_only')
        imported=command('convert',identifier=identifier)['checkpoint']
        self.assertEqual(imported['phase'],'imported')
        self.assertEqual(command('checkpoint')['checkpoint'],imported)
        environment.clear()
        self.assertEqual(command('checkpoint',identifier=identifier)['checkpoint'],imported)
        with self.assertRaisesRegex(ConversionError,'conversion_result_mismatch'):
            command('complete',identifier=identifier,expected_digest='f'*64)
        complete=command('complete',identifier=identifier,expected_digest=imported['target_digest'])['checkpoint']
        self.assertEqual(complete['phase'],'complete')
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],1)

    def test_preview_preserves_source_and_permissions_then_import_reads_final_delta(self):
        preview=self.handover.preview()
        self.assertEqual(preview['phase'],'preview')
        self.assertIs(preview['records_changed'],False)
        self.assertIs(preview['writers_fenced'],False)
        self.assertEqual(preview['target_counts']['bookings'],1)
        self.assertNotIn('fixture@example.test',str(preview))
        self.assertNotIn('Synthetic Customer',str(preview))
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],0)
        self.assertIsNone(self.handover.checkpoint())
        schema='public' if preview['layout']=='legacy-003-16' else 'sarsa_booking'
        # Only fixture schema identifiers are used; customer values remain bound.
        self.connection.execute('UPDATE '+schema+'.bookings SET full_name=%s WHERE id=%s',
                                ('Synthetic change after preview',self.book))
        from tools.conversion.difference import compare
        compared=compare(preview,self.handover.preview())
        self.assertEqual(compared['source_changes'],[dict(table=schema+'.bookings',previous_count=1,current_count=1,contents_changed=True)])
        identifier=self.start();actual=self.handover.convert(identifier)
        self.assertNotEqual(actual['source_digest'],preview['source_digest'])
        self.assertEqual(self.connection.execute('SELECT full_name FROM appointment_system.bookings WHERE id=%s',
                                                (self.book,)).fetchone()[0],'Synthetic change after preview')
        self.handover.complete(identifier,actual['target_digest'])

    def test_checkpoint_recovers_each_committed_phase_without_repeating_commands(self):
        identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
        saved=self.handover.checkpoint()
        self.assertEqual(saved['id'],identifier);self.assertEqual(saved['phase'],'prepared')
        self.handover.enter_journal_only(identifier,self.journal)
        self.assertEqual(self.handover.checkpoint(identifier)['phase'],'journal_only')
        actual=self.handover.convert(identifier)
        saved=self.handover.checkpoint(identifier)
        self.assertEqual(saved['phase'],'imported');self.assertEqual(saved['target_digest'],actual['target_digest'])
        self.assertEqual(saved,self.handover.checkpoint())
        self.handover.complete(identifier,saved['target_digest'])
        saved=self.handover.checkpoint(identifier)
        self.assertEqual(saved['phase'],'complete')
        self.assertEqual(self.connection.execute('SELECT count(*) FROM appointment_system.bookings').fetchone()[0],1)
        self.assertNotIn('fixture@example.test',str(saved));self.assertNotIn('Synthetic Customer',str(saved))
        with self.assertRaisesRegex(ConversionError,'conversion_phase_conflict'):
            self.handover.convert(identifier)
        self.assertEqual(self.handover.checkpoint(identifier),saved)

    def test_checkpoint_rejects_unknown_identity_release_and_writer_set(self):
        identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
        for value in ('not-a-uuid','00000000-0000-0000-0000-000000000000'):
            with self.subTest(identifier=value),self.assertRaisesRegex(ConversionError,'conversion_checkpoint_invalid'):
                self.handover.checkpoint(value)
        with self.assertRaisesRegex(ConversionError,'conversion_checkpoint_unavailable'):
            self.handover.checkpoint(str(uuid4()))
        for digest,writers in (('b'*64,self.handover.writer_roles),('a'*64,('unrelated_writer',))):
            with self.subTest(digest=digest,writers=writers),self.assertRaisesRegex(ConversionError,'conversion_authority_mismatch'):
                Handover(self.connection,self.bound,digest,writers).checkpoint(identifier)
        self.handover.abort_before_import(identifier)
        self.assertEqual(self.handover.checkpoint(identifier)['phase'],'aborted')

    def test_explicit_wrong_source_layout_cannot_preview_prepare_or_read_a_checkpoint(self):
        actual=self.handover.preview()['layout']
        wrong='legacy-004-31' if actual=='legacy-003-16' else 'legacy-003-16'
        handover=Handover(self.connection,self.bound,'a'*64,self.handover.writer_roles,expected_layout=wrong)
        with self.assertRaisesRegex(ConversionError,'conversion_source_layout_mismatch'):handover.preview()
        with self.assertRaisesRegex(ConversionError,'conversion_source_layout_mismatch'):
            handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
        self.assertIsNone(self.handover.checkpoint())
        identifier=self.handover.prepare([{'provider':'razorpay','account_id':'merchant123','mode':'test'}])
        with self.assertRaisesRegex(ConversionError,'conversion_source_layout_mismatch'):handover.checkpoint(identifier)
