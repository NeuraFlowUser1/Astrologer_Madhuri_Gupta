"""Private Contact worker lanes; empty inputs cannot select recipient or record."""
from fastapi import Request
from fastapi.responses import JSONResponse
from .google_worker import WakeRequest
from .contact_delivery import run_contact_email_once,run_contact_google_once


def add_contact_worker_routes(app,store,*,email_key,sender,keys,google_key,services):
    def denied(request,key,ready):
        if key is None or not ready:return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):return JSONResponse({'code':'unauthorized'},401)
        return None

    @app.post('/api/internal/contact/email',include_in_schema=False)
    def email(request:Request,body:WakeRequest):
        rejection=denied(request,email_key,sender is not None and keys is not None)
        if rejection is not None:return rejection
        return {'application':'004-sarsa-jyotish-sansthan',**run_contact_email_once(store,sender,keys)}

    @app.post('/api/internal/contact/google',include_in_schema=False)
    def google(request:Request,body:WakeRequest):
        rejection=denied(request,google_key,services is not None)
        if rejection is not None:return rejection
        return {'application':'004-sarsa-jyotish-sansthan',**run_contact_google_once(store,services)}
