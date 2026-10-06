"""Run the actual installed observer without factory, database or provider access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CHILD = r'''
import importlib.util,json,os,sys
from pathlib import Path
project=Path(sys.argv[1]).absolute();blocked=[Path(x).absolute() for x in sys.argv[2:]]
package=project/'appointment-system'
def audit(event,args):
    if event=='socket.connect':raise AssertionError('Real network access forbidden')
    if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).absolute()
        if any(path==root or root in path.parents for root in blocked):
            raise AssertionError('External factory or other client accessed')
sys.addaudithook(audit)
spec=importlib.util.spec_from_file_location('installed_monitor',package/'tools/automation/monitor.py')
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)
profile=project/'appointment-settings/project.json';config,origins=monitor.public(profile)
repository={'full_name':config['repository'],'visibility':'public','private':False,
    'fork':False,'archived':False,'disabled':False,'default_branch':'main'}
event=Path.cwd()/'event.json'
event.write_text(json.dumps({'repository':repository,'schedule':monitor.CRON}))
environment={'BOOKING_PROFILE':str(profile),'BOOKING_MONITOR_KEY':'a'*43+'=',
    'GITHUB_TOKEN':'synthetic-application-monitor-token','GITHUB_REPOSITORY':config['repository'],
    'GITHUB_EVENT_PATH':str(event),'GITHUB_EVENT_NAME':'schedule','GITHUB_REF':'refs/heads/main',
    'RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux'}
repo_url='https://api.github.com/repos/'+config['repository']
responses={repo_url:repository,origins[1]+'/health':{'status':'healthy'},
    origins[0]+'/api/health':{'status':'online'},origins[0]+'/api/service-state':
    {'enabled':False,'activation_epoch':'a94d81a8-461d-413a-8335-b337f0ee44b5'},
    origins[0]+'/':b'<!doctype html><html><body>Ordinary website</body></html>'}
calls=[]
class Response:
    status=200
    def __init__(self,url):self.url=url
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):
        value=responses[self.url]
        body=value if isinstance(value,bytes) else json.dumps(value).encode()
        return body[:limit]
class Network:
    def open(self,request,timeout):
        assert timeout==10
        assert request.full_url in responses,'Undeclared service accessed'
        calls.append((request.full_url,request.get_header('Authorization')))
        return Response(request.full_url)
def run(env=None):return monitor.run(environment if env is None else env,opener=Network())
for enabled in (False,True):
    calls.clear();responses[origins[0]+'/api/service-state']['enabled']=enabled
    assert run()=={'status':'healthy','booking_enabled':enabled}
    assert calls==[(repo_url,'Bearer synthetic-application-monitor-token'),
        (origins[1]+'/health','Bearer '+'a'*43+'='),(origins[0]+'/api/health',None),
        (origins[0]+'/api/service-state',None),(origins[0]+'/',None)]
def rejected(env,reason,expected_calls):
    calls.clear()
    try:run(env)
    except monitor.MonitorError as error:assert reason in str(error)
    else:raise AssertionError('Invalid monitoring authority accepted')
    assert len(calls)==expected_calls
rejected(environment|{'BOOKING_DATABASE_URL':'synthetic-forbidden-authority'},'private_authority',0)
rejected(environment|{'GITHUB_REPOSITORY':'UnrelatedOwner/OtherProject'},'runner_ineligible',0)
event.write_text(json.dumps({'repository':repository|{'private':True},'schedule':monitor.CRON}))
rejected(environment,'repository_ineligible',0)
event.write_text(json.dumps({'repository':repository,'schedule':monitor.CRON}))
responses[repo_url]=repository|{'visibility':'private'}
rejected(environment,'repository_ineligible',1)
responses[repo_url]=repository;responses[origins[1]+'/health']={'status':'attention'}
rejected(environment,'recovery_attention',2)
release=monitor.verify(package)
assert all(not name.startswith(('appointment_system','psycopg')) for name in sys.modules)
print(json.dumps({'status':'passed','release_digest':release['content_digest'],
    'repository':config['repository'],'installation_id':config['installation_id'],
    'scenarios':7,'external_requests':0,'database_access':False}))
'''


@unittest.skipUnless(os.environ.get('BOOKING_TEST_PROJECT'), 'Explicit installed local project required.')
class ContainedMonitor(unittest.TestCase):
    def test_installed_observer_is_independent_and_uses_only_its_own_declared_endpoints(self):
        project=Path(os.environ['BOOKING_TEST_PROJECT']).absolute()
        self.assertTrue(project.is_dir());self.assertFalse(project.is_symlink())
        master=Path(__file__).absolute().parents[1]
        self.assertNotEqual(project,master.parent)
        other_projects=[path for path in project.parent.iterdir() if path.is_dir() and path!=project]
        environment={key:value for key,value in os.environ.items()
            if key not in ('PYTHONPATH','PYTHONHOME') and not key.startswith(('BOOKING_','PG','VERCEL'))}
        environment['PYTHONDONTWRITEBYTECODE']='1'
        with tempfile.TemporaryDirectory(prefix='abs-installed-monitor-') as temporary:
            # Exercise the exact installed files on a native filesystem. Seven
            # complete integrity scans on a Windows-mounted checkout exceed the
            # child deadline even when each individual scan succeeds. Relocation
            # also proves the observer cannot rely on its original project path.
            detached=Path(temporary)/'project';detached.mkdir()
            shutil.copytree(project/'appointment-system',detached/'appointment-system',
                ignore=shutil.ignore_patterns('node_modules','__pycache__','.wrangler'))
            (detached/'appointment-settings').mkdir()
            for name in ('project.json','monitor.json'):
                shutil.copyfile(project/'appointment-settings'/name,detached/'appointment-settings'/name)
            result=subprocess.run([sys.executable,'-c',CHILD,str(detached),str(project),str(master),
                *(str(path) for path in other_projects)],env=environment,cwd=temporary,
                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr[-3000:])
        report=json.loads(result.stdout)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['scenarios'],7)
        self.assertFalse(report['database_access']);self.assertEqual(report['external_requests'],0)
        release=json.loads((project/'appointment-system/release.json').read_text())
        self.assertEqual(report['release_digest'],release['content_digest'])
        facts=json.loads((project/'appointment-settings/project.json').read_text())
        self.assertEqual(report['installation_id'],facts['installation_id'])
