import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.booking_engine.retired_routes import RetiredSubmissions,RETIRED_PATHS


class RetiredRoutesTests(unittest.TestCase):
    def test_obsolete_requests_never_reach_handlers_or_body_parsing(self):
        app=FastAPI()
        called=[]
        @app.api_route('/{path:path}',methods=['GET','POST'])
        def downstream(path):
            called.append(path)
            return {'ok':True}
        app.add_middleware(RetiredSubmissions)
        with TestClient(app) as client:
            for path in RETIRED_PATHS:
                for suffix in ('','/'):
                    response=client.post(path+suffix,content='not JSON')
                    self.assertEqual(response.status_code,410)
                    self.assertEqual(response.json()['code'],'endpoint_retired')
                    self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(called,[])
            self.assertEqual(client.post('/api/contact/status',json={}).status_code,200)
            self.assertEqual(called,['api/contact/status'])
