"""Process and stream failure injection supplements the native cryptographic round trip."""
from io import BytesIO,StringIO
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
from appointment_system.backup import age_stream as stream
from appointment_system.backup.protocol import BackupError

class StreamFailureBoundaries(unittest.TestCase):
 def test_only_exact_executable_version_and_finite_real_files_are_accepted(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'tool';path.write_bytes(b'synthetic');path.chmod(0o700)
   for failure in [SimpleNamespace(stdout=b'v1.0.0'),OSError('private'),subprocess.TimeoutExpired('tool',5)]:
    with patch.object(stream.subprocess,'run',**({'side_effect':failure} if isinstance(failure,Exception) else {'return_value':failure})):
     with self.assertRaisesRegex(BackupError,'tool_version_invalid'):stream.tool(path)
   empty=root/'empty';empty.touch()
   with self.assertRaisesRegex(BackupError,'size_limit'):stream.hashed(empty)
   linked=root/'linked';linked.symlink_to(path)
   with self.assertRaisesRegex(BackupError,'archive_invalid'):stream.hashed(linked)
   with patch.object(stream,'MAX_BYTES',1):
    with self.assertRaisesRegex(BackupError,'size_limit'):stream.hashed(path)

 def test_disappeared_process_cleanup_is_safe(self):
  process=Mock();process.poll.return_value=None;process.kill.side_effect=ProcessLookupError()
  stream.stop(process);process.kill.assert_called_once()

 def test_invalid_oversize_empty_or_broken_input_removes_partial_output(self):
  for source,error in [(StringIO('not bytes'),'stream_invalid'),(BytesIO(b'12345'),'size_limit'),(BytesIO(b''),'encryption_failed'),(Mock(read=Mock(side_effect=OSError('private'))),'encryption_failed')]:
   with self.subTest(error=error),tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'archive.age';process=Mock();process.stdin=BytesIO();process.wait.return_value=0
    with patch.object(stream,'tool',return_value='synthetic'),patch.object(stream.subprocess,'Popen',return_value=process),patch.object(stream.threading,'Timer'),patch.object(stream,'stop'),patch.object(stream,'MAX_BYTES',4):
     with self.assertRaisesRegex(BackupError,error):stream.encrypt(source,output,'age1'+'a'*50,'synthetic')
    self.assertFalse(output.exists());self.assertTrue(process.stdin.closed)

 def test_decrypt_start_or_private_input_failure_does_not_expose_key(self):
  identity='AGE-SECRET-KEY-1'+'A'*50
  for failure in [OSError('private'),subprocess.SubprocessError('private')]:
   with patch.object(stream.subprocess,'Popen',side_effect=failure):
    with self.assertRaisesRegex(BackupError,'^backup_decryption_failed$'):stream.decrypt_process('synthetic',identity,'synthetic',None)
  process=Mock();process.stdin.write.side_effect=OSError('private');process.wait.return_value=1
  with patch.object(stream.subprocess,'Popen',return_value=process),patch.object(stream,'stop') as stop:
   with self.assertRaisesRegex(BackupError,'^backup_decryption_failed$'):stream.decrypt_process('synthetic',identity,'synthetic',None)
   stop.assert_called_once_with(process)

 def test_authentication_timeout_never_yields_an_archive(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'archive.age';path.write_bytes(b'synthetic ciphertext');sha,size=stream.hashed(path)
   process=Mock();process.wait.side_effect=[subprocess.TimeoutExpired('synthetic',120),0]
   with patch.object(stream,'tool',return_value='synthetic'),patch.object(stream,'decrypt_process',return_value=process),patch.object(stream,'stop'):
    with self.assertRaisesRegex(BackupError,'authentication_timeout'):
     with stream.authenticated_archive(path,'synthetic','synthetic',sha,size):self.fail('Unauthenticated archive was yielded')

 def test_restore_output_failure_and_size_limit_cannot_report_success(self):
  archive=stream._Authenticated('synthetic','synthetic','synthetic')
  for sink,error in [(Mock(write=Mock(side_effect=OSError('private'))),'restore_stream_failed'),(BytesIO(),'size_limit')]:
   process=Mock();process.stdout=BytesIO(b'12345');process.wait.return_value=0
   with patch.object(stream,'decrypt_process',return_value=process),patch.object(stream.threading,'Timer'),patch.object(stream,'stop'),patch.object(stream,'MAX_BYTES',100 if error=='restore_stream_failed' else 4):
    with self.assertRaisesRegex(BackupError,error):stream.restore_stream(archive,sink)
   self.assertTrue(process.stdout.closed)
