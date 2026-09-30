"""Assisted recovery: staff callback attestation, short code, customer-owned new receipt."""
import hashlib
import hmac
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import Request
from fastapi.responses import FileResponse,JSONResponse
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator,model_validator
from .access import AccessDenied
from .connection import StorageUnavailable
from .models import BookingInput
from .security import receipt_digest
from .studio_calendar import CalendarAction


def recovery_code(key,operation,reference):
    raw=hmac.new(key,f'sarsa:004:support-code:v1:{operation}:{reference}'.encode(),hashlib.sha256).digest()
    return str(int.from_bytes(raw,'big')%100000000).zfill(8)


def code_digest(key,reference,code):
    return hmac.new(key,f'sarsa:004:support-code-digest:v1:{reference}:{code}'.encode(),hashlib.sha256).hexdigest()


class SupportChange(CalendarAction):
    reference:UUID
    expected_revision:int=Field(ge=1,lt=2147483647,strict=True)
    action:Literal['receipt_recovery','contact_correction']
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
        if self.action=='contact_correction' and (self.email is None or self.phone is None):raise ValueError('Email and mobile are required.')
        if self.action=='receipt_recovery' and (self.email is not None or self.phone is not None):raise ValueError('Receipt recovery cannot change contacts.')
        return self


class RedeemRecovery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    code:str=Field(pattern=r'^[0-9]{8}$')
    secret:str=Field(pattern=r'^[A-Za-z0-9_-]{43}$')


def add_staff_recovery_routes(app,store,client_id,origin,actor,browser_request,limit,key,wake=None):
    @app.post('/api/studio/appointments/support')
    def support(request:Request,body:SupportChange):
        browser_request(request);limit(request,'studio')
        session,owner=actor(request)
        if owner.get('role')!='client':raise AccessDenied()
        code=recovery_code(key,body.operation_id,body.reference)
        value=store.studio_support_change(session,client_id,origin,body.operation_id,body.reference,body.expected_revision,
            body.action,body.reason,body.verified_payment_id,str(body.email) if body.email is not None else None,body.phone,
            code_digest(key,body.reference,code))
        if not isinstance(value,dict):raise StorageUnavailable()
        outcome=value.get('code')
        if outcome=='access_unavailable':raise AccessDenied()
        if outcome in ('booking_unavailable','revision_changed','request_conflict','invalid_change','support_verification_unavailable','support_wait'):
            return JSONResponse({'code':outcome},422 if outcome=='invalid_change' else 409)
        if outcome!='support_saved' or type(value.get('active')) is not bool:raise StorageUnavailable()
        if wake is not None and body.action=='contact_correction':
            try:wake.publish()
            except Exception:pass
        return dict(value,activation_code=code if value['active'] else None)


def add_receipt_recovery_routes(app,store,settings,browser_request,limit):
    assets=Path(__file__).with_name('studio_assets')
    @app.get('/booking-help',include_in_schema=False)
    @app.get('/booking-help/',include_in_schema=False)
    def help_page():return FileResponse(assets/'recovery.html',media_type='text/html')
    @app.get('/api/booking-help/interface.js',include_in_schema=False)
    def help_script():return FileResponse(assets/'recovery.js',media_type='text/javascript')
    @app.get('/api/booking-help/interface.css',include_in_schema=False)
    def help_style():return FileResponse(assets/'interface.css',media_type='text/css')
    @app.post('/api/checkout/recover-receipt')
    def redeem(request:Request,body:RedeemRecovery):
        browser_request(request);limit(request,'receipt')
        value=store.redeem_receipt_recovery(body.request_id,code_digest(settings.receipt_key,body.request_id,body.code),
                                          receipt_digest(body.request_id,body.secret,settings.receipt_key))
        if not isinstance(value,dict):raise StorageUnavailable()
        if value.get('code')=='access_unavailable':raise AccessDenied()
        if value.get('code')!='receipt_restored':raise StorageUnavailable()
        return value
