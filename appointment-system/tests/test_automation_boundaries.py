"""Fork/private/runner/run provenance and secret separation, without allocating Actions."""
from copy import deepcopy
import unittest
from appointment_system.backup.protocol import BackupError,canonical
from tools.automation.eligibility import eligible,runner,source_run,WORKFLOW
from tools.automation.backup import settings,PRIVATE,COMMON
from . import test_backup_protocol as crypto_tests

class AutomationBoundaries(unittest.TestCase):
    def setUp(self):
        self.repo={'full_name':'ExampleOwner/ExamplePractice','default_branch':'main','visibility':'public','private':False,'archived':False,'disabled':False,'fork':False}
        self.env={'GITHUB_REPOSITORY':self.repo['full_name'],'GITHUB_REF':'refs/heads/main','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux'}
        self.run={'path':WORKFLOW,'head_branch':'main','status':'completed','conclusion':'success','event':'schedule',
            'repository':{'full_name':self.repo['full_name']},'head_repository':{'full_name':self.repo['full_name']},'id':123,'run_attempt':1,'head_sha':'a'*40}
        _,self.export=crypto_tests.signing();_,self.validator=crypto_tests.signing()
    def test_only_exact_owned_public_unforked_active_main_repository_is_eligible(self):
        eligible(self.repo,self.repo['full_name'])
        for change in ({'full_name':'OtherOwner/OtherPractice'},{'default_branch':'feature'},{'private':True},{'fork':True},
            {'archived':True},{'disabled':True},{'private':0},{'private':None},{'visibility':'private'},{'visibility':None}):
            with self.subTest(change=change),self.assertRaises(BackupError):eligible(dict(self.repo,**change),self.repo['full_name'])
    def test_standard_hosted_linux_and_main_ref_are_required_again_at_runtime(self):
        runner(self.env,self.repo['full_name'],{'repository':self.repo})
        for change in ({'RUNNER_ENVIRONMENT':'self-hosted'},{'RUNNER_OS':'Windows'},{'GITHUB_REF':'refs/pull/1/merge'},
            {'GITHUB_REPOSITORY':'ForeignOwner/Practice'}):
            with self.assertRaises(BackupError):runner(dict(self.env,**change),self.repo['full_name'],{'repository':self.repo})
        with self.assertRaises(BackupError):runner(self.env,self.repo['full_name'],{})
    def test_validator_requires_successful_exact_export_not_fork_or_archive_selected_code(self):
        self.assertEqual(source_run(self.run,self.repo,self.repo['full_name'],'123'),('123','1','a'*40))
        for change in ({'path':'.github/workflows/foreign.yml'},{'head_branch':'feature'},{'status':'in_progress'},
            {'conclusion':'failure'},{'event':'pull_request'},{'head_repository':{'full_name':'Fork/Practice'}},
            {'id':True},{'run_attempt':True},{'head_sha':'invalid'}):
            with self.subTest(change=change),self.assertRaises(BackupError):source_run(dict(self.run,**change),self.repo,self.repo['full_name'],'123')
        with self.assertRaises(BackupError):source_run(self.run,self.repo,self.repo['full_name'],'124')
    def stage(self,mode):
        values={name:'synthetic' for name in COMMON|PRIVATE[mode]}
        values['BOOKING_BACKUP_EXPORT_VERIFY_KEYS']=canonical({'export':self.export}).decode()
        values['BOOKING_BACKUP_VALIDATION_VERIFY_KEYS']=canonical({'validator':self.validator}).decode()
        return values
    def test_each_duty_refuses_every_other_dutys_private_credentials(self):
        for mode in PRIVATE:
            stage=self.stage(mode);self.assertEqual(settings(stage,mode),({'export':self.export},{'validator':self.validator}))
            for other in set().union(*PRIVATE.values())-(COMMON|PRIVATE[mode]):
                with self.subTest(mode=mode,other=other),self.assertRaisesRegex(BackupError,'wrong_duty'):settings(dict(stage,**{other:'private other authority'}),mode)
            for other in ('BOOKING_DATABASE_URL','BOOKING_COMPANY_DATABASE_URL','BOOKING_GOOGLE_CLIENT_SECRET','BOOKING_PRIVACY_KEYS'):
                with self.assertRaisesRegex(BackupError,'wrong_duty'):settings(dict(stage,**{other:'serving secret'}),mode)
    def test_missing_ambient_or_shared_signing_authority_is_refused_before_any_provider(self):
        for mode in PRIVATE:
            stage=self.stage(mode)
            for key in stage:
                changed=deepcopy(stage);del changed[key]
                with self.assertRaises(BackupError):settings(changed,mode)
            with self.assertRaisesRegex(BackupError,'ambient'):settings(dict(stage,PGPASSWORD='unexpected'),mode)
            changed=dict(stage,BOOKING_BACKUP_VALIDATION_VERIFY_KEYS=stage['BOOKING_BACKUP_EXPORT_VERIFY_KEYS'])
            with self.assertRaisesRegex(BackupError,'not_separate'):settings(changed,mode)

if __name__=='__main__':unittest.main()
