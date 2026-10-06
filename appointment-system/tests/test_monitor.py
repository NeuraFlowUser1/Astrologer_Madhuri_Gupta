"""Independent observer refuses foreign/charged authority and never reads SQL."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from tools.install.package import build
from tools.automation import monitor
from .fixtures import installation

class Reply:
    def __init__(self,url,body,status=200):self.url=url;self.body=body;self.status=status
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def geturl(self):return self.url
    def read(self,limit):return self.body[:limit]

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.package=self.root/'appointment-system';(self.package/'engine/appointment_system').mkdir(parents=True)
        (self.package/'engine/appointment_system/application.py').write_text('VALUE=1\n');build(self.package)
        self.settings=self.root/'appointment-settings';self.settings.mkdir();facts=installation();facts['environment']='production'
        (self.settings/'project.json').write_text(json.dumps(facts))
        self.repository={'full_name':'ExampleOwner/Practice','visibility':'public','private':False,'fork':False,'archived':False,'disabled':False,'default_branch':'main'}
        (self.settings/'monitor.json').write_text(json.dumps(dict(version=1,installation_id=facts['installation_id'],environment='production',repository=self.repository['full_name'],cron=monitor.CRON)))
        self.event=self.root/'event.json';self.event.write_text(json.dumps({'repository':self.repository,'schedule':monitor.CRON}))
        self.env={'BOOKING_PROFILE':str(self.settings/'project.json'),'BOOKING_MONITOR_KEY':'a'*43+'=',
          'GITHUB_TOKEN':'synthetic-token','GITHUB_REPOSITORY':self.repository['full_name'],'GITHUB_EVENT_PATH':str(self.event),
          'GITHUB_EVENT_NAME':'schedule','GITHUB_REF':'refs/heads/main','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux'}
        self.responses={'https://api.github.com/repos/'+self.repository['full_name']:self.repository,
          facts['worker']['origin']+'/health':{'status':'healthy'},facts['origin']+'/api/health':{'status':'online'},
          facts['origin']+'/api/service-state':{'enabled':False,'activation_epoch':str(uuid4())},facts['origin']+'/':b'<!doctype html><html><body>Normal website</body></html>'}
        self.calls=[];self.behaviour='normal'
        patcher=patch.object(monitor,'ROOT',self.package);patcher.start();self.addCleanup(patcher.stop)
    def open(self,request,timeout):
        self.calls.append(request);value=self.responses[request.full_url]
        body=value if type(value) is bytes else json.dumps(value).encode()
        return Reply(request.full_url+'foreign' if self.behaviour=='redirect' else request.full_url,body,503 if self.behaviour=='503' else 200)
    def run_monitor(self,env=None):return monitor.run(self.env if env is None else env,opener=self)
    def test_off_website_and_independent_health_are_healthy_without_any_database_read(self):
        self.assertEqual(self.run_monitor(),{'status':'healthy','booking_enabled':False});self.assertEqual(len(self.calls),5)
        self.assertEqual([request.get_header('Authorization') for request in self.calls],['Bearer synthetic-token','Bearer '+'a'*43+'=',None,None,None])
        self.assertTrue(all(timeout not in request.full_url for request in self.calls for timeout in ('neon','/api/internal/','/api/booking/')))
    def test_serving_or_other_duty_credentials_are_refused_before_any_network(self):
        for name in ('PGPASSWORD','BOOKING_DATABASE_URL','BOOKING_BACKUP_DATABASE_URL','BOOKING_GOOGLE_CLIENT_SECRET'):
            with self.subTest(name=name),self.assertRaisesRegex(monitor.MonitorError,'private_authority'):self.run_monitor(self.env|{name:'foreign-secret'})
        self.assertEqual(self.calls,[])
    def test_all_requests_identify_the_observer_and_keep_credentials_at_their_own_origin(self):
        original=self.open
        def require_identity(request,timeout):
            self.assertEqual(request.get_header('User-agent'),'appointment-system-monitor')
            expected=('application/vnd.github+json' if request.full_url.startswith('https://api.github.com/')
                      else 'text/html' if request.full_url.endswith('/') else 'application/json')
            self.assertEqual(request.get_header('Accept'),expected)
            return original(request,timeout)
        self.open=require_identity
        self.assertEqual(self.run_monitor(),{'status':'healthy','booking_enabled':False})
        self.assertEqual(len(self.calls),5)
        self.assertEqual([request.get_header('Authorization') for request in self.calls],
                         ['Bearer synthetic-token','Bearer '+'a'*43+'=',None,None,None])
    def test_private_fork_unknown_event_cadence_and_nonmain_ref_refuse_before_network(self):
        for change in ({'private':True},{'private':None},{'private':0},{'fork':True},{'visibility':'private'},{'disabled':True}):
            self.event.write_text(json.dumps({'repository':self.repository|change,'schedule':monitor.CRON}))
            with self.assertRaises(monitor.MonitorError):self.run_monitor()
        self.event.write_text(json.dumps({'repository':self.repository,'schedule':'* * * * *'}))
        with self.assertRaisesRegex(monitor.MonitorError,'schedule'):self.run_monitor()
        self.event.write_text(json.dumps({'repository':self.repository,'schedule':monitor.CRON}))
        for change in ({'GITHUB_REF':'refs/heads/feature'},{'GITHUB_EVENT_NAME':'pull_request'},{'RUNNER_ENVIRONMENT':'self-hosted'}):
            with self.assertRaisesRegex(monitor.MonitorError,'runner'):self.run_monitor(self.env|change)
        self.assertEqual(self.calls,[])
    def test_actual_repository_change_health_attention_and_redirect_never_report_success(self):
        self.responses['https://api.github.com/repos/'+self.repository['full_name']]=self.repository|{'private':True}
        with self.assertRaisesRegex(monitor.MonitorError,'repository'):self.run_monitor()
        self.responses['https://api.github.com/repos/'+self.repository['full_name']]=self.repository
        self.responses[installation()['worker']['origin']+'/health']={'status':'attention'}
        with self.assertRaisesRegex(monitor.MonitorError,'recovery'):self.run_monitor()
        for behaviour in ('redirect','503'):
            self.behaviour=behaviour
            with self.assertRaisesRegex(monitor.MonitorError,'read_failed'):self.run_monitor()
    def test_foreign_profile_invalid_documents_links_and_tampered_package_are_refused(self):
        foreign=self.root/'foreign/appointment-settings';foreign.mkdir(parents=True)
        with self.assertRaisesRegex(monitor.MonitorError,'profile_path'):self.run_monitor(self.env|{'BOOKING_PROFILE':str(foreign/'project.json')})
        with self.assertRaisesRegex(monitor.MonitorError,'document'):monitor.document(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(monitor.MonitorError,'document'):monitor.document(b'{"a":NaN}')
        self.event.write_bytes(b'x'*65537)
        with self.assertRaisesRegex(monitor.MonitorError,'file'):self.run_monitor()
        self.event.unlink();self.event.symlink_to(self.settings/'project.json')
        with self.assertRaisesRegex(monitor.MonitorError,'file'):self.run_monitor()
        (self.package/'engine/appointment_system/application.py').write_text('VALUE=2\n')
        with self.assertRaises(ValueError):self.run_monitor()

    def test_incomplete_credentials_and_event_shape_do_not_contact_any_service(self):
        for change in ({'GITHUB_TOKEN':None},{'GITHUB_TOKEN':'private\ninjected'},{'BOOKING_MONITOR_KEY':'short'}):
            with self.subTest(change=change),self.assertRaisesRegex(monitor.MonitorError,'credential'):
                self.run_monitor(self.env|change)
        self.event.write_text('[]')
        with self.assertRaisesRegex(monitor.MonitorError,'event'):self.run_monitor()
        self.assertEqual(self.calls,[])

    def test_wrong_project_identity_and_unsafe_origins_are_rejected(self):
        profile=self.settings/'project.json';config=self.settings/'monitor.json'
        facts=json.loads(profile.read_text());settings=json.loads(config.read_text())
        for identity in ('invalid','00000000-0000-0000-0000-000000000000'):
            profile.write_text(json.dumps(facts|{'installation_id':identity}))
            config.write_text(json.dumps(settings|{'installation_id':identity}))
            with self.assertRaisesRegex(monitor.MonitorError,'profile'):self.run_monitor()
        config.write_text(json.dumps(settings))
        for origin in ('http://practice.example.test','https://user:pass@practice.example.test','https://practice.example.test/path','https://localhost'):
            profile.write_text(json.dumps(facts|{'origin':origin}))
            with self.assertRaisesRegex(monitor.MonitorError,'profile'):self.run_monitor()
        self.assertEqual(self.calls,[])

    def test_unknown_process_or_public_state_and_empty_website_raise_attention(self):
        origin=installation()['origin'];process=origin+'/api/health';state=origin+'/api/service-state'
        self.responses[process]={'status':'offline'}
        with self.assertRaisesRegex(monitor.MonitorError,'process_attention'):self.run_monitor()
        self.responses[process]={'status':'online'}
        for body in ({'enabled':False},{'enabled':1,'activation_epoch':str(uuid4())},
            {'enabled':False,'activation_epoch':'invalid'}, {'enabled':False,'activation_epoch':'00000000-0000-0000-0000-000000000000'}):
            self.responses[state]=body
            with self.assertRaisesRegex(monitor.MonitorError,'projection_attention'):self.run_monitor()
        self.responses[state]={'enabled':False,'activation_epoch':str(uuid4())}
        for page in (b'',b'Unexpected service response',b'x'*524289):
            self.responses[origin+'/']=page
            with self.assertRaises(monitor.MonitorError):self.run_monitor()

    def test_transport_errors_are_private_and_redirects_are_never_followed(self):
        class Broken:
            def open(self,*args,**kwargs):raise RuntimeError('private transport data')
        with self.assertRaisesRegex(monitor.MonitorError,'^monitor_read_failed$'):
            monitor.read('https://practice.example.test',opener=Broken())
        with self.assertRaisesRegex(monitor.MonitorError,'redirect'):
            monitor.NoRedirect().redirect_request(None,None,302,'',{},'https://foreign.example.test')
