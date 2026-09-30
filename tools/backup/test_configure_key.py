"""Verify setup never rotates an existing recovery key or logs private bytes."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from envelope import BackupError

spec=importlib.util.spec_from_file_location('backup_key_setup',Path(__file__).with_name('configure-key.py'))
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

class KeySetupTests(unittest.TestCase):
    def test_existing_key_stops_before_clipboard_or_write(self):
        result=subprocess.CompletedProcess([],0,stdout=b'{"secrets":[{"name":"SARSA_BACKUP_ENCRYPTION_KEY"}]}')
        with patch.object(setup.subprocess,'run',return_value=result) as run:
            with self.assertRaisesRegex(BackupError,'already_saved'):setup.main()
        self.assertEqual(run.call_count,1)
    def test_replacement_refuses_when_database_is_connected(self):
        result=subprocess.CompletedProcess([],0,stdout=b'{"secrets":[{"name":"SARSA_BACKUP_ENCRYPTION_KEY"},{"name":"SARSA_BACKUP_DATABASE_URL"}]}')
        with patch.object(setup.subprocess,'run',return_value=result) as run:
            with self.assertRaisesRegex(BackupError,'archived_key_review'):setup.main(replace_unused=True)
        self.assertEqual(run.call_count,1)
    def test_replacement_refuses_any_published_workflow(self):
        results=[subprocess.CompletedProcess([],0,stdout=b'{"secrets":[{"name":"SARSA_BACKUP_ENCRYPTION_KEY"}]}'),subprocess.CompletedProcess([],0,stdout=b'{"total_count":1}')]
        with patch.object(setup.subprocess,'run',side_effect=results) as run:
            with self.assertRaisesRegex(BackupError,'archived_key_review'):setup.main(replace_unused=True)
        self.assertEqual(run.call_count,2)
    def test_clipboard_failure_stops_before_saving_unrecoverable_key(self):
        results=[subprocess.CompletedProcess([],0,stdout=b'{"secrets":[]}'),subprocess.CompletedProcess([],1)]
        with patch.object(setup.subprocess,'run',side_effect=results) as run:
            with self.assertRaisesRegex(BackupError,'clipboard_failed'):setup.main()
        self.assertEqual(run.call_count,2)
    def test_key_uses_stdin_and_fixed_destination(self):
        results=[subprocess.CompletedProcess([],0,stdout=b'{"secrets":[]}'),subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0)]
        with patch.object(setup.subprocess,'run',side_effect=results) as run,patch('builtins.print') as output:
            setup.main()
        calls=run.call_args_list
        private=calls[1].kwargs['input']
        self.assertEqual(len(private),44)
        self.assertEqual(calls[2].kwargs['input'],private)
        self.assertEqual(calls[2].args[0],['gh','secret','set','SARSA_BACKUP_ENCRYPTION_KEY','--repo','NeuraFlowUser1/Astrologer_Madhuri_Gupta'])
        self.assertNotIn(private.decode(),str(output.call_args_list))

if __name__=='__main__':unittest.main()
