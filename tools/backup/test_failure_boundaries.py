"""Backup size/authentication/process failures never release an invalid restore."""
import io
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from envelope import BackupError,MAGIC,encrypt,decrypt
from postgres import HOST,command,dump_encrypted,restore_check
from diagnostics import PrivateErrors


class FailureBoundaryTests(unittest.TestCase):
    key=b'x'*32
    metadata={'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':'2026-10-01'}

    def test_manifest_size_archive_size_and_header_are_bounded(self):
        with self.assertRaisesRegex(BackupError,'manifest_too_large'):encrypt(io.BytesIO(b'data'),io.BytesIO(),self.key,dict(self.metadata,large='x'*4096))
        with patch('envelope.MAX_BYTES',4),self.assertRaisesRegex(BackupError,'size_limit'):encrypt(io.BytesIO(b'12345'),io.BytesIO(),self.key,self.metadata)
        for header in (b'bad',MAGIC+b'x'*12+struct.pack('>I',4097)+b'x'*16,MAGIC+b'x'*12+struct.pack('>I',4096)+b'x'*16):
            with self.assertRaises(BackupError):decrypt(io.BytesIO(header),self.key)
        archive=io.BytesIO();encrypt(io.BytesIO(b'12345'),archive,self.key,self.metadata)
        with patch('envelope.MAX_BYTES',4),self.assertRaisesRegex(BackupError,'size_invalid'):decrypt(io.BytesIO(archive.getvalue()),self.key)

    def test_authenticated_wrong_project_is_not_a_sarsa_restore(self):
        for change in ({'project':'003-astroadvice'},{'format':'unknown'}):
            archive=io.BytesIO();encrypt(io.BytesIO(b'data'),archive,self.key,dict(self.metadata,**change))
            with self.assertRaisesRegex(BackupError,'identity_invalid'):decrypt(archive,self.key)

    def test_truncated_stream_does_not_release_a_validated_result(self):
        archive=io.BytesIO();encrypt(io.BytesIO(b'data'),archive,self.key,self.metadata)
        class Interrupted(io.BytesIO):
            calls=0
            def read(self,count=-1):
                self.calls+=1
                return b'' if self.calls==4 else super().read(count)
        with self.assertRaisesRegex(BackupError,'truncated'):decrypt(Interrupted(archive.getvalue()),self.key)

    def test_dump_command_failures_are_fixed_codes_and_process_is_stopped(self):
        dsn=f'postgresql://sarsa_booking_backup:synthetic@{HOST}/neondb'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'backup'
            with patch('postgres.Path.is_file',return_value=False),self.assertRaisesRegex(BackupError,'certificate_bundle'):dump_encrypted(dsn,path,self.key,self.metadata)
            process=Mock(stdout=io.BytesIO(b'data'),stderr=io.BytesIO(b'password authentication failed private-value'))
            process.wait.return_value=1;process.poll.return_value=None
            with patch('postgres.Path.is_file',return_value=True),patch('postgres.subprocess.Popen',return_value=process),self.assertRaisesRegex(BackupError,'authentication_failed'):dump_encrypted(dsn,path,self.key,self.metadata)
            process.kill.assert_called_once();self.assertTrue(process.stdout.closed);self.assertTrue(process.stderr.closed)
        with patch('postgres.subprocess.run',return_value=SimpleNamespace(returncode=1)),self.assertRaisesRegex(BackupError,'command_failed'):command(['synthetic'],capture=True)

    def test_failed_restore_start_only_removes_the_exact_owned_container(self):
        archive=io.BytesIO();encrypt(io.BytesIO(b'data'),archive,self.key,self.metadata)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive';path.write_bytes(archive.getvalue())
            for matching in (False,True):
                calls=[];owner=None
                def run(arguments,**kwargs):
                    nonlocal owner
                    calls.append(arguments)
                    if 'run' in arguments:owner=arguments[arguments.index('--label')+1].split('=')[1];return SimpleNamespace(returncode=1)
                    if 'inspect' in arguments:return SimpleNamespace(returncode=0,stdout=(owner if matching else 'other-owner').encode())
                    return SimpleNamespace(returncode=0)
                with patch('postgres.subprocess.run',side_effect=run),self.assertRaisesRegex(BackupError,'container_start_failed'):restore_check(path,self.key)
                self.assertEqual(any('rm' in call for call in calls),matching)
                if matching:self.assertEqual(calls[-1][-1],calls[0][calls[0].index('--name')+1])

    def test_closed_error_stream_is_sanitised(self):
        stream=Mock();stream.read.side_effect=ValueError('private detail');errors=PrivateErrors(stream);errors.finish()
        self.assertEqual(errors.code('dump'),'postgres_dump_failed');self.assertEqual(errors.clues(),[])
