"""Read-only customer booking lookup; identity pairs never become credentials."""
import base64
from datetime import timezone
import json
import re
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .access import AccessDenied
from .connection import StorageUnavailable
from .models import BookingInput
from .rate_limit import RateLimited, risk_digest
from .receipt_view import receipt_facts, timestamp

PATH = '/api/booking/details'
UUID_TEXT = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z')
CURSOR_TEXT = re.compile(r'[A-Za-z0-9_-]{1,512}\Z')
WHITESPACE = '\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
SUMMARY_FIELDS = ('request_id','booking_revision','service_name','starts_at','ends_at','timezone','appointment_state')


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    full_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=1, max_length=32)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)
    request_id: UUID | None = None

    @field_validator('full_name')
    @classmethod
    def name_controls(cls, value):
        if any((ord(c)<32 or ord(c)==127) and c not in WHITESPACE for c in value):
            raise ValueError('Unsupported name characters.')
        if len(value.strip(WHITESPACE))<2:
            raise ValueError('Enter the full name saved with the booking.')
        return value

    @field_validator('phone')
    @classmethod
    def mobile(cls, value):
        result = BookingInput.international_mobile(value.strip())
        if not result:
            raise ValueError('Enter the phone number saved with the booking.')
        return result

    @field_validator('request_id', mode='before')
    @classmethod
    def reference(cls, value):
        if type(value) is not str or not UUID_TEXT.fullmatch(value) or not UUID(value).int:
            raise ValueError('Invalid booking selection.')
        return UUID(value)

    @field_validator('cursor')
    @classmethod
    def cursor_characters(cls, value):
        if value is None or not CURSOR_TEXT.fullmatch(value):
            raise ValueError('Refresh the booking list.')
        return value

    @model_validator(mode='after')
    def selection(self):
        if self.cursor is not None and self.request_id is not None:
            raise ValueError('Use one booking selection.')
        return self


def decode_cursor(value):
    """Opaque ordering only; the database always re-applies the identity match."""
    if value is None:
        return (None, None, None, None)
    try:
        from .serialization import decode
        raw = base64.b64decode(value+'='*((-len(value))%4),altchars=b'-_',validate=True)
        body = decode(raw, maximum=512)
        if (type(body) is not dict or set(body)!={'v','as_of','bucket','start','id'}
                or type(body['v']) is not int or body['v']!=1
                or type(body['bucket']) is not int or body['bucket'] not in (0,1)
                or type(body['id']) is not str or not UUID_TEXT.fullmatch(body['id']) or not UUID(body['id']).int):
            raise ValueError()
        def utc(value):
            if type(value) is not str or len(value)>40 or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)',value):
                raise ValueError()
            result = timestamp(value)
            if result.utcoffset().total_seconds()!=0:
                raise ValueError()
            return result
        return (utc(body['as_of']),body['bucket'],utc(body['start']),UUID(body['id']))
    except Exception:
        # Cursor bytes and identities must never enter error text.
        raise ValueError('Refresh the booking list.') from None


def encode_cursor(as_of, row):
    def utc(value):
        return timestamp(value).astimezone(timezone.utc).isoformat(timespec='microseconds')
    body={'v':1,'as_of':utc(as_of),'bucket':row['bucket'],'start':utc(row['starts_at']),'id':row['request_id']}
    return base64.urlsafe_b64encode(json.dumps(body,separators=(',',':'),allow_nan=False).encode()).decode().rstrip('=')


def preparse_admission(store, settings, verified_address):
    def admit(request):
        if request.headers.getlist('origin') != [settings.origin]:
            raise AccessDenied()
        epoch=getattr(request.state,'booking_activation_epoch',None)
        if epoch is None:
            raise StorageUnavailable()
        result=store.consume_booking_lookup_limits(risk_digest(verified_address(request),settings.risk_key),epoch)
        if type(result) is not dict or type(result.get('allowed')) is not bool:
            raise StorageUnavailable()
        if not result['allowed']:
            raise RateLimited(result.get('retry_after',60))
    return admit


def add_routes(app, store):
    @app.post(PATH)
    def details(request: Request, body: LookupRequest):
        try:
            cursor=decode_cursor(body.cursor)
        except ValueError:
            return JSONResponse({'code':'invalid_cursor','message':'Search again to refresh the list.','fields':['cursor']},422)
        epoch=getattr(request.state,'booking_activation_epoch',None)
        if epoch is None:
            raise StorageUnavailable()
        value=store.booking_details(body.full_name,body.phone,epoch,body.request_id,*cursor)
        if type(value) is not dict:
            raise StorageUnavailable()
        if value.get('code') in ('invalid_cursor','invalid_name'):
            field='cursor' if value['code']=='invalid_cursor' else 'full_name'
            return JSONResponse({'code':value['code'],'message':'Search again to refresh the list.' if field=='cursor' else 'Please enter the full name saved when booking.','fields':[field]},422)
        if body.request_id is not None:
            if value.get('booking') is None:
                return JSONResponse({'code':'booking_not_found','message':'We could not find a booking with these details.'},404)
            facts=receipt_facts(value,body.request_id)
            return {'version':1,'kind':'detail','receipt':facts,'capabilities':{
                'refresh':True,'download_pdf':facts['appointment_state']=='confirmed' and bool(facts.get('booking_revision')) and facts.get('meeting_mode') in ('google_meet','internal')}}
        rows=value.get('items')
        if type(rows) is not list or len(rows)>21:
            raise StorageUnavailable()
        items=[]
        for row in rows[:20]:
            if (type(row) is not dict or not set(SUMMARY_FIELDS).issubset(row)
                    or type(row.get('bucket')) is not int or row['bucket'] not in (0,1)):
                raise StorageUnavailable()
            items.append({key:row[key] for key in SUMMARY_FIELDS})
        return {'version':1,'kind':'list','server_now':value['server_now'],'items':items,
                'next_cursor':encode_cursor(value['as_of'],rows[19]) if len(rows)>20 else None}
