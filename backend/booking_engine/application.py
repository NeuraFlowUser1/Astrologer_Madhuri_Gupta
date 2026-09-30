"""Final booking HTTP boundary; deployment routing is connected at cutover.

Contact uses separate durable contracts. Retired public submission paths are blocked. No unpaid-booking aliases,
mock modes, public admin routes or external fallback URLs exist in this app.
"""

from dataclasses import dataclass,field
from datetime import date,datetime,time,timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict

from .retired_routes import RetiredSubmissions
from .access import (AccessDenied,COOKIE_NAME,CONTEXT_SECONDS,authorize_context,new_context,parse_context)
from .availability import IntakeClosed,available_times
from .connection import StorageUnavailable
from .policy import IST,InvalidSelection,policy_snapshot,policy_version
from .rate_limit import RateLimited,consume_limit
from .receipt_view import receipt_view,timestamp
from .webhook import EventConflict,InvalidWebhook,MAX_WEBHOOK_BYTES,accept_webhook


@dataclass(frozen=True)
class Settings:
    origin: str
    receipt_key: bytes = field(repr=False)
    context_key: bytes = field(repr=False)
    risk_key: bytes = field(repr=False)

    def __post_init__(self):
        parsed=urlsplit(self.origin)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or self.origin!=f'https://{parsed.netloc}'
                or any(not isinstance(v,bytes) or len(v)<32 for v in
                       (self.receipt_key,self.context_key,self.risk_key))):
            raise ValueError('Secure booking application settings are required.')


class ReceiptRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID


class RequestBoundary:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        async def protected_send(message):
            if message['type']=='http.response.start':
                message=dict(message)
                headers=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'cache-control']
                message['headers']=headers+[(b'cache-control',b'no-store'),(b'referrer-policy',b'no-referrer'),
                    (b'x-content-type-options',b'nosniff')]
            await send(message)
        if scope['method'] in ('POST','PUT','PATCH'):
            headers=dict(scope.get('headers',[]))
            if (headers.get(b'content-type',b'').split(b';',1)[0].strip().lower()!=b'application/json'
                    or headers.get(b'content-encoding',b'identity').lower()!=b'identity'):
                return await JSONResponse({'code':'json_required','message':'Please send a supported request.'},415)(scope,receive,protected_send)
            maximum=MAX_WEBHOOK_BYTES if scope['path'] in ('/api/webhooks/razorpay','/api/webhooks/resend') else 16384
            body=bytearray()
            while True:
                message=await receive()
                if message['type']=='http.disconnect':
                    return
                body.extend(message.get('body',b''))
                if len(body)>maximum:
                    return await JSONResponse({'code':'request_too_large','message':'This request is too large.'},413)(scope,receive,protected_send)
                if not message.get('more_body',False):
                    break
            sent=False
            async def bounded_receive():
                nonlocal sent
                if not sent:
                    sent=True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()
            return await self.app(scope,bounded_receive,protected_send)
        return await self.app(scope,receive,protected_send)


