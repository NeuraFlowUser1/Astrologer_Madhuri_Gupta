import base64
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.google_worker import WorkerKey
from backend.booking_engine.connection import StorageUnavailable


class GoogleWorkerTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock()
        self.key=WorkerKey(base64.urlsafe_b64encode(b'w'*32).decode())
        self.settings=Settings('https://sarsa.example',b'a'*32,b'b'*32,b'c'*32)

    def client(self,enabled=True):
        # No StudioServices: add the internal route to a bare app explicitly.
        from fastapi import FastAPI
        from backend.booking_engine.google_worker import add_google_worker_route
        app=FastAPI(); add_google_worker_route(app,self.store,Mock(),self.key if enabled else None)
        return TestClient(app,raise_server_exceptions=False)

    def test_missing_config_unauthenticated_and_duplicate_credentials_do_not_claim(self):
        for client,headers,status in [(self.client(False),{},503),(self.client(),{},401),
            (self.client(),{'Authorization':'Bearer wrong'},401),
            (self.client(),[('Authorization','Bearer '+self.key.value),('Authorization','Bearer '+self.key.value)],401)]:
            response=client.post('/api/internal/google/run',json={},headers=headers)
            self.assertEqual(response.status_code,status)
        self.store.claim_google_delivery.assert_not_called()

    def test_valid_wakeup_accepts_no_customer_target_and_returns_no_private_payload(self):
        client=self.client(); headers={'Authorization':'Bearer '+self.key.value}
        with patch('backend.booking_engine.google_worker.run_google_delivery_once',return_value={'processed':1,'state':'done'}) as run:
            response=client.post('/api/internal/google/run',json={'role':'client'},headers=headers)
            self.assertEqual(response.status_code,422); run.assert_not_called()
            response=client.post('/api/internal/google/run',json={},headers=headers)
            self.assertEqual(response.status_code,200); run.assert_called_once()
            self.assertEqual(response.json(),{'application':'004-sarsa-jyotish-sansthan','environment':'production','processed':1,'state':'done'})
            self.assertNotIn(self.key.value,response.text)

    def test_key_validation_and_repr(self):
        self.assertNotIn(self.key.value,repr(self.key))
        for invalid in ('','short',self.key.value+'\n',None):
            with self.assertRaises(ValueError): WorkerKey(invalid)


class ObsoleteMeetingTests(unittest.TestCase):
    def test_old_revision_is_removed_without_creating_another_meeting(self):
        from backend.booking_engine.google_delivery import run_google_delivery_once
        store=Mock();job={'kind':'booking_calendar','obsolete':True,'attempts':2,'payload':{'id':'synthetic','revision':1}}
        store.claim_google_delivery.return_value=job;store.finish_google_delivery.return_value=True
        with patch('backend.booking_engine.google_delivery.refresh_connection'),patch('backend.booking_engine.google_delivery.Workspace') as workspace:
            result=run_google_delivery_once(store,Mock())
            workspace.return_value.cancel_meeting.assert_called_once_with(job['payload'])
            workspace.return_value.ensure_meeting.assert_not_called()
            self.assertEqual(result,{'processed':1,'state':'obsolete'})
            self.assertEqual(store.finish_google_delivery.call_args.args[1],'obsolete')

if __name__=='__main__':unittest.main()
