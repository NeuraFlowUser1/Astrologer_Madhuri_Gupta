"""The test runner must never reset an unrelated or network-exposed database.

Docker replies are synthetic here; no container is started, stopped or erased.
Actual SQL behavior is exercised separately by the owned native suites.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import tempfile
import unittest
from tools.checks import sql_target as module


def reply(text='',code=0):
    return SimpleNamespace(returncode=code,stdout=text,stderr='Synthetic failure')


class ProofTargetSafety(unittest.TestCase):
    def target(self):
        # Exercise command safety without taking a real database's shared lock.
        target=object.__new__(module.SQLTarget)
        target.name='abs-implementation-pg16'
        return target

    def test_unknown_targets_and_roles_never_reach_docker(self):
        with patch.object(module,'command') as command:
            for name in ('production','abs-implementation-pg17',''):
                with self.assertRaises(ValueError):module.SQLTarget(name)
                with self.assertRaises(ValueError):
                    with module.delegated_proof(name):self.fail('Unknown delegation accepted')
            with self.assertRaises(ValueError):self.target().sql('SELECT 1',role='neondb_owner')
            command.assert_not_called()

    def test_reset_refuses_foreign_purpose_and_published_network_before_removal(self):
        for responses in ([reply(),reply('foreign-purpose')],
                          [reply(),reply(module.LABEL),reply('bridge|{}')],
                          [reply(),reply(module.LABEL),reply('none|{"5432":[]}')]):
            with self.subTest(responses=responses),patch.object(module,'command',side_effect=responses) as command:
                with self.assertRaises(ValueError):self.target().start(reset=True)
                self.assertFalse(any(call.args[0][0] in ('rm','run','start') for call in command.call_args_list))

    def test_owned_reset_creates_only_pinned_disconnected_target_and_rechecks_it(self):
        responses=[reply(),reply(module.LABEL),reply('none|null'),reply(),reply(),reply(),reply(module.LABEL),reply('none|{}')]
        with patch.object(module,'command',side_effect=responses) as command:
            self.target().start(reset=True)
            calls=[c.args[0] for c in command.call_args_list]
            self.assertEqual(calls[3],['rm','-f','abs-implementation-pg16'])
            created=calls[4];self.assertEqual(created[created.index('--network')+1],'none')
            self.assertNotIn('-p',created);self.assertEqual(created[-1],module.IMAGES['abs-implementation-pg16'])
            self.assertEqual(calls[-1][0],'inspect')

    def test_stopped_owned_target_restarts_and_failures_do_not_continue(self):
        with patch.object(module,'command',side_effect=[reply(),reply(module.LABEL),reply('none|null'),reply(),reply(),reply(module.LABEL),reply('none|null')]) as command:
            self.target().start();self.assertEqual(command.call_args_list[3].args[0],['start','abs-implementation-pg16'])
        for reset,responses in [(False,[reply(),reply(module.LABEL),reply('none|null'),reply(code=1)]),
                                (True,[reply(),reply(module.LABEL),reply('none|null'),reply(code=1)]),
                                (False,[reply(code=1),reply(code=1)])]:
            with self.subTest(reset=reset),patch.object(module,'command',side_effect=responses):
                with self.assertRaises(RuntimeError):self.target().start(reset=reset)

    def test_readiness_deadline_is_bounded_and_socket_ownership_is_exact(self):
        with patch.object(module,'command',side_effect=[reply(code=1),reply()]+[reply(code=1)]*60) as command,patch.object(module.time,'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'did not become ready'):self.target().start()
            self.assertEqual(sleep.call_count,60);self.assertEqual(command.call_count,62)
        target=self.target()
        with tempfile.TemporaryDirectory(prefix='abs-native-socket-') as temporary:
            path=Path(temporary);(path/'proof-target').write_text(module.LABEL+'\n'+target.name+'\n')
            mount={'Type':'bind','Source':str(path),'Destination':'/var/run/postgresql'}
            with patch.object(target,'check_owned'),patch.object(module,'command',return_value=reply(json.dumps([mount]))):
                self.assertEqual(target.native_socket(),str(path));(path/'proof-target').write_text('foreign\n')
                with self.assertRaisesRegex(ValueError,'not owned'):target.native_socket()
            for mounts in ([],[mount,mount]):
                with patch.object(target,'check_owned'),patch.object(module,'command',return_value=reply(json.dumps(mounts))):
                    with self.assertRaisesRegex(ValueError,'missing'):target.native_socket()

    def test_migration_rejects_unknown_and_changed_history_and_applies_only_missing_files(self):
        target=self.target()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'engine/appointment_system/migrations';directory.mkdir(parents=True)
            (directory/'001_fixture.sql').write_text('SELECT 1;');(directory/'002_fixture.sql').write_text('SELECT 2;')
            digest=hashlib.sha256(b'SELECT 1;').hexdigest()
            with patch.object(module,'ROOT',root),patch.object(target,'check_owned'),patch.object(target,'scalar',return_value='t'),patch.object(target,'sql') as sql:
                for history in ({'000_foreign.sql':'x'},{'001_fixture.sql':'wrong'}):
                    with patch.object(target,'value',return_value=history),self.assertRaises(AssertionError):target.migrate()
                    sql.assert_not_called()
                with patch.object(target,'value',return_value={'001_fixture.sql':digest}):self.assertEqual(target.migrate(),2)
                self.assertEqual(sql.call_count,1);statement=sql.call_args.args[0];self.assertIn('SELECT 2;',statement);self.assertIn('BEGIN;',statement);self.assertTrue(statement.endswith('COMMIT;'))

    def test_sql_errors_are_bounded_and_test_literals_do_not_accept_objects_or_unbounded_integers(self):
        target=self.target()
        with patch.object(module,'command',return_value=reply(code=1)):
            with self.assertRaises(AssertionError):target.sql('SELECT 1')
            self.assertEqual(target.sql('SELECT 1',check=False).returncode,1)
        for value in (object(),1.25,2**63,-2**63-1):
            with self.assertRaises(ValueError):module.literal(value)
        self.assertEqual(module.literal("O'Neil"),"'O''Neil'")
        self.assertEqual([module.literal(value) for value in (None,True,False,0)],['NULL','true','false','0'])
        self.assertEqual(module.literal({'x':1}),"'{\"x\":1}'")
        with patch.object(target,'scalar',return_value=''):self.assertIsNone(target.value('SELECT NULL'))
        with patch.object(target,'scalar',return_value='{"ok":true}'):self.assertEqual(target.value('SELECT fixture'),{'ok':True})

    def test_delegation_releases_only_its_owned_lock_and_reacquires_after_failure(self):
        from unittest.mock import Mock
        previous=Mock();other=Mock()
        name=self.target().name
        with patch.object(module,'_PROOF_LOCKS',{name:previous,'other':other}),patch.object(module,'SQLTarget') as target:
            with self.assertRaisesRegex(RuntimeError,'synthetic child'):
                with module.delegated_proof(name):
                    previous.close.assert_called_once();other.close.assert_not_called();raise RuntimeError('synthetic child')
            target.assert_called_once_with('abs-implementation-pg16')
        with patch.object(module,'_PROOF_LOCKS',{'a':previous,'b':other}):
            module._release_proof_locks();self.assertEqual(module._PROOF_LOCKS,{});other.close.assert_called_once()

    def test_native_socket_creation_remains_local_and_records_exact_fixture_ownership(self):
        responses=[reply(code=1),reply(),reply(),reply(module.LABEL),reply('none|{}')]
        with tempfile.TemporaryDirectory(prefix='abs-native-socket-') as directory:
            with patch.object(module.tempfile,'mkdtemp',return_value=directory),patch.object(module,'command',side_effect=responses) as command:
                self.target().start(native_socket=True)
            self.assertEqual((Path(directory)/'proof-target').read_text(),module.LABEL+'\n'+self.target().name+'\n')
            created=command.call_args_list[1].args[0];self.assertIn('type=bind,src='+directory+',dst=/var/run/postgresql',created);self.assertEqual(created[created.index('--network')+1],'none');self.assertNotIn('-p',created)
