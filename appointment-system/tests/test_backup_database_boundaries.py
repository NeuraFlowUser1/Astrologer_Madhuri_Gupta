"""Isolated restore failures preserve ownership and never imply a verified backup."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
from appointment_system.backup import database
from appointment_system.backup.protocol import BackupError

class BackupProcessBoundaries(unittest.TestCase):
 def test_migration_manifest_requires_real_release_files(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   with self.assertRaisesRegex(BackupError,'migrations_invalid'):database.migration_hashes(root)
   (root/'001_valid.sql').write_text('SELECT 1;');self.assertEqual(len(database.migration_hashes(root)['001_valid.sql']),64)
   (root/'002_link.sql').symlink_to(root/'001_valid.sql')
   with self.assertRaisesRegex(BackupError,'migrations_invalid'):database.migration_hashes(root)

 def test_dump_process_receives_password_only_through_environment_and_enforces_read_only_tls(self):
  with tempfile.TemporaryDirectory() as directory:
   ca=Path(directory)/'ca.pem';ca.write_text('synthetic certificate')
   config=dict(host='synthetic.invalid',dbname='synthetic',user='backup',password='synthetic-private-password',sslrootcert=str(ca))
   with patch.object(database.subprocess,'Popen',return_value=Mock()) as start:
    database.start_dump(config,{'postgres_major':16,'snapshot':'synthetic-snapshot'})
   args=start.call_args.args[0];env=start.call_args.kwargs['env']
   self.assertNotIn(config['password'],' '.join(args));self.assertEqual(env['PGPASSWORD'],config['password']);self.assertEqual(env['PGSSLMODE'],'verify-full');self.assertIn('default_transaction_read_only=on',env['PGOPTIONS']);self.assertIn('--snapshot=synthetic-snapshot',args)
   for snapshot in ({'postgres_major':17,'snapshot':'x'},):
    with self.assertRaisesRegex(BackupError,'dump_tool_invalid'):database.start_dump(config,snapshot)
   with patch.object(database.subprocess,'Popen',side_effect=OSError('private process detail')):
    with self.assertRaisesRegex(BackupError,'^backup_dump_start_failed$'):database.start_dump(config,{'postgres_major':16,'snapshot':'x'})

 def test_failed_dump_removes_partial_ciphertext_and_always_closes_process(self):
  for failure in [BackupError('encryption_failed'),OSError('private-detail'),subprocess.TimeoutExpired('synthetic',1),None]:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
    destination=Path(directory)/'archive.age';process=Mock();process.stdout=BytesIO(b'synthetic');process.wait.return_value=1
    def encrypt(*args):
     destination.write_bytes(b'partial ciphertext')
     if failure:raise failure
    with patch.object(database,'capture',return_value={'snapshot':'synthetic'}),patch.object(database,'encrypt',side_effect=encrypt),patch.object(database,'stop') as stop,patch.object(database.threading,'Timer') as timer:
     with self.assertRaises(BackupError):database.export_connection(None,None,{},[],destination,'synthetic','synthetic',dump_factory=lambda _:process)
    self.assertFalse(destination.exists());self.assertTrue(process.stdout.closed);timer.return_value.cancel.assert_called_once();stop.assert_called_once_with(process)

 def test_restore_commands_bound_output_time_and_owned_cleanup(self):
  for value in [True,17,'16']:
   with self.assertRaisesRegex(BackupError,'version_invalid'):database.IsolatedPostgres(value)
  target=database.IsolatedPostgres(16)
  for result in [SimpleNamespace(returncode=1,stdout=b''),SimpleNamespace(returncode=0,stdout=b'x'*9)]:
   with patch.object(database.subprocess,'run',return_value=result):
    with self.assertRaisesRegex(BackupError,'command_failed'):target.run(['synthetic'],capture=True,limit=8)
  with patch.object(database.subprocess,'run',side_effect=OSError('private')):
   with self.assertRaisesRegex(BackupError,'^backup_restore_command_failed$'):target.run(['synthetic'])
  with patch.object(database.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'foreign-owner')),patch.object(target,'run') as run:
   with self.assertRaisesRegex(BackupError,'cleanup_refused'):target.close()
   run.assert_not_called()
  with patch.object(database.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=target.owner.encode())),patch.object(target,'run',side_effect=[None,b'still-present']):
   with self.assertRaisesRegex(BackupError,'cleanup_unconfirmed'):target.close()

 def test_restore_start_and_wait_failures_cleanup_only_the_new_owned_container(self):
  for failure in [OSError('private'),subprocess.TimeoutExpired('synthetic',1),SimpleNamespace(returncode=1)]:
   target=database.IsolatedPostgres(16)
   with patch.object(database.subprocess,'run',**({'side_effect':failure} if isinstance(failure,Exception) else {'return_value':failure})),patch.object(target,'close') as close:
    with self.assertRaisesRegex(BackupError,'start_failed'):target.__enter__()
    close.assert_called_once()
  target=database.IsolatedPostgres(16)
  with patch.object(database.subprocess,'run',return_value=SimpleNamespace(returncode=0)),patch.object(database.time,'monotonic',side_effect=[0,36]),patch.object(target,'close') as close:
   with self.assertRaisesRegex(BackupError,'not_ready'):target.__enter__()
   close.assert_called_once()

 def test_restore_stream_creation_and_failed_exit_never_claim_success(self):
  target=database.IsolatedPostgres(16)
  with patch.object(database.subprocess,'Popen',side_effect=OSError('private')):
   with self.assertRaisesRegex(BackupError,'command_failed'):target.load(None)
  process=Mock();process.stdin=BytesIO();process.wait.return_value=1
  with patch.object(database.subprocess,'Popen',return_value=process),patch.object(database,'restore_stream'),patch.object(database,'stop') as stop,patch.object(database.threading,'Timer') as timer:
   with self.assertRaisesRegex(BackupError,'restore_failed'):target.load(None)
  self.assertTrue(process.stdin.closed);stop.assert_called_once_with(process);timer.return_value.cancel.assert_called_once()
