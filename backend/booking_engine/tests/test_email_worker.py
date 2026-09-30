import base64
import unittest
from unittest.mock import Mock,patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from backend.booking_engine.email_worker import add_email_worker_routes
from backend.booking_engine.google_worker import WorkerKey
from backend.booking_engine.hosting import create_hosted_application,ORIGIN
from backend.booking_engine.tests import test_hosting as hosting_tests
key=hosting_tests.key


class EmailWorkerTests(unittest.TestCase):
    def test_scoped_authority_and_no_job_input(self):
        app=FastAPI();store=Mock();sender=Mock();secret=key(b'e')
        add_email_worker_routes(app,store,WorkerKey(secret),sender)
        client=TestClient(app)
        for path in ('/api/internal/email/run','/api/internal/email/events'):
            self.assertEqual(client.post(path,json={}).status_code,401)
            self.assertEqual(client.post(path,json={},headers={'authorization':'Bearer wrong'}).status_code,401)
            self.assertEqual(client.post(path,json={'destination':'other@example.com'},headers={'authorization':'Bearer '+secret}).status_code,422)
        store.reconcile_email_event.return_value=True
        store.reconcile_enquiry_email_event.return_value=False
        response=client.post('/api/internal/email/events',json={},headers={'authorization':'Bearer '+secret})
        self.assertEqual(response.json()['processed'],1)
        sender.send.assert_not_called()

    def test_missing_or_bad_mail_configuration_does_not_disable_studio(self):
        fixture=hosting_tests.HostingTests();fixture.setUp()
        env=dict(fixture.environment,SARSA_RESEND_WEBHOOK_SECRET='invalid',SARSA_RESEND_API_KEY='invalid',SARSA_EMAIL_WORKER_KEY='invalid')
        with patch('psycopg.connect') as connect:
            app=create_hosted_application(env)
            self.assertIn('/studio',{r.path for r in app.routes})
            client=TestClient(app,base_url=ORIGIN)
            self.assertEqual(client.post('/api/webhooks/resend',json={}).status_code,503)
            self.assertEqual(client.post('/api/internal/email/run',json={}).status_code,503)
        connect.assert_not_called()

    def test_google_key_cannot_authorize_email_lane(self):
        fixture=hosting_tests.HostingTests();fixture.setUp()
        secret=key(b'e')
        env=dict(fixture.environment,SARSA_GOOGLE_WORKER_KEY=secret,SARSA_EMAIL_WORKER_KEY=secret)
        app=create_hosted_application(env)
        response=TestClient(app,base_url=ORIGIN).post('/api/internal/email/events',json={},headers={'authorization':'Bearer '+secret})
        self.assertEqual(response.status_code,503)
