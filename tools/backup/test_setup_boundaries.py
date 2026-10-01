"""Setup credentials never leave private pipes; no actual consent or secret write."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,MagicMock,patch
import httpx
import authorize
import database_setting
from envelope import BackupError
from test_database_setting import DSN
from test_configure_key import setup

class SetupBoundaryTests(unittest.TestCase):
    def test_desktop_configuration_rejects_another_project_or_web_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.json'
            client={'project_id':authorize.PROJECT,'client_id':'synthetic.apps.googleusercontent.com','client_secret':'synthetic'}
            path.write_text(json.dumps({'installed':client}));self.assertEqual(authorize.load_client(path)['client_id'],client['client_id'])
            for data in [{'web':client},{'installed':{**client,'project_id':'other'}},{'installed':{**client,'client_secret':''}}]:
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(BackupError,'desktop_client_invalid'):authorize.load_client(path)

    def test_oauth_exchange_requires_durable_scope_and_verified_owner(self):
        for fields,code in [({'scope':''},'permission_missing'),({'refresh_token':''},'offline_permission_missing'),({'refresh_token_expires_in':604800},'grant_temporary')]:
            value={'scope':authorize.SCOPE,'refresh_token':'synthetic',**fields};response=httpx.Response(200,json=value,request=httpx.Request('POST','https://oauth2.googleapis.com/token'));client=MagicMock();client.__enter__.return_value.post.return_value=response
            with patch.object(authorize.httpx,'Client',return_value=client),patch.object(authorize,'Drive') as drive,self.assertRaisesRegex(BackupError,code):authorize.exchange({'client_id':'synthetic','client_secret':'synthetic'},'code','verifier','redirect')
            drive.assert_not_called()
        response=httpx.Response(200,json={'scope':authorize.SCOPE,'refresh_token':'synthetic'},request=httpx.Request('POST','https://oauth2.googleapis.com/token'));client=MagicMock();client.__enter__.return_value.post.return_value=response;drive=Mock(available=10000000)
        with patch.object(authorize.httpx,'Client',return_value=client),patch.object(authorize,'Drive',return_value=drive):grant,available=authorize.exchange({'client_id':'synthetic','client_secret':'synthetic'},'code','verifier','redirect')
        drive.close.assert_called_once();self.assertEqual(available,10000000);self.assertEqual(grant['refresh_token'],'synthetic')
        client.__enter__.return_value.post.side_effect=RuntimeError('private')
        with patch.object(authorize.httpx,'Client',return_value=client),self.assertRaisesRegex(BackupError,'^backup_google_exchange_failed$'):authorize.exchange({},'code','verifier','redirect')

    def test_loopback_callback_checks_host_state_and_reports_only_safe_outcomes(self):
        for failure in (None,BackupError('fixed_code'),RuntimeError('private')):
            replies=[]
            class Server:
                server_port=12345
                def __init__(self,address,handler):self.handler=handler;self.step=0
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def handle_request(self):
                    paths=['/start/entry','/callback?state=wrong&code=code','/callback?state=state&code=code'];h=self.handler.__new__(self.handler);h.server=self;h.path=paths[min(self.step,len(paths)-1)];h.headers={'Host':'evil.invalid' if self.step==0 else '127.0.0.1:12345'};self.step+=1;h.wfile=io.BytesIO();h.send_response=lambda status:replies.append(status);h.send_header=Mock();h.end_headers=Mock();h.do_GET();h.log_message('private')
            exchange=Mock(return_value=({'refresh_token':'synthetic'},100),side_effect=failure)
            with patch('sys.argv',['authorize.py','--client','unused']),patch.object(authorize,'load_client',return_value={'client_id':'synthetic','client_secret':'synthetic'}),patch.object(authorize.secrets,'token_urlsafe',side_effect=['state','verifier','entry']),patch.object(authorize,'HTTPServer',Server),patch.object(authorize,'exchange',exchange),patch.object(authorize,'copy_grant') as copy,patch('sys.stdout',new_callable=io.StringIO) as output:authorize.main()
            self.assertEqual(replies[:2],[400,400]);self.assertEqual(replies[-1],200 if failure is None else 400);self.assertEqual(copy.call_count,int(failure is None));self.assertNotIn('private',output.getvalue())

    def test_loopback_start_redirect_and_expiry_do_not_exchange_a_code(self):
        captured=[]
        class Server:
            server_port=12345
            def __init__(self,address,handler):self.handler=handler
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def handle_request(self):
                h=self.handler.__new__(self.handler);h.server=self;h.path='/start/entry';h.headers={'Host':'127.0.0.1:12345'};h.send_response=lambda status:captured.append(status);h.send_header=lambda k,v:captured.append((k,v));h.end_headers=Mock();h.do_GET()
        with patch('sys.argv',['authorize.py','--client','unused']),patch.object(authorize,'load_client',return_value={'client_id':'synthetic','client_secret':'synthetic'}),patch.object(authorize.secrets,'token_urlsafe',side_effect=['state','verifier','entry']),patch.object(authorize,'HTTPServer',Server),patch.object(authorize.time,'monotonic',side_effect=[0,1,1000]),patch.object(authorize,'exchange') as exchange,patch('builtins.print'),self.assertRaisesRegex(BackupError,'authorization_expired'):authorize.main()
        self.assertEqual(captured[0],302);exchange.assert_not_called();self.assertTrue(any(item[0]=='Location' and item[1].startswith('https://accounts.google.com/') for item in captured if isinstance(item,tuple)))

    def test_clipboard_and_database_failures_are_sanitised_before_secret_write(self):
        for helper,args,code in [(authorize.copy_grant,({'refresh_token':'synthetic'},),'clipboard_unavailable'),(database_setting.read_clipboard,(),'clipboard_unavailable')]:
            with patch('subprocess.run',return_value=Mock(returncode=1)),self.assertRaisesRegex(BackupError,code):helper(*args)
        with patch('subprocess.run',return_value=Mock(returncode=0,stdout=DSN.encode())):self.assertEqual(database_setting.read_clipboard(),DSN)
        with patch('subprocess.run',return_value=Mock(returncode=0)) as run:authorize.copy_grant({'refresh_token':'synthetic'})
        self.assertNotIn('synthetic',str(run.call_args.args));self.assertIn(b'synthetic',run.call_args.kwargs['input'])
        for waiting in (-1,901):
            with self.assertRaisesRegex(BackupError,'wait_invalid'):database_setting.acquire_connection(waiting)
        connector=MagicMock();connection=connector.return_value.__enter__.return_value;connection.execute.return_value.fetchone.return_value=('wrong','neondb',True,False)
        with patch.dict('sys.modules',{'psycopg':SimpleNamespace(connect=connector)}),self.assertRaisesRegex(BackupError,'access_invalid'):database_setting.validate_connection(DSN)
        connector.side_effect=RuntimeError('password authentication failed: synthetic-private')
        with patch.dict('sys.modules',{'psycopg':SimpleNamespace(connect=connector)}),self.assertRaisesRegex(BackupError,'^backup_database_authentication_failed$'):database_setting.validate_connection(DSN)
        with patch.object(database_setting,'acquire_connection',return_value=DSN),patch.object(database_setting,'validate_connection',return_value=31),patch('subprocess.run',return_value=Mock(returncode=1)),patch('builtins.print'),self.assertRaisesRegex(BackupError,'secret_save_failed'):database_setting.main(20)

    def test_key_creation_handles_unavailable_metadata_and_manual_save_without_logging_key(self):
        with patch.object(setup.subprocess,'run',return_value=Mock(returncode=1)),self.assertRaisesRegex(BackupError,'names_unavailable'):setup.main()
        outputs=[Mock(returncode=0,stdout=b'{"secrets":[]}'),Mock(returncode=0),Mock(returncode=1)]
        with patch.object(setup.subprocess,'run',side_effect=outputs),patch('sys.stdout',new_callable=io.StringIO) as output:key=setup.main()
        self.assertNotIn(key.decode(),output.getvalue());self.assertIn('manually',output.getvalue())
        outputs=[Mock(returncode=0,stdout=b'{"secrets":[{"name":"SARSA_BACKUP_ENCRYPTION_KEY"}]}'),Mock(returncode=0,stdout=b'{"total_count":0}'),Mock(returncode=0),Mock(returncode=0)]
        with patch.object(setup.subprocess,'run',side_effect=outputs),patch('builtins.print'):self.assertEqual(len(setup.main(replace_unused=True)),44)

if __name__=='__main__':unittest.main()
