"""Explicit production-branch metadata and trusted workflow rendering.

Only bounded ASCII Git-compatible names are accepted. Version 1 keeps its
original main-only contract; version 2 must declare its production branch.
This module deliberately has no engine, database or provider imports.
"""
import re


class ProductionBranchError(ValueError):
    pass


def branch_name(value):
    if (type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', value)
            or value == 'HEAD' or '..' in value):
        raise ProductionBranchError('automation_branch_invalid')
    for part in value.split('/'):
        if not part or part.startswith('.') or part.endswith('.') or part.lower().endswith('.lock'):
            raise ProductionBranchError('automation_branch_invalid')
    return value


def configuration_branch(value, fields):
    if type(value) is not dict or type(value.get('version')) is not int or value['version'] not in (1, 2):
        raise ProductionBranchError('automation_branch_configuration_invalid')
    expected = set(fields) | ({'production_branch'} if value['version'] == 2 else set())
    if set(value) != expected:
        raise ProductionBranchError('automation_branch_configuration_invalid')
    return branch_name(value['production_branch']) if value['version'] == 2 else 'main'


WORKFLOWS = {
    'appointment-background-monitor.yml': (1, 0),
    'appointment-database-backup.yml': (1, 0),
    'appointment-backup-validation.yml': (2, 1),
}


def render_workflow(name, body, production_branch='main'):
    branch = branch_name(production_branch)
    if type(name) is not str or name not in WORKFLOWS or type(body) is not bytes:
        raise ProductionBranchError('automation_workflow_invalid')
    try:
        text = body.decode('utf-8')
    except UnicodeError:
        raise ProductionBranchError('automation_workflow_invalid') from None
    guards, filters = WORKFLOWS[name]
    if (text.count("github.ref == 'refs/heads/main'") != guards
            or text.count('refs/heads/') != guards
            or text.count('branches: [main]') != filters):
        raise ProductionBranchError('automation_workflow_invalid')
    if branch == 'main':
        return body
    return text.replace('refs/heads/main', 'refs/heads/' + branch).replace(
        'branches: [main]', 'branches: [' + branch + ']').encode('utf-8')
