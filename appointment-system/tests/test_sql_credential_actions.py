"""Re-entry is admitted and bound; replacing a password revokes previous access."""
from uuid import uuid4
from .test_sql_company import CompanyFixture
from appointment_system.company_auth import password_hash
from tools.checks.sql_target import literal


class CredentialActionsSQL(CompanyFixture):
    def begin_action(self,action='reauthenticate'):
        return self.db.value('SELECT appointment_system.company_credential_begin('+','.join(map(literal,
            (self.token,self.csrf,uuid4().hex*2,action)))+');',role='abs_company')

    def finish_action(self,attempt,verified=True,action='reauthenticate',token=None,secret=None):
        fresh=uuid4().hex*2;csrf=uuid4().hex*2
        args=(token or self.token,self.csrf,attempt['attempt_id'],attempt['credential_revision'],verified,
              action,password_hash(secret) if secret else None,fresh,csrf)
        result=self.db.scalar('SELECT appointment_system.company_credential_finish('+','.join(map(literal,args))+');',role='abs_company')
        return result=='t',fresh,csrf

    def test_reentry_rotates_token_preserves_absolute_expiry_and_is_one_use(self):
        expires=self.db.scalar('SELECT expires_at::text FROM appointment_system.control_company_sessions WHERE token_hash='+literal(self.token)+';')
        attempt=self.begin_action();accepted,fresh,_=self.finish_action(attempt)
        self.assertTrue(accepted)
        self.assertEqual(self.db.scalar('SELECT appointment_system.company_session_touch('+literal(self.token)+');'),'f')
        self.assertEqual(self.db.scalar('SELECT appointment_system.company_session_touch('+literal(fresh)+');'),'t')
        self.assertEqual(self.db.scalar('SELECT expires_at::text FROM appointment_system.control_company_sessions WHERE token_hash='+literal(fresh)+';'),expires)
        with self.assertRaises(AssertionError):self.finish_action(attempt)

    def test_wrong_password_consumes_attempt_and_cannot_be_retried_as_verified(self):
        attempt=self.begin_action();self.assertFalse(self.finish_action(attempt,False)[0])
        self.assertFalse(self.finish_action(attempt)[0])
        self.assertEqual(self.db.scalar('SELECT appointment_system.company_session_touch('+literal(self.token)+');'),'t')

    def test_bound_attempt_cannot_login_or_change_a_different_session_or_action(self):
        attempt=self.begin_action()
        self.assertFalse(self.finish(attempt,True))
        self.assertFalse(self.finish_action(attempt,action='password',secret='Replacement synthetic password for tests')[0])
        self.assertFalse(self.finish_action(attempt,token=uuid4().hex*2)[0])
        self.assertTrue(self.finish_action(attempt)[0])

    def test_replaced_password_revokes_all_old_sessions_and_stale_hash_attempts(self):
        stale_login=self.begin();self.token=uuid4().hex*2;self.assertTrue(self.finish(self.begin(),True))
        attempt=self.begin_action('password');accepted,fresh,_=self.finish_action(attempt,action='password',secret='Replacement synthetic password for tests')
        self.assertTrue(accepted);self.assertFalse(self.finish(stale_login,True))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.control_company_sessions WHERE revoked_at IS NULL;'),'1')
        self.assertEqual(self.db.scalar('SELECT appointment_system.company_session_touch('+literal(fresh)+');'),'t')
        self.assertEqual(self.db.scalar('SELECT credential_revision FROM appointment_system.company_credentials WHERE username=\'company.owner\';'),
                         str(attempt['credential_revision']+1))

    def test_expired_attempt_and_revoked_session_cannot_finish(self):
        attempt=self.begin_action();self.db.sql('UPDATE appointment_system.company_login_attempts SET expires_at=clock_timestamp()-interval \'1 second\';')
        self.assertFalse(self.finish_action(attempt)[0])
        attempt=self.begin_action();self.db.sql('UPDATE appointment_system.control_company_sessions SET revoked_at=clock_timestamp();')
        with self.assertRaises(AssertionError):self.finish_action(attempt)

    def test_reentry_limits_are_shared_with_login_and_public_role_has_no_credential_access(self):
        for _ in range(4):self.assertIn('attempt_id',self.begin_action())
        self.assertEqual(self.begin_action(),{'code':'please_wait'})
        rejected=self.db.sql('SELECT appointment_system.company_credential_begin('+','.join(map(literal,
              (self.token,self.csrf,uuid4().hex*2,'reauthenticate')))+');',role='appointment_system_web',check=False)
        self.assertNotEqual(rejected.returncode,0)
