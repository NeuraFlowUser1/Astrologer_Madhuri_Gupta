"""Separate company obligation capability using the same appointment services.

Only accepted appointments and financial obligations can be selected. This
router never adopts an agency/client session, holds time, creates an order or
issues a refund. Each write is authorized again inside its SQL transaction.
"""
import hashlib
import hmac
import html
from uuid import UUID
from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,JSONResponse,Response
from pydantic import Field
from .studio_calendar import EmptyRequest,LocalTime
from psycopg.types.json import Jsonb
from .company_control import ASSETS,PRIVATE_HEADERS,re_full_csrf
from .configuration import label,project_id
from .service_control import COOKIE,ORIGIN,ControlError
from .studio_appointments import AppointmentDetail,BookingLookup,CancelAppointment,RescheduleAppointment
from .studio_calendar import CalendarAction
from .receipt_recovery import SupportChange,recovery_code,code_digest,support_key,support_protection

class VerifiedRefund(CalendarAction):
    case_id:UUID
    expected_revision:int=Field(ge=0,lt=2147483647,strict=True)

def router(settings,store,receipt_key,wake=None,database=None):
    routes=APIRouter()
    def session(request,*,write=False):
        if settings is None:raise ControlError()
        token=request.cookies.get(COOKIE,'')
        if not 40<=len(token)<=100:raise ControlError('company_session_required',401)
        if database is None:raise ControlError()
        from .company_auth import Credentials
        # This committed activity/idle check precedes the separate action
        # transaction, which rechecks authority under the product barrier.
        Credentials(database,settings).session(token)
        csrf=settings.digest('csrf',token)
        if write:
            if (request.headers.get('origin')!=ORIGIN
                    or request.headers.get('content-type','').split(';')[0]!='application/json'
                    or request.headers.get('content-encoding','identity')!='identity'
                    or not re_full_csrf(request.headers.get('x-company-csrf',''))
                    or not hmac.compare_digest(csrf,request.headers['x-company-csrf'])):
                raise ControlError('company_request_rejected',403)
        return settings.digest('session',token),hashlib.sha256(csrf.encode()).hexdigest(),csrf
    def checked(value):
        if not isinstance(value,dict):raise ControlError()
        code=value.get('code')
        if code=='access_unavailable':raise ControlError('company_session_required',401)
        if code not in ('ok','cancelled','rescheduled','support_saved','refund_verified','resource_reviewed'):
            return JSONResponse({'code':code},status_code=409,headers=PRIVATE_HEADERS)
        return value
    def action(request,name,body):
        token,csrf,_=session(request,write=True)
        value=checked(store._call('SELECT appointment_system.control_obligation_action(%s,%s,%s,%s,%s)',
            (token,csrf,settings.google_client_id,name,Jsonb(body))))
        if isinstance(value,dict) and name not in ('lookup','detail') and wake is not None:
            try:wake.publish()
            except Exception:pass
        return JSONResponse(value,headers=PRIVATE_HEADERS) if isinstance(value,dict) else value
    @routes.get('/company/booking-support')
    def page():
        source=(ASSETS/'support.html').read_text().replace('CLIENT_NAME',html.escape(label())).replace('PROJECT_NUMBER',html.escape(project_id()))
        return HTMLResponse(source,headers=PRIVATE_HEADERS)
    @routes.get('/api/company/support.js')
    def script():return Response((ASSETS/'support.js').read_bytes(),media_type='text/javascript',headers=PRIVATE_HEADERS)
    @routes.post('/api/company/support/time-context')
    def time_context(request:Request,body:EmptyRequest):
        token,_,_=session(request,write=True)
        return checked(store.studio_time_context(token,settings.google_client_id,ORIGIN+'/company/booking-support'))

    @routes.post('/api/company/support/resolve-time')
    def resolve_time(request:Request,body:LocalTime):
        token,_,_=session(request,write=True)
        return checked(store.studio_resolve_time(token,settings.google_client_id,ORIGIN+'/company/booking-support',body.local,body.timezone))

    @routes.get('/api/company/support/status')
    def status(request:Request):
        token,_,csrf=session(request)
        result=checked(store._call('SELECT appointment_system.control_obligation_summary(%s)',(token,)))
        if isinstance(result,dict):return JSONResponse(dict(result,csrf_token=csrf),headers=PRIVATE_HEADERS)
        return result
    @routes.get('/api/company/support/actions/{operation}')
    def action_result(operation:UUID,request:Request):
        token,_,_=session(request)
        value=store.studio_action_result(token,settings.google_client_id,ORIGIN+'/company/booking-support',operation)
        if not isinstance(value,dict):raise ControlError()
        if value.get('code')=='access_unavailable':raise ControlError('company_session_required',401)
        if value.get('code') not in ('operation_not_found','operation_conflict','cancelled','rescheduled','support_saved','refund_verified','resource_reviewed'):raise ControlError()
        if value.get('code')=='support_saved' and value.get('active') is True:
            reference=UUID(value['reference']);protection=support_protection(receipt_key,store,reference,operation)
            value=dict(value,activation_code=recovery_code(receipt_key,operation,reference,**protection))
        return JSONResponse(value,headers=PRIVATE_HEADERS)
    @routes.post('/api/company/support/lookup')
    def lookup(request:Request,body:BookingLookup):return action(request,'lookup',body.model_dump(mode='json'))
    @routes.post('/api/company/support/detail')
    def detail(request:Request,body:AppointmentDetail):return action(request,'detail',body.model_dump(mode='json'))
    @routes.post('/api/company/support/cancel')
    def cancel(request:Request,body:CancelAppointment):return action(request,'cancel',body.model_dump(mode='json'))
    @routes.post('/api/company/support/reschedule')
    def reschedule(request:Request,body:RescheduleAppointment):return action(request,'reschedule',body.model_dump(mode='json'))
    @routes.post('/api/company/support/support')
    def support(request:Request,body:SupportChange):
        session(request,write=True)
        key_id=support_key(receipt_key,store,body.reference,body.operation_id,new=True)
        code=recovery_code(receipt_key,body.operation_id,body.reference,key_id=key_id)
        data=body.model_dump(mode='json')|{'code_digest':code_digest(receipt_key,body.reference,code,key_id=key_id),'code_key_id':key_id}
        response=action(request,'support',data)
        if response.status_code==200:
            import json
            value=json.loads(response.body)
            return JSONResponse(dict(value,activation_code=code if value.get('active') is True else None),headers=PRIVATE_HEADERS)
        return response
    @routes.post('/api/company/support/verified-refund')
    def verified_refund(request:Request,body:VerifiedRefund):return action(request,'verified_refund',body.model_dump(mode='json'))
    @routes.post('/api/company/support/resource-reviewed')
    def resource_reviewed(request:Request,body:VerifiedRefund):return action(request,'resource_reviewed',body.model_dump(mode='json'))
    return routes
