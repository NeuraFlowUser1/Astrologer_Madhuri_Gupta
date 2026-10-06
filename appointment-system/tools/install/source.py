"""Export reviewed website files plus the whole contained engine, without deploying."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,shutil,tempfile
from appointment_system.settings import Installation
from .host import ENTRY
from .package import PackageError,_pairs,canonical,git_root,verify

REQUIRED={'api/index.py','requirements.txt','vercel.json','package.json',
 'appointment-settings/project.json','appointment-settings/business-settings.json'}
FORBIDDEN={'.git','.env','.vercel','.wrangler','node_modules','__pycache__','.venv','venv',
 'secrets','credentials','private','verification-results'}
HIDDEN={'.gitignore','.vercelignore','.oxlintrc.json','.python-version'}
EXTENSIONLESS={'_redirects','_headers'}
EXTENSIONS={'.py','.mjs','.js','.jsx','.ts','.tsx','.json','.jsonc','.css','.html','.txt','.xml',
 '.svg','.png','.webp','.jpg','.jpeg','.ico','.woff','.woff2','.ttf','.otf','.mp4','.webm','.avif'}
MANIFEST='appointment-settings/hosting-files.json'


def site_path(value):
 if (type(value) is not str or len(value)>240 or not re.fullmatch(r'[A-Za-z0-9_ ./-]+',value)
     or value.startswith('/') or any(part in ('','.','..') or part!=part.strip() for part in value.split('/'))):
  raise PackageError('Unsafe hosting path.')
 path=PurePosixPath(value)
 if (path.parts[0]=='appointment-system' or any(part in FORBIDDEN or part.startswith('.env')
      or part.startswith('client_secret_') or part.startswith('service_account')
      or part.startswith('.') and part not in HIDDEN for part in path.parts)
     or path.suffix not in EXTENSIONS and path.name not in HIDDEN|EXTENSIONLESS):
  raise PackageError('Unreviewed or private hosting path.')
 return path


def regular(root,relative):
 path=root/relative
 if path.resolve()!=path or not path.is_file():raise PackageError('Hosting files must be regular contained files.')
 return path


def read_manifest(root):
 value=json.loads(regular(root,MANIFEST).read_text(),object_pairs_hook=_pairs)
 if (type(value) is not dict or set(value)!={'version','files'} or type(value['version']) is not int
     or value['version']!=1 or type(value['files']) is not list or not value['files']
     or any(type(item) is not str for item in value['files'])
     or len(value['files'])!=len(set(value['files'])) or not REQUIRED<=set(value['files'])):
  raise PackageError('The website hosting file list is incomplete or invalid.')
 for name in value['files']:site_path(name)
 return sorted(set(value['files'])|{MANIFEST})


def copy_checked(root,name,destination):
 source=regular(root,name);before=source.stat();target=destination/name
 target.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256();size=0
 with source.open('rb') as incoming,target.open('xb') as outgoing:
  while block:=incoming.read(1024*1024):outgoing.write(block);digest.update(block);size+=len(block)
 after=source.stat()
 if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
     or size!=before.st_size):raise PackageError('A source file changed during hosting preparation.')
 return {'path':name,'bytes':size,'sha256':digest.hexdigest()}


def prepare(target,*,expected_root):
 root=git_root(target,expected_root);files=read_manifest(root)
 if regular(root,'api/index.py').read_text()!=ENTRY:raise PackageError('Hosting entry does not use the contained engine.')
 profile=Installation.parse(json.loads(regular(root,'appointment-settings/project.json').read_text(),object_pairs_hook=_pairs))
 release=verify(root/'appointment-system')
 files+=['appointment-system/'+name for name in release['files']]+['appointment-system/release.json']
 destination=Path(tempfile.mkdtemp(prefix='appointment-hosting-source-')).resolve();report_path=Path(str(destination)+'.manifest.json');report_created=False
 try:
  manifest=[copy_checked(root,name,destination) for name in sorted(files)]
  if verify(root/'appointment-system')!=release or verify(destination/'appointment-system')!=release:
   raise PackageError('The contained release changed during hosting preparation.')
  if read_manifest(root)!=read_manifest(destination):raise PackageError('The website manifest changed during preparation.')
  for item in manifest:
   with regular(root,item['path']).open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
   if digest!=item['sha256']:raise PackageError('A source file changed during hosting preparation.')
  # Validate identity again from the copy; the tool never reads environment credentials.
  copied=Installation.parse(json.loads((destination/'appointment-settings/project.json').read_text(),object_pairs_hook=_pairs))
  if copied.document!=profile.document:raise PackageError('The project identity changed during preparation.')
  report={'version':1,'installation_id':profile.installation_id,'release_digest':release['content_digest'],
   'files':manifest,'content_digest':hashlib.sha256(canonical(manifest)).hexdigest(),'deployed':False}
  with report_path.open('x') as handle:
   report_created=True;json.dump(report,handle,sort_keys=True,indent=2);handle.write('\n')
  return {'destination':str(destination),'manifest':str(report_path),'files':len(manifest),
   'bytes':sum(item['bytes'] for item in manifest),'release_digest':release['content_digest'],'deployed':False}
 except BaseException:
  shutil.rmtree(destination)
  if report_created:report_path.unlink(missing_ok=True)
  raise


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description='Prepare a local complete hosting source copy. No upload, account link or deployment.')
 parser.add_argument('target',type=Path);parser.add_argument('--expected-root',type=Path,required=True)
 options=parser.parse_args()
 try:result=prepare(options.target,expected_root=options.expected_root)
 except (OSError,ValueError):raise SystemExit('Hosting preparation refused. Review the contained release and exact website file list.') from None
 print(json.dumps(result,sort_keys=True))
