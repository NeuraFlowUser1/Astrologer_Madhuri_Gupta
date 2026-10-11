"""Authorized direct contact correction; no customer code or replacement secret."""
from typing import Literal
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import EmailStr,Field,field_validator,model_validator
from .access import AccessDenied
from .connection import StorageUnavailable
from .models import BookingInput
from .studio_calendar import CalendarAction


class SupportChange(CalendarAction):
    reference:UUID
    expected_revision:int=Field(ge=1,lt=2147483647,strict=True)
    action:Literal['contact_correction']
    verified_payment_id:str=Field(pattern=r'^pay_[A-Za-z0-9]{1,64}$')
    verification_confirmed:Literal[True]
    email:EmailStr|None=Field(default=None,max_length=254)
    phone:str|None=Field(default=None,min_length=7,max_length=32)

    @field_validator('verification_confirmed',mode='before')
    @classmethod
    def explicit_acknowledgement(cls,value):
        if value is not True:raise ValueError('Complete the approved callback verification first.')
        return value

    @field_validator('phone')
    @classmethod
    def mobile(cls,value):
        return BookingInput.international_mobile(value) if value is not None else None

    @model_validator(mode='after')
    def action_fields(self):
        if self.action=='contact_correction' and self.phone is None:raise ValueError('Mobile is required.')
        return self


def add_staff_correction_routes(app,store,client_id,origin,actor,browser_request,limit,wake=None):
    @app.post('/api/studio/appointments/support')
    def support(request:Request,body:SupportChange):
        browser_request(request);limit(request,'studio')
        session,owner=actor(request)
        if owner.get('role')!='client':raise AccessDenied()
        value=store.studio_support_change(session,client_id,origin,body.operation_id,body.reference,body.expected_revision,
            body.action,body.reason,body.verified_payment_id,str(body.email) if body.email is not None else None,body.phone)
        if not isinstance(value,dict):raise StorageUnavailable()
        outcome=value.get('code')
        if outcome=='access_unavailable':raise AccessDenied()
        if outcome in ('booking_unavailable','revision_changed','request_conflict','invalid_change','support_verification_unavailable','support_wait'):
            return JSONResponse({'code':outcome},422 if outcome=='invalid_change' else 409)
        if outcome!='contact_corrected':raise StorageUnavailable()
        if wake is not None and body.action=='contact_correction':
            try:wake.publish()
            except Exception:pass
        return value

