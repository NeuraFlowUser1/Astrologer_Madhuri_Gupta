"""Private recovery planning and payment lanes; no caller-selected customer/job."""
from fastapi import Request
from fastapi.responses import JSONResponse
from .google_worker import WakeRequest
from .recovery import run_payment_recovery_once, run_payment_event_once

APPLICATION = '004-sarsa-jyotish-sansthan'
LANES = frozenset(('email','email_events','google','payment','payment_events','contact_email','contact_google','maintenance'))


def add_configuration_route(app, key, evidence):
    """Private operator composition checks; never readiness or provider proof.

    Only fixed boolean evidence is accepted, with no environment values,
    messages, customer records, connectivity probes or database writes.
    """
    checks = ('google_client_id_format', 'google_client_secret_format',
              'google_token_keys_format', 'studio_signing_key_format', 'studio_signing_key_independent')
    components = ('studio', 'google_worker', 'email_sender', 'email_worker', 'email_webhook',
                  'recovery_worker', 'wake_publisher', 'contact_protection', 'contact_delivery',
                  'payment_accounts', 'payment_webhook')
    if (set(evidence) != {'checks', 'configured'} or set(evidence['checks']) != set(checks)
            or set(evidence['configured']) != set(components)
            or any(type(v) is not bool for group in evidence.values() for v in group.values())):
        raise ValueError('Configuration evidence invalid.')
    response = {group: dict(values) for group, values in evidence.items()}

    @app.post('/api/internal/recovery/configuration', include_in_schema=False)
    def configuration(request: Request, body: WakeRequest):
        if key is None:
            return JSONResponse({'code': 'worker_unavailable'}, 503)
        if not key.accepts(request.headers):
            return JSONResponse({'code': 'unauthorized'}, 401)
        return dict(application=APPLICATION, version=1, provider_acceptance='not_checked', **response)


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

    @app.post('/api/internal/recovery/maintenance',include_in_schema=False)
    def maintenance(request:Request,body:WakeRequest):
        rejection=denied(request)
        if rejection is not None:return rejection
        value=store.cleanup_temporary_records()
        if (not isinstance(value,dict) or set(value)!={'processed','removed'}
                or type(value['processed']) is not int or value['processed'] not in (0,1)
                or not isinstance(value['removed'],dict)
                or set(value['removed'])!={'attempts','sessions','limits'}
                or any(type(n) is not int or not 0<=n<=500 for n in value['removed'].values())
                or value['processed']!=int(sum(value['removed'].values())>0)):
            raise ValueError('Maintenance result unavailable.')
        return dict(application=APPLICATION,**value)