def create_application(store,settings,*,verified_client_address,webhook_account=None,studio_services=None,worker_key=None,email_webhook=None,email_worker_key=None,email_sender=None,recovery_worker_key=None,payment_accounts=None,wake_publisher=None,contact_secrets=None,contact_delivery_ready=False):
    """Host integration must supply a tested, trusted client-address resolver.

    This is intentionally not inferred from user-supplied proxy headers. A
    missing resolver is a configuration error, never an unlimited-access mode.
    """
    if not isinstance(settings,Settings) or not callable(verified_client_address):
        raise ValueError('Booking application configuration is incomplete.')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(RequestBoundary)
    app.add_middleware(RetiredSubmissions)

    def browser_request(request):
        if request.headers.get('origin')!=settings.origin:
            raise AccessDenied()

    def limit(request,scope):
        consume_limit(store,scope,verified_client_address(request),settings.risk_key)

    from .contact_routes import add_contact_routes
    add_contact_routes(app,store,contact_secrets,browser_request,limit,wake_publisher,delivery_ready=contact_delivery_ready)
    from .contact_worker import add_contact_worker_routes
    add_contact_worker_routes(app,store,email_key=email_worker_key,sender=email_sender,keys=contact_secrets,
                              google_key=worker_key,services=studio_services)

    from .checkout_verification import add_checkout_verification_route
    add_checkout_verification_route(app,store,settings,payment_accounts,browser_request,limit,wake_publisher)
    from .checkout import add_checkout_routes
    add_checkout_routes(app,store,settings,payment_accounts,browser_request,limit,wake_publisher)

    @app.exception_handler(Exception)
    async def unexpected(request,error):
        return JSONResponse({'code':'temporarily_unavailable','message':'We cannot complete this request right now. Please try again shortly.'},503,
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})

    @app.exception_handler(AccessDenied)
    async def denied(request,error):
        return JSONResponse({'code':'access_unavailable','message':'We cannot safely open this booking here. Please use your original booking page or contact us.'},403)

    @app.exception_handler(StorageUnavailable)
    async def unavailable(request,error):
        return JSONResponse({'code':'temporarily_unavailable','message':'We cannot check bookings right now. Please try again shortly.'},503)

    @app.exception_handler(IntakeClosed)
    async def closed(request,error):
        return JSONResponse({'code':'booking_unavailable','message':'Online booking is not available at the moment. Please contact us for help.'},503)

    @app.exception_handler(RateLimited)
    async def limited(request,error):
        return JSONResponse({'code':'please_wait','message':'Please wait before trying again.'},429,
                            headers={'Retry-After':str(error.retry_after)})

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(InvalidSelection)
    async def invalid(request,error):
        # Do not return Pydantic's raw input values (names/contact/notes).
        return JSONResponse({'code':'invalid_request','message':'Please check the details and try again.'},422)

    from .recovery_worker import add_recovery_worker_routes
    add_recovery_worker_routes(app,store,recovery_worker_key,payment_accounts)

    from .email_worker import add_email_worker_routes
    add_email_worker_routes(app,store,email_worker_key,email_sender)

    @app.get('/api/booking-policy')
    def booking_policy(request:Request):
        limit(request,'availability')
        return dict(policy=policy_snapshot(),quote_version=policy_version())

    @app.get('/api/availability')
    def availability(request:Request,service_id:str,day:date):
        limit(request,'availability')
        return available_times(store,service_id,day)

    @app.post('/api/checkout-context')
    def checkout_context(request:Request):
        browser_request(request)
        limit(request,'context')
        # Context issue follows schedule browsing, independently of payments. Existing
        # receipts retain independent recovery access through the status route.
        today=datetime.now(IST).date()
        start=datetime.combine(today,time(),IST)
        snapshot=store.scheduling_snapshot(start,start+timedelta(days=1))
        if not snapshot or snapshot.get('schedule_browsing_open') is not True:
            raise IntakeClosed()
        if snapshot.get('policy_version')!=policy_version() or snapshot.get('specification')!=policy_snapshot():
            raise StorageUnavailable('Policy mismatch')
        token=request.cookies.get(COOKIE_NAME)
        if token:
            try:
                context_id,digest=parse_context(token,settings.context_key)
                saved=store.context_snapshot(context_id)
                row=saved.get('context')
                if row:
                    row=dict(row,expires_at=timestamp(row['expires_at']))
                authorize_context(row,digest,timestamp(saved['server_now']))
                return {'ready':True}
            except AccessDenied:
                pass
        context_id,token,digest=new_context(settings.context_key)
        store.create_context(context_id,digest)
        response=JSONResponse({'ready':True})
        response.set_cookie(COOKIE_NAME,token,max_age=CONTEXT_SECONDS,secure=True,httponly=True,samesite='strict',path='/')
        return response

    from .receipt_recovery import add_receipt_recovery_routes
    add_receipt_recovery_routes(app,store,settings,browser_request,limit)

    @app.post('/api/checkout/status')
    def checkout_status(request:Request,body:ReceiptRequest):
        browser_request(request)
        limit(request,'receipt')
        snapshot=store.receipt_snapshot(body.request_id)
        return receipt_view(snapshot,body.request_id,request.headers.get('x-booking-receipt'),settings.receipt_key)

    @app.post('/api/webhooks/razorpay')
    async def razorpay_webhook(request:Request):
        if webhook_account is None:
            raise StorageUnavailable('Payment events are not configured.')
        # No browser Origin/IP quota on signed provider delivery.
        body=await request.body()
        from starlette.concurrency import run_in_threadpool
        try:
            return await run_in_threadpool(accept_webhook,store,webhook_account,body,
                request.headers.get('x-razorpay-signature'),request.headers.get('x-razorpay-event-id'),
                on_saved=wake_publisher.publish if wake_publisher else None)
        except InvalidWebhook:
            return JSONResponse({'code':'invalid_event'},400)
        except EventConflict:
            return JSONResponse({'code':'event_conflict'},409)

    @app.post('/api/webhooks/resend')
    async def resend_webhook(request:Request):
        if email_webhook is None:
            raise StorageUnavailable('Email events are not configured.')
        body=await request.body()
        from starlette.concurrency import run_in_threadpool
        try:
            return await run_in_threadpool(email_webhook.receive,store,body,request.headers,
                on_saved=wake_publisher.publish if wake_publisher else None)
        except InvalidWebhook:
            return JSONResponse({'code':'invalid_event'},400)
        except EventConflict:
            return JSONResponse({'code':'event_conflict'},409)

    from .google_worker import add_google_worker_route
    add_google_worker_route(app,store,studio_services,worker_key)

    if studio_services is not None:
        from .studio import add_studio_routes
        add_studio_routes(app,store,settings,studio_services,limit,browser_request,wake_publisher)
    else:
        @app.get('/studio')
        @app.api_route('/api/studio/{path:path}', methods=['GET','POST'])
        def studio_unavailable(path: str = ''):
            return JSONResponse({'code':'temporarily_unavailable',
                'message':'Private account access is not available at the moment.'},503)

    return app
