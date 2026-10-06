"""Executable backup duties preserve authority separation and run identity.

The real command orchestration uses synthetic files and provider doubles.
Native archive/restore and real signature checks live in their separate suites.
"""
import base64
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch,MagicMock
import httpx
from appointment_system.backup.protocol import BackupError,canonical
from tools.automation import backup
from . import test_automation_boundaries as automation_tests
from .backup_fixtures import SCOPE


class BackupCommandBoundaries(unittest.TestCase):
    def setUp(self):
        self.base=automation_tests.AutomationBoundaries();self.base.setUp()
        self.config={'version':1,'installation_id':SCOPE.installation_id,'environment':'test',
            'owner_email':SCOPE.owner_email,'folder':'synthetic-folder','folder_name':'Synthetic backups',
            'repository':self.base.repo['full_name'],'cron':'37 1 * * *',
            'retention':{'mode':'recent','recent_copies':3,'daily_days':0,'monthly_months':0}}
        self.facts={'installation_id':SCOPE.installation_id,'project_id':SCOPE.project,'environment':'test','owners':{'client_email':SCOPE.owner_email}}

    def test_bounded_file_refuses_links_directories_missing_and_large_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'input.json';source.write_bytes(b'1234');link=root/'link';link.symlink_to(source)
            self.assertEqual(backup.bounded_file(source,4),b'1234')
            for path,size in ((root,4),(root/'missing',4),(source,3),(link,4)):
                with self.subTest(path=path),self.assertRaisesRegex(BackupError,'input_file_invalid'):backup.bounded_file(path,size)

    def test_public_backup_facts_are_owned_contained_and_strictly_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);package=root/'appointment-system';package.mkdir();settings=root/'appointment-settings';settings.mkdir()
            profile=settings/'project.json';profile.write_text('{}');saved=settings/'backup.json'
            with patch.object(backup,'ROOT',package),patch.object(backup,'load'),patch.object(backup,'installation',return_value=self.facts):
                saved.write_bytes(canonical(self.config));self.assertEqual(backup.public_settings(profile),self.config)
                for changed in ({'version':True},{'installation_id':'foreign'},{'owner_email':'foreign@example.test'},
                                {'environment':'production'},{'cron':'* * * * *'},{'folder_name':''},{'unexpected':1}):
                    saved.write_bytes(canonical(self.config|changed))
                    with self.subTest(changed=changed),self.assertRaises(BackupError):backup.public_settings(profile)
                for wrong in (root/'project.json',settings/'other.json'):
                    with self.assertRaisesRegex(BackupError,'profile_path_invalid'):backup.public_settings(wrong)

    def test_github_reads_are_bounded_and_identity_errors_do_not_echo_token_or_response(self):
        calls=[]
        def response(request):calls.append(request);return httpx.Response(200,json={'visibility':'public'})
        with httpx.Client(transport=httpx.MockTransport(response)) as client:
            self.assertEqual(backup.github_read('',self.config['repository'],'synthetic-private-token',client),{'visibility':'public'})
            self.assertEqual(calls[0].url.host,'api.github.com');self.assertEqual(calls[0].headers['authorization'],'Bearer synthetic-private-token')
            for token in (None,'','x'*8193):
                with self.assertRaisesRegex(BackupError,'identity_unavailable'):backup.github_read('',self.config['repository'],token,client)
            self.assertEqual(len(calls),1)
        for status,body in ((403,b'synthetic-private-token'),(200,b'x'*65537),(200,b'{"a":1,"a":2}')):
            with httpx.Client(transport=httpx.MockTransport(lambda _,status=status,body=body:httpx.Response(status,content=body))) as client:
                with self.assertRaises(BackupError) as error:backup.github_read('',self.config['repository'],'synthetic-private-token',client)
                self.assertNotIn('synthetic-private-token',str(error.exception))

    def test_source_selection_requires_exact_schedule_or_completed_export_identity(self):
        env=self.base.env|{'GITHUB_EVENT_NAME':'schedule','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40,'GITHUB_TOKEN':'synthetic'}
        event={'repository':self.base.repo,'schedule':self.config['cron']};arguments=SimpleNamespace(source_run='123',source_attempt='1',source_commit='a'*40)
        with patch.object(backup,'github_read',side_effect=[self.base.repo]) as read:
            self.assertEqual(backup.checked_source(env,event,self.config,'export',arguments),('123','1','a'*40));self.assertEqual(read.call_count,1)
        for changed,event_change,mode in (({'GITHUB_EVENT_NAME':'push'}, {},'export'),({}, {'schedule':'* * * * *'},'export'),({}, {},'validate'),({'GITHUB_EVENT_NAME':'workflow_dispatch'},{'inputs':{'source_run':'124'}},'validate')):
            with patch.object(backup,'github_read') as read,self.assertRaises(BackupError):backup.checked_source(env|changed,event|event_change,self.config,mode,arguments)
            read.assert_not_called()
        for event_name,extra in (('workflow_run',{'workflow_run':{'id':123}}),('workflow_dispatch',{'inputs':{'source_run':'123'}})):
            with patch.object(backup,'github_read',side_effect=[self.base.repo,self.base.run]):
                self.assertEqual(backup.checked_source(env|{'GITHUB_EVENT_NAME':event_name},event|extra,self.config,'validate',arguments),('123','1','a'*40))
        with patch.object(backup,'github_read',side_effect=[self.base.repo,self.base.run|{'run_attempt':2}]),self.assertRaisesRegex(BackupError,'identity_mismatch'):
            backup.checked_source(env|{'GITHUB_EVENT_NAME':'workflow_run'},event|{'workflow_run':{'id':123}},self.config,'validate',arguments)

    def command(self,mode,root,*,failure=False,output=True,proof=None):
        source=self.base.stage(mode)|{'GITHUB_EVENT_PATH':str(root/'event.json'),'GITHUB_SHA':'b'*40}
        source['BOOKING_PROFILE']=str(root/'appointment-settings/project.json')
        (root/'event.json').write_text('{}');(root/'database').mkdir(exist_ok=True);(root/'database/relations.json').write_text('[]')
        source['BOOKING_BACKUP_DRIVE_READER' if mode=='validate' else 'BOOKING_BACKUP_DRIVE_WRITER']='{}'
        if output:source['GITHUB_OUTPUT']=str(root/'result')
        signed={'payload':{'synthetic':True},'signature':'synthetic'}
        if mode=='retain':source['BOOKING_RESTORE_PROOF']=proof if proof is not None else base64.b64encode(canonical(signed)).decode()
        with ExitStack() as stack:
            stack.enter_context(patch.object(backup,'ROOT',root));stack.enter_context(patch.object(backup.os,'umask'))
            stack.enter_context(patch.object(backup,'verify',return_value={'content_digest':SCOPE.release_digest}))
            stack.enter_context(patch.object(backup,'public_settings',return_value=self.config));stack.enter_context(patch.object(backup,'installation',return_value=self.facts))
            stack.enter_context(patch.object(backup,'checked_source',return_value=('123','1','a'*40)))
            drive=stack.enter_context(patch('appointment_system.backup.drive.Drive'));store=drive.return_value
            stage=stack.enter_context(patch.object(backup.pipeline,mode,return_value=signed if mode=='validate' else {'stored':True},side_effect=BackupError('synthetic_failure') if failure else None))
            dump=stack.enter_context(patch('appointment_system.backup.database.export_age'));stack.enter_context(patch('appointment_system.backup.database.migration_hashes',return_value={'001_fixture.sql':'c'*64}))
            with redirect_stdout(io.StringIO()) as printed:
                try:result=backup.main([mode],source=source)
                except BackupError:
                    store.close.assert_called_once();raise
            store.close.assert_called_once();self.assertEqual(drive.call_args.kwargs['reader'],mode=='validate')
            if mode=='export':stage.call_args.kwargs['dump'](root/'encrypted.age');self.assertEqual(dump.call_args.args[0],source['BOOKING_BACKUP_DATABASE_URL'])
            self.assertNotIn('synthetic-private',printed.getvalue());return result,stage.call_args,source

    def test_executable_export_validate_and_retention_bind_the_same_identity_and_disjoint_duties(self):
        for mode in ('export','validate','retain'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);result,call,source=self.command(mode,root)
                self.assertEqual(call.args[0],SCOPE);self.assertEqual(call.args[2:5],('123','1','a'*40))
                self.assertTrue(result['stored'])
                if mode=='validate':self.assertTrue((root/'result').read_text().startswith('restore_proof='));self.assertFalse(result['retention_completed'])
                else:self.assertFalse((root/'result').exists())

    def test_every_failed_duty_closes_its_drive_client_and_invalid_proof_never_prunes(self):
        for mode in ('export','validate','retain'):
            with tempfile.TemporaryDirectory() as temporary,self.assertRaisesRegex(BackupError,'synthetic_failure'):self.command(mode,Path(temporary),failure=True)
        with tempfile.TemporaryDirectory() as temporary,self.assertRaisesRegex(BackupError,'output_missing'):self.command('validate',Path(temporary),output=False)
        with tempfile.TemporaryDirectory() as temporary,self.assertRaisesRegex(BackupError,'restore_proof_invalid'):self.command('retain',Path(temporary),proof='not valid base64')
