"""Exercise the distributed installer commands against disposable project folders."""
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
import runpy
import sys
import unittest
from unittest.mock import patch
from tools.install import package
from . import test_package as fixtures

class PackageCommandBoundaries(unittest.TestCase):
 setUp=fixtures.PackageTests.setUp
 def command(self,*args):
  output=StringIO()
  with patch.object(sys,'argv',['package',*map(str,args)]),redirect_stdout(output):
   runpy.run_module('tools.install.package',run_name='__main__')
  return json.loads(output.getvalue())
 def test_build_verify_install_and_identical_commands_preserve_project_binding(self):
  release=self.command('build',self.source);self.assertNotIn('files',release)
  self.assertEqual(self.command('verify',self.source),release)
  installed=self.command('install',self.source,'--target',self.target,'--expected-root',self.target,'--installation-id',self.options['installation_id'],'--project-id',self.options['project_id'])
  self.assertEqual(installed['status'],'installed')
  same=self.command('identical',self.source,'--target',self.target/'appointment-system');self.assertEqual(same['content_digest'],release['content_digest'])
 def test_upgrade_command_retains_previous_package_and_missing_target_is_refused(self):
  self.command('install',self.source,'--target',self.target,'--expected-root',self.target,'--installation-id',self.options['installation_id'],'--project-id',self.options['project_id'])
  (self.source/'engine/appointment_system/application.py').write_text('VALUE=2\n');self.command('build',self.source,'--release','1.0.0-rc.2')
  result=self.command('upgrade',self.source,'--target',self.target,'--expected-root',self.target,'--installation-id',self.options['installation_id'],'--project-id',self.options['project_id'])
  self.assertEqual(package.verify(self.target/result['rollback']),self.release)
  with redirect_stderr(StringIO()),self.assertRaises(SystemExit) as error:self.command('install',self.source)
  self.assertEqual(error.exception.code,2)
