"""Google authorization boundary for the two explicitly approved Practice owners.

This module does not expose a callback or authenticate staff. Its caller must
atomically consume a persisted, expiring, browser/session-bound OAuth attempt
BEFORE exchanging its code, and commit the returned encrypted grant only while
that staff session and connection revision are still current. Provider calls
must run outside database transactions. Failed exchange never replaces a grant.
"""
from .configuration import owners,sender,project_id,label,worker_origin,origin
from .request_budget import observe_provider

from .request_budget import BudgetExpired,provider_timeout,chunks,remaining

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from google.auth.exceptions import GoogleAuthError
from google.oauth2.id_token import verify_oauth2_token

AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN = 'https://oauth2.googleapis.com/token'
CERTS = 'https://www.googleapis.com/oauth2/v1/certs'
USERINFO = 'https://openidconnect.googleapis.com/v1/userinfo'
DRIVE_IDENTITY = 'https://www.googleapis.com/drive/v3/about'
EMAIL_SCOPE = 'https://www.googleapis.com/auth/userinfo.email'
FILE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events.owned'
CALENDAR_READ_SCOPE = 'https://www.googleapis.com/auth/calendar.calendars.readonly'
SHEET_SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
RESOURCE_ROLES={'calendar':'client','client_sheet':'client','agency_sheet':'agency'}
RESOURCE_SCOPES={name:frozenset(('openid',EMAIL_SCOPE,CALENDAR_SCOPE if name=='calendar' else FILE_SCOPE))
                 for name in RESOURCE_ROLES}
OWNERS = owners()
MAX_RESPONSE = 65536
CALLBACK = '/api/studio/google/callback'
SIGN_IN_CALLBACK = '/api/studio/sign-in/callback'
REPAIR_CALLBACK = '/api/company/grant-repair/callback'
REPAIR_PURPOSE = 'existing_obligation_grant_repair'


class GoogleFailure(Exception):
    """Only stable, non-secret codes may leave this provider boundary."""


def scopes_for(role):
    if role not in OWNERS:
        raise GoogleFailure('google_role_invalid')
    return frozenset(('openid', EMAIL_SCOPE, FILE_SCOPE)) | (
        frozenset((CALENDAR_SCOPE,)) if role == 'client' else frozenset())

def resource_scopes_valid(resources,scopes):
    if (type(resources) is not tuple or not resources or tuple(sorted(set(resources)))!=resources
        or any(name not in RESOURCE_ROLES for name in resources)):
        return False
    calendar=RESOURCE_SCOPES['calendar'];sheet=RESOURCE_SCOPES['client_sheet']
    combined=calendar|{FILE_SCOPE}
    if resources==('calendar','client_sheet'):return scopes==combined
    if len(resources)!=1:return False
    return scopes in ((calendar,calendar|{CALENDAR_READ_SCOPE},combined) if resources[0]=='calendar'
                      else (sheet,sheet|{SHEET_SCOPE},frozenset((FILE_SCOPE,SHEET_SCOPE)),combined)
                      if resources[0]=='client_sheet' else (sheet,sheet|{SHEET_SCOPE},frozenset((FILE_SCOPE,SHEET_SCOPE))))


def _opaque(value, minimum=1, maximum=8192):
    return (isinstance(value, str) and minimum <= len(value) <= maximum
            and all(33 <= ord(char) <= 126 for char in value))


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GoogleFailure('google_time_invalid')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class OAuthSettings:
    client_id: str
    client_secret: str = field(repr=False)
    origin: str
    callback_path: str=CALLBACK

    @classmethod
    def from_environment(cls, environment):
        """Explicit protected settings only; never discover another client's keys."""
        try:
            return cls(environment['BOOKING_GOOGLE_CLIENT_ID'],
                       environment['BOOKING_GOOGLE_CLIENT_SECRET'],
                       origin())
        except (KeyError, TypeError, ValueError):
            raise GoogleFailure('google_configuration_invalid') from None

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if (not re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', self.client_id)
                or not _opaque(self.client_secret) or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or not _opaque(self.origin) or parsed.netloc != parsed.hostname
                or self.callback_path not in (CALLBACK,'/api/studio/resources/callback','/api/company/resources/callback',REPAIR_CALLBACK)):
            raise GoogleFailure('google_configuration_invalid')

    @property
    def redirect_uri(self):
        return self.origin + self.callback_path


