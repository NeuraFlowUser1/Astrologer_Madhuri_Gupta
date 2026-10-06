"""A fresh process executes a relocated complete copy, without factory access."""
import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from tools.install.package import build,inventory,install,identical,PackageError
from tools.install.host import prepare,ENTRY
from .fixtures import installation,business

CHILD = '''import builtins,importlib.util,json,os,socket,sys
from pathlib import Path
project=Path(sys.argv[1]);blocked=Path(sys.argv[2]);original=builtins.open
def audit(event,args):
    if event=="open" and args and isinstance(args[0],(str,bytes,os.PathLike)):
        value=Path(os.fsdecode(args[0])).absolute()
        denied=(blocked,project/"src/backend",project/"backend")
        if any(value==path or path in value.parents for path in denied):raise AssertionError("An external or retired engine path was accessed")
    if event=="socket.connect":raise AssertionError("External connection attempted")
sys.addaudithook(audit)
def open_file(path,*args,**kwargs):
    if isinstance(path,(str,bytes,os.PathLike)):
        value=Path(os.fsdecode(path)).absolute()
        if value==blocked or blocked in value.parents:raise AssertionError("Master path was accessed")
    return original(path,*args,**kwargs)
builtins.open=open_file
def no_network(*args,**kwargs):raise AssertionError("External connection attempted")
socket.create_connection=no_network
socket.socket.connect=no_network
spec=importlib.util.spec_from_file_location("contained_entry",project/"api/index.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from fastapi.testclient import TestClient
from appointment_system.configuration import installation
from appointment_system.runtime import contained_release
facts=installation();root,digest=contained_release()
client=TestClient(module.app,base_url=facts["origin"])
health=client.get("/api/health");assert health.status_code==200,health.text
for path in ("/booking","/studio","/studio/calendar","/booking-help"):
    assert client.get(path).status_code==404
assert client.get("/api/health",headers={"Host":"foreign.example.test"}).status_code==421
from appointment_system.configuration import configure
try:configure(dict(facts,project_id="foreign-project"),json.loads((project/"appointment-settings/business-settings.json").read_bytes()))
except ValueError:pass
else:raise AssertionError("Process switched installations")
assert root==project/"appointment-system"
assert all(str(blocked) not in value for value in sys.path)
assert not any(name.startswith(("src.backend", "backend.booking_engine")) for name in sys.modules)
print(json.dumps({"status":"passed","installation_id":facts["installation_id"],"project_id":facts["project_id"],"release_digest":digest}))
'''


class ContainedHost(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'master'
        master=Path(__file__).absolute().parents[1]
        for name in inventory(master):
            destination=self.source/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(master/name,destination)
        self.release=build(self.source)
        self.project=self.root/'initial'/'client';self.project.mkdir(parents=True)
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        facts=installation();facts['environment']='production'
        settings=self.project/'appointment-settings';settings.mkdir()
        (settings/'project.json').write_text(json.dumps(facts))
        (settings/'business-settings.json').write_text(json.dumps(business()))
        self.facts=facts
        install(self.source,self.project,expected_root=self.project,installation_id=facts['installation_id'],project_id=facts['project_id'])

    def test_fresh_relocated_process_uses_its_whole_copy_and_own_settings(self):
        prepare(self.project,expected_root=self.project)
        moved=self.root/'different-parent'/'handed-over-client';moved.parent.mkdir()
        shutil.move(self.project,moved)
        identical(self.source,moved/'appointment-system')
        # The original master is removed before process creation, not merely absent from sys.path.
        shutil.rmtree(self.source)
        from appointment_system.keys import encode
        environment={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME') and not key.startswith(('BOOKING_','PG','VERCEL'))}
        environment.update(VERCEL='1',VERCEL_ENV='production',PYTHONDONTWRITEBYTECODE='1')
        environment['BOOKING_DATABASE_URL']='host=localhost dbname=postgres user=appointment_system_web password=synthetic sslmode=require'
        for purpose,byte in (('receipt',41),('context',42),('risk',43)):
            environment['BOOKING_'+purpose.upper()+'_KEYS']=json.dumps({'version':1,'installation_id':self.facts['installation_id'],
                'environment':'production','purpose':purpose,'active':'test','keys':{'test':encode(bytes([byte])*32)}})
        reply=subprocess.run([sys.executable,'-c',CHILD,str(moved),str(self.source)],cwd=moved,
            env=environment,capture_output=True,text=True,timeout=30)
        self.assertEqual(reply.returncode,0,reply.stderr[-2500:])
        value=json.loads(reply.stdout);self.assertEqual(value['status'],'passed')
        self.assertEqual(value['installation_id'],self.facts['installation_id'])
        self.assertEqual(value['release_digest'],self.release['content_digest'])

    def test_existing_host_work_is_preserved_and_matching_preparation_is_idempotent(self):
        path=self.project/'api';path.mkdir();entry=path/'index.py';entry.write_text('existing client work')
        with self.assertRaises(PackageError):prepare(self.project,expected_root=self.project)
        self.assertEqual(entry.read_text(),'existing client work')
        entry.write_text(ENTRY)
        self.assertEqual(prepare(self.project,expected_root=self.project)['status'],'existing')

    def test_entry_directory_and_file_links_are_refused(self):
        outside=self.root/'outside';outside.mkdir();(self.project/'api').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(PackageError):prepare(self.project,expected_root=self.project)
        self.assertEqual(list(outside.iterdir()),[])
        (self.project/'api').unlink();(self.project/'api').mkdir()
        (self.project/'api/index.py').symlink_to(outside/'index.py')
        with self.assertRaises(PackageError):prepare(self.project,expected_root=self.project)
