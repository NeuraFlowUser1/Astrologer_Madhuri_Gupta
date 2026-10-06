"""Per-request time budget and sanitized operational observations.

No provider/body/URL/identity enters this log. Provider reads leave three
seconds for recording uncertainty. The platform retains its final margin.
"""
from .configuration import owners,sender,project_id,label,worker_origin,origin
import contextvars
import json
import logging
import time
from contextlib import contextmanager
from http.client import HTTPResponse
from uuid import uuid4
import httpx
import psycopg


CEILING = 20.0
_deadline = contextvars.ContextVar('booking_deadline', default=None)
_incident = contextvars.ContextVar('booking_incident', default=None)
log = logging.getLogger('booking.operations')

class BudgetExpired(TimeoutError):
    """An uncertain operation stays recoverable; do not fabricate success."""

def reference():
    return _incident.get()


_provider_active = contextvars.ContextVar('booking_provider_active', default=False)
_metrics = contextvars.ContextVar('booking_request_metrics', default=None)
PROVIDERS = frozenset(('google','razorpay','resend'))

@contextmanager
def observe_provider(provider, *, clock=time.monotonic):
    """Optional operation timing. No URL, payload or exception is observed.

    A returned operation is not proof of provider acceptance. Nested refresh
    transports belong to the outer operation and are not counted twice.
    """
    if _provider_active.get() or not isinstance(provider,str) or provider not in PROVIDERS:
        yield
        return
    token = _provider_active.set(True)
    try:started = clock()
    except Exception:started = None
    returned = False
    try:
        yield
        returned = True
    finally:
        try:
            elapsed = max(0,min(60000,round((clock()-started)*1000)))
            totals = _metrics.get()
            if totals is not None:
                totals['provider_elapsed_ms'] = min(60000,totals['provider_elapsed_ms']+elapsed)
                totals['provider_calls'] = min(1000,totals['provider_calls']+1)
            log.info(json.dumps(dict(version=1,project=project_id(),stage='provider',provider=provider,
                reference=reference(),elapsed_ms=elapsed,outcome='returned' if returned else 'interrupted',
                acceptance='not_asserted'),separators=(',',':')))
        except Exception:
            pass  # Optional metrics cannot change dispatch or its saved result.
        _provider_active.reset(token)

def remaining(reserve=0):
    end = _deadline.get()
    value = CEILING if end is None else end-time.monotonic()
    if value <= reserve:
        raise BudgetExpired('request_budget_exhausted')
    return value-reserve

@contextmanager
def budget(seconds=CEILING, *, clock=time.monotonic):
    if not 0 < seconds <= CEILING:
        raise ValueError('Invalid request budget')
    outer = _deadline.get()
    token = _deadline.set(min(outer,clock()+seconds) if outer is not None else clock()+seconds)
    try:
        yield
    finally:
        _deadline.reset(token)

def provider_timeout(maximum=8):
    value = min(maximum, remaining(3))
    return httpx.Timeout(value,connect=min(value,3),read=min(value,1.5),write=min(value,3),pool=min(value,1))

def chunks(response):
    for chunk in response.iter_bytes():
        remaining(2)
        yield chunk

def read_bounded(response, maximum):
    # read1 returns available bytes, allowing a deadline check between arrivals.
    stream = response if isinstance(response,HTTPResponse) else getattr(response,'fp',None)
    if not isinstance(stream,HTTPResponse):
        remaining(2)
        raw = response.read(maximum+1)
        if not isinstance(raw,bytes) or len(raw)>maximum:
            raise ValueError('response_size_invalid')
        return raw
    body = bytearray()
    while True:
        remaining(2)
        part = stream.read1(min(16384,maximum+1-len(body)))
        if not part:
            return bytes(body)
        body.extend(part)
        if len(body)>maximum:
            raise ValueError('response_size_invalid')

class BudgetCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        available=remaining(.25)
        previous=getattr(self.connection,'_budget_statement_seconds',5.0)
        if available < previous:
            milliseconds=max(1,int(available*1000))
            super().execute("SELECT set_config('statement_timeout',%s,true)",(str(milliseconds),))
            self.fetchone()
            self.connection._budget_statement_seconds=available
        return super().execute(query,params,**kwargs)

def operation_kind(path):
    for prefix,kind in (('/api/company','control'),('/company','control'),('/api/webhooks','provider_event'),
            ('/api/internal','recovery'),('/api/auth','verification'),('/api/contact','enquiry'),
            ('/api/studio','staff'),('/api/admin','staff'),('/api/checkout','checkout'),
            ('/api/booking','booking'),('/api/availability','availability')):
        if path.startswith(prefix):
            return kind
    return 'site'

class BudgetMiddleware:
    def __init__(self,app):
        self.app=app
        self.first_request=True
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        started=time.monotonic();identity=str(uuid4());token=_incident.set(identity)
        first=self.first_request;self.first_request=False
        totals={'provider_elapsed_ms':0,'provider_calls':0}
        metrics_token=_metrics.set(totals)
        scope.setdefault('state',{})['booking_reference']=identity
        status=503
        async def observed_send(message):
            nonlocal status
            if message['type']=='http.response.start':
                status=message['status']
                message=dict(message)
                headers=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'x-booking-reference']
                message['headers']=headers+[(b'x-booking-reference',identity.encode())]
            await send(message)
        try:
            with budget():
                await self.app(scope,receive,observed_send)
        except Exception:
            scope.setdefault('state',{})['booking_failure_code']='unexpected_failure'
            raise
        finally:
            try:
                from .diagnostics import record_optional,CODES
                elapsed=max(0,round((time.monotonic()-started)*1000))
                code=scope.get('state',{}).get('booking_failure_code','service_unavailable')
                code=code if code in CODES else 'service_unavailable'
                diagnostic=await record_optional(scope,identity,operation_kind(scope.get('path','')),elapsed) if status>=500 else 'not_required'
                log.info(json.dumps(dict(version=1,project=project_id(),operation=operation_kind(scope.get('path','')),
                    reference=identity,status=status,elapsed_ms=elapsed,first_request=first,stage='request',
                    provider_elapsed_ms=totals['provider_elapsed_ms'],provider_calls=totals['provider_calls'],
                    application_elapsed_ms=max(0,elapsed-totals['provider_elapsed_ms']),
                    code=code if status>=500 else None,diagnostic=diagnostic,
                    outcome='completed' if status<400 else 'rejected' if status<500 else 'recoverable'),separators=(',',':')))
            except Exception:
                pass  # Diagnostics must never undo or hide an already committed result.
            _metrics.reset(metrics_token)
            _incident.reset(token)
