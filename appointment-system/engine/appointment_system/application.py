"""Final booking HTTP boundary; deployment routing is connected at cutover.

Contact uses separate durable contracts. Retired public submission paths are blocked. No unpaid-booking aliases,
mock modes, public admin routes or external fallback URLs exist in this app.
"""

from .request_budget import BudgetMiddleware,BudgetExpired,reference

from dataclasses import dataclass,field
from datetime import date,datetime,time,timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict

from .retired_routes import RetiredSubmissions
from .access import (AccessDenied,COOKIE_NAME,CONTEXT_SECONDS,authorize_context,new_context,parse_context,context_identifier)
from .availability import IntakeClosed,available_times
from .connection import StorageUnavailable
from .policy import InvalidSelection,timezone
from .rate_limit import RateLimited,consume_limit
from .receipt_view import receipt_view,timestamp
from .webhook import EventConflict,InvalidWebhook,MAX_WEBHOOK_BYTES,accept_webhook
from .credentials import ReceiptKeys,ContextKeys
from .keys import KeyRing,independent


@dataclass(frozen=True)
class Settings:
    origin: str
    receipt_key: ReceiptKeys = field(repr=False)
    context_key: ContextKeys = field(repr=False)
    risk_key: KeyRing = field(repr=False)

    def __post_init__(self):
        parsed=urlsplit(self.origin)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or self.origin!=f'https://{parsed.netloc}'
                or not isinstance(self.receipt_key,ReceiptKeys)
                or not isinstance(self.context_key,ContextKeys)
                or not isinstance(self.risk_key,KeyRing) or self.risk_key.purpose!='risk'):
            raise ValueError('Secure booking application settings are required.')
        independent((self.receipt_key.ring,self.context_key.ring,self.risk_key))


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
            webhook=scope['path'] in ('/api/webhooks/razorpay','/api/webhooks/resend')
            maximum=MAX_WEBHOOK_BYTES if webhook or scope['path']=='/api/company/settings' else 16384
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
            if not webhook:
                from .serialization import decode
                from .errors import Rejected
                try:decode(bytes(body),maximum=maximum)
                except Rejected:
                    return await JSONResponse({'code':'invalid_request','message':'Please check the information and try again.'},422)(scope,receive,protected_send)
            sent=False
            async def bounded_receive():
                nonlocal sent
                if not sent:
                    sent=True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()
            return await self.app(scope,bounded_receive,protected_send)
        return await self.app(scope,receive,protected_send)


