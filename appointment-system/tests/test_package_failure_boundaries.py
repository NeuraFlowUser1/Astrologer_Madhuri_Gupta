"""Whole-package replacement cannot follow links or guess after an interrupted move."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch
import unittest
from tools.install import package
from . import test_package as package_tests
from .fixtures import installation,business
from appointment_system.serialization import fingerprint


class PackageFailureBoundaries(unittest.TestCase):
    setUp=package_tests.PackageTests.setUp
    run_install=package_tests.PackageTests.run_install

    def test_declared_package_paths_and_release_names_reject_unexpected_content(self):
        for name in ('/engine/x.py','engine//x.py','engine/../x.py','engine/./x.py','foreign/x.py','unknown.py','engine/key.pem','engine/x y.py','x'*241,None):
            with self.subTest(name=name),self.assertRaises(package.PackageError):package._path(name)
        for release in ('1','v1.0.0','1.0.0-rc.0','1.0.0+unreviewed'):
            with self.assertRaises(package.PackageError):package.build(self.source,release=release)
        self.assertEqual(package._path('.gitignore'),'.gitignore')
        with self.assertRaises(package.PackageError):package.inventory(self.root/'missing')
        empty=self.root/'empty';empty.mkdir()
        with self.assertRaises(package.PackageError):package.inventory(empty)

    def test_valid_digest_cannot_authorize_malformed_file_metadata_or_wrong_runtime(self):
        manifest=self.source/'release.json';base=json.loads(manifest.read_text())
        def save(value):
            unsigned={k:v for k,v in value.items() if k!='content_digest'}
            value['content_digest']=hashlib.sha256(package.canonical(unsigned)).hexdigest();manifest.write_text(json.dumps(value))
        for changes in ({'release':1},{'runtime':{'python':'9'}},{'files':[]},{'format_version':2},{'worker_contract':False}):
            save(base|changes)
            with self.subTest(changes=changes),self.assertRaises(package.PackageError):package.verify(self.source)
        for facts in (None,{}, {'sha256':'a'*64,'bytes':True},{'sha256':'INVALID','bytes':1},{'sha256':'a'*64,'bytes':-1},{'sha256':'a'*64,'bytes':8*1024*1024+1}):
            save(base|{'files':{'engine/appointment_system/application.py':facts}})
            with self.subTest(facts=facts),self.assertRaises(package.PackageError):package.verify(self.source)
        manifest.write_text('NaN')
        with self.assertRaises(package.PackageError):package.verify(self.source)

    def test_links_at_manifest_settings_lock_destination_and_rollback_are_never_followed(self):
        manifest=self.source/'release.json';content=manifest.read_bytes();manifest.unlink();manifest.symlink_to(self.root/'foreign-manifest')
        with self.assertRaises(package.PackageError):package.build(self.source)
        with self.assertRaises(package.PackageError):package.verify(self.source)
        manifest.unlink();manifest.write_bytes(content)
        for name in ('.appointment-install.lock','appointment-system',package.INTENT):
            link=self.target/name;link.symlink_to(self.root/'foreign-target')
            with self.subTest(name=name),self.assertRaises(package.PackageError):self.run_install()
            link.unlink()
        settings=self.target/'appointment-settings/project.json';content=settings.read_bytes();settings.unlink();settings.symlink_to(self.root/'foreign-settings')
        with self.assertRaises(package.PackageError):self.run_install()
        settings.unlink();settings.write_bytes(content)
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');package.build(self.source)
        (self.target/'.appointment-rollbacks').symlink_to(self.root/'foreign-rollbacks')
        with self.assertRaises(package.PackageError):self.run_install(upgrade=True)
        self.assertEqual(package.verify(self.target/'appointment-system'),self.release)

    def test_concurrent_installer_cannot_take_a_second_lock(self):
        if os.name=='nt':self.skipTest('Native POSIX lock assertion; Windows lock branch is separately tested.')
        with package.locked(self.target):
            with self.assertRaises(BlockingIOError):
                with package.locked(self.target):self.fail('Concurrent install entered')

    def test_missing_or_foreign_interrupted_state_never_guesses_a_replacement(self):
        intent={'installation_id':installation()['installation_id'],'project_id':installation()['project_id'],
            'project_digest':fingerprint(installation()),'bootstrap_business_digest':fingerprint(business()),
            'release_digest':self.release['content_digest'],'stage':'.appointment-stage-abcdef','rollback':None}
        path=self.target/package.INTENT
        for value in ('not JSON',json.dumps(intent|{'stage':'../foreign'}),json.dumps(intent|{'rollback':'../foreign'}),json.dumps(intent|{'project_id':'other'}),json.dumps(intent)):
            path.write_text(value)
            with self.assertRaises(package.PackageError):self.run_install()
            self.assertFalse((self.target/'appointment-system').exists());self.assertTrue(path.exists())
        path.unlink();path.mkdir()
        with self.assertRaises(package.PackageError):self.run_install()

    def test_lost_staging_directory_restores_verified_previous_copy_without_claiming_upgrade(self):
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');package.build(self.source)
        original=os.replace
        def interruption(source,target):
            if Path(source).name.startswith('.appointment-stage-'):raise KeyboardInterrupt('Synthetic interruption')
            return original(source,target)
        with patch.object(package.os,'replace',side_effect=interruption),self.assertRaises(KeyboardInterrupt):self.run_install(upgrade=True)
        pending=json.loads((self.target/package.INTENT).read_text());shutil.rmtree(self.target/pending['stage'])
        with self.assertRaisesRegex(package.PackageError,'Previous package restored'):self.run_install(upgrade=True)
        self.assertEqual(package.verify(self.target/'appointment-system'),self.release);self.assertFalse((self.target/package.INTENT).exists())
        self.assertEqual(self.run_install(upgrade=True)['status'],'installed')

    def test_tampered_interrupted_staging_is_refused_and_valid_current_copy_is_not_deleted(self):
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');package.build(self.source)
        original=os.replace
        def interruption(source,target):
            if Path(source).name=='appointment-system':raise KeyboardInterrupt('Synthetic interruption')
            return original(source,target)
        with patch.object(package.os,'replace',side_effect=interruption),self.assertRaises(KeyboardInterrupt):self.run_install(upgrade=True)
        pending=json.loads((self.target/package.INTENT).read_text());(self.target/pending['stage']/'engine/appointment_system/application.py').write_text('VALUE=999\n')
        with self.assertRaises(package.PackageError):self.run_install(upgrade=True)
        self.assertEqual(package.verify(self.target/'appointment-system'),self.release);self.assertTrue((self.target/package.INTENT).exists())

    def test_empty_or_different_copy_set_cannot_claim_identical_release(self):
        with self.assertRaises(package.PackageError):package.identical()
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');package.build(self.source)
        with self.assertRaises(package.PackageError):package.identical(self.source,self.target/'appointment-system')
        with self.assertRaises(package.PackageError):package.install(self.source,self.target,**(self.options|{'expected_root':self.root}))

    def test_package_limits_and_non_repository_target_are_rejected(self):
        huge=self.source/'engine/large.py'
        with huge.open('wb') as handle:handle.truncate(8*1024*1024+1)
        with self.assertRaisesRegex(package.PackageError,'Unexpected package file'):package.inventory(self.source)
        huge.unlink()
        with patch.object(package.subprocess,'run',side_effect=OSError('synthetic missing git')):
            with self.assertRaisesRegex(package.PackageError,'Git root'):self.run_install()
        inside=self.target/'nested-master';shutil.copytree(self.source,inside)
        with self.assertRaisesRegex(package.PackageError,'inside the target'):package.install(inside,self.target,**self.options)

    def test_interrupted_install_rechecks_rollback_and_resumes_without_replacing_valid_current_copy(self):
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');package.build(self.source)
        original=os.replace
        def interruption(source,target):
            if Path(source).name=='appointment-system':raise KeyboardInterrupt('Synthetic interruption')
            return original(source,target)
        with patch.object(package.os,'replace',side_effect=interruption),self.assertRaises(KeyboardInterrupt):self.run_install(upgrade=True)
        journal=self.target/package.INTENT;pending=json.loads(journal.read_text());rollback=self.target/pending['rollback'];staged=self.target/pending['stage']
        # A separately occupied rollback destination must never be overwritten.
        rollback.mkdir()
        with self.assertRaisesRegex(package.PackageError,'Unexpected package'):self.run_install(upgrade=True)
        rollback.rmdir()
        original(self.target/'appointment-system',rollback);shutil.copytree(staged,self.target/'appointment-system')
        report=self.run_install(upgrade=True)
        self.assertEqual(report['status'],'resumed');self.assertFalse(staged.exists());self.assertFalse(journal.exists())
        self.assertEqual(package.verify(rollback),self.release)

    def test_interrupted_stage_digest_or_rebound_settings_never_replace_existing_records(self):
        original=os.replace
        def interruption(source,target):raise KeyboardInterrupt('Synthetic initial interruption')
        with patch.object(package.os,'replace',side_effect=interruption),self.assertRaises(KeyboardInterrupt):self.run_install()
        journal=self.target/package.INTENT;pending=json.loads(journal.read_text());staged=self.target/pending['stage']
        (staged/'engine/appointment_system/application.py').write_text('VALUE=999\n');package.build(staged)
        with self.assertRaisesRegex(package.PackageError,'staged package differs'):self.run_install()
        self.assertTrue(journal.exists());self.assertFalse((self.target/'appointment-system').exists())
        shutil.rmtree(staged);journal.unlink()
        with self.assertRaisesRegex(package.PackageError,'missing package'):self.run_install(upgrade=True)

    def test_native_windows_lock_is_released_even_when_installer_raises(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        lock=Mock();native=SimpleNamespace(locking=lock,LK_NBLCK=1,LK_UNLCK=2)
        with patch.object(package,'os',SimpleNamespace(name='nt')),patch.dict('sys.modules',{'msvcrt':native}):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'synthetic write'):
                    with package.locked(self.target):raise RuntimeError('synthetic write')
        self.assertEqual([c.args[1:] for c in lock.call_args_list],[(1,1),(2,1),(1,1),(2,1)])
        self.assertEqual((self.target/'.appointment-install.lock').read_bytes(),b'0')
