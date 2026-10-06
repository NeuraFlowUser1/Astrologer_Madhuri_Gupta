"""Private identity and Google connection routes; no customer booking authority.

The public route shells reveal no private records. Identity is granted only by
Google's signed response for one of the two approved owners. Each authenticated
owner may save only their own Google connection. Staff sign-in grants no public
booking receipt, refund or arbitrary record access.
"""

import hashlib
import hmac
import base64
import binascii
import json
from html import escape
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

from .access import AccessDenied
from .errors import Rejected
from .connection import StorageUnavailable
from .google_oauth import Attempt, CALLBACK, SIGN_IN_CALLBACK, GoogleFailure, OWNERS, GoogleOAuth, OAuthSettings, GrantCipher
from .google_records import prepare_owner_workbook
from .google_workspace import WorkspaceFailure, resource_id
from .security import new_secret
from .configuration import label

SESSION_COOKIE = '__Host-appointment-studio'
SIGNIN_COOKIE = '__Host-appointment-signin'


@dataclass(frozen=True)
class StudioServices:
    google: object = field(repr=False)
    cipher: object = field(repr=False)
    signing_key: object = field(repr=False)
    resources: object = field(default=None,repr=False)

    @classmethod
    def from_environment(cls, environment):
        try:
            config = OAuthSettings.from_environment(environment)
            from .secret_configuration import ring
            from .keys import independent
            grant=ring(environment,'BOOKING_GOOGLE_TOKEN_KEYS','google-grant')
            staff=ring(environment,'BOOKING_STAFF_SESSION_KEYS','staff-session')
            independent((grant,staff))
            from .google_resources import Resources
            try:
                resources=Resources.from_environment(environment)
                independent((grant,staff,resources.cipher.ring))
            except (KeyError,ValueError,TypeError,GoogleFailure,Rejected):
                resources=None
            return cls(GoogleOAuth(config), GrantCipher(config.client_id, grant,
                environment.get('BOOKING_LEGACY_GOOGLE_GRANTS')), staff,resources)
        except (KeyError, ValueError, TypeError, binascii.Error, GoogleFailure):
            raise ValueError('Private access configuration is missing.') from None

    def __post_init__(self):
        from .keys import KeyRing
        from .configuration import installation
        facts=installation()
        if (not isinstance(self.signing_key,KeyRing) or self.signing_key.purpose!='staff-session'
            or self.signing_key.installation_id!=facts['installation_id']
            or self.signing_key.environment!=facts['environment']):
            raise ValueError('Private access configuration is missing.')

    def issue(self,purpose):
        prefix={'session':'s1','browser':'b1','state':'a1'}.get(purpose)
        if prefix is None:raise AccessDenied()
        return prefix+'.'+self.signing_key.active+'.'+new_secret()

    def attempt(self,role):
        return Attempt(role,self.issue('state'),new_secret(),new_secret())

    def digest(self, purpose, value):
        expected={'session':'s1','csrf':'s1','browser':'b1','state':'a1'}.get(purpose)
        if expected is None or not isinstance(value,str):raise AccessDenied()
        parts=value.split('.')
        if (len(parts)!=3 or parts[0]!=expected or not re.fullmatch(r'[A-Za-z0-9_-]{43}',parts[2])):
            raise AccessDenied()
        try:return self.signing_key.digest('staff:'+purpose,parts[2].encode(),key_id=parts[1])
        except ValueError:raise AccessDenied() from None


class SigninRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['client']


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


