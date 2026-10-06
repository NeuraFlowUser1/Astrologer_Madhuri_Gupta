"""Contained monitor preparation preserves owner files and never contacts a provider."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from tools.install.package import build,install,verify,PackageError
from tools.install.monitor import prepare,WORKFLOW
from tools.automation import monitor
from . import test_host_source as hosting


class MonitorPreparation(unittest.TestCase):
    def setUp(self):
        hosting.HostingSource.setUp(self)
        self.patch.stop()  # The hosting-export temp-folder hook is unrelated here.
        self.package=self.project/'appointment-system'
        workflow=self.master/'deploy/workflows'/WORKFLOW;workflow.parent.mkdir(parents=True)
        actual=Path(__file__).resolve().parents[1]/'deploy/workflows'/WORKFLOW
        shutil.copyfile(actual,workflow);build(self.master)
        facts=json.loads((self.project/'appointment-settings/project.json').read_text())
        facts['environment']='production';(self.project/'appointment-settings/project.json').write_text(json.dumps(facts))
        install(self.master,self.project,expected_root=self.project,installation_id=facts['installation_id'],
            project_id=facts['project_id'],upgrade=True)
        self.repository='ExampleOwner/Practice';self.config=self.project/'appointment-settings/monitor.json'
        self.workflow=self.project/'.github/workflows'/WORKFLOW

    def save(self,**changes):hosting.HostingSource.save(self,**changes)

    def prepare(self):return prepare(self.project,expected_root=self.project,repository=self.repository)

    def test_prepared_profile_passes_actual_observer_validation_and_rerun_preserves_bytes(self):
        with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            report=self.prepare();first=[self.config.read_bytes(),self.workflow.read_bytes()]
            self.assertEqual(self.prepare(),report)
        self.assertFalse(report['published']);self.assertEqual(first,[self.config.read_bytes(),self.workflow.read_bytes()])
        with patch.object(monitor,'ROOT',self.package):
            config,origins=monitor.public(self.config.with_name('project.json'))
        self.assertEqual(config['repository'],self.repository);self.assertEqual(config['cron'],'8,23,38,53 * * * *')
        self.assertEqual(len(origins),2)
        body=self.workflow.read_text()
        self.assertIn('github.event.repository.visibility == \'public\'',body)
        self.assertNotIn('BOOKING_DATABASE_URL',body)

    def test_owner_configuration_conflict_preserves_both_files(self):
        self.config.write_text('{"owner":"existing work"}')
        with self.assertRaisesRegex(PackageError,'existing monitoring'):self.prepare()
        self.assertFalse(self.workflow.exists());self.assertEqual(self.config.read_text(),'{"owner":"existing work"}')

    def test_changed_workflow_refuses_before_creating_settings(self):
        self.workflow.parent.mkdir(parents=True);self.workflow.write_text('existing workflow')
        with self.assertRaisesRegex(PackageError,'existing monitoring'):self.prepare()
        self.assertFalse(self.config.exists());self.assertEqual(self.workflow.read_text(),'existing workflow')

    def test_linked_workflow_directory_cannot_write_outside_project(self):
        outside=self.root/'outside';outside.mkdir();(self.project/'.github').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(PackageError):self.prepare()
        self.assertFalse(self.config.exists());self.assertEqual(list(outside.iterdir()),[])

    def test_invalid_repository_or_nonproduction_profile_creates_no_observer(self):
        for repository in ('../foreign','https://github.com/Owner/Repo','Owner/Repo\n'):
            self.repository=repository
            with self.assertRaises(ValueError):self.prepare()
        self.repository='ExampleOwner/Practice'
        path=self.config.with_name('project.json');facts=json.loads(path.read_text());facts['environment']='test';path.write_text(json.dumps(facts))
        with self.assertRaisesRegex(PackageError,'production profile'):self.prepare()
        self.assertFalse(self.config.exists());self.assertFalse(self.workflow.exists())

    def test_interrupted_creation_resumes_complete_files_without_overwriting(self):
        link=__import__('os').link;count=0
        def interrupt(*args):
            nonlocal count
            count+=1
            if count==2:raise OSError('Synthetic interruption')
            return link(*args)
        with patch('tools.install.monitor.os.link',side_effect=interrupt),self.assertRaises(OSError):self.prepare()
        first=self.config.read_bytes();self.assertFalse(self.workflow.exists())
        self.prepare();self.assertEqual(first,self.config.read_bytes());self.assertTrue(self.workflow.is_file())
        self.assertEqual(list(self.project.rglob('.monitor-prepare-*')),[])

    def test_profile_change_during_write_cannot_be_reported_as_prepared(self):
        link=__import__('os').link
        def change(*args):
            result=link(*args)
            path=self.config.with_name('project.json');facts=json.loads(path.read_text());facts['label']='Changed owner label'
            path.write_text(json.dumps(facts));return result
        with patch('tools.install.monitor.os.link',side_effect=change),self.assertRaisesRegex(PackageError,'project changed'):
            self.prepare()
        self.assertEqual(json.loads(self.config.with_name('project.json').read_text())['label'],'Changed owner label')

    def test_package_change_before_writing_is_refused_without_creating_files(self):
        calls=0
        def change(package):
            nonlocal calls
            calls+=1
            if calls==1:
                result=verify(package)
                return result
            # The preceding raw-profile read has already occurred. A changed
            # package identity during that boundary must prevent preparation.
            return verify(package)|{'content_digest':'0'*64}
        with patch('tools.install.monitor.verify',side_effect=change),self.assertRaisesRegex(PackageError,'project changed'):
            self.prepare()
        self.assertFalse(self.config.exists());self.assertFalse(self.workflow.exists())

    def test_concurrently_created_configuration_is_preserved_and_rejected(self):
        calls=0
        def change(package):
            nonlocal calls
            calls+=1
            result=verify(package)
            if calls==2:self.config.write_text('concurrent owner settings')
            return result
        with patch('tools.install.monitor.verify',side_effect=change),self.assertRaisesRegex(PackageError,'configuration changed'):
            self.prepare()
        self.assertEqual(self.config.read_text(),'concurrent owner settings');self.assertFalse(self.workflow.exists())

    def test_configuration_changed_after_creation_cannot_report_success(self):
        link=__import__('os').link
        def change(*args):
            result=link(*args)
            if Path(args[1])==self.workflow:self.config.write_text('concurrent owner replacement')
            return result
        with patch('tools.install.monitor.os.link',side_effect=change),self.assertRaisesRegex(PackageError,'configuration changed'):
            self.prepare()
        self.assertEqual(self.config.read_text(),'concurrent owner replacement')

    def test_missing_template_oversized_profile_and_directory_target_are_refused(self):
        workflow=self.package/'deploy/workflows'/WORKFLOW;body=workflow.read_bytes();workflow.unlink();build(self.package)
        with self.assertRaisesRegex(PackageError,'workflow is missing'):self.prepare()
        workflow.write_bytes(body);build(self.package)
        profile=self.config.with_name('project.json');raw=profile.read_bytes();profile.write_bytes(raw+b' '*131072)
        with self.assertRaisesRegex(PackageError,'Explicit project'):self.prepare()
        profile.write_bytes(raw);self.config.mkdir()
        with self.assertRaisesRegex(PackageError,'must be a file'):self.prepare()
        self.assertFalse(self.workflow.exists())

    def test_cli_returns_public_setup_names_and_redacts_invalid_input(self):
        root=Path(__file__).resolve().parents[1]
        import os
        env={k:v for k,v in os.environ.items() if not k.startswith(('BOOKING_','PG'))}
        env['PYTHONPATH']=str(root/'engine')+os.pathsep+str(root)
        command=[sys.executable,'-m','tools.install.monitor',str(self.project),'--expected-root',str(self.project),'--repository']
        result=subprocess.run(command+[self.repository],env=env,cwd=root,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(json.loads(result.stdout)['published'])
        invalid='synthetic-private-wrong-input'
        result=subprocess.run(command+[invalid],env=env,cwd=root,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertNotIn(invalid,result.stdout+result.stderr)
        self.assertNotIn('Traceback',result.stderr)
