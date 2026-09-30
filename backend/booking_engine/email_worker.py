"""Email-only worker routes. No customer-controlled destination or job input."""
from fastapi import Request
from fastapi.responses import JSONResponse
from .google_worker import WakeRequest
from .email_delivery import run_email_delivery_once


def add_email_worker_routes(app,store,key,sender):
    def denied(request,needs_sender=False):
        if key is None or (needs_sender and sender is None):
            return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):
            return JSONResponse({'code':'unauthorized'},401)
        return None

    @app.post('/api/internal/email/run',include_in_schema=False)
    def run(request:Request,body:WakeRequest):
        rejection=denied(request,True)
        if rejection is not None:return rejection
        return {'application':'004-sarsa-jyotish-sansthan',**run_email_delivery_once(store,sender)}

    @app.post('/api/internal/email/events',include_in_schema=False)
    def events(request:Request,body:WakeRequest):
        rejection=denied(request)
        if rejection is not None:return rejection
        # Each transaction retains its own durable event; neither lane can starve
        # the other, and a failure never rolls back a previously saved event.
        booking=store.reconcile_email_event()
        contact=store.reconcile_enquiry_email_event()
        return {'application':'004-sarsa-jyotish-sansthan','processed':int(booking)+int(contact)}
