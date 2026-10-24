"""Owned public/default-branch/standard-runner boundaries, independent of secrets."""
import re
from appointment_system.backup.protocol import BackupError
from appointment_system.backup.pipeline import run_identity
from tools.automation.production import branch_name,ProductionBranchError

WORKFLOW='.github/workflows/appointment-database-backup.yml'

def repository_name(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',value):
        raise BackupError('automation_repository_invalid')
    return value

def _branch(value):
    try:return branch_name(value)
    except ProductionBranchError:raise BackupError('automation_branch_invalid') from None

def eligible(repository,expected,*,branch='main'):
    branch=_branch(branch)
    repository_name(expected)
    if (type(repository) is not dict or repository.get('full_name')!=expected or repository.get('default_branch')!=branch
        or repository.get('visibility')!='public' or repository.get('private') is not False or repository.get('archived') is not False or repository.get('disabled') is not False
        or repository.get('fork') is not False):raise BackupError('automation_free_repository_required')

def runner(environment,expected,event,*,branch='main'):
    branch=_branch(branch)
    repository_name(expected)
    if (environment.get('GITHUB_REPOSITORY')!=expected or environment.get('GITHUB_REF')!='refs/heads/'+branch
        or environment.get('RUNNER_ENVIRONMENT')!='github-hosted' or environment.get('RUNNER_OS')!='Linux'
        or type(event) is not dict):raise BackupError('automation_runner_rejected')
    eligible(event.get('repository'),expected,branch=branch)

def source_run(value,repository,expected,run_id,*,branch='main'):
    branch=_branch(branch)
    eligible(repository,expected,branch=branch)
    if (type(value) is not dict or value.get('path')!=WORKFLOW or value.get('head_branch')!=branch
        or value.get('status')!='completed' or value.get('conclusion')!='success'
        or value.get('event') not in ('schedule','workflow_dispatch')
        or type(value.get('repository')) is not dict or value['repository'].get('full_name')!=expected
        or type(value.get('head_repository')) is not dict or value['head_repository'].get('full_name')!=expected
        or type(value.get('id')) is not int or type(value.get('run_attempt')) is not int):raise BackupError('backup_validator_trigger_rejected')
    identity=run_identity(str(value['id']),str(value['run_attempt']),value.get('head_sha'))
    if identity[0]!=run_id:raise BackupError('backup_validator_trigger_rejected')
    return identity
