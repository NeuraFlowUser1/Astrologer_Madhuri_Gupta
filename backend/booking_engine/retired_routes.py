"""Reject obsolete public submission contracts before parsing or side effects."""
from starlette.responses import JSONResponse

RETIRED_PATHS=frozenset(('/api/otp/send','/api/otp/verify','/api/book-appointment','/api/bookings','/api/contact'))


class RetiredSubmissions:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and scope['path'].rstrip('/') in RETIRED_PATHS:
            return await JSONResponse(
                {'code':'endpoint_retired','message':'Please use the current website form.'},
                status_code=410,headers={'Cache-Control':'no-store'},
            )(scope,receive,send)
        return await self.app(scope,receive,send)
