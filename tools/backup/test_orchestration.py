"""Backup ordering and replay safety with real encryption, synthetic Drive only."""
import base64
from datetime import datetime,timezone
import importlib.util
import io
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock,patch
from envelope import BackupError,encrypt,decrypt
from test_retention import archive

spec=importlib.util.spec_from_file_location('backup_daily_run',Path(__file__).with_name('run.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
KEY=bytes(range(32));DAY=datetime.now(timezone.utc).date().isoformat();REVISION='a'*40

class OrchestrationTests(unittest.TestCase):
    def flow(self,existing=False,kind='daily',metadata=None):
        events=[];encrypted=[];drive=Mock();record=archive(DAY,'synthetic',False)
        if kind=='checkpoint':
            record['name']=f'sarsa-004-{DAY}-checkpoint-{REVISION}.pgdump.aesgcm'
            record['appProperties'].update(backupKind=kind,sourceCommit=REVISION)
        drive.folder.return_value='folder';drive.existing.return_value=record if existing else None
        drive.upload.side_effect=lambda *a:(events.append('upload') or record)
        drive.mark_verified.side_effect=lambda *a:(events.append('verified') or record)
        drive.retain.side_effect=lambda *a:(events.append('retain') or 0)
        def dump(_dsn,path,key,manifest):
            events.append('dump');encrypted.clear()
            data=io.BytesIO();encrypt(io.BytesIO(b'synthetic postgres archive'),data,key,manifest)
            encrypted.append(data.getvalue());path.write_bytes(encrypted[0])
        if existing:
            manifest=metadata or {'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':DAY,'kind':kind,'source_commit':REVISION}
            buffer=io.BytesIO();encrypt(io.BytesIO(b'synthetic archive'),buffer,KEY,manifest);encrypted.append(buffer.getvalue())
        def download(_record,path):events.append('download');path.write_bytes(encrypted[0])
        drive.download.side_effect=download
        def restore(path,key,**kwargs):
            events.append('restore');self.assertEqual(decrypt(io.BytesIO(path.read_bytes()),key)['day'],DAY)
            return {'restored_migrations':31,'day':DAY}
        settings={'SARSA_BACKUP_ENCRYPTION_KEY':base64.urlsafe_b64encode(KEY).decode(),'SARSA_BACKUP_GOOGLE':'{}',
                  'SARSA_BACKUP_DATABASE_URL':'synthetic-never-opened','SARSA_BACKUP_KIND':kind,'GITHUB_SHA':REVISION}
        return drive,events,settings,dump,restore

    def run_flow(self,values):
        drive,events,settings,dump,restore=values
        with patch.dict(os.environ,settings),patch.object(runner,'Drive',return_value=drive),patch.object(runner,'dump_encrypted',side_effect=dump),patch.object(runner,'restore_check',side_effect=restore),patch('builtins.print'):
            runner.main()
        return events

    def test_new_and_existing_daily_checkpoint_backups_verify_before_retention(self):
        for existing in (False,True):
            for kind in ('daily','checkpoint'):
                with self.subTest(existing=existing,kind=kind):
                    values=self.flow(existing,kind);drive=values[0];events=self.run_flow(values)
                    self.assertLess(events.index('restore'),events.index('verified'))
                    self.assertLess(events.index('download'),events.index('verified'))
                    self.assertEqual(events[-2:],['verified','retain']);drive.close.assert_called_once()
                    self.assertEqual(drive.upload.call_count,0 if existing else 1)

    def test_wrong_day_or_checkpoint_manifest_never_marks_verified_or_deletes(self):
        for changes,expected in [({'day':'2000-01-01'},'day_mismatch'),({'kind':'daily'},'checkpoint_mismatch'),({'source_commit':'b'*40},'checkpoint_mismatch')]:
            manifest={'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':DAY,'kind':'checkpoint','source_commit':REVISION,**changes}
            values=self.flow(True,'checkpoint',manifest)
            with self.assertRaisesRegex(BackupError,expected):self.run_flow(values)
            values[0].mark_verified.assert_not_called();values[0].retain.assert_not_called();values[0].close.assert_called_once()

    def test_restore_or_readback_failure_does_not_start_retention(self):
        values=self.flow();values=list(values);values[4]=Mock(side_effect=BackupError('restore_failed'))
        with self.assertRaisesRegex(BackupError,'restore_failed'):self.run_flow(values)
        values[0].upload.assert_not_called();values[0].retain.assert_not_called();values[0].close.assert_called_once()
        values=self.flow();normal=values[0].download.side_effect
        def wrong(record,path):
            normal(record,path)
            buffer=io.BytesIO();encrypt(io.BytesIO(b'synthetic'),buffer,KEY,{'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':DAY})
            path.write_bytes(buffer.getvalue())
        values[0].download.side_effect=wrong
        with self.assertRaisesRegex(BackupError,'readback_mismatch'):self.run_flow(values)
        values[0].mark_verified.assert_not_called();values[0].retain.assert_not_called()

    def test_invalid_backup_kind_and_key_fail_before_contacting_storage(self):
        for setting in ({'SARSA_BACKUP_KIND':'arbitrary'},{'SARSA_BACKUP_KIND':'checkpoint','GITHUB_SHA':'wrong'},{'SARSA_BACKUP_ENCRYPTION_KEY':'broken'}):
            values=self.flow();values[2].update(setting)
            with patch.object(runner,'Drive') as drive,patch.dict(os.environ,values[2]),self.assertRaises(BackupError):runner.main()
            drive.assert_not_called()

    def test_cli_failures_hide_unknown_exception_details(self):
        for failure in (BackupError('fixed_code'),RuntimeError('synthetic-private-value')):
            with patch.dict(os.environ,{'SARSA_BACKUP_ENCRYPTION_KEY':'synthetic'}),patch('envelope.decode_key',side_effect=failure),self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(Path(__file__).with_name('run.py')),run_name='__main__')
            self.assertNotIn('synthetic-private-value',str(stopped.exception))

    def test_database_cli_passes_bounded_wait_and_sanitises_errors(self):
        path=str(Path(__file__).with_name('save-database-setting.py'))
        with patch('sys.argv',[path,'--wait-seconds','20']),patch('database_setting.main') as main:runpy.run_path(path,run_name='__main__')
        main.assert_called_once_with(20)
        for failure in (BackupError('fixed_code'),RuntimeError('synthetic-private-value')):
            with patch('sys.argv',[path]),patch('database_setting.main',side_effect=failure),self.assertRaises(SystemExit) as stopped:runpy.run_path(path,run_name='__main__')
            self.assertNotIn('synthetic-private-value',str(stopped.exception))

if __name__=='__main__':unittest.main()
