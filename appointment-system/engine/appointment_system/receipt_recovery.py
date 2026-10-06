"""Assisted recovery: staff callback attestation, short code, customer-owned new receipt."""
import hashlib
import hmac
from typing import Literal
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator,model_validator
from .access import AccessDenied
from .connection import StorageUnavailable
from .models import BookingInput
from .security import receipt_digest
from .credentials import ReceiptKeys,historical_keys
from .studio_calendar import CalendarAction


def legacy_material(key,format,key_id):
    if not isinstance(key,ReceiptKeys):raise StorageUnavailable()
    definition=key.recovery_readers.get(format)
    if definition is None or definition['key_id']!=key_id:raise StorageUnavailable()
    return definition,historical_keys(key.legacy_keys)[key_id]


def recovery_code(key,operation,reference,*,key_id=None,format='v1'):
    if format!='v1':
        definition,material=legacy_material(key,format,key_id)
        raw=hmac.new(material,(definition['code_audience']+str(UUID(str(operation)))+':'+str(UUID(str(reference)))).encode(),hashlib.sha256).digest()
        return str(int.from_bytes(raw,'big')%100000000).zfill(8)
    if isinstance(key,ReceiptKeys):
        raw=bytes.fromhex(key.ring.digest('support-code:'+str(UUID(str(reference))),str(UUID(str(operation))).encode(),key_id=key_id))
        return str(int.from_bytes(raw,'big')%100000000).zfill(8)
    raw=hmac.new(key,f'appointment:v1:support-code:v1:{operation}:{reference}'.encode(),hashlib.sha256).digest()
    return str(int.from_bytes(raw,'big')%100000000).zfill(8)


def code_digest(key,reference,code,*,key_id=None,format='v1'):
    if format!='v1':
        definition,material=legacy_material(key,format,key_id)
        return hmac.new(material,(definition['digest_audience']+str(UUID(str(reference)))+':'+code).encode(),hashlib.sha256).hexdigest()
    if isinstance(key,ReceiptKeys):return key.ring.digest('support-digest:'+str(UUID(str(reference))),code.encode(),key_id=key_id)
    return hmac.new(key,f'appointment:v1:support-code-digest:v1:{reference}:{code}'.encode(),hashlib.sha256).hexdigest()


def support_protection(key,store,reference,operation=None,*,new=False):
    """Replay uses the issued code's key; rotation cannot silently change it."""
    if not isinstance(key,ReceiptKeys):raise StorageUnavailable()
    saved=store.recovery_protection(reference,operation)
    if saved is None:
        if new and operation is not None:return {'format':'v1','key_id':key.ring.active}
        raise AccessDenied()
    if not isinstance(saved,dict) or set(saved)!={'format','key_id'} or not isinstance(saved.get('format'),str) or not isinstance(saved.get('key_id'),str):
        raise StorageUnavailable()
    if saved['format']!='v1':
        legacy_material(key,saved['format'],saved['key_id']);return saved
    try:key.ring.key(saved['key_id'])
    except ValueError:raise StorageUnavailable() from None
    return saved


def support_key(key,store,reference,operation=None,*,new=False):
    value=support_protection(key,store,reference,operation,new=new)
    if value['format']!='v1':raise StorageUnavailable()
    return value['key_id']


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
    secret:str=Field(pattern=r'^r1\.[a-z0-9][a-z0-9_-]{0,31}\.[A-Za-z0-9_-]{43}$')


def add_staff_recovery_routes(app,store,client_id,origin,actor,browser_request,limit,key,wake=None):
    @app.post('/api/studio/appointments/support')
    def support(request:Request,body:SupportChange):
        browser_request(request);limit(request,'studio')
        session,owner=actor(request)
        if owner.get('role')!='client':raise AccessDenied()
        key_id=support_key(key,store,body.reference,body.operation_id,new=True)
        code=recovery_code(key,body.operation_id,body.reference,key_id=key_id)
        value=store.studio_support_change(session,client_id,origin,body.operation_id,body.reference,body.expected_revision,
            body.action,body.reason,body.verified_payment_id,str(body.email) if body.email is not None else None,body.phone,
            code_digest(key,body.reference,code,key_id=key_id),key_id)
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
    @app.post('/api/checkout/recover-receipt')
    def redeem(request:Request,body:RedeemRecovery):
        browser_request(request);limit(request,'receipt')
        protection=support_protection(settings.receipt_key,store,body.request_id)
        new_key=settings.receipt_key.metadata(body.secret)['key_id']
        value=store.redeem_receipt_recovery(body.request_id,code_digest(settings.receipt_key,body.request_id,body.code,**protection),
                                          receipt_digest(body.request_id,body.secret,settings.receipt_key),new_key)
        if not isinstance(value,dict):raise StorageUnavailable()
        if value.get('code')=='access_unavailable':raise AccessDenied()
        if value.get('code')!='receipt_restored':raise StorageUnavailable()
        return value
