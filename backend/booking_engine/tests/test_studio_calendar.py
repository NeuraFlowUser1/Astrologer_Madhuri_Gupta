"""Synthetic HTTP tests; no Google, database, email or payment traffic."""
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock
from uuid import uuid4
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.studio import StudioServices,SESSION_COOKIE
from backend.booking_engine.google_oauth import GoogleOAuth,OAuthSettings,GrantCipher
from backend.booking_engine.connection import StorageUnavailable

ORIGIN='https://sarsa.example'
class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock()
        self.store.consume_limit.return_value={'allowed':True,'retry_after':1}
        self.store.studio_session.return_value={'role':'client','subject':'synthetic'}
        google=GoogleOAuth(OAuthSettings('123-test.apps.googleusercontent.com','synthetic-secret',ORIGIN))
        services=StudioServices(google,GrantCipher(google.settings.client_id,[Fernet.generate_key()]),b'd'*32)
        app=create_application(self.store,Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32),
            verified_client_address=lambda _:'192.0.2.1',studio_services=services)
        self.client=TestClient(app,base_url=ORIGIN,raise_server_exceptions=False)
        self.client.cookies.set(SESSION_COOKIE,'a'*43)
        self.headers={'Origin':ORIGIN}
        start=(datetime.now(timezone.utc)+timedelta(days=1)).replace(second=0,microsecond=0)
        self.body={'operation_id':str(uuid4()),'reason':'Personal commitment','starts_at':start.isoformat(),
                   'ends_at':(start+timedelta(hours=1)).isoformat()}
    def post(self,path,body=None,headers=None):
        return self.client.post('/api/studio/calendar/'+path,json=self.body if body is None else body,
            headers=self.headers if headers is None else headers)
    def test_client_closure_derives_actor_and_preserves_operation(self):
        self.store.studio_calendar_close.return_value={'code':'closed','claim_id':str(uuid4())}
        result=self.post('close');self.assertEqual(result.status_code,200)
        args=self.store.studio_calendar_close.call_args.args
        self.assertEqual(str(args[3]),self.body['operation_id']);self.assertEqual(args[4],self.body['reason'])
        self.assertEqual(result.headers['cache-control'],'no-store')
    def test_agency_cannot_view_or_modify(self):
        self.store.studio_session.return_value={'role':'agency'}
        for path,body in [('list',{'day':'2030-01-01'}),('close',self.body),('reopen',{'operation_id':str(uuid4()),'claim_id':str(uuid4()),'reason':'Open again'})]:
            self.assertEqual(self.post(path,body).status_code,403)
        self.store.studio_calendar_list.assert_not_called();self.store.studio_calendar_close.assert_not_called();self.store.studio_calendar_reopen.assert_not_called()
    def test_missing_revoked_or_wrong_origin_denied(self):
        self.assertEqual(self.post('close',headers={'Origin':'https://evil.example'}).status_code,403)
        self.client.cookies.clear();self.assertEqual(self.post('close').status_code,403)
        self.client.cookies.set(SESSION_COOKIE,'a'*43);self.store.studio_session.return_value=None
        self.assertEqual(self.post('close').status_code,403);self.store.studio_calendar_close.assert_not_called()
    def test_naive_times_extra_actor_long_period_and_control_reason_rejected(self):
        variants=[dict(self.body,actor='agency'),dict(self.body,starts_at='2030-01-01T10:00:00'),
                  dict(self.body,ends_at='2035-01-01T10:00:00Z'),dict(self.body,reason='secret\nline')]
        for body in variants:self.assertEqual(self.post('close',body).status_code,422)
        self.store.studio_calendar_close.assert_not_called()
    def test_database_session_recheck_denies_after_http_authorization(self):
        self.store.studio_calendar_close.return_value={'code':'access_unavailable'}
        self.assertEqual(self.post('close').status_code,403)
    def test_conflict_and_unknown_commit_are_not_success(self):
        self.store.studio_calendar_close.return_value={'code':'time_already_reserved'}
        self.assertEqual(self.post('close').status_code,409)
        self.store.studio_calendar_close.side_effect=StorageUnavailable('private connection detail')
        result=self.post('close');self.assertEqual(result.status_code,503);self.assertNotIn('private connection',result.text)
    def test_reopen_and_list_use_same_authorized_session(self):
        self.store.studio_calendar_reopen.return_value={'code':'already_open'}
        result=self.post('reopen',{'operation_id':str(uuid4()),'claim_id':str(uuid4()),'reason':'Open again'})
        self.assertEqual(result.status_code,200)
        self.store.studio_calendar_list.return_value={'code':'ok','items':[],'next_cursor':None}
        self.assertEqual(self.post('list',{'day':'2030-01-01'}).status_code,200)
        self.assertEqual(self.store.studio_calendar_list.call_args.args[0],self.store.studio_calendar_reopen.call_args.args[0])
    def test_rate_limit_prevents_mutation(self):
        self.store.consume_limit.return_value={'allowed':False,'retry_after':60}
        result=self.post('close');self.assertEqual(result.status_code,429);self.assertEqual(result.headers['retry-after'],'60')
        self.store.studio_calendar_close.assert_not_called()
    def test_unknown_database_code_fails_closed(self):
        self.store.studio_calendar_close.return_value={'code':'surprise'}
        self.assertEqual(self.post('close').status_code,503)