@dataclass(frozen=True)
class Attempt:
    role: str
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)

    def __post_init__(self):
        scopes_for(self.role)
        if (not isinstance(self.state,str) or not re.fullmatch(r'(?:a1\.[a-zA-Z0-9_-]{1,32}\.)?[A-Za-z0-9_-]{43}',self.state)
            or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', v)
               for v in (self.nonce, self.verifier))):
            raise GoogleFailure('google_attempt_invalid')

    @classmethod
    def new(cls, role):
        return cls(role, *(secrets.token_urlsafe(32) for _ in range(3)))


@dataclass(frozen=True)
class Grant:
    role: str
    subject: str
    email: str
    refresh_token: str = field(repr=False)
    scopes: frozenset
    refresh_expires_at: datetime | None = None
    resources: tuple = ()

    def __post_init__(self):
        if (self.email != OWNERS.get(self.role) or not _opaque(self.subject, 1, 255)
                or not _opaque(self.refresh_token)
                or (self.scopes != scopes_for(self.role) if not self.resources else
                    not resource_scopes_valid(self.resources,self.scopes)
                    or any(RESOURCE_ROLES.get(resource)!=self.role for resource in self.resources))):
            raise GoogleFailure('google_grant_invalid')
        if self.refresh_expires_at is not None:
            _time(self.refresh_expires_at)


@dataclass(frozen=True)
class Access:
    token: str = field(repr=False)
    expires_at: datetime
    grant: Grant = field(repr=False)
    client_id: str | None = None


