"""Create the small project-owned entry point; never import a factory checkout."""
from pathlib import Path
from .package import PackageError,git_root,verify

ENTRY = '''"""Project-contained appointment application; no account work runs on import."""
import os
import sys
from pathlib import Path

entry = Path(__file__).absolute()
if any(path.is_symlink() for path in (entry, *entry.parents)):
    raise RuntimeError("Project entry point links are forbidden.")
project = entry.parents[1]
package = project / "appointment-system"
sys.path[:0] = [str(package), str(package / "engine")]
from appointment_system.runtime import create_application

app = create_application(project / "appointment-settings/project.json", dict(os.environ))
'''


def prepare(target, *, expected_root):
    root=git_root(target,expected_root)
    release=verify(root/'appointment-system')
    directory=root/'api'
    if directory.is_symlink():raise PackageError('Project entry directory links are forbidden.')
    directory.mkdir(exist_ok=True)
    path=directory/'index.py'
    if path.is_symlink():raise PackageError('Project entry point links are forbidden.')
    if path.exists():
        if not path.is_file() or path.read_bytes()!=ENTRY.encode():
            raise PackageError('Review and replace the existing host entry point explicitly.')
        status='existing'
    else:
        with path.open('xb') as handle:handle.write(ENTRY.encode())
        status='created'
    return {'status':status,'entry':'api/index.py','release_digest':release['content_digest']}


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description='Prepare a contained project entry point; no deployment or account change.')
    parser.add_argument('target',type=Path);parser.add_argument('--expected-root',required=True,type=Path)
    args=parser.parse_args()
    try:result=prepare(args.target,expected_root=args.expected_root)
    except (PackageError,OSError):raise SystemExit('Host preparation refused. Verify the project and review any existing entry point.') from None
    print(json.dumps(result,sort_keys=True))