def add_studio_routes(app, store, settings, services, limit, browser_request, wake=None):
    google, cipher = services.google, services.cipher
    if google.settings.origin != settings.origin:
        raise ValueError('Private access origin must match the booking origin.')
    client_id, origin = google.settings.client_id, google.settings.origin
    assets = Path(__file__).with_name('studio_assets')

    def actor(request, *, allow_off=False):
        digest = services.digest('session', request.cookies.get(SESSION_COOKIE))
        result = store.studio_session(digest, client_id, origin)
        if not result:
            raise AccessDenied()
        expected_role = 'agency' if request.url.path.startswith('/api/company/records/') else 'client'
        if result.get('role') != expected_role:
            raise AccessDenied()
        if result['role']=='client' and not allow_off:store.require_booking_admission()
        return digest, result

    from .studio_calendar import add_calendar_routes
    add_calendar_routes(app, store, client_id, origin, actor, browser_request, limit)

    from .receipt_recovery import add_staff_recovery_routes
    add_staff_recovery_routes(app,store,client_id,origin,actor,browser_request,limit,settings.receipt_key,wake)

    from .studio_appointments import add_appointment_routes
    add_appointment_routes(app,store,client_id,origin,actor,browser_request,limit,wake,settings.receipt_key)

    from .studio_inbox import add_inbox_routes
    add_inbox_routes(app, store, client_id, origin, actor, browser_request, limit,wake)

    def start(request, purpose, role, session=None,portal='booking'):
        if purpose!='signin' or role!='client':raise AccessDenied()
        browser_request(request)
        limit(request, 'studio')
        attempt, browser = services.attempt(role), services.issue('browser')
        state_digest = services.digest('state', attempt.state)
        committed = store.start_google_attempt(state_digest, services.digest('browser', browser),
            purpose, role, cipher.seal_attempt(attempt, purpose), session, client_id, origin,portal)
        if committed is not True:
            raise AccessDenied()
        response = JSONResponse({'authorization_url': google.authorization_url(attempt, signin=purpose=='signin')})
        response.set_cookie(SIGNIN_COOKIE, browser,
                            max_age=600, secure=True, httponly=True, samesite='lax', path='/')
        return response

    def callback(request, purpose):
        if purpose!='signin':raise AccessDenied()
        cookie = SIGNIN_COOKIE
        response = RedirectResponse('/studio?connection=failed', status_code=303)
        try:
            query = request.query_params
            if (len(request.scope.get('query_string', b'')) > 8192
                    or any(len(query.getlist(key)) > 1 for key in ('state','code','error'))
                    or ('code' in query and 'error' in query)):
                return response
            state = query.get('state')
            digest = services.digest('state', state)
            browser = services.digest('browser', request.cookies.get(cookie))
            saved = store.consume_google_attempt(digest, browser, purpose, client_id, origin)
            if not saved:
                return response
            destination = '/enquiries-studio' if saved.get('portal')=='enquiry' else '/studio'
            response.headers['location'] = destination+'?connection=failed'
            # Consumption COMMITTED before provider exchange. No retrying a used
            # authorization code after an ambiguous response or database commit.
            response.delete_cookie(cookie, secure=True, httponly=True, samesite='lax', path='/')
            if query.get('error') or not query.get('code'):
                return response
            attempt = cipher.open_attempt(saved['encrypted_attempt'], state=state,
                                          role=saved['role'], purpose=purpose)
            if purpose == 'signin':
                subject = google.sign_in(attempt, query['code'])
                secret = services.issue('session')
                committed = store.finish_google_signin(digest, subject, services.digest('session', secret))
                if committed is True:
                    response.headers['location'] = destination+'?connection=signed-in'
                    response.set_cookie(SESSION_COOKIE, secret, max_age=3600, secure=True,
                                        httponly=True, samesite='strict', path='/')
        except (AccessDenied, GoogleFailure):
            pass
        except StorageUnavailable:
            # A lost commit response is unknown, not proof the grant was not
            # saved. Remove callback codes from the browser URL and check status.
            response.headers['location'] = locals().get('destination','/studio')+'?connection=check'
        return response

    @app.get('/studio', include_in_schema=False)
    @app.get('/studio/calendar', include_in_schema=False)
    def studio_page():
        store.require_booking_admission()
        return HTMLResponse((assets/'index.html').read_text().replace('{{PRACTICE_NAME}}',escape(label())), headers={
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            'X-Robots-Tag': 'noindex, nofollow', 'Cache-Control': 'no-store'})

    @app.get('/api/studio/interface.js', include_in_schema=False)
    def studio_script():
        return FileResponse(assets/'interface.js', media_type='text/javascript')

    @app.get('/api/studio/booking-guard.mjs',include_in_schema=False)
    def studio_guard():return FileResponse(assets/'booking-guard.mjs',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/api/studio/product-state.mjs',include_in_schema=False)
    def studio_product_state():
        return FileResponse(Path(__file__).parents[2]/'browser/product-state.mjs',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/api/studio/calendar.js', include_in_schema=False)
    def calendar_script():
        return FileResponse(assets/'calendar.js', media_type='text/javascript')

    @app.get('/api/studio/appointments.js', include_in_schema=False)
    def appointment_script():
        return FileResponse(assets/'appointments.js',media_type='text/javascript')

    @app.get('/api/studio/inbox.js', include_in_schema=False)
    def inbox_script():
        return FileResponse(assets/'inbox.js', media_type='text/javascript')

    @app.get('/api/studio/interface.css', include_in_schema=False)
    def studio_style():
        return FileResponse(assets/'interface.css', media_type='text/css')

    @app.post('/api/studio/sign-in/start')
    def sign_in_start(request: Request, body: SigninRequest):
        store.require_booking_admission()
        return start(request, 'signin', body.role)

    @app.post('/api/enquiry-studio/sign-in/start')
    def enquiry_sign_in_start(request:Request,body:SigninRequest):
        return start(request,'signin',body.role,portal='enquiry')

    @app.get('/enquiries-studio',include_in_schema=False)
    def enquiry_page():
        return FileResponse(assets/'enquiries.html',headers={
            'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            'X-Robots-Tag':'noindex, nofollow','Cache-Control':'no-store'})

    @app.get('/api/enquiry-studio/interface.js',include_in_schema=False)
    def enquiry_script():return FileResponse(assets/'enquiries.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/api/enquiry-studio/interface.css',include_in_schema=False)
    def enquiry_style():return FileResponse(assets/'enquiries.css',media_type='text/css',headers={'Cache-Control':'no-store'})

    @app.get('/api/enquiry-studio/status')
    def enquiry_status(request:Request):
        limit(request,'studio_status')
        try:session,owner=actor(request,allow_off=True)
        except AccessDenied:return JSONResponse({'signed_in':False},status_code=401)
        return {'signed_in':True,'email':OWNERS['client']}

    @app.post('/api/enquiry-studio/logout')
    def enquiry_logout(request:Request,body:EmptyRequest):
        browser_request(request);limit(request,'studio')
        digest,_=actor(request,allow_off=True);store.studio_logout(digest,client_id,origin)
        response=JSONResponse({'signed_out':True})
        response.delete_cookie(SESSION_COOKIE,secure=True,httponly=True,samesite='strict',path='/')
        return response

    @app.get(SIGN_IN_CALLBACK)
    def sign_in_callback(request: Request):
        return callback(request, 'signin')

    @app.post('/api/studio/google/start')
    def google_start(request: Request, body: EmptyRequest):
        from .service_control import ControlError
        raise ControlError('use_resource_connection',410)

    @app.get(CALLBACK)
    def google_callback(request: Request):
        from .service_control import ControlError
        raise ControlError('use_resource_connection',410)

    @app.get('/api/studio/status')
    def status(request: Request):
        limit(request, 'studio_status')
        try:
            session, owner = actor(request)
        except AccessDenied:
            return JSONResponse({'signed_in': False}, status_code=401)
        if services.resources is not None:
            resources=store._call('SELECT appointment_system.resource_connection_status(%s,%s,%s)',('staff',session,client_id))
            sheet=next((item for item in resources if item['resource']=='client_sheet'),{})
            saved={'authorization_saved':sheet.get('connected') is True,'reconnect_required':sheet.get('reconnect_required') is True,
                   'workbook_id':sheet.get('spreadsheet_id')}
        else:
            resources=[];saved={'authorization_saved':False,'reconnect_required':False,'workbook_id':None}
        if saved is None:
            raise AccessDenied()
        return {'signed_in': True, 'role': owner['role'], 'email': OWNERS[owner['role']],
                'resources':resources,'authorization_saved': saved['authorization_saved'], 'reconnect_required': saved['reconnect_required'],
                'workbook_url': 'https://docs.google.com/spreadsheets/d/'+resource_id(saved['workbook_id']) if saved.get('workbook_id') else None}

    @app.post('/api/studio/workbook/prepare')
    def prepare_workbook(request: Request, body: EmptyRequest):
        browser_request(request)
        limit(request, 'studio')
        _, owner = actor(request)
        try:
            _, saved = prepare_owner_workbook(store, services, owner['role'])
        except (GoogleFailure, WorkspaceFailure):
            return JSONResponse({'code':'workbook_not_ready',
                'message':'We could not finish preparing your spreadsheet. Please check your Google connection and try again shortly.'},503)
        return {'workbook_url':'https://docs.google.com/spreadsheets/d/'+resource_id(saved['spreadsheet_id'])}

    @app.post('/api/studio/logout')
    def logout(request: Request, body: EmptyRequest):
        browser_request(request)
        digest, _ = actor(request, allow_off=True)
        store.studio_logout(digest, client_id, origin)
        response = JSONResponse({'signed_out': True})
        response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite='strict', path='/')
        return response
