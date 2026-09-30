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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

from .access import AccessDenied
from .connection import StorageUnavailable
from .google_oauth import Attempt, CALLBACK, SIGN_IN_CALLBACK, GoogleFailure, OWNERS, GoogleOAuth, OAuthSettings, GrantCipher
from .google_records import prepare_owner_workbook
from .google_workspace import WorkspaceFailure, resource_id
from .receipt_view import timestamp
from .security import new_secret

SESSION_COOKIE = '__Host-sarsa-studio'
SIGNIN_COOKIE = '__Host-sarsa-signin'
CONNECT_COOKIE = '__Host-sarsa-google'


@dataclass(frozen=True)
class StudioServices:
    google: object = field(repr=False)
    cipher: object = field(repr=False)
    signing_key: bytes = field(repr=False)

    @classmethod
    def from_environment(cls, environment):
        try:
            config = OAuthSettings.from_environment(environment)
            keys = json.loads(environment['SARSA_GOOGLE_TOKEN_KEYS'])
            encoded = environment['SARSA_STUDIO_SIGNING_KEY']
            if not isinstance(encoded, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=', encoded):
                raise ValueError()
            key = base64.b64decode(encoded, altchars=b'-_', validate=True)
            return cls(GoogleOAuth(config), GrantCipher(config.client_id, keys), key)
        except (KeyError, ValueError, TypeError, binascii.Error, GoogleFailure):
            raise ValueError('Private access configuration is missing.') from None

    def __post_init__(self):
        if not isinstance(self.signing_key, bytes) or len(self.signing_key) < 32:
            raise ValueError('Private access configuration is missing.')

    def digest(self, purpose, value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', value):
            raise AccessDenied()
        return hmac.new(self.signing_key, ('sarsa:004:studio:v1:'+purpose+':'+value).encode(), hashlib.sha256).hexdigest()


class SigninRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['client', 'agency']


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


def add_studio_routes(app, store, settings, services, limit, browser_request, wake=None):
    google, cipher = services.google, services.cipher
    if google.settings.origin != settings.origin:
        raise ValueError('Private access origin must match the booking origin.')
    client_id, origin = google.settings.client_id, google.settings.origin
    assets = Path(__file__).with_name('studio_assets')

    def actor(request):
        digest = services.digest('session', request.cookies.get(SESSION_COOKIE))
        result = store.studio_session(digest, client_id, origin)
        if not result:
            raise AccessDenied()
        return digest, result

    from .studio_calendar import add_calendar_routes
    add_calendar_routes(app, store, client_id, origin, actor, browser_request, limit)

    from .receipt_recovery import add_staff_recovery_routes
    add_staff_recovery_routes(app,store,client_id,origin,actor,browser_request,limit,settings.receipt_key,wake)

    from .studio_appointments import add_appointment_routes
    add_appointment_routes(app,store,client_id,origin,actor,browser_request,limit,wake)

    from .studio_inbox import add_inbox_routes
    add_inbox_routes(app, store, client_id, origin, actor, browser_request, limit,wake)

    def start(request, purpose, role, session=None):
        browser_request(request)
        limit(request, 'studio')
        attempt, browser = Attempt.new(role), new_secret()
        state_digest = services.digest('state', attempt.state)
        committed = store.start_google_attempt(state_digest, services.digest('browser', browser),
            purpose, role, cipher.seal_attempt(attempt, purpose), session, client_id, origin)
        if committed is not True:
            raise AccessDenied()
        response = JSONResponse({'authorization_url': google.authorization_url(attempt, signin=purpose=='signin')})
        response.set_cookie(SIGNIN_COOKIE if purpose=='signin' else CONNECT_COOKIE, browser,
                            max_age=600, secure=True, httponly=True, samesite='lax', path='/')
        return response

    def callback(request, purpose):
        cookie = SIGNIN_COOKIE if purpose=='signin' else CONNECT_COOKIE
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
            # Consumption COMMITTED before provider exchange. No retrying a used
            # authorization code after an ambiguous response or database commit.
            response.delete_cookie(cookie, secure=True, httponly=True, samesite='lax', path='/')
            if query.get('error') or not query.get('code'):
                return response
            attempt = cipher.open_attempt(saved['encrypted_attempt'], state=state,
                                          role=saved['role'], purpose=purpose)
            if purpose == 'signin':
                subject = google.sign_in(attempt, query['code'])
                secret = new_secret()
                committed = store.finish_google_signin(digest, subject, services.digest('session', secret))
                if committed is True:
                    response.headers['location'] = '/studio?connection=signed-in'
                    response.set_cookie(SESSION_COOKIE, secret, max_age=3600, secure=True,
                                        httponly=True, samesite='strict', path='/')
            else:
                access = google.exchange(attempt, query['code'], now=timestamp(saved['server_now']),
                                         previous_subject=saved['subject'])
                grant = access.grant
                committed = store.finish_google_connection(digest, grant.subject, cipher.seal(grant),
                                                           grant.refresh_expires_at)
                if committed is True:
                    response.headers['location'] = '/studio?connection=saved'
        except (AccessDenied, GoogleFailure):
            pass
        except StorageUnavailable:
            # A lost commit response is unknown, not proof the grant was not
            # saved. Remove callback codes from the browser URL and check status.
            response.headers['location'] = '/studio?connection=check'
        return response

    @app.get('/studio', include_in_schema=False)
    def studio_page():
        return FileResponse(assets/'index.html', headers={
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            'X-Robots-Tag': 'noindex, nofollow', 'Cache-Control': 'no-store'})

    @app.get('/api/studio/interface.js', include_in_schema=False)
    def studio_script():
        return FileResponse(assets/'interface.js', media_type='text/javascript')

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
        return start(request, 'signin', body.role)

    @app.get(SIGN_IN_CALLBACK)
    def sign_in_callback(request: Request):
        return callback(request, 'signin')

    @app.post('/api/studio/google/start')
    def google_start(request: Request, body: EmptyRequest):
        browser_request(request)
        session, owner = actor(request)
        return start(request, 'connect', owner['role'], session)

    @app.get(CALLBACK)
    def google_callback(request: Request):
        return callback(request, 'connect')

    @app.get('/api/studio/status')
    def status(request: Request):
        limit(request, 'studio_status')
        try:
            session, owner = actor(request)
        except AccessDenied:
            return JSONResponse({'signed_in': False}, status_code=401)
        saved = store.studio_connection_status(session, client_id, origin)
        if saved is None:
            raise AccessDenied()
        return {'signed_in': True, 'role': owner['role'], 'email': OWNERS[owner['role']],
                'authorization_saved': saved['authorization_saved'], 'reconnect_required': saved['reconnect_required'],
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
        digest, _ = actor(request)
        store.studio_logout(digest, client_id, origin)
        response = JSONResponse({'signed_out': True})
        response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite='strict', path='/')
        return response