def create_application(store,settings,*,verified_client_address,webhook_account=None,studio_services=None,worker_key=None,email_webhook=None,email_worker_key=None,email_sender=None,recovery_worker_key=None,payment_accounts=None,wake_publisher=None,contact_secrets=None,contact_delivery_ready=False,company_settings=None,company_database=None,control_publisher=None,staff_store=None,worker_store=None,company_store=None,projection_reader=None,booking_verification_keys=None,recovery_release=None,provider_store=None):
    """Host integration must supply a tested, trusted client-address resolver.

    This is intentionally not inferred from user-supplied proxy headers. A
    missing resolver is a configuration error, never an unlimited-access mode.
    """
    if not isinstance(settings,Settings) or not callable(verified_client_address):
        raise ValueError('Booking application configuration is incomplete.')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.operational_store=store
    from .staff_browser import add_routes as add_staff_browser_routes
    add_staff_browser_routes(app,settings.receipt_key.ring)
    provider_store=store if provider_store is None else provider_store
    from .storage import UnavailableStore
    staff_store=staff_store if staff_store is not None else UnavailableStore()
    worker_store=worker_store if worker_store is not None else UnavailableStore()
    company_store=company_store if company_store is not None else UnavailableStore()
    app.add_middleware(RequestBoundary)
    app.add_middleware(RetiredSubmissions)
    # The last declared middleware is outermost: include slow body reception.
    app.add_middleware(BudgetMiddleware)
    from .visibility import BookingVisibility
    app.add_middleware(BookingVisibility,reader=projection_reader)

    @app.get('/api/health',include_in_schema=False)
    def process_health():
        # Process liveness, independent of provider/account/database readiness.
        return JSONResponse({'status':'online'},headers={'Cache-Control':'no-store'})
    from .company_control import router as company_router,PRIVATE_HEADERS
    from .service_control import ControlError,settings_from_environment
    company_host=getattr(store,'_expected_host','')
    company_config=company_settings or settings_from_environment(company_host)
    from .service_control import ControlDatabase
    from .control_publication import Publisher,settings_from_environment as publication_settings
    company_database=company_database or (ControlDatabase(company_config) if company_config else None)
    control_publisher=control_publisher or (Publisher(company_database,publication_settings()) if company_database else None)
    app.include_router(company_router(company_config,
        database=company_database,publisher=control_publisher,
        worker_key=recovery_worker_key,address=verified_client_address))
    from .company_support import router as company_support_router
    app.include_router(company_support_router(company_config,company_store,settings.receipt_key,wake_publisher,database=company_database))

    @app.exception_handler(BudgetExpired)
    async def budget_exhausted(request,error):
        from .diagnostics import note
        note(request,'time_budget')
        return JSONResponse({'code':'request_pending','message':'This request could not finish in time. Please check its status before trying again.','reference':reference()},503,headers={'Cache-Control':'no-store'})

    @app.exception_handler(ControlError)
    async def controlled_error(request,error):
        message=('Online booking is unavailable. Please use the contact page.' if error.code=='booking_disabled'
                 else 'Please refresh this page or sign in again to continue.')
        return JSONResponse({'code':error.code,'message':message},status_code=error.status,headers=PRIVATE_HEADERS)

    from .errors import Rejected
    @app.exception_handler(Rejected)
    async def rejected_request(request,error):
        # These errors contain only the defined public wording and field names.
        return JSONResponse(error.public(),status_code=error.status,headers=PRIVATE_HEADERS)

    def browser_request(request):
        if request.headers.get('origin')!=settings.origin:
            raise AccessDenied()

    def limit(request,scope,*,booking=False):
        consume_limit(store,scope,verified_client_address(request),settings.risk_key,booking=booking)

    from .resource_consent import router as resource_consent_router
    app.include_router(resource_consent_router(studio_services,company_config,company_database,staff_store,limit))

    from .contact_routes import add_contact_routes
    add_contact_routes(app,store,contact_secrets,browser_request,limit,wake_publisher,delivery_ready=contact_delivery_ready)

    from .checkout_verification import add_checkout_verification_route
    add_checkout_verification_route(app,store,settings,payment_accounts,browser_request,limit,wake_publisher)
    from .checkout import add_checkout_routes
    add_checkout_routes(app,store,settings,payment_accounts,browser_request,limit,wake_publisher,verification_keys=booking_verification_keys)
    from .booking_verification import add_booking_verification_routes
    from .booking_verification_delivery import run_booking_code_once
    deliver=(lambda job:run_booking_code_once(worker_store,email_sender,booking_verification_keys,job=job)) if email_sender is not None and booking_verification_keys is not None else None
    add_booking_verification_routes(app,store,settings,booking_verification_keys,browser_request,limit,wake_publisher,deliver=deliver)

    @app.exception_handler(Exception)
    async def unexpected(request,error):
        from .diagnostics import request_reference
        identity=request_reference(request)
        return JSONResponse({'code':'temporarily_unavailable','message':'We cannot complete this request right now. Please try again shortly.'},503,
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Booking-Reference':identity or ''})

    @app.exception_handler(AccessDenied)
    async def denied(request,error):
        return JSONResponse({'code':'access_unavailable','message':'We cannot safely open this booking here. Please use your original booking page or contact us.'},403)

    @app.exception_handler(StorageUnavailable)
    async def unavailable(request,error):
        from .diagnostics import note
        note(request,'storage_unavailable')
        return JSONResponse({'code':'temporarily_unavailable','message':'We cannot complete this request right now. Please try again shortly.'},503)

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

    # The nine-lane contract is the only asynchronous consumer entry point.
    # Old empty-body routes cannot bypass release/generation/turn admission.
    from .recovery_contract import add_routes as add_common_worker_routes
    add_common_worker_routes(app,worker_store,recovery_release,recovery_key=recovery_worker_key,
        email_key=email_worker_key,google_key=worker_key,sender=email_sender,code_keys=booking_verification_keys,
        contact_keys=contact_secrets,google=studio_services,accounts=payment_accounts,publisher=control_publisher)

    @app.get('/api/booking-policy')
    def booking_policy(request:Request):
        limit(request,'availability',booking=True)
        policy=store.public_policy()
        policy["receipt_access"]={"version":1,"key_id":settings.receipt_key.ring.active}
        return policy

    @app.get('/api/availability')
    def availability(request:Request,service_id:str,day:date,questions:int=1):
        limit(request,'availability',booking=True)
        return available_times(store,service_id,day,questions)

    @app.post('/api/checkout-context')
    def checkout_context(request:Request):
        browser_request(request)
        limit(request,'context')
        epoch=store.require_booking_admission()
        # Context issue follows schedule browsing, independently of payments. Existing
        # receipts retain independent recovery access through the status route.
        policy=store.public_policy()
        if not policy or policy.get('schedule_browsing_open') is not True:
            raise IntakeClosed()
        token=request.cookies.get(COOKIE_NAME)
        if token:
            try:
                context_id=context_identifier(token,settings.context_key)
                saved=store.context_snapshot(context_id)
                row=saved.get('context')
                if row:
                    row=dict(row,expires_at=timestamp(row['expires_at']))
                context_id,digest=parse_context(token,settings.context_key,row)
                authorize_context(row,digest,timestamp(saved['server_now']))
                if row.get("activation_epoch")==str(epoch):
                    return {'ready':True}
            except AccessDenied:
                pass
        context_id,token,digest=new_context(settings.context_key)
        metadata=settings.context_key.metadata(token)
        store.create_context(context_id,digest,metadata=metadata)
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
            return await run_in_threadpool(accept_webhook,provider_store,webhook_account,body,
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
            return await run_in_threadpool(email_webhook.receive,provider_store,body,request.headers,
                on_saved=wake_publisher.publish if wake_publisher else None)
        except InvalidWebhook:
            return JSONResponse({'code':'invalid_event'},400)
        except EventConflict:
            return JSONResponse({'code':'event_conflict'},409)

    if studio_services is not None:
        from .studio import add_studio_routes
        add_studio_routes(app,staff_store,settings,studio_services,limit,browser_request,wake_publisher)
    else:
        @app.get('/studio')
        @app.get('/enquiries-studio')
        @app.api_route('/api/studio/{path:path}', methods=['GET','POST'])
        @app.api_route('/api/enquiry-studio/{path:path}', methods=['GET','POST'])
        def studio_unavailable(request:Request,path: str = ''):
            request.scope.setdefault('state',{})['booking_diagnostic_skip']=True
            return JSONResponse({'code':'temporarily_unavailable',
                'message':'Private account access is not available at the moment.'},503)

    return app
