"""Deterministic release manifests and independently contained package copies."""
from contextlib import contextmanager
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,shutil,subprocess,tempfile
from uuid import uuid4

DIRECTORIES={'engine','database','browser','worker','tools','deploy','tests','docs','contracts','hosting'}
ROOT_FILES={'requirements.txt','requirements-checks.txt','requirements.lock','requirements-checks.lock','README.md','.gitignore'}
IGNORED={'__pycache__','.pytest_cache','.coverage','coverage.json','coverage.xml','htmlcov','node_modules','.wrangler'}
FIELDS={'format_version','release','engine_contract','database_contract','worker_contract','runtime','files','content_digest'}
MANIFEST='release.json'
INTENT='.appointment-install-intent.json'
EXTENSIONS={'.py','.sql','.md','.mjs','.js','.json','.yml','.yaml','.ps1','.css','.html','.txt','.sh','.lock','.svg'}

class PackageError(ValueError):pass

def canonical(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def _pairs(values):
    result={}
    for key,value in values:
        if key in result:raise PackageError('Duplicate manifest field.')
        result[key]=value
    return result

def _path(value):
    if (type(value) is not str or len(value)>240 or not re.fullmatch(r'[A-Za-z0-9_./-]+',value)
        or value.startswith('/') or any(part in ('','.','..') for part in value.split('/'))):
        raise PackageError('Unsafe package path.')
    path=PurePosixPath(value)
    if path.suffix not in EXTENSIONS and value!='.gitignore':raise PackageError('Undeclared file type.')
    if (len(path.parts)==1 and value not in ROOT_FILES) or (len(path.parts)>1 and path.parts[0] not in DIRECTORIES):
        raise PackageError('Undeclared package file.')
    return value

def inventory(root):
    root=Path(root)
    if any(path.is_symlink() for path in (root,*root.parents)) or not root.is_dir():raise PackageError('A real package directory is required.')
    result={}
    for directory,folders,files in os.walk(root,followlinks=False):
        parent=Path(directory)
        for name in folders+files:
            if (parent/name).is_symlink():raise PackageError('Package links are forbidden.')
        folders[:]=[name for name in folders if name not in IGNORED]
        for name in files:
            relative=(parent/name).relative_to(root).as_posix()
            if name in IGNORED or relative==MANIFEST:continue
            _path(relative)
            path=parent/name
            if not path.is_file() or path.stat().st_size>8*1024*1024:raise PackageError('Unexpected package file.')
            data=path.read_bytes()
            result[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    if not result or 'engine/appointment_system/application.py' not in result:raise PackageError('Package is incomplete.')
    return dict(sorted(result.items()))

def build(root,*,release='1.0.0-rc.1'):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[1-9][0-9]*)?',release):raise PackageError('Invalid release name.')
    result=dict(format_version=1,release=release,engine_contract=1,database_contract=1,worker_contract=1,
        runtime={'python':'3.12','node':'22','postgres':[16,18]},files=inventory(root))
    result['content_digest']=hashlib.sha256(canonical(result)).hexdigest()
    path=Path(root)/MANIFEST
    if path.is_symlink():raise PackageError('Package links are forbidden.')
    path.write_bytes(canonical(result)+b'\n')
    return result

def verify(root):
    path=Path(root)/MANIFEST
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:raise PackageError('Release manifest is required.')
    try:
        value=json.loads(path.read_text(),object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(PackageError('Invalid number.')))
    except (ValueError,TypeError,UnicodeError,RecursionError) as error:raise PackageError('Invalid release manifest.') from error
    if type(value) is not dict or set(value)!=FIELDS or any(type(value[k]) is not int or value[k]!=1 for k in ('format_version','engine_contract','database_contract','worker_contract')):
        raise PackageError('Unsupported release contract.')
    if (type(value['release']) is not str or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[1-9][0-9]*)?',value['release'])
        or value['runtime']!={'python':'3.12','node':'22','postgres':[16,18]} or type(value['files']) is not dict):
        raise PackageError('Unsupported runtime or release.')
    claimed=value['content_digest']
    unsigned={key:item for key,item in value.items() if key!='content_digest'}
    if type(claimed) is not str or claimed!=hashlib.sha256(canonical(unsigned)).hexdigest():raise PackageError('Manifest digest differs.')
    for name,facts in value['files'].items():
        _path(name)
        if (type(facts) is not dict or set(facts)!={'sha256','bytes'} or type(facts['bytes']) is not int
            or not 0<=facts['bytes']<=8*1024*1024 or type(facts['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',facts['sha256'])):
            raise PackageError('Invalid file identity.')
    if inventory(root)!=value['files']:raise PackageError('Package files differ from the manifest.')
    return value

def git_root(path,expected):
    path=Path(path).absolute();expected=Path(expected).absolute()
    if path.is_symlink() or path!=expected or path.resolve()!=expected.resolve():raise PackageError('Unexpected target directory.')
    for parent in (path,*path.parents):
        if parent.is_symlink():raise PackageError('Target links are forbidden.')
    try:
        result=subprocess.run(['git','-C',str(path),'rev-parse','--show-toplevel'],capture_output=True,text=True,timeout=10,check=True)
    except (OSError,subprocess.SubprocessError) as error:raise PackageError('An existing target Git root is required.') from error
    if Path(result.stdout.strip()).resolve()!=path.resolve():raise PackageError('Target is not its Git root.')
    return path

@contextmanager
def locked(root):
    path=root/'.appointment-install.lock'
    if path.is_symlink():raise PackageError('Target lock is unsafe.')
    with path.open('a+b') as handle:
        if os.name=='nt':
            import msvcrt
            if path.stat().st_size==0:handle.write(b'0');handle.flush()
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)

