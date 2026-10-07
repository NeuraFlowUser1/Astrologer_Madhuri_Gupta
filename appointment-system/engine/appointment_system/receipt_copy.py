"""Owned receipt copies: one immutable request, no direct provider call or contact edit."""
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator,model_validator
from .access import AccessDenied
from .connection import StorageUnavailable
from .receipt_view import receipt_view,email_copy_view

class ReceiptCopy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID
    operation_id:UUID
    expected_revision:int=Field(ge=1,le=2147483647,strict=True)
    email:EmailStr|None=Field(default=None,max_length=254)

    @field_validator('email',mode='before')
    @classmethod
    def absent_email(cls,value):
        return None if isinstance(value,str) and not value.strip() else value

    @model_validator(mode='after')
    def references(self):
        if self.request_id.int==0 or self.operation_id.int==0:raise ValueError('Use the saved booking and a valid operation.')
        return self


def add_receipt_copy_routes(app,store,settings,browser_request,limit,wake,*,sending_ready=False):
    @app.post('/api/checkout/email-details')
    def request_copy(body:ReceiptCopy,request:Request):
        browser_request(request);limit(request,'checkout',booking=True)
        secret=request.headers.get('x-booking-receipt')
        receipt_view(store.receipt_snapshot(body.request_id),body.request_id,secret,settings.receipt_key)
        try:
            result=store.request_receipt_copy(body.request_id,secret,settings.receipt_key,body.operation_id,
                body.expected_revision,str(body.email) if body.email is not None else None,sending_ready=sending_ready)
        except StorageUnavailable:
            return JSONResponse({'code':'request_pending'},503)
        if not isinstance(result,dict):return JSONResponse({'code':'request_pending'},503)
        code=result.get('code')
        if code=='access_unavailable':raise AccessDenied()
        if code=='receipt_copy_accepted':
            try:
                operation=UUID(result['operation_id'])
                copy=email_copy_view(result['email_copy'])
                if (str(body.operation_id)!=str(operation) or result['request_id']!=str(body.request_id)
                    or type(result['booking_revision']) is not int or result['booking_revision']!=body.expected_revision
                    or copy['operation_id']!=str(operation) or copy['booking_revision']!=body.expected_revision
                    or type(result['replayed']) is not bool):raise ValueError('Invalid accepted copy identity.')
                accepted=dict(code=code,request_id=str(body.request_id),operation_id=str(operation),
                    booking_revision=body.expected_revision,email_copy=copy,replayed=result['replayed'])
            except (ValueError,TypeError,KeyError,AttributeError):return JSONResponse({'code':'request_pending'},503)
            if wake is not None:
                try:wake.publish()
                except Exception:pass
            return accepted
        statuses={'invalid_request':422,'revision_changed':409,'request_conflict':409,'email_destination_conflict':409,
            'booking_not_confirmed':409,'copy_pending':409,'copy_limit':429,'copy_cooldown':429,
            'email_destination_unavailable':409,'copy_unavailable':503}
        if code not in statuses:return JSONResponse({'code':'request_pending'},503)
        public={'code':code}
        if 'email_copy' in result:
            try:public['email_copy']=email_copy_view(result['email_copy'])
            except (ValueError,TypeError,KeyError,AttributeError):return JSONResponse({'code':'request_pending'},503)
        retry=result.get('retry_after')
        headers={'Retry-After':str(retry)} if statuses[code]==429 and type(retry) is int and 1<=retry<=86400 else None
        return JSONResponse(public,statuses[code],headers=headers)
