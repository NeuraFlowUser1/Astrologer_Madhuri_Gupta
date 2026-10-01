"""Provider setup is rehearsed without invoking Windows or Cloudflare."""
import io
import json
from unittest import TestCase,main
from unittest.mock import Mock,patch,MagicMock
import test_connect as fixtures
connect=fixtures.connect

class OperationalBoundaryTests(TestCase):
    def setUp(self):
        fixture=fixtures.PrivateTransferTests();fixture.setUp();self.keys=fixture.keys;self.plan=fixture.plan

    def test_private_capture_is_cleared_and_never_echoes_provider_output(self):
        result=Mock(returncode=0,stdout=json.dumps(self.keys),stderr='private provider text')
        with patch.object(connect.subprocess,'run',return_value=result):self.assertEqual(connect.private_keys(),self.keys)
        self.assertEqual(result.stdout,'');self.assertEqual(result.stderr,'')
        for result in [Mock(returncode=1,stdout='private',stderr='private'),Mock(returncode=0,stdout='x'*1025,stderr='private')]:
            with patch.object(connect.subprocess,'run',return_value=result),self.assertRaisesRegex(connect.SafeFailure,'private_copy_unavailable'):connect.private_keys()

    def test_plan_checks_status_content_type_size_and_new_maintenance_lane(self):
        opener=MagicMock()
        for status,kind,raw in [(503,'application/json',b'{}'),(200,'text/html',b'{}'),(200,'application/json',b'x'*8193)]:
            response=fixtures.PrivateTransferTests.response(self.plan,content_type=kind);response.status=status;response.read.return_value=raw;opener.open.return_value.__enter__.return_value=response
            with patch.object(connect.urllib.request,'build_opener',return_value=opener),self.assertRaises(connect.SafeFailure):connect.hosted_plan(self.keys)
        plan={**self.plan,'lanes':{**self.plan['lanes'],'maintenance':900}};opener.open.return_value.__enter__.return_value=fixtures.PrivateTransferTests.response(plan)
        with patch.object(connect.urllib.request,'build_opener',return_value=opener):self.assertEqual(connect.hosted_plan(self.keys),plan)

    def test_configuration_verifies_account_queue_namespace_and_bindings_before_success(self):
        identity={'loggedIn':True,'email':'neuraflowindia@gmail.com','accounts':[{'id':connect.ACCOUNT}]}
        queue='8d602c4b56f44eca8ae5bcfa6cde1fab sarsa-booking-recovery'
        kv=[{'id':'927be5fbe5c54002ae03e55c48a0a2e5','title':'sarsa-booking-recovery-heartbeats'}]
        bindings=[{'name':name,'type':'secret_text'} for name in connect.NAMES]
        def results():return [Mock(stdout=json.dumps(identity)),Mock(stdout=queue),Mock(stdout=json.dumps(kv)),Mock(stdout='private',stderr='private'),Mock(stdout=json.dumps(bindings))]
        with patch.object(connect,'wrangler',side_effect=results()) as run,patch('builtins.print'):
            connect.configure(self.keys)
        self.assertEqual(run.call_args_list[3].args[0],['secret','bulk']);self.assertEqual(json.loads(run.call_args_list[3].kwargs['payload']),self.keys)
        for index,stdout,code in [(0,'{}','identity_mismatch'),(1,'other queue','queue_missing'),(2,'[]','namespace_missing'),(4,'[]','binding_missing')]:
            values=results();values[index]=Mock(stdout=stdout)
            with patch.object(connect,'wrangler',side_effect=values),self.assertRaisesRegex(connect.SafeFailure,code):connect.configure(self.keys)
        configuration=json.loads((connect.WORKER/'wrangler.json').read_text());configuration['name']='other-client'
        with patch.object(connect.Path,'read_text',return_value=json.dumps(configuration)),patch.object(connect,'wrangler') as run,self.assertRaisesRegex(connect.SafeFailure,'identity_mismatch'):connect.configure(self.keys)
        run.assert_not_called()

    def test_failed_wrangler_never_discloses_captured_output(self):
        with patch.object(connect.subprocess,'run',return_value=Mock(returncode=1,stdout='private',stderr='private')),self.assertRaisesRegex(connect.SafeFailure,'^cloudflare_operation_failed$'):connect.wrangler(['whoami'])

    def test_cli_paths_clear_keys_on_success_and_unexpected_failure(self):
        for action in ('verify-local','verify-hosted','configure-worker'):
            values=dict(self.keys)
            with patch('sys.argv',['connect.py',action]),patch.object(connect,'private_keys',return_value=values),patch.object(connect,'hosted_plan',return_value=self.plan),patch.object(connect,'configure') as configure,patch('sys.stdout',new_callable=io.StringIO):self.assertEqual(connect.main(),0)
            self.assertEqual(values,{});self.assertEqual(configure.call_count,int(action=='configure-worker'))
        values=dict(self.keys)
        with patch('sys.argv',['connect.py','verify-hosted']),patch.object(connect,'private_keys',return_value=values),patch.object(connect,'hosted_plan',side_effect=RuntimeError('private exception')),patch('sys.stdout',new_callable=io.StringIO) as output:self.assertEqual(connect.main(),1)
        self.assertEqual(values,{});self.assertNotIn('private exception',output.getvalue())

if __name__=='__main__':main()
