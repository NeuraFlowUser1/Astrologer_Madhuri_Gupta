"""Configured branch acceptance and refusal through actual operational commands."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from appointment_system.backup.protocol import BackupError
from tools.automation import backup, eligibility, monitor, trigger
from tools.automation.production import (
    ProductionBranchError, branch_name, configuration_branch, render_workflow,
)
from tools.install.monitor import prepare
from tools.install.package import PackageError
from . import test_monitor as monitor_fixtures
from . import test_monitor_install as install_fixtures
from . import test_backup_automation_commands as backup_fixtures
from . import test_backup_trigger as trigger_fixtures


ROOT = Path(__file__).resolve().parents[1]


class ProductionBranchContract(unittest.TestCase):
    def helper(self, kind):
        value = kind()
        value.setUp()
        self.addCleanup(value.doCleanups)
        return value

    def test_bounded_ascii_names_also_pass_actual_git_branch_validation(self):
        for name in ('main', 'prod', 'release/prod-v2', 'Prod_2.1', 'a' * 200):
            with self.subTest(name=name):
                self.assertEqual(branch_name(name), name)
                checked = subprocess.run(['git', 'check-ref-format', '--branch', name],
                                         capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stderr)
        for name in (None, True, 1, '', 'a' * 201, 'HEAD', '-prod', '.prod', 'a..b',
                     'a//b', '/prod', 'prod/', 'a/.private', 'a/end.', 'a/file.lock',
                     'a/file.LOCK', 'prod\n', 'prod name', 'prod:other', 'a@{1}',
                     'refs/*', '$(printf synthetic)', 'a[prod]'):
            with self.subTest(name=name), self.assertRaisesRegex(ProductionBranchError, 'branch_invalid'):
                branch_name(name)

    def test_version_one_stays_main_and_version_two_is_explicit_without_unknown_keys(self):
        fields = {'version', 'repository'}
        self.assertEqual(configuration_branch({'version': 1, 'repository': 'Owner/Repo'}, fields), 'main')
        self.assertEqual(configuration_branch(
            {'version': 2, 'repository': 'Owner/Repo', 'production_branch': 'prod'}, fields), 'prod')
        invalid = [None, [], {}, {'version': True, 'repository': 'Owner/Repo'},
                   {'version': 1.0, 'repository': 'Owner/Repo'},
                   {'version': 3, 'repository': 'Owner/Repo'},
                   {'version': 2, 'repository': 'Owner/Repo'},
                   {'version': 1, 'repository': 'Owner/Repo', 'production_branch': 'prod'},
                   {'version': 2, 'repository': 'Owner/Repo', 'production_branch': 'prod', 'extra': 1},
                   {'version': 2, 'production_branch': 'prod'},
                   {'version': 2, 'repository': 'Owner/Repo', 'production_branch': False}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ProductionBranchError):
                configuration_branch(value, fields)

    def test_three_trusted_workflows_pin_guards_and_source_filter_to_the_same_branch(self):
        for name in ('appointment-background-monitor.yml', 'appointment-database-backup.yml',
                     'appointment-backup-validation.yml'):
            body = (ROOT / 'deploy/workflows' / name).read_bytes()
            self.assertEqual(render_workflow(name, body), body)
            for branch in ('prod', 'release/prod-v2'):
                rendered = render_workflow(name, body, branch).decode()
                self.assertNotIn('refs/heads/main', rendered)
                self.assertIn("github.ref == 'refs/heads/" + branch + "'", rendered)
                self.assertIn("github.event.repository.visibility == 'public'", rendered)
                self.assertIn("github.event.repository.fork) == 'false'", rendered)
                if name == 'appointment-backup-validation.yml':
                    self.assertIn('branches: [' + branch + ']', rendered)
                    self.assertEqual(rendered.count("github.ref == 'refs/heads/" + branch + "'"), 2)
            for invalid in (None, b'\xff', body.replace(b'refs/heads/main', b'refs/heads/foreign'),
                            body + b'\n# refs/heads/foreign'):
                with self.assertRaisesRegex(ProductionBranchError, 'workflow_invalid'):
                    render_workflow(name, invalid, 'prod')
        with self.assertRaises(ProductionBranchError):
            render_workflow('foreign.yml', b'', 'prod')
        with self.assertRaises(ProductionBranchError):
            render_workflow([], b'', 'prod')

    def test_backup_eligibility_pins_repository_event_runner_and_source_to_prod(self):
        repository = {'full_name': 'Owner/Repo', 'default_branch': 'prod', 'visibility': 'public',
                      'private': False, 'fork': False, 'archived': False, 'disabled': False}
        environment = {'GITHUB_REPOSITORY': 'Owner/Repo', 'GITHUB_REF': 'refs/heads/prod',
                       'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux'}
        source = {'path': eligibility.WORKFLOW, 'head_branch': 'prod', 'status': 'completed',
                  'conclusion': 'success', 'event': 'schedule', 'repository': repository,
                  'head_repository': repository, 'id': 123, 'run_attempt': 1, 'head_sha': 'a' * 40}
        eligibility.eligible(repository, 'Owner/Repo', branch='prod')
        eligibility.runner(environment, 'Owner/Repo', {'repository': repository}, branch='prod')
        self.assertEqual(eligibility.source_run(source, repository, 'Owner/Repo', '123', branch='prod'),
                         ('123', '1', 'a' * 40))
        for change in ({'default_branch': 'main'}, {'private': True}, {'fork': True},
                       {'full_name': 'Foreign/Repo'}, {'disabled': True}):
            with self.assertRaises(BackupError):
                eligibility.eligible(repository | change, 'Owner/Repo', branch='prod')
        for ref in ('refs/heads/main', 'refs/heads/dev', 'refs/tags/prod', 'refs/pull/1/merge'):
            with self.assertRaises(BackupError):
                eligibility.runner(environment | {'GITHUB_REF': ref}, 'Owner/Repo',
                                   {'repository': repository}, branch='prod')
        for change in ({'head_branch': 'main'}, {'conclusion': 'failure'}, {'event': 'pull_request'},
                       {'head_repository': {'full_name': 'Foreign/Repo'}}):
            with self.assertRaises(BackupError):
                eligibility.source_run(source | change, repository, 'Owner/Repo', '123', branch='prod')
        for branch in (None, False, 'a..b'):
            with self.assertRaisesRegex(BackupError, 'branch_invalid'):
                eligibility.eligible(repository, 'Owner/Repo', branch=branch)

    def test_actual_prod_monitor_checks_fresh_default_before_reading_any_health(self):
        helper = self.helper(monitor_fixtures.MonitorTests)
        path = helper.settings / 'monitor.json'
        config = json.loads(path.read_text()) | {'version': 2, 'production_branch': 'prod'}
        path.write_text(json.dumps(config))
        helper.repository['default_branch'] = 'prod'
        helper.event.write_text(json.dumps({'repository': helper.repository, 'schedule': monitor.CRON}))
        helper.env['GITHUB_REF'] = 'refs/heads/prod'
        self.assertEqual(helper.run_monitor(), {'status': 'healthy', 'booking_enabled': False})
        self.assertEqual(len(helper.calls), 5)
        helper.calls.clear()
        for ref in ('refs/heads/main', 'refs/heads/dev', 'refs/tags/prod'):
            with self.assertRaisesRegex(monitor.MonitorError, 'runner'):
                helper.run_monitor(helper.env | {'GITHUB_REF': ref})
        self.assertEqual(helper.calls, [])
        url = 'https://api.github.com/repos/' + helper.repository['full_name']
        helper.responses[url] = helper.repository | {'default_branch': 'main'}
        with self.assertRaisesRegex(monitor.MonitorError, 'repository'):
            helper.run_monitor()
        self.assertEqual(len(helper.calls), 1)
        for invalid in ({'version': 2}, {'version': 1, 'production_branch': 'prod'},
                        {'version': 2, 'production_branch': False}):
            body = dict(config)
            body.pop('production_branch')
            body.update(invalid)
            path.write_text(json.dumps(body))
            with self.assertRaisesRegex(monitor.MonitorError, 'profile'):
                monitor.public(helper.settings / 'project.json')
        with self.assertRaisesRegex(monitor.MonitorError, 'profile'):
            monitor.eligible(helper.repository, helper.repository['full_name'], branch=False)

    def test_actual_backup_source_selection_rechecks_configured_branch_for_all_duties(self):
        helper = self.helper(backup_fixtures.BackupCommandBoundaries)
        config = helper.config | {'version': 2, 'production_branch': 'prod'}
        repository = helper.base.repo | {'default_branch': 'prod'}
        record = helper.base.run | {'head_branch': 'prod'}
        environment = helper.base.env | {'GITHUB_REF': 'refs/heads/prod', 'GITHUB_EVENT_NAME': 'schedule',
            'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'a' * 40, 'GITHUB_TOKEN': 'synthetic'}
        event = {'repository': repository, 'schedule': config['cron']}
        args = SimpleNamespace(source_run='123', source_attempt='1', source_commit='a' * 40)
        with patch.object(backup, 'github_read', side_effect=[repository]):
            self.assertEqual(backup.checked_source(environment, event, config, 'export', args),
                             ('123', '1', 'a' * 40))
        for mode in ('validate', 'retain'):
            with patch.object(backup, 'github_read', side_effect=[repository, record]):
                self.assertEqual(backup.checked_source(environment | {'GITHUB_EVENT_NAME': 'workflow_run'},
                    event | {'workflow_run': {'id': 123}}, config, mode, args), ('123', '1', 'a' * 40))
        with patch.object(backup, 'github_read', return_value=repository | {'default_branch': 'main'}):
            with self.assertRaises(BackupError):
                backup.checked_source(environment, event, config, 'export', args)
        with patch.object(backup, 'github_read') as read:
            with self.assertRaises(BackupError):
                backup.checked_source(environment | {'GITHUB_REF': 'refs/heads/main'}, event, config, 'export', args)
            read.assert_not_called()

    def test_actual_trigger_never_promotes_an_old_main_run_to_prod_authority(self):
        helper = self.helper(trigger_fixtures.BackupTriggerTests)
        helper.repository['default_branch'] = 'prod'
        helper.record['head_branch'] = 'prod'
        helper.event['repository'] = deepcopy(helper.repository)
        helper.environment['GITHUB_REF'] = 'refs/heads/prod'
        trigger.public_settings.return_value = {'repository': 'Owner/SyntheticProject',
                                                'production_branch': 'prod'}
        helper.run_trigger()
        self.assertIn('source_run=123', helper.output.read_text())
        helper.output.unlink()
        helper.record['head_branch'] = 'main'
        with self.assertRaises(BackupError):
            helper.run_trigger()
        self.assertFalse(helper.output.exists())

    def test_monitor_preparation_renders_prod_and_preserves_existing_owner_main_files(self):
        helper = self.helper(install_fixtures.MonitorPreparation)
        report = prepare(helper.project, expected_root=helper.project, repository=helper.repository,
                         production_branch='prod')
        config = json.loads(helper.config.read_text())
        self.assertEqual((config['version'], config['production_branch']), (2, 'prod'))
        self.assertIn(b"refs/heads/prod", helper.workflow.read_bytes())
        self.assertNotIn(b"refs/heads/main", helper.workflow.read_bytes())
        self.assertFalse(report['published'])
        before = [helper.config.read_bytes(), helper.workflow.read_bytes()]
        with self.assertRaisesRegex(PackageError, 'existing monitoring'):
            helper.prepare()
        self.assertEqual(before, [helper.config.read_bytes(), helper.workflow.read_bytes()])
        with self.assertRaisesRegex(PackageError, 'valid production branch'):
            prepare(helper.project, expected_root=helper.project, repository=helper.repository,
                    production_branch='prod\n')



    def test_version_two_backup_file_is_validated_before_source_selection(self):
        helper = self.helper(backup_fixtures.BackupCommandBoundaries)
        config = helper.config | {'version': 2, 'production_branch': 'prod'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'appointment-system'
            package.mkdir()
            settings = root / 'appointment-settings'
            settings.mkdir()
            profile = settings / 'project.json'
            profile.write_text('{}')
            saved = settings / 'backup.json'
            with patch.object(backup, 'ROOT', package), patch.object(backup, 'load'), patch.object(
                    backup, 'installation', return_value=helper.facts):
                saved.write_text(json.dumps(config))
                self.assertEqual(backup.public_settings(profile), config)
                for change in ({'version': 1}, {'production_branch': False}, {'extra': 1},
                               {'owner_email': 'foreign@example.test'}):
                    saved.write_text(json.dumps(config | change))
                    with self.assertRaises(BackupError):
                        backup.public_settings(profile)
                missing = dict(config)
                del missing['production_branch']
                saved.write_text(json.dumps(missing))
                with self.assertRaises(BackupError):
                    backup.public_settings(profile)

    def test_production_cli_flag_and_invalid_template_refuse_without_disclosing_input(self):
        import contextlib
        import io
        import runpy
        import sys
        import warnings
        helper = self.helper(install_fixtures.MonitorPreparation)
        argv = ['tools.install.monitor', str(helper.project), '--expected-root', str(helper.project),
                '--repository', helper.repository, '--production-branch', 'prod']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as output:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                runpy.run_module('tools.install.monitor', run_name='__main__')
        self.assertFalse(json.loads(output.getvalue())['published'])
        self.assertEqual(json.loads(helper.config.read_text())['production_branch'], 'prod')
        with patch.object(sys, 'argv', argv[:-1] + ['private invalid branch']):
            with warnings.catch_warnings(), self.assertRaises(SystemExit) as caught:
                warnings.simplefilter('ignore', RuntimeWarning)
                runpy.run_module('tools.install.monitor', run_name='__main__')
        self.assertNotIn('private invalid branch', str(caught.exception))
        helper.config.unlink()
        helper.workflow.unlink()
        template = helper.package / 'deploy/workflows/appointment-background-monitor.yml'
        template.write_text('malformed managed workflow')
        from tools.install.package import build
        build(helper.package)
        with self.assertRaisesRegex(PackageError, 'workflow is invalid'):
            prepare(helper.project, expected_root=helper.project, repository=helper.repository,
                    production_branch='prod')
        self.assertFalse(helper.config.exists())
        self.assertFalse(helper.workflow.exists())
if __name__ == '__main__':
    unittest.main()
