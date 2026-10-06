"""Contained release equality, unsafe inputs and interrupted whole-copy upgrades."""
import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.install.package import build,verify,install,identical,PackageError,INTENT
from .fixtures import installation,business

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'master';(self.source/'engine/appointment_system').mkdir(parents=True)
        (self.source/'engine/appointment_system/application.py').write_text('VALUE=1\n')
        (self.source/'requirements.txt').write_text('fastapi==0.142.2\n')
        self.release=build(self.source)
        self.target=self.root/'client';self.target.mkdir()
        subprocess.run(['git','init','-q',str(self.target)],check=True)
        settings=self.target/'appointment-settings';settings.mkdir()
        (settings/'project.json').write_text(json.dumps(installation()));(settings/'business-settings.json').write_text(json.dumps(business()))
        self.options=dict(expected_root=self.target,installation_id=installation()['installation_id'],project_id=installation()['project_id'])

    def run_install(self,**changes):return install(self.source,self.target,**(self.options|changes))

    def test_releases_are_deterministic_and_all_copies_match(self):
        self.assertEqual(build(self.source),self.release)
        report=self.run_install();self.assertEqual(report['status'],'installed')
        self.assertEqual(identical(self.source,self.target/'appointment-system'),self.release['content_digest'])
        self.assertEqual(self.run_install()['status'],'existing')

    def test_unrelated_dirty_files_and_settings_are_preserved_on_upgrade(self):
        page=self.target/'website.html';page.write_text('existing user work')
        settings=(self.target/'appointment-settings/project.json').read_bytes();self.run_install()
        (self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');build(self.source,release='1.0.0-rc.2')
        with self.assertRaises(PackageError):self.run_install()
        report=self.run_install(upgrade=True)
        self.assertEqual(page.read_text(),'existing user work');self.assertEqual((self.target/'appointment-settings/project.json').read_bytes(),settings)
        self.assertEqual(verify(self.target/report['rollback'])['content_digest'],self.release['content_digest'])

    def test_file_tampering_and_extra_executable_or_secret_file_are_rejected(self):
        application=self.source/'engine/appointment_system/application.py';application.write_text('VALUE=99\n')
        with self.assertRaises(PackageError):self.run_install()
        application.write_text('VALUE=1\n');extra=self.source/'engine/appointment_system/extra.py';extra.write_text('VALUE=3')
        with self.assertRaises(PackageError):verify(self.source)
        extra.unlink();(self.source/'.env').write_text('synthetic private setting')
        with self.assertRaises(PackageError):build(self.source)

    def test_manifest_duplicates_boolean_contracts_and_path_traversal_are_rejected(self):
        path=self.source/'release.json';original=path.read_text()
        for mutation in ('duplicate','boolean','traversal','digest'):
            if mutation=='duplicate':value=original.rstrip()[:-1]+',"format_version":1}'
            else:
                data=json.loads(original)
                if mutation=='boolean':data['engine_contract']=True
                elif mutation=='traversal':data['files']['../foreign.py']={'sha256':'a'*64,'bytes':1}
                else:data['content_digest']='a'*64
                value=json.dumps(data)
            path.write_text(value)
            with self.assertRaises(PackageError):verify(self.source)
        path.write_text(original)

    def test_source_target_and_nested_repository_links_are_forbidden(self):
        nested=self.target/'nested';nested.mkdir()
        with self.assertRaises(PackageError):install(self.source,nested,**(self.options|{'expected_root':nested}))
        link=self.root/'linked';link.symlink_to(self.target,target_is_directory=True)
        with self.assertRaises(PackageError):install(self.source,link,**(self.options|{'expected_root':link}))
        (self.source/'engine/appointment_system/link.py').symlink_to(self.source/'engine/appointment_system/application.py')
        with self.assertRaises(PackageError):build(self.source)

    def test_wrong_installation_missing_settings_and_unrecognized_package_are_rejected(self):
        with self.assertRaises(PackageError):self.run_install(project_id='foreign-project')
        path=self.target/'appointment-settings/business-settings.json';saved=path.read_bytes();path.unlink()
        with self.assertRaises(PackageError):self.run_install()
        path.write_bytes(saved);(self.target/'appointment-system').mkdir()
        with self.assertRaises(PackageError):self.run_install(upgrade=True)

    def test_interrupted_upgrade_resumes_before_or_after_old_directory_move(self):
        for before_move in (True,False):
            if (self.target/'appointment-system').exists():shutil.rmtree(self.target/'appointment-system')
            (self.source/'engine/appointment_system/application.py').write_text('VALUE=1\n');build(self.source);self.run_install()
            (self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');build(self.source,release='1.0.0-rc.2')
            import os
            replace=os.replace
            def power_outage(source,target):
                if (before_move and Path(source).name=='appointment-system') or (not before_move and Path(source).name.startswith('.appointment-stage-')):
                    raise KeyboardInterrupt('Synthetic power outage')
                return replace(source,target)
            with patch('tools.install.package.os.replace',side_effect=power_outage):
                with self.assertRaises(KeyboardInterrupt):self.run_install(upgrade=True)
            self.assertTrue((self.target/INTENT).exists())
            report=self.run_install(upgrade=True);self.assertEqual(report['status'],'resumed')
            self.assertFalse((self.target/INTENT).exists());identical(self.source,self.target/'appointment-system')

    def test_failed_activation_restores_previous_package(self):
        self.run_install();(self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');build(self.source,release='1.0.0-rc.2')
        import os
        replace=os.replace
        def fail_stage(source,target):
            if Path(source).name.startswith('.appointment-stage-'):raise OSError('Synthetic rename failure')
            return replace(source,target)
        with patch('tools.install.package.os.replace',side_effect=fail_stage):
            with self.assertRaises(OSError):self.run_install(upgrade=True)
        self.assertEqual(verify(self.target/'appointment-system')['content_digest'],self.release['content_digest'])

    def test_malformed_explicit_identity_is_rejected_before_any_install(self):
        for value in (None,True,42,'bad','00000000-0000-0000-0000-000000000000'):
            with self.subTest(value=value),self.assertRaises(PackageError):self.run_install(installation_id=value)
        for value in (None,True,42,'Mixed Name','../foreign'):
            with self.subTest(value=value),self.assertRaises(PackageError):self.run_install(project_id=value)
        self.assertFalse((self.target/'appointment-system').exists())

    def test_changed_settings_during_staging_preserve_previous_package_and_user_work(self):
        self.run_install();owner=self.target/'owner-page.txt';owner.write_text('Preserve this page')
        (self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');build(self.source,release='1.0.0-rc.2')
        copy=shutil.copyfile;changed=False
        def change_settings(source,target):
            nonlocal changed
            result=copy(source,target)
            if not changed:
                path=self.target/'appointment-settings/business-settings.json';spec=json.loads(path.read_text())
                spec['notice_minutes']=45;path.write_text(json.dumps(spec));changed=True
            return result
        with patch('tools.install.package.shutil.copyfile',side_effect=change_settings):
            with self.assertRaisesRegex(PackageError,'settings changed'):self.run_install(upgrade=True)
        self.assertEqual(verify(self.target/'appointment-system')['content_digest'],self.release['content_digest'])
        self.assertEqual(owner.read_text(),'Preserve this page');self.assertFalse((self.target/INTENT).exists())
