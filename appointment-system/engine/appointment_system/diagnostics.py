"""Optional bounded diagnostics. Business results remain independent."""
import logging
from uuid import UUID
from starlette.concurrency import run_in_threadpool
CODES=frozenset(('service_unavailable','storage_unavailable','time_budget','unexpected_failure','provider_rejected','result_invalid'))
log=logging.getLogger('booking.operations')

def note(request,code):
    if code in CODES:request.scope.setdefault('state',{})['booking_failure_code']=code

def request_reference(request):
    try:return str(UUID(str(request.scope.get('state',{}).get('booking_reference'))))
    except (ValueError,TypeError,AttributeError):return None

async def record_optional(scope,identity,operation,elapsed):
    code=scope.get('state',{}).get('booking_failure_code','service_unavailable')
    code=code if code in CODES else 'service_unavailable'
    path=scope.get('path','')
    if (code=='storage_unavailable' or elapsed>15000 or scope.get('state',{}).get('booking_diagnostic_skip') is True
        or path.startswith(('/api/internal','/api/webhooks','/api/auth','/api/company'))):return 'host_only'
    try:
        store=getattr(getattr(scope.get('app'),'state',None),'operational_store',None)
        if store is None:return 'host_only'
        def save():
            from .request_budget import budget
            with budget(3.5):return store.record_operation_incident(identity,operation,'request',code,min(60000,elapsed)) is True
        return 'saved' if await run_in_threadpool(save) else 'host_only'
    except Exception:
        log.warning('operational_incident_not_saved')
        return 'host_only'
