"""Prepare the common observer locally, without account access or publication."""
from pathlib import Path
import json
import os
import tempfile
from appointment_system.serialization import decode
from appointment_system.settings import Installation
from appointment_system.backup.protocol import BackupError
from tools.automation.eligibility import repository_name
from tools.automation.monitor import CRON
from .package import PackageError,git_root,locked,verify

WORKFLOW='appointment-background-monitor.yml'


def _contained(root,path):
    if root not in path.parents or any(item.is_symlink() for item in (path,*path.parents)):
        raise PackageError('Monitor files must stay in their own project.')
    if path.exists() and not path.is_file():raise PackageError('Monitor target must be a file.')


def prepare(target,*,expected_root,repository):
    try:repository_name(repository)
    except BackupError:raise PackageError('An explicit owned repository name is required.') from None
    root=git_root(target,expected_root)
    with locked(root):
        package=root/'appointment-system';release=verify(package)
        profile=root/'appointment-settings/project.json';_contained(root,profile)
        if not profile.is_file() or profile.stat().st_size>131072:
            raise PackageError('Explicit project settings are required.')
        raw=profile.read_bytes();facts=Installation.parse(decode(raw)).document
        if facts['environment']!='production':
            raise PackageError('Scheduled monitoring requires a production profile.')
        config={'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],
                'repository':repository,'cron':CRON}
        template=package/'deploy/workflows'/WORKFLOW
        if not template.is_file():
            raise PackageError('The contained monitoring workflow is missing.')
        files={root/'appointment-settings/monitor.json':(json.dumps(config,indent=2)+'\n').encode(),
               root/'.github/workflows'/WORKFLOW:template.read_bytes()}
        # Refuse changed owner work before creating either output. Interrupted
        # preparation can resume already-complete, byte-identical files.
        for path,body in files.items():
            _contained(root,path)
            if path.exists() and path.read_bytes()!=body:
                raise PackageError('Review the existing monitoring configuration first.')
        if profile.read_bytes()!=raw or verify(package)!=release:
            raise PackageError('The project changed during preparation.')
        for path,body in files.items():
            _contained(root,path)
            if path.exists():
                if path.read_bytes()!=body:
                    raise PackageError('The monitoring configuration changed during preparation.')
                continue
            path.parent.mkdir(parents=True,exist_ok=True);_contained(root,path)
            descriptor,temporary=tempfile.mkstemp(prefix='.monitor-prepare-',dir=path.parent)
            try:
                with os.fdopen(descriptor,'wb') as stream:
                    stream.write(body);stream.flush();os.fsync(stream.fileno())
                # Atomic creation, never overwrite a concurrently created file.
                os.link(temporary,path)
            finally:Path(temporary).unlink(missing_ok=True)
        if profile.read_bytes()!=raw or verify(package)!=release:
            raise PackageError('The project changed during preparation.')
        for path,body in files.items():
            _contained(root,path)
            if not path.is_file() or path.read_bytes()!=body:
                raise PackageError('The monitoring configuration changed during preparation.')
        return {'status':'prepared','release_digest':release['content_digest'],'repository':repository,
                'cron':CRON,'environment':'appointment-monitor','secret_names':['BOOKING_MONITOR_KEY'],
                'repository_variables':{'BOOKING_REPOSITORY':repository},'published':False}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Prepare contained monitoring files only; no network or publication.')
    parser.add_argument('target',type=Path);parser.add_argument('--expected-root',required=True,type=Path)
    parser.add_argument('--repository',required=True)
    args=parser.parse_args()
    try:result=prepare(args.target,expected_root=args.expected_root,repository=args.repository)
    except (ValueError,OSError):raise SystemExit('Monitor preparation refused. Review the owned project and existing files.') from None
    print(json.dumps(result,sort_keys=True))