def install(source,target,*,expected_root,installation_id,project_id,upgrade=False):
    from uuid import UUID
    try:valid=(type(installation_id) is str and str(UUID(installation_id))==installation_id and bool(UUID(installation_id).int)
               and type(project_id) is str and bool(re.fullmatch('[a-z0-9][a-z0-9-]{0,74}',project_id)))
    except (ValueError,TypeError,AttributeError):valid=False
    if not valid:
        raise PackageError('Explicit project identity is required.')
    release=verify(source);root=git_root(target,expected_root)
    source=Path(source).resolve()
    if source==root.resolve() or root.resolve() in source.parents:raise PackageError('Source cannot be inside the target project.')
    destination=root/'appointment-system'
    if destination.is_symlink():raise PackageError('Target links are forbidden.')
    with locked(root):
        from appointment_system.configuration import Profile
        from appointment_system.settings import Installation,BusinessSettings
        from appointment_system.serialization import decode
        from appointment_system.serialization import fingerprint
        settings=root/'appointment-settings'
        if settings.is_symlink():raise PackageError('Project settings links are forbidden.')
        def read_profile():
            try:
                paths=[settings/'project.json',settings/'business-settings.json']
                if settings.is_symlink() or any(path.is_symlink() or not path.is_file() or path.stat().st_size>131072 for path in paths):raise ValueError()
                return Profile(Installation.parse(decode(paths[0].read_bytes())),BusinessSettings.parse(decode(paths[1].read_bytes())))
            except (OSError,ValueError) as error:raise PackageError('Valid project settings are required.') from error
        profile=read_profile()
        if profile.facts()['installation_id']!=installation_id or profile.facts()['project_id']!=project_id:
            raise PackageError('Target project settings differ from the intended installation.')
        binding={'installation_id':installation_id,'project_id':project_id,'project_digest':fingerprint(profile.facts()),
                 'bootstrap_business_digest':fingerprint(profile.initial_business.document)}
        journal=root/INTENT
        if journal.is_symlink():raise PackageError('Install intention is unsafe.')
        if journal.exists():
            if not journal.is_file() or journal.stat().st_size>4096:raise PackageError('Invalid install intention.')
            try:pending=json.loads(journal.read_text(),object_pairs_hook=_pairs)
            except (ValueError,OSError) as error:raise PackageError('Invalid install intention.') from error
            if (type(pending) is not dict or set(pending)!=set(binding)|{'release_digest','stage','rollback'}
                or any(pending[key]!=value for key,value in binding.items()) or pending['release_digest']!=release['content_digest']
                or type(pending['stage']) is not str or not re.fullmatch(r'\.appointment-stage-[a-z0-9_]{6,32}',pending['stage'])
                or pending['rollback'] is not None and (type(pending['rollback']) is not str or not re.fullmatch(r'\.appointment-rollbacks/[a-f0-9]{64}-[a-f0-9-]{36}',pending['rollback']))):
                raise PackageError('Interrupted installation needs its exact original settings and release.')
            staged=root/pending['stage'];rollback=root/pending['rollback'] if pending['rollback'] else None
            if rollback is not None and rollback.parent.is_symlink():raise PackageError('Rollback links are forbidden.')
            if destination.exists():
                previous_digest=verify(destination)['content_digest']
                if previous_digest!=release['content_digest']:
                    if (rollback is None or rollback.exists() or previous_digest!=rollback.name.split('-')[0]
                        or not staged.exists() or verify(staged)['content_digest']!=release['content_digest']):
                        raise PackageError('Unexpected package during interrupted installation.')
                    os.replace(destination,rollback);os.replace(staged,destination)
            elif staged.exists():
                if verify(staged)['content_digest']!=release['content_digest']:raise PackageError('Interrupted staged package differs.')
                os.replace(staged,destination)
            elif rollback is not None and rollback.exists():
                verify(rollback);os.replace(rollback,destination);journal.unlink()
                raise PackageError('Previous package restored; repeat the explicit upgrade.')
            else:raise PackageError('Interrupted installation has no recoverable package.')
            verify(destination)
            if staged.exists():
                if verify(staged)['content_digest']!=release['content_digest']:raise PackageError('Interrupted staged package differs.')
                shutil.rmtree(staged)
            journal.unlink()
            return dict(status='resumed',release_digest=release['content_digest'],**binding,rollback=pending['rollback'])
        previous=verify(destination) if destination.exists() else None
        if previous and previous['content_digest']==release['content_digest']:
            return dict(status='existing',release_digest=release['content_digest'],**binding)
        if previous is not None and not upgrade:raise PackageError('Use an explicit package upgrade.')
        if previous is None and upgrade:raise PackageError('Cannot upgrade a missing package.')
        staged=Path(tempfile.mkdtemp(prefix='.appointment-stage-',dir=root));rollback=None
        try:
            for name in release['files']:
                path=staged/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,path)
            shutil.copyfile(source/MANIFEST,staged/MANIFEST);verify(staged)
            current=read_profile()
            if (fingerprint(current.facts())!=binding['project_digest']
                or fingerprint(current.initial_business.document)!=binding['bootstrap_business_digest']):
                raise PackageError('Project settings changed during installation.')
            if previous:
                folder=root/'.appointment-rollbacks'
                if folder.is_symlink():raise PackageError('Rollback links are forbidden.')
                folder.mkdir(exist_ok=True);rollback=folder/(previous['content_digest']+'-'+str(uuid4()))
            pending=dict(binding,release_digest=release['content_digest'],stage=staged.name,
                         rollback=rollback.relative_to(root).as_posix() if rollback else None)
            with journal.open('xb') as handle:
                handle.write(canonical(pending));handle.flush();os.fsync(handle.fileno())
            try:
                if rollback is not None:os.replace(destination,rollback)
                os.replace(staged,destination)
            except OSError:
                if rollback is not None and not destination.exists():os.replace(rollback,destination)
                journal.unlink()
                raise
            verify(destination)
            journal.unlink()
        finally:
            if staged.exists() and not journal.exists():shutil.rmtree(staged)
    return dict(status='installed',release_digest=release['content_digest'],**binding,
        rollback=str(rollback.relative_to(root)) if rollback else None)