class GrantCipher:
    """One new envelope protocol, with explicitly selected historical readers."""
    def __init__(self,client_id,keys,legacy=None):
        from .keys import KeyRing
        from .configuration import installation
        from .serialization import decode,canonical
        facts=installation()
        if (not isinstance(keys,KeyRing) or keys.purpose!='google-grant'
            or keys.installation_id!=facts['installation_id'] or keys.environment!=facts['environment']
            or type(client_id) is not str or not re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com',client_id)):
            raise GoogleFailure('google_encryption_configuration_invalid')
        self._ring,self._client_id=keys,client_id
        self._legacy={}
        if legacy is not None:
            from .serialization import object_fields,integer
            value=decode(legacy) if isinstance(legacy,(str,bytes)) else decode(canonical(legacy))
            object_fields(value,{'version','installation_id','environment','purpose','readers'})
            integer(value['version'],1,1)
            if (value['installation_id']!=facts['installation_id'] or value['environment']!=facts['environment']
                or value['purpose']!='google-grant' or type(value['readers']) is not dict or len(value['readers'])>8):
                raise GoogleFailure('google_encryption_configuration_invalid')
            for name,reader in value['readers'].items():
                object_fields(reader,{'algorithm','keys','grant_purpose','attempt_purpose'})
                if (name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name)
                    or reader['algorithm']!='fernet-json' or type(reader['keys']) is not list
                    or not 1<=len(reader['keys'])<=8 or len(set(reader['keys']))!=len(reader['keys'])
                    or any(type(reader[item]) is not str or not _opaque(reader[item],1,200)
                           for item in ('grant_purpose','attempt_purpose'))):
                    raise GoogleFailure('google_encryption_configuration_invalid')
                try:
                    from .keys import material
                    for item in reader['keys']:material(item,32)
                    crypt=MultiFernet([Fernet(item) for item in reader['keys']])
                except (ValueError,TypeError):raise GoogleFailure('google_encryption_configuration_invalid') from None
                self._legacy[name]=(crypt,reader['grant_purpose'],reader['attempt_purpose'])

    def _record(self,kind,*parts):
        from .serialization import canonical
        return 'google-'+kind+':'+hashlib.sha256(canonical([self._client_id,*parts])).hexdigest()

    def _seal(self,record,data):
        from .serialization import canonical
        return 'g1.'+canonical(self._ring.seal(record,canonical(data))).decode()

    def _open(self,record,ciphertext,format,kind):
        from .serialization import decode
        from .errors import Rejected
        try:
            if not _opaque(ciphertext,1,32768):raise ValueError()
            if format=='v1':
                if not ciphertext.startswith('g1.'):raise ValueError()
                data=decode(self._ring.open(record,decode(ciphertext[3:])))
                expected='appointment:v1:google-'+kind+':v1'
            else:
                selected=self._legacy.get(format)
                if selected is None:raise ValueError()
                data=decode(selected[0].decrypt(ciphertext.encode()))
                expected=selected[1 if kind=='grant' else 2]
            if type(data) is not dict or data.get('purpose')!=expected:raise ValueError()
            return data
        except (Rejected,InvalidToken,ValueError,TypeError,UnicodeError):
            raise GoogleFailure('google_saved_'+kind+'_invalid') from None

    def seal_attempt(self,attempt,purpose):
        if not isinstance(attempt,Attempt) or purpose not in ('signin','connect',REPAIR_PURPOSE):
            raise GoogleFailure('google_attempt_invalid')
        data=dict(purpose='appointment:v1:google-attempt:v1',flow=purpose,client_id=self._client_id,
                  role=attempt.role,state=attempt.state,nonce=attempt.nonce,verifier=attempt.verifier)
        return self._seal(self._record('attempt',purpose,attempt.role,attempt.state),data)

    def open_attempt(self,ciphertext,*,state,role,purpose,format='v1'):
        if purpose not in ('signin','connect',REPAIR_PURPOSE) or role not in OWNERS:
            raise GoogleFailure('google_attempt_invalid')
        data=self._open(self._record('attempt',purpose,role,state),ciphertext,format,'attempt')
        if (set(data)!={'purpose','flow','client_id','role','state','nonce','verifier'}
            or data['flow']!=purpose or data['client_id']!=self._client_id or data['role']!=role or data['state']!=state):
            raise GoogleFailure('google_attempt_invalid')
        return Attempt(role,state,data['nonce'],data['verifier'])

    def seal(self,grant):
        if not isinstance(grant,Grant):raise GoogleFailure('google_grant_invalid')
        if grant.resources:raise GoogleFailure('google_resource_cipher_required')
        data=dict(purpose='appointment:v1:google-grant:v1',client_id=self._client_id,
                  role=grant.role,subject=grant.subject,email=grant.email,refresh_token=grant.refresh_token,
                  scopes=sorted(grant.scopes),refresh_expires_at=grant.refresh_expires_at.isoformat()
                  if grant.refresh_expires_at else None)
        return self._seal(self._record('grant',grant.role,grant.subject),data)

    def open(self,ciphertext,*,role,subject,now,format='v1'):
        now=_time(now)
        data=self._open(self._record('grant',role,subject),ciphertext,format,'grant')
        try:
            if (set(data)!={'purpose','client_id','role','subject','email','refresh_token','scopes','refresh_expires_at'}
                or data['client_id']!=self._client_id or data['role']!=role or data['subject']!=subject
                or type(data['scopes']) is not list or any(type(value) is not str for value in data['scopes'])
                or len(set(data['scopes']))!=len(data['scopes'])):raise ValueError()
            expiry=datetime.fromisoformat(data['refresh_expires_at']) if data['refresh_expires_at'] else None
            grant=Grant(role,subject,data['email'],data['refresh_token'],frozenset(data['scopes']),expiry)
            if expiry is not None and _time(expiry)<=now:raise GoogleFailure('google_reconnect_required')
            return grant
        except (KeyError,TypeError,ValueError):raise GoogleFailure('google_saved_grant_invalid') from None


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate response field')
        result[key] = value
    return result


