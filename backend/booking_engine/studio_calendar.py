"""Client-only calendar controls. No cancellation, refund or agency override."""
from datetime import date, datetime, timedelta
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .access import AccessDenied
from .connection import StorageUnavailable


class CalendarDay(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: date
    after: UUID | None = None


class CalendarAction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    operation_id: UUID
    reason: str = Field(min_length=2, max_length=500)

    @field_validator('reason')
    @classmethod
    def clean_reason(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Use a single-line reason.')
        return value


class CloseTime(CalendarAction):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def valid_interval(self):
        if any(t.tzinfo is None or t.utcoffset() is None or t.second or t.microsecond
               for t in (self.starts_at, self.ends_at)):
            raise ValueError('Use whole-minute times with a timezone.')
        if not timedelta(0) < self.ends_at-self.starts_at <= timedelta(days=31):
            raise ValueError('Choose a period of at most31 days.')
        return self


class ReopenTime(CalendarAction):
    claim_id: UUID


def add_calendar_routes(app, store, client_id, origin, actor, browser_request, limit):
    def authorize(request, scope):
        browser_request(request)
        limit(request, scope)
        session, owner = actor(request)
        if owner.get('role') != 'client':
            raise AccessDenied()
        return session

    def result(value, allowed):
        if not isinstance(value, dict) or value.get('code') not in allowed | {
                'access_unavailable', 'invalid_calendar_date', 'invalid_closure', 'request_conflict',
                'time_already_reserved', 'closure_not_found'}:
            raise StorageUnavailable()
        code = value['code']
        if code == 'access_unavailable':
            raise AccessDenied()
        if code not in allowed:
            return JSONResponse({'code': code}, 409 if code in ('request_conflict', 'time_already_reserved', 'closure_not_found') else 422)
        return value

    @app.post('/api/studio/calendar/list')
    def list_calendar(request: Request, body: CalendarDay):
        session = authorize(request, 'studio_status')
        return result(store.studio_calendar_list(session, client_id, origin, body.day, body.after), {'ok'})

    @app.post('/api/studio/calendar/close')
    def close(request: Request, body: CloseTime):
        session = authorize(request, 'studio')
        value = store.studio_calendar_close(session, client_id, origin, body.operation_id,
                                            body.reason, body.starts_at, body.ends_at)
        return result(value, {'closed', 'existing'})

    @app.post('/api/studio/calendar/reopen')
    def reopen(request: Request, body: ReopenTime):
        session = authorize(request, 'studio')
        return result(store.studio_calendar_reopen(session, client_id, origin, body.operation_id,
                      body.claim_id, body.reason), {'reopened', 'already_open', 'existing'})
