"""Private composition evidence, without secret values or provider calls."""
from fastapi import Request
from fastapi.responses import JSONResponse
from .configuration import project_id
from .worker_access import WakeRequest

COMPONENTS=frozenset(('staff_connection','worker_connection','company_connection','studio',
    'google_resources','contact_protection','email_sender','email_webhook','payment_accounts',
    'payment_webhook','projection_reader','recovery_contract'))

def add_configuration_route(app,key,evidence,release_digest):
    if (type(evidence) is not dict or set(evidence)!=COMPONENTS
        or any(type(value) is not bool for value in evidence.values())):
        raise ValueError('Configuration evidence invalid.')
    fixed=dict(evidence)
    @app.post('/api/internal/recovery/configuration',include_in_schema=False)
    def configuration(request:Request,body:WakeRequest):
        if key is None:return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):return JSONResponse({'code':'unauthorized'},401)
        return {'application':project_id(),'version':1,'release_digest':release_digest,
                'provider_acceptance':'not_checked','configured':dict(fixed)}