class GoogleOAuth:
    def __init__(self, settings, *, transport=None,resource=None):
        if not isinstance(settings, OAuthSettings):
            raise GoogleFailure('google_configuration_invalid')
        if resource is not None and resource not in RESOURCE_ROLES:raise GoogleFailure('google_resource_invalid')
        self.settings, self._transport,self.resource = settings, transport,resource

    def expected_scopes(self,role):
        if self.resource is None:return scopes_for(role)
        if RESOURCE_ROLES[self.resource]!=role:raise GoogleFailure('google_account_mismatch')
        return RESOURCE_SCOPES[self.resource]

    def authorization_url(self, attempt, *, signin=False, repair=False):
        if signin and repair: raise GoogleFailure('google_attempt_invalid')
        challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b'=').decode()
        return AUTH + '?' + urlencode(dict(
            client_id=self.settings.client_id,
            redirect_uri=self.settings.origin + (REPAIR_CALLBACK if repair else SIGN_IN_CALLBACK) if signin or repair else self.settings.redirect_uri,
            response_type='code', scope='openid email' if signin else ' '.join(sorted(self.expected_scopes(attempt.role))),
            access_type='online' if signin else 'offline',
            prompt='select_account' if signin else 'consent', include_granted_scopes='false',
            login_hint=OWNERS[attempt.role], state=attempt.state, nonce=attempt.nonce,
            code_challenge=challenge, code_challenge_method='S256'))

    @observe_provider('google')
    def _request(self, url, *, data=None, access_token=None,params=None):
        if url not in (TOKEN, CERTS, USERINFO,DRIVE_IDENTITY):
            raise GoogleFailure('google_endpoint_invalid')
        if (url==DRIVE_IDENTITY and (data is not None or params!={'fields':'user(emailAddress)'})) or (url!=DRIVE_IDENTITY and params is not None):
            raise GoogleFailure('google_endpoint_invalid')
        headers = {'Accept': 'application/json'}
        if access_token:
            headers['Authorization'] = 'Bearer ' + access_token
        try:
            with httpx.Client(timeout=provider_timeout(8), follow_redirects=False, trust_env=False,
                              transport=self._transport) as client:
                with client.stream('POST' if data is not None else 'GET', url,
                                   data=data, headers=headers,params=params) as response:
                    if response.status_code != 200:
                        if url==TOKEN and response.status_code==400 and response.headers.get('content-type','').split(';')[0]=='application/json':
                            raw=bytearray()
                            for chunk in chunks(response):
                                raw.extend(chunk)
                                if len(raw)>4096:break
                            if len(raw)<=4096:
                                try:
                                    detail=json.loads(raw,object_pairs_hook=_json_object)
                                    if isinstance(detail,dict) and detail.get('error')=='invalid_grant':
                                        raise GoogleFailure('google_reconnect_required')
                                except (ValueError,UnicodeError):pass
                        # No provider body/URL/token in logs or error text. A lost
                        # code exchange requires a NEW authorization, never retry.
                        raise GoogleFailure('google_request_failed')
                    body = bytearray()
                    for chunk in chunks(response):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE:
                            raise GoogleFailure('google_response_invalid')
                    if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                        raise GoogleFailure('google_response_invalid')
                    result = json.loads(body, object_pairs_hook=_json_object,
                                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    if not isinstance(result, dict):
                        raise GoogleFailure('google_response_invalid')
                    return result
        except (BudgetExpired,httpx.HTTPError, ValueError, UnicodeError):
            raise GoogleFailure('google_request_failed') from None

    def _certificates(self, url, method='GET', **kwargs):
        # google-auth gets its signing certificates exclusively through the same
        # bounded transport. Reject a token-supplied or changed certificate URL.
        if url != CERTS or method != 'GET':
            raise GoogleFailure('google_certificate_source_invalid')
        data = self._request(CERTS)
        if not data or any(not isinstance(v, str) or 'BEGIN CERTIFICATE' not in v for v in data.values()):
            raise GoogleFailure('google_certificates_invalid')
        return SimpleNamespace(status=200, data=json.dumps(data).encode())

    def _identity(self, value, role, *, subject=None):
        if (not isinstance(value, dict) or value.get('email_verified') is not True
                or not isinstance(value.get('email'), str)
                or value['email'].lower() != OWNERS[role]
                or not _opaque(value.get('sub'), 1, 255)
                or (subject is not None and value['sub'] != subject)):
            raise GoogleFailure('google_account_mismatch')
        return value['sub']

    def _scopes(self, value, role,*,expected=None):
        if not isinstance(value, str):
            raise GoogleFailure('google_permissions_missing')
        scopes = frozenset(EMAIL_SCOPE if s == 'email' else s for s in value.split())
        if scopes != (self.expected_scopes(role) if expected is None else expected):
            raise GoogleFailure('google_permissions_mismatch')
        return scopes

    def _access(self, tokens, grant, now):
        seconds = tokens.get('expires_in')
        if (not isinstance(tokens.get('token_type'), str)
                or tokens['token_type'].lower() != 'bearer'
                or not _opaque(tokens.get('access_token'))
                or type(seconds) is not int or not 0 < seconds <= 86400):
            raise GoogleFailure('google_token_invalid')
        return Access(tokens['access_token'], _time(now) + timedelta(seconds=seconds), grant,self.settings.client_id)

    def _exchange_identity(self, attempt, code, *, signin=False, previous_subject=None, repair=False):
        if signin and repair: raise GoogleFailure('google_attempt_invalid')
        if not _opaque(code, 1, 4096):
            raise GoogleFailure('google_code_invalid')
        tokens = self._request(TOKEN, data=dict(client_id=self.settings.client_id,
            client_secret=self.settings.client_secret, code=code,
            redirect_uri=self.settings.origin + (REPAIR_CALLBACK if repair else SIGN_IN_CALLBACK) if signin or repair else self.settings.redirect_uri,
            grant_type='authorization_code',
            code_verifier=attempt.verifier))
        try:
            encoded = tokens.get('id_token')
            if not _opaque(encoded, 1, 16384):
                raise ValueError()
            identity = verify_oauth2_token(encoded, self._certificates, self.settings.client_id)
            if (identity.get('aud') != self.settings.client_id
                    or identity.get('azp', self.settings.client_id) != self.settings.client_id
                    or not _opaque(identity.get('nonce'), 43, 43)
                    or not hmac.compare_digest(identity['nonce'], attempt.nonce)):
                raise ValueError()
        except (ValueError, TypeError, KeyError, GoogleAuthError):
            raise GoogleFailure('google_identity_invalid') from None
        subject = self._identity(identity, attempt.role, subject=previous_subject)
        return tokens, subject

    def sign_in(self, attempt, code):
        """Identity only: never persist access/refresh tokens from staff sign-in."""
        _, subject = self._exchange_identity(attempt, code, signin=True)
        return subject

    def exchange(self, attempt, code, *, now, previous_subject=None, repair=False):
        """Called only after durable one-time attempt consumption by staff flow."""
        now = _time(now)
        tokens, subject = self._exchange_identity(attempt, code, previous_subject=previous_subject, repair=repair)
        scopes = self._scopes(tokens.get('scope'), attempt.role)
        if not _opaque(tokens.get('refresh_token')):
            # Never attach newly granted scopes to an old refresh token whose
            # actual permissions are unknown. Preserve the old DB grant instead.
            raise GoogleFailure('google_offline_permission_missing')
        refresh_expiry = None
        if 'refresh_token_expires_in' in tokens:
            seconds = tokens['refresh_token_expires_in']
            if type(seconds) is not int or not 0 < seconds <= 315360000:
                raise GoogleFailure('google_token_invalid')
            refresh_expiry = now + timedelta(seconds=seconds)
        grant = Grant(attempt.role, subject, OWNERS[attempt.role], tokens['refresh_token'], scopes, refresh_expiry,
                      (self.resource,) if self.resource is not None else ())
        return self._access(tokens, grant, now)

    def refresh(self, grant, *, now):
        now = _time(now)
        if not isinstance(grant, Grant):
            raise GoogleFailure('google_grant_invalid')
        if (self.resource is None and grant.resources or self.resource is not None and self.resource not in grant.resources):
            raise GoogleFailure('google_resource_mismatch')
        if grant.refresh_expires_at is not None and grant.refresh_expires_at <= now:
            raise GoogleFailure('google_reconnect_required')
        tokens = self._request(TOKEN, data=dict(client_id=self.settings.client_id,
            client_secret=self.settings.client_secret, refresh_token=grant.refresh_token,
            grant_type='refresh_token'))
        if 'scope' in tokens:
            self._scopes(tokens['scope'], grant.role,expected=grant.scopes)
        # Any returned replacement must be committed before this access is used.
        replacement = tokens.get('refresh_token', grant.refresh_token)
        expiry = grant.refresh_expires_at
        if 'refresh_token_expires_in' in tokens:
            seconds = tokens['refresh_token_expires_in']
            if type(seconds) is not int or not 0 < seconds <= 315360000:
                raise GoogleFailure('google_token_invalid')
            expiry = now + timedelta(seconds=seconds)
        refreshed = Grant(grant.role, grant.subject, grant.email, replacement, grant.scopes, expiry,grant.resources)
        access = self._access(tokens, refreshed, now)
        if grant.resources and FILE_SCOPE in grant.scopes and EMAIL_SCOPE not in grant.scopes:
            # Retained desktop Sheets grants did not request identity scopes.
            # Verify their existing owner through Drive; do not widen permission.
            identity=self._request(DRIVE_IDENTITY,access_token=access.token,params={'fields':'user(emailAddress)'})
            user=identity.get('user')
            if not isinstance(user,dict) or user.get('emailAddress','').lower()!=grant.email:
                raise GoogleFailure('google_account_mismatch')
        else:
            identity = self._request(USERINFO, access_token=access.token)
            self._identity(identity, grant.role, subject=grant.subject)
        return access