def identical(*roots):
    values=[verify(root) for root in roots]
    if not values or any(value!=values[0] for value in values[1:]):raise PackageError('Installed releases differ.')
    return values[0]['content_digest']

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Verify or install a whole contained release; no accounts are changed.')
    parser.add_argument('action',choices=('build','verify','install','upgrade','identical'))
    parser.add_argument('source',type=Path);parser.add_argument('--target',type=Path);parser.add_argument('--expected-root',type=Path)
    parser.add_argument('--installation-id');parser.add_argument('--project-id');parser.add_argument('--release',default='1.0.0-rc.1')
    arguments=parser.parse_args()
    if arguments.action=='build':result=build(arguments.source,release=arguments.release)
    elif arguments.action=='verify':result=verify(arguments.source)
    elif arguments.action=='identical':result={'content_digest':identical(arguments.source,arguments.target)}
    else:
        if any(value is None for value in (arguments.target,arguments.expected_root,arguments.installation_id,arguments.project_id)):parser.error('Target, expected Git root and project identity are required.')
        result=install(arguments.source,arguments.target,expected_root=arguments.expected_root,installation_id=arguments.installation_id,project_id=arguments.project_id,upgrade=arguments.action=='upgrade')
    print(json.dumps({key:value for key,value in result.items() if key!='files'},sort_keys=True))
