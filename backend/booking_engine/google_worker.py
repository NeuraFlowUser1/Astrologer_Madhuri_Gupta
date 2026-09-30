"""Authenticated, bounded Google delivery entry point for the permanent worker.

No browser, customer receipt or owner-session authority can invoke this route.
It never accepts an owner, workbook, meeting, destination or booking identifier.
A scheduler/queue wake-up asks the database to select one eligible saved job.
"""

import base64
import binascii
import hmac
import re
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .google_delivery import run_google_delivery_once


@dataclass(frozen=True)
class WorkerKey:
    value: str = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=',self.value):
                raise ValueError()
            if len(base64.b64decode(self.value,altchars=b'-_',validate=True))!=32:
                raise ValueError()
        except (ValueError,binascii.Error):
            raise ValueError('Worker configuration is incomplete.') from None

    def accepts(self, headers):
        values=headers.getlist('authorization')
        return len(values)==1 and hmac.compare_digest(values[0].encode(),('Bearer '+self.value).encode())


class WakeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')


def add_google_worker_route(app,store,services,key):
    @app.post('/api/internal/google/run',include_in_schema=False)
    def run(request:Request,body:WakeRequest):
        if key is None or services is None:
            return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):
            return JSONResponse({'code':'unauthorized'},401)
        result=run_google_delivery_once(store,services)
        return {'application':'004-sarsa-jyotish-sansthan','environment':'production',**result}
