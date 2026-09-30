"""Private recovery planning and payment lanes; no caller-selected customer/job."""
from fastapi import Request
from fastapi.responses import JSONResponse
from .google_worker import WakeRequest
from .recovery import run_payment_recovery_once, run_payment_event_once

APPLICATION = '004-sarsa-jyotish-sansthan'
LANES = frozenset(('email','email_events','google','payment','payment_events','contact_email','contact_google'))


def checked_plan(value):
    if (not isinstance(value,dict) or set(value)!={'lanes','attention'}
            or not isinstance(value['lanes'],dict) or set(value['lanes'])!=LANES
            or type(value['attention']) is not bool
            or any(v is not None and (type(v) is not int or not 0<=v<=900)
                   for v in value['lanes'].values())):
        raise ValueError('Recovery plan unavailable.')
    return dict(application=APPLICATION,version=1,**value)


def add_recovery_worker_routes(app,store,key,accounts=None):
    def denied(request,payment=False):
        if key is None or (payment and accounts is None):
            return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):
            return JSONResponse({'code':'unauthorized'},401)
        return None

    @app.post('/api/internal/recovery/plan',include_in_schema=False)
    def plan(request:Request,body:WakeRequest):
        rejection=denied(request)
        if rejection is not None:return rejection
        return checked_plan(store.recovery_plan())

    @app.post('/api/internal/recovery/payment',include_in_schema=False)
    def payment(request:Request,body:WakeRequest):
        rejection=denied(request,True)
        if rejection is not None:return rejection
        return dict(application=APPLICATION,**run_payment_recovery_once(store,accounts))

    @app.post('/api/internal/recovery/payment-events',include_in_schema=False)
    def events(request:Request,body:WakeRequest):
        rejection=denied(request,True)
        if rejection is not None:return rejection
        return dict(application=APPLICATION,**run_payment_event_once(store,accounts))
