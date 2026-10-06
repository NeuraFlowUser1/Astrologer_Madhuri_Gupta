"""Contained Vercel composition. Identity comes only from validated project data.

Import performs no database/provider calls or migrations. Optional provider
failures affect their own operations, not another component's credentials.
"""
from ipaddress import ip_address
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .configuration import installation,origin,worker_origin
from .connection import StorageUnavailable
from .errors import Rejected
from .serialization import decode
from .storage import Store,UnavailableStore


def vercel_client_address(request):
    values=request.headers.getlist('x-vercel-forwarded-for')
    try:
        if len(values)!=1 or '%' in values[0]:raise ValueError()
        return str(ip_address(values[0]))
    except (ValueError,TypeError):return None


class CanonicalHost:
    def __init__(self,app):self.app=app;self.host=origin().split('://',1)[1].encode()
    async def __call__(self,scope,receive,send):
        if scope['type']=='http':
            hosts=[v for k,v in scope.get('headers',[]) if k.lower()==b'host']
            if hosts!=[self.host]:
                return await JSONResponse({'code':'website_address_required'},421,
                    headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})(scope,receive,send)
        return await self.app(scope,receive,send)


def optional(factory,*arguments):
    try:return factory(*arguments)
    except (KeyError,ValueError,TypeError,Rejected,StorageUnavailable):return None


def purpose_store(environment,purpose):
    facts=installation()
    name='BOOKING_DATABASE_URL' if purpose=='web' else 'BOOKING_'+purpose.upper()+'_DATABASE_URL'
    try:return Store(environment[name],expected_host=facts['database_targets'][purpose]['host'],purpose=purpose)
    except (KeyError,ValueError,TypeError,Rejected,StorageUnavailable):
        if purpose=='web':raise StorageUnavailable() from None
        return UnavailableStore()

def ingress_store(environment,web_store):
    facts=installation()
    if 'journal' not in facts['database_targets']:return web_store
    from .provider_ingress import JournalCipher,JournalStore
    from .secret_configuration import ring
    try:
        cipher=JournalCipher(ring(environment,'BOOKING_JOURNAL_KEYS','provider-journal'))
        return JournalStore(environment['BOOKING_JOURNAL_DATABASE_URL'],
            expected_host=facts['database_targets']['journal']['host'],cipher=cipher)
    except (KeyError,ValueError,TypeError,Rejected,StorageUnavailable):return UnavailableStore()


def unavailable_application():
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.api_route('/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'])
    async def unavailable(path):
        return JSONResponse({'code':'temporarily_unavailable',
            'message':'We cannot complete this request right now. Please try again shortly.'},503,
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
    app.add_middleware(CanonicalHost)
    return app


def create_hosted_application(environment,*,release_digest):
    from .application import create_application
    from .secret_configuration import booking_settings
    from .studio import StudioServices
    from .contact import ContactSecrets
    from .worker_access import WorkerKey
    from .resend_email import ResendSender
    from .email_events import EmailWebhook
    from .payment_configuration import payment_accounts,payment_webhook
    from .razorpay import RazorpayFailure
    from .service_control import settings_from_environment as company_configuration,ControlDatabase,ControlError
    from .control_publication import Publisher,settings_from_environment as publication_configuration
    from .projection import ProjectionReader,key
    from .wake import WakePublisher
    from .recovery_contract import RecoveryRuntime
    try:
        runtime=RecoveryRuntime(release_digest)
        facts=installation()
        if (environment.get('VERCEL')!='1' or environment.get('VERCEL_ENV')!='production'
                or facts['environment']!='production'):
            raise ValueError()
        # No optional provider name or account silently selects another project.
        settings=booking_settings(environment)
        stores={purpose:purpose_store(environment,purpose) for purpose in ('web','staff','worker','company')}
        ingress=ingress_store(environment,stores['web'])
        studio=optional(StudioServices.from_environment,environment)
        contact=optional(ContactSecrets.from_environment,environment)
        from .booking_verification import VerificationSecrets
        verification=optional(VerificationSecrets.from_environment,environment)
        sender=optional(ResendSender.from_environment,environment)
        worker_keys={name:optional(WorkerKey,environment.get('BOOKING_'+name+'_WORKER_KEY'))
                     for name in ('GOOGLE','EMAIL','RECOVERY')}
        usable=[value.value for value in worker_keys.values() if value is not None]
        wake=optional(WakePublisher,worker_origin()+'/wake',environment.get('BOOKING_WAKE_KEY',''))
        if wake is not None:usable.append(wake.key)
        if len(set(usable))!=len(usable):raise ValueError('Independent worker credentials required.')
        protected={material for value in (settings.receipt_key.ring,settings.context_key.ring,settings.risk_key)
                   for _,material in value.keys}
        if any(key(value) in protected for value in usable):raise ValueError('Independent worker credentials required.')
        try:accounts=payment_accounts(environment.get('BOOKING_RAZORPAY_ACCOUNTS',''))
        except (RazorpayFailure,ValueError,TypeError,Rejected):accounts=None
        try:webhook=payment_webhook(environment.get('BOOKING_RAZORPAY_WEBHOOK_KEYS',''),accounts)
        except (RazorpayFailure,ValueError,TypeError,Rejected):webhook=None
        def mail_events():
            from .email_configuration import webhook
            return webhook(environment['BOOKING_EMAIL_WEBHOOK_KEYS'],sender.declared if sender else None)
        email_webhook=optional(mail_events)
        company=company_configuration(environment=environment)
        company_database=ControlDatabase(company) if company is not None else None
        publication=publication_configuration(environment)
        publisher=Publisher(stores['worker'],publication) if publication is not None else None
        try:reader=ProjectionReader(key(environment['BOOKING_CONTROL_READ_KEY']),worker_origin())
        except (KeyError,ControlError):reader=None
        app=create_application(stores['web'],settings,verified_client_address=vercel_client_address,
            staff_store=stores['staff'],worker_store=stores['worker'],company_store=stores['company'],
            studio_services=studio,worker_key=worker_keys['GOOGLE'],email_webhook=email_webhook,
            email_worker_key=worker_keys['EMAIL'],email_sender=sender,recovery_worker_key=worker_keys['RECOVERY'],
            wake_publisher=wake,payment_accounts=accounts,webhook_account=webhook,contact_secrets=contact,
            contact_delivery_ready=contact is not None and sender is not None and worker_keys['EMAIL'] is not None,
            company_settings=company,company_database=company_database,control_publisher=publisher,projection_reader=reader,
            booking_verification_keys=verification,recovery_release=runtime,provider_store=ingress)
        from .configuration_evidence import add_configuration_route
        add_configuration_route(app,worker_keys['RECOVERY'],{
            'staff_connection':not isinstance(stores['staff'],UnavailableStore),
            'worker_connection':not isinstance(stores['worker'],UnavailableStore),
            'company_connection':company is not None,'studio':studio is not None,
            'google_resources':studio is not None and studio.resources is not None,
            'contact_protection':contact is not None,'email_sender':sender is not None,
            'email_webhook':email_webhook is not None and not isinstance(ingress,UnavailableStore),'payment_accounts':accounts is not None,
            'payment_webhook':webhook is not None and not isinstance(ingress,UnavailableStore),'projection_reader':reader is not None,
            'recovery_contract':True},runtime.release_digest)
        app.add_middleware(CanonicalHost)
        return app
    except (KeyError,ValueError,TypeError,Rejected,ControlError,StorageUnavailable):
        return unavailable_application()
