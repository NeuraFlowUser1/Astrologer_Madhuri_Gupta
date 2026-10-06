"""Validation selects only an independently checked successful owned backup run."""
from contextlib import ExitStack,redirect_stdout
from copy import deepcopy
import io,json,tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import httpx
from tools.automation import trigger
from tools.automation.eligibility import WORKFLOW
from appointment_system.backup.protocol import BackupError

class BackupTriggerTests(TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.repository={'full_name':'Owner/SyntheticProject','default_branch':'main','visibility':'public','private':False,'fork':False,'archived':False,'disabled':False}
        self.event={'repository':deepcopy(self.repository),'workflow_run':{'id':123}}
        self.record={'path':WORKFLOW,'head_branch':'main','status':'completed','conclusion':'success','event':'schedule',
            'repository':deepcopy(self.repository),'head_repository':deepcopy(self.repository),'id':123,'run_attempt':2,'head_sha':'a'*40}
        self.output=self.root/'output';self.event_path=self.root/'event.json';self.calls=[]
        self.environment={'BOOKING_PROFILE':'synthetic-public-profile','GITHUB_EVENT_PATH':str(self.event_path),'GITHUB_EVENT_NAME':'workflow_run',
            'GITHUB_REPOSITORY':'Owner/SyntheticProject','GITHUB_REF':'refs/heads/main','RUNNER_ENVIRONMENT':'github-hosted',
            'RUNNER_OS':'Linux','GITHUB_TOKEN':'synthetic-token','GITHUB_OUTPUT':str(self.output)}
        client=httpx.Client
        def provider(request):
            self.calls.append(str(request.url));self.assertEqual(request.method,'GET')
            self.assertEqual(request.headers['authorization'],'Bearer synthetic-token')
            if str(request.url)=='https://api.github.com/repos/Owner/SyntheticProject':return httpx.Response(200,json=self.repository)
            self.assertEqual(str(request.url),'https://api.github.com/repos/Owner/SyntheticProject/actions/runs/123')
            return httpx.Response(200,json=self.record)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        # Package integrity/profile contents have their own installation tests;
        # this test runs the real event, HTTP, repository and source-run checks.
        self.verify=self.stack.enter_context(patch.object(trigger,'verify',return_value={'content_digest':'a'*64}))
        self.stack.enter_context(patch.object(trigger,'public_settings',return_value={'repository':'Owner/SyntheticProject'}))
        self.stack.enter_context(patch('httpx.Client',side_effect=lambda **kwargs:client(transport=httpx.MockTransport(provider),**kwargs)))

    def run_trigger(self,changes=None):
        self.event_path.write_text(json.dumps(self.event))
        with redirect_stdout(io.StringIO()) as output:trigger.main(self.environment|(changes or {}))
        return output.getvalue()

    def test_completed_owned_run_records_only_verified_identity(self):
        text=self.run_trigger();self.verify.assert_called_once_with(trigger.ROOT)
        self.assertEqual(self.output.read_text(),'source_run=123\nsource_attempt=2\nsource_commit='+'a'*40+'\n')
        self.assertEqual(len(self.calls),2);self.assertNotIn('synthetic-token',text)
        self.event={'repository':self.repository,'inputs':{'source_run':'123'}}
        self.run_trigger({'GITHUB_EVENT_NAME':'workflow_dispatch'})
        self.assertEqual(len(self.output.read_text().splitlines()),6)

    def test_private_credentials_and_unrelated_execution_are_rejected_before_network(self):
        for changes in ({'BOOKING_DATABASE_URL':'synthetic-private-authority'},{'GITHUB_REPOSITORY':'Other/Project'},
            {'RUNNER_ENVIRONMENT':'self-hosted'},{'GITHUB_REF':'refs/heads/other'},{'GITHUB_EVENT_NAME':'schedule'}):
            with self.subTest(changes=changes),self.assertRaises(BackupError):self.run_trigger(changes)
        self.assertEqual(self.calls,[]);self.assertFalse(self.output.exists())

    def test_invalid_source_identity_cannot_be_written_as_workflow_output(self):
        self.event={'repository':self.repository,'inputs':{}}
        for value in (None,True,0,'0','-1','12\nsource_commit=forged','1'*21):
            self.event['inputs']['source_run']=value
            with self.subTest(value=value),self.assertRaises(BackupError):self.run_trigger({'GITHUB_EVENT_NAME':'workflow_dispatch'})
        self.assertEqual(self.calls,[]);self.assertFalse(self.output.exists())

    def test_foreign_failed_or_private_remote_backup_never_unlocks_validation(self):
        original=deepcopy(self.record)
        for changes in ({'path':'.github/workflows/unrelated.yml'},{'conclusion':'failure'},{'status':'in_progress'},
            {'head_branch':'other'},{'event':'pull_request'},{'id':456},{'run_attempt':True},{'head_sha':'invalid'},
            {'head_repository':{'full_name':'Other/Project'}}):
            self.record=original|changes
            with self.subTest(changes=changes),self.assertRaises(BackupError):self.run_trigger()
        self.record=original;self.repository['private']=True
        with self.assertRaises(BackupError):self.run_trigger()
        self.assertFalse(self.output.exists())

    def test_missing_output_and_invalid_github_token_do_not_expose_success(self):
        for changes in ({'GITHUB_OUTPUT':''},{'GITHUB_OUTPUT':None},{'GITHUB_TOKEN':None}):
            with self.subTest(changes=changes),self.assertRaises(BackupError):self.run_trigger(changes)
        self.assertFalse(self.output.exists())
