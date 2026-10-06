"""Exact publication acknowledgements and a separate fresh probe of the hosted guard."""
import asyncio
from dataclasses import dataclass,field
import os
import time
from uuid import UUID
from .configuration import installation,worker_origin
from .projection import key,signature,response_json,checked_attestation,ProjectionReader
from .serialization import canonical
from .service_control import ControlError,snapshot


@dataclass(frozen=True,repr=False)
class PublicationSettings:
    publish_key:bytes=field(repr=False)
    read_key:bytes=field(repr=False)
    origin:str

    def __post_init__(self):
        if (self.origin!=worker_origin() or any(type(value) is not bytes or len(value)!=32
                                               for value in (self.publish_key,self.read_key))
            or self.publish_key==self.read_key):
            raise ControlError("publication_configuration")


def settings_from_environment(environment=None):
    source=os.environ if environment is None else environment
    try:return PublicationSettings(key(source["BOOKING_CONTROL_PUBLISH_KEY"]),key(source["BOOKING_CONTROL_READ_KEY"]),worker_origin())
    except (KeyError,ControlError):return None


class Publisher:
    def __init__(self,database,settings,*,transport=None,clock=None):
        self.database,self.settings=database,settings
        self.transport,self.clock=transport,clock or (lambda:int(time.time()*1000))

    def __call__(self):
        # Automatic calls already hold the common lane/turn authority. Immediate
        # company calls claim the same fenced publication job; neither creates
        # a second legacy recovery run or fabricates a lane completion.
        return self._publish()

    def _publish(self):
        if self.settings is None:raise ControlError("publication_configuration")
        self.settings.__post_init__()
        job=self.database.claim_publication()
        if job is None:
            job=self.database.claim_probe()
            if job is None:return {"processed":0,"retry":False}
            return {"processed":1,"retry":not self._probe(job,retry_claim=True)}
        facts=installation();error=None;ack=None
        try:
            body={"version":1,"installation_id":facts["installation_id"],"project":facts["project_id"],
                  "environment":facts["environment"],"purpose":"publish","operation_id":str(UUID(str(job["operation_id"]))),
                  "issued_at_ms":self.clock(),"snapshot":snapshot(job["snapshot"])}
            value=asyncio.run(response_json("POST",self.settings.origin+"/service-control/publish",
                 transport=self.transport,headers={"Content-Type":"application/json",
                 "X-Booking-Control-Signature":signature(self.settings.publish_key,"publish",body)},content=canonical(body)))
            ack=checked_attestation(value,self.settings.publish_key,"publish-ack",now=self.clock(),
                                    operation=body["operation_id"],expected=job["snapshot"])
        except ControlError as failure:error=failure.code
        except (ValueError,TypeError,KeyError):error="publication_unconfirmed"
        finished=self.database.finish_publication(job,ack,error)
        effective=False
        if error is None and finished is True:
            effective=self._probe(job)
        return {"processed":1,"retry":error is not None or finished is not True or not effective}

    def _probe(self,job,*,retry_claim=False):
        error=None
        try:
            reader=ProjectionReader(self.settings.read_key,self.settings.origin,self.transport,self.clock)
            observed=asyncio.run(reader.attestation(host=True))["snapshot"]
            if self.database.record_probe(job,observed) is True:return True
            error="hosted_probe_changed"
        except ControlError as failure:error=failure.code
        if retry_claim:self.database.probe_retry(job,error)
        return False
