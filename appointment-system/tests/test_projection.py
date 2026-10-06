import asyncio
from copy import deepcopy
import hashlib
import json
import unittest
from uuid import uuid4
import httpx
from appointment_system.configuration import installation
from appointment_system.projection import ProjectionReader,checked_attestation,key,signature,response_json
from appointment_system.serialization import canonical
from appointment_system.service_control import ControlError
from appointment_system.visibility import BookingVisibility

NOW=1790956800000
SECRET=b"x"*32


def state(enabled=True):
    facts=installation()
    return dict(version=1,installation_id=facts["installation_id"],project=facts["project_id"],environment=facts["environment"],
          origin=facts["origin"],enabled=enabled,restore_generation=str(uuid4()),generation_sequence="1",revision="9007199254740993",
          activation_epoch=str(uuid4()))


def attestation(snapshot,nonce):
    facts=installation()
    value=dict(version=1,installation_id=facts["installation_id"],project=facts["project_id"],environment=facts["environment"],
          purpose="read",operation_id=None,issued_at_ms=NOW,published_at_ms=NOW-86400000,snapshot=snapshot,
          snapshot_hash=hashlib.sha256(canonical(snapshot)).hexdigest(),reconcile_pending=False,nonce=nonce)
    return value|{"signature":signature(SECRET,"read",value)}


class ProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reader_validates_fresh_nonce_and_preserves_large_counters_and_old_publication_age(self):
        snap=state()
        def handler(request):
            self.assertEqual(str(request.url),"https://worker.example.test/service-state")
            return httpx.Response(200,json=attestation(snap,request.headers["x-booking-state-nonce"]))
        reader=ProjectionReader(SECRET,"https://worker.example.test",httpx.MockTransport(handler),lambda:NOW)
        self.assertEqual(await reader.read(),snap)
        self.assertEqual((await reader.attestation("a"*64))["published_at_ms"],NOW-86400000)

    async def test_tampering_scope_nonce_freshness_shape_and_numeric_ambiguity_are_rejected(self):
        good=attestation(state(),"a"*64)
        changes={"installation_id":str(uuid4()),"project":"other","environment":"production","purpose":"publish-ack",
                 "operation_id":str(uuid4()),"issued_at_ms":NOW-60001,"published_at_ms":NOW+1,"nonce":"b"*64,
                 "signature":"0"*64,"snapshot_hash":"0"*64,"reconcile_pending":True,"version":True}
        for name,value in changes.items():
            with self.subTest(name=name):
                bad=deepcopy(good);bad[name]=value
                with self.assertRaises(ControlError):
                    checked_attestation(bad,SECRET,"read",now=NOW,nonce="a"*64)
        for field,value in (("revision",9007199254740993),("activation_epoch",str(uuid4())),("enabled",1)):
            bad=deepcopy(good);bad["snapshot"][field]=value
            with self.assertRaises(ControlError):checked_attestation(bad,SECRET,"read",now=NOW,nonce="a"*64)
        for bad in (None,[],good|{"extra":1}):
            with self.assertRaises(ControlError):checked_attestation(bad,SECRET,"read",now=NOW,nonce="a"*64)

    async def test_redirect_wrong_type_oversize_duplicate_keys_and_timeout_are_unavailable(self):
        for response in (httpx.Response(302,headers={"Location":"https://other.example.test"}),
                         httpx.Response(200,text="{}",headers={"Content-Type":"text/html"}),
                         httpx.Response(200,content=b"x"*4097,headers={"Content-Type":"application/json"}),
                         httpx.Response(200,content=b'{"enabled":true,"enabled":false}',headers={"Content-Type":"application/json"})):
            with self.assertRaises(ControlError):
                await response_json("GET","https://worker.example.test/service-state",transport=httpx.MockTransport(lambda request:response))
        async def blocked(request):
            await asyncio.sleep(10)
        with self.assertRaises(ControlError):
            await response_json("GET","https://worker.example.test/service-state",transport=httpx.MockTransport(blocked))

    async def test_projection_settings_and_key_bounds(self):
        for invalid in (None,"short","!"*44,"eA"*22,b"x"*32):
            with self.assertRaises(ControlError):key(invalid)
        for origin,secret in (("https://other.example.test",SECRET),("https://worker.example.test",b"short")):
            with self.assertRaises(ControlError):ProjectionReader(secret,origin)
        reader=ProjectionReader(SECRET,"https://worker.example.test")
        with self.assertRaises(ControlError):await reader.attestation("bad")

    async def test_off_and_unknown_hide_booking_but_leave_enquiries_company_and_provider_routes(self):
        class Reader:
            async def read(self):return state(False)
        async def app(scope,receive,send):
            await send({"type":"http.response.start","status":200,"headers":[]})
            await send({"type":"http.response.body","body":b"general"})
        async def get(path,reader):
            client=httpx.AsyncClient(transport=httpx.ASGITransport(app=BookingVisibility(app,reader)),base_url="https://practice.example.test")
            async with client:return await client.get(path)
        for reader in (Reader(),None):
            for path in ("/booking","/receipt","/api/checkout/status","/studio","/api/studio/assets/calendar.js","/dashboard"):
                self.assertEqual((await get(path,reader)).status_code,404)
            for path in ("/","/contact","/api/contact/start","/company/booking-control","/api/internal/recovery","/api/webhooks/razorpay"):
                self.assertEqual((await get(path,reader)).status_code,200)

    async def test_public_state_and_probe_use_fresh_reads_without_database_access(self):
        class Reader:
            async def read(self):return state(True)
            async def attestation(self,nonce):return attestation(state(True),nonce)
        async def app(*args):raise AssertionError("A state read must not reach the application/database.")
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=BookingVisibility(app,Reader())),base_url="https://practice.example.test")
        async with client:
            response=await client.get("/api/service-state");self.assertTrue(response.json()["enabled"])
            self.assertEqual((await client.get("/api/service-state/probe")).status_code,400)
            response=await client.get("/api/service-state/probe",headers={"X-Booking-State-Nonce":"c"*64})
            self.assertEqual(response.json()["nonce"],"c"*64)
            self.assertEqual((await client.post("/api/service-state")).status_code,405)
            self.assertEqual((await client.get("/api/service-state/probe",headers={"X-Booking-State-Nonce":"bad"})).status_code,400)
