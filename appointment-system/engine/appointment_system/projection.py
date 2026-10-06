"""Fresh, signed display state. Reads never connect to the booking database."""
import asyncio
import base64
import binascii
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass,field
import httpx
from .configuration import installation,worker_origin
from .serialization import canonical,decode
from .errors import Rejected
from .service_control import ControlError,snapshot

MAXIMUM=4096


def key(value):
    try:
        if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{43}=",value):raise ValueError()
        result=base64.b64decode(value,altchars=b"-_",validate=True)
        if len(result)!=32 or base64.urlsafe_b64encode(result).decode()!=value:raise ValueError()
        return result
    except (ValueError,TypeError,binascii.Error):
        raise ControlError("projection_configuration") from None


def signature(secret,purpose,value):
    facts=installation()
    scope=f"booking-product:{facts['installation_id']}:{facts['environment']}:v1:{purpose}:".encode()
    return hmac.new(secret,scope+canonical(value),hashlib.sha256).hexdigest()


def checked_attestation(value,secret,purpose,*,now,nonce=None,operation=None,expected=None):
    facts=installation()
    names={"version","installation_id","project","environment","purpose","operation_id","issued_at_ms",
           "published_at_ms","snapshot","snapshot_hash","reconcile_pending","signature"}
    if nonce is not None:names.add("nonce")
    if (type(value) is not dict or set(value)!=names or type(value["version"]) is not int or value["version"]!=1
        or value["installation_id"]!=facts["installation_id"] or value["project"]!=facts["project_id"]
        or value["environment"]!=facts["environment"] or value["purpose"]!=purpose
        or value["operation_id"]!=operation or value.get("nonce")!=nonce
        or type(value["issued_at_ms"]) is not int or abs(now-value["issued_at_ms"])>60000
        or type(value["published_at_ms"]) is not int or not 0<value["published_at_ms"]<=value["issued_at_ms"]
        or value["reconcile_pending"] is not False or type(value["signature"]) is not str
        or not re.fullmatch(r"[a-f0-9]{64}",value["signature"])):
        raise ControlError("projection_response_invalid")
    accepted=snapshot(value["snapshot"])
    if (expected is not None and accepted!=snapshot(expected)
        or value["snapshot_hash"]!=hashlib.sha256(canonical(accepted)).hexdigest()
        or not hmac.compare_digest(value["signature"],signature(secret,purpose,
                   {name:item for name,item in value.items() if name!="signature"}))):
        raise ControlError("projection_response_invalid")
    return accepted


async def response_json(method,url,*,transport=None,headers=None,content=None):
    try:
        async with asyncio.timeout(2):
            async with httpx.AsyncClient(timeout=2,follow_redirects=False,trust_env=False,transport=transport) as client:
                async with client.stream(method,url,headers=headers,content=content) as response:
                    if response.status_code!=200:raise ControlError("projection_unconfirmed")
                    if response.headers.get("content-type","").split(";")[0]!="application/json":
                        raise ControlError("projection_response_invalid")
                    body=bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>MAXIMUM:raise ControlError("projection_response_invalid")
                    return decode(bytes(body),maximum=MAXIMUM)
    except ControlError:raise
    except (TimeoutError,httpx.HTTPError,ValueError,TypeError,Rejected):
        raise ControlError("projection_unconfirmed") from None


@dataclass(frozen=True,repr=False)
class ProjectionReader:
    read_key:bytes=field(repr=False)
    origin:str
    transport:object=field(default=None,repr=False)
    clock:object=field(default=None,repr=False)

    def __post_init__(self):
        if self.origin!=worker_origin() or type(self.read_key) is not bytes or len(self.read_key)!=32:
            raise ControlError("projection_configuration")

    async def attestation(self,nonce=None,*,host=False):
        self.__post_init__()
        nonce=nonce or secrets.token_hex(32)
        if type(nonce) is not str or not re.fullmatch(r"[a-f0-9]{64}",nonce):
            raise ControlError("projection_response_invalid")
        url=(installation()["origin"]+"/api/service-state/probe") if host else self.origin+"/service-state"
        value=await response_json("GET",url,transport=self.transport,headers={"X-Booking-State-Nonce":nonce})
        checked_attestation(value,self.read_key,"read",now=(self.clock or (lambda:int(time.time()*1000)))(),nonce=nonce)
        return value

    async def read(self):
        return (await self.attestation())["snapshot"]

    def read_sync(self):
        return asyncio.run(self.read())
