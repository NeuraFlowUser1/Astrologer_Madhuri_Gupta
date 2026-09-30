"""Private enquiry/problem review. Human notes do not resolve provider facts."""
from typing import Literal
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from .access import AccessDenied
from .connection import StorageUnavailable

ITEM_PATTERN=r'^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'

class InboxList(BaseModel):
    model_config=ConfigDict(extra='forbid')
    view: Literal['enquiries','issues']
    after: str|None=Field(default=None,max_length=64,pattern=ITEM_PATTERN)

class InboxItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_key: str=Field(max_length=64,pattern=ITEM_PATTERN)

class InboxReview(InboxItem):
    operation_id: UUID
    expected_revision: int=Field(ge=0,lt=2147483647,strict=True)
    note: str=Field(min_length=2,max_length=1000)

    @field_validator('note')
    @classmethod
    def valid_note(cls,value):
        if len(value.strip())<2 or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Use a short single-line review note.')
        return value


def add_inbox_routes(app,store,client_id,origin,actor,browser_request,limit,wake=None):
    def authorize(request):
        browser_request(request)
        limit(request,'studio_status' if request.url.path.endswith(('/list','/detail')) else 'studio')
        session,owner=actor(request)
        if owner.get('role') not in ('client','agency'):raise AccessDenied()
        return session,owner['role']

    def result(value):
        if not isinstance(value,dict):raise StorageUnavailable()
        code=value.get('code')
        if code=='access_unavailable':raise AccessDenied()
        if code in ('invalid_request','item_unavailable','request_conflict','revision_changed','retry_unavailable','retry_wait','refund_not_verified'):
            return JSONResponse({'code':code},422 if code=='invalid_request' else 409)
        if code not in ('ok','review_saved','retry_queued','refund_verified'):raise StorageUnavailable()
        return value

    @app.post('/api/studio/inbox/list')
    def listing(request:Request,body:InboxList):
        session,role=authorize(request)
        if body.view=='enquiries' and role!='client':raise AccessDenied()
        return result(store.studio_inbox_list(session,client_id,origin,body.view,body.after))

    @app.post('/api/studio/inbox/detail')
    def detail(request:Request,body:InboxItem):
        session,role=authorize(request)
        if role=='agency' and body.item_key.startswith(('enquiry:','payment:')):raise AccessDenied()
        return result(store.studio_inbox_detail(session,client_id,origin,body.item_key))

    @app.post('/api/studio/inbox/review')
    def review(request:Request,body:InboxReview):
        session,role=authorize(request)
        if role=='agency' and body.item_key.startswith(('enquiry:','payment:')):raise AccessDenied()
        return result(store.studio_inbox_review(session,client_id,origin,body.operation_id,body.item_key,body.expected_revision,body.note))

    @app.post('/api/studio/inbox/retry')
    def retry(request:Request,body:InboxReview):
        session,role=authorize(request)
        if body.item_key.startswith('enquiry:') or (role=='agency' and body.item_key.startswith('payment:')):raise AccessDenied()
        value=result(store.studio_inbox_retry(session,client_id,origin,body.operation_id,body.item_key,body.expected_revision,body.note))
        if isinstance(value,dict) and wake is not None:
            try:wake.publish()
            except Exception:pass
        return value

    @app.post('/api/studio/inbox/refund-verified')
    def refund_verified(request:Request,body:InboxReview):
        session,role=authorize(request)
        if role!='client' or not body.item_key.startswith('payment:'):raise AccessDenied()
        return result(store.studio_inbox_refund_verified(session,client_id,origin,body.operation_id,body.item_key,body.expected_revision,body.note))
