"""Practice-only appointment changes; never initiates a refund."""
from uuid import UUID
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from .studio_calendar import CalendarAction
from .access import AccessDenied
from .connection import StorageUnavailable

class AppointmentDetail(BaseModel):
    model_config=ConfigDict(extra='forbid')
    claim_id:UUID

class BookingLookup(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reference:UUID

class ActionResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID


class CancelAppointment(CalendarAction):
    claim_id:UUID
    expected_revision:int=Field(ge=1,lt=2147483647,strict=True)


class RescheduleAppointment(CancelAppointment):
    starts_at:datetime

    @field_validator('starts_at')
    @classmethod
    def zoned_minute(cls,value):
        if value.tzinfo is None or value.utcoffset() is None or value.second or value.microsecond:
            raise ValueError('Use a whole-minute time with a timezone.')
        return value


def add_appointment_routes(app,store,client_id,origin,actor,browser_request,limit,wake=None,receipt_key=None):
    def authorize(request,scope):
        browser_request(request)
        limit(request,scope)
        session,owner=actor(request)
        if owner.get('role')!='client':raise AccessDenied()
        return session

    def checked(value,success):
        if not isinstance(value,dict):raise StorageUnavailable()
        code=value.get('code')
        if code=='access_unavailable':raise AccessDenied()
        if code in ('booking_unavailable','appointment_unavailable','revision_changed','request_conflict','invalid_change','time_unavailable','time_already_reserved','late_reschedule_used'):
            return JSONResponse({'code':code},422 if code=='invalid_change' else 409)
        if code!=success:raise StorageUnavailable()
        return value

    @app.post('/api/studio/appointments/action-result')
    def action_result(request:Request,body:ActionResult):
        session=authorize(request,'studio_status')
        value=store.studio_action_result(session,client_id,origin,body.operation_id)
        if not isinstance(value,dict):raise StorageUnavailable()
        if value.get('code')=='access_unavailable':raise AccessDenied()
        if value.get('code') not in ('operation_not_found','operation_conflict','cancelled','rescheduled','support_saved','refund_verified','resource_reviewed'):raise StorageUnavailable()
        if value.get('code')=='support_saved' and value.get('active') is True:
            from .receipt_recovery import recovery_code,support_protection
            if not receipt_key:raise StorageUnavailable()
            reference=UUID(value['reference']);protection=support_protection(receipt_key,store,reference,body.operation_id)
            value=dict(value,activation_code=recovery_code(receipt_key,body.operation_id,reference,**protection))
        return value

    @app.post('/api/studio/appointments/detail')
    def detail(request:Request,body:AppointmentDetail):
        session=authorize(request,'studio_status')
        return checked(store.studio_appointment_detail(session,client_id,origin,body.claim_id),'ok')

    @app.post('/api/studio/appointments/cancel')
    def cancel(request:Request,body:CancelAppointment):
        session=authorize(request,'studio')
        value=checked(store.studio_appointment_cancel(session,client_id,origin,body.operation_id,
                      body.claim_id,body.expected_revision,body.reason),'cancelled')
        if isinstance(value,dict) and wake is not None:
            # An already committed cancellation is successful even if wake-up fails.
            try:wake.publish()
            except Exception:pass
        return value

    @app.post('/api/studio/appointments/reschedule')
    def reschedule(request:Request,body:RescheduleAppointment):
        session=authorize(request,'studio')
        value=checked(store.studio_appointment_reschedule(session,client_id,origin,body.operation_id,
                      body.claim_id,body.expected_revision,body.reason,body.starts_at),'rescheduled')
        if isinstance(value,dict) and wake is not None:
            try:wake.publish()
            except Exception:pass
        return value

    @app.post('/api/studio/appointments/lookup')
    def lookup(request:Request,body:BookingLookup):
        session=authorize(request,'studio_status')
        return checked(store.studio_booking_lookup(session,client_id,origin,body.reference),'ok')
