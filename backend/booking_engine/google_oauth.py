"""Google authorization boundary for the two explicitly approved Sarsa owners.

This module does not expose a callback or authenticate staff. Its caller must
atomically consume a persisted, expiring, browser/session-bound OAuth attempt
BEFORE exchanging its code, and commit the returned encrypted grant only while
that staff session and connection revision are still current. Provider calls
must run outside database transactions. Failed exchange never replaces a grant.
"""

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
EMAIL_SCOPE = 'https://www.googleapis.com/auth/userinfo.email'
FILE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events.owned'
OWNERS = {'client': 'sarsajyotish@gmail.com', 'agency': 'neuraflowindia@gmail.com'}
MAX_RESPONSE = 65536
CALLBACK = '/api/studio/google/callback'
SIGN_IN_CALLBACK = '/api/studio/sign-in/callback'


class GoogleFailure(Exception):
    """Only stable, non-secret codes may leave this provider boundary."""


def scopes_for(role):
    if role not in OWNERS:
        raise GoogleFailure('google_role_invalid')
    return frozenset(('openid', EMAIL_SCOPE, FILE_SCOPE)) | (
        frozenset((CALENDAR_SCOPE,)) if role == 'client' else frozenset())


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

    @classmethod
    def from_environment(cls, environment):
        """Explicit protected settings only; never discover another client's keys."""
        try:
            return cls(environment['SARSA_GOOGLE_CLIENT_ID'],
                       environment['SARSA_GOOGLE_CLIENT_SECRET'],
                       environment['SARSA_PUBLIC_ORIGIN'])
        except (KeyError, TypeError, ValueError):
            raise GoogleFailure('google_configuration_invalid') from None

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if (not re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', self.client_id)
                or not _opaque(self.client_secret) or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or not _opaque(self.origin) or parsed.netloc != parsed.hostname):
            raise GoogleFailure('google_configuration_invalid')

    @property
    def redirect_uri(self):
        return self.origin + CALLBACK


@dataclass(frozen=True)
class Attempt:
    role: str
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)

    def __post_init__(self):
        scopes_for(self.role)
        if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', v)
               for v in (self.state, self.nonce, self.verifier)):
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

    def __post_init__(self):
        if (self.email != OWNERS.get(self.role) or not _opaque(self.subject, 1, 255)
                or not _opaque(self.refresh_token) or self.scopes != scopes_for(self.role)):
            raise GoogleFailure('google_grant_invalid')
        if self.refresh_expires_at is not None:
            _time(self.refresh_expires_at)


@dataclass(frozen=True)
class Access:
    token: str = field(repr=False)
    expires_at: datetime
    grant: Grant = field(repr=False)


class GrantCipher:
    """Authenticated encryption bound to project, OAuth client, role and subject.

    Keys come from protected host settings, never from this module or database.
    The first key writes new records; remaining keys permit deliberate rotation.
    Database caller must separately compare-and-swap the connection revision to
    prevent replaying an older but otherwise valid grant for the same identity.
    """

    def __init__(self, client_id, keys):
        if not isinstance(keys, (tuple, list)) or not 1 <= len(keys) <= 3:
            raise GoogleFailure('google_encryption_configuration_invalid')
        try:
            self._cipher = MultiFernet([Fernet(key) for key in keys])
        except (ValueError, TypeError):
            raise GoogleFailure('google_encryption_configuration_invalid') from None
        self._client_id = client_id

    def seal_attempt(self, attempt, purpose):
        if purpose not in ('signin', 'connect'):
            raise GoogleFailure('google_attempt_invalid')
        return self._cipher.encrypt(json.dumps(dict(
            purpose='sarsa:004:google-attempt:v1', flow=purpose, client_id=self._client_id,
            role=attempt.role, state=attempt.state, nonce=attempt.nonce,
            verifier=attempt.verifier), separators=(',', ':')).encode()).decode()

    def open_attempt(self, ciphertext, *, state, role, purpose):
        try:
            if not _opaque(ciphertext, 1, 32768):
                raise ValueError()
            data = json.loads(self._cipher.decrypt(ciphertext.encode()))
            if (data['purpose'] != 'sarsa:004:google-attempt:v1' or data['flow'] != purpose
                    or data['client_id'] != self._client_id or data['role'] != role
                    or data['state'] != state):
                raise ValueError()
            return Attempt(role, state, data['nonce'], data['verifier'])
        except (InvalidToken, KeyError, ValueError, TypeError, UnicodeError):
            raise GoogleFailure('google_attempt_invalid') from None

    def seal(self, grant):
        if not isinstance(grant, Grant):
            raise GoogleFailure('google_grant_invalid')
        data = dict(purpose='sarsa:004:google-grant:v1', client_id=self._client_id,
                    role=grant.role, subject=grant.subject, email=grant.email,
                    refresh_token=grant.refresh_token, scopes=sorted(grant.scopes),
                    refresh_expires_at=grant.refresh_expires_at.isoformat()
                    if grant.refresh_expires_at else None)
        return self._cipher.encrypt(json.dumps(data, separators=(',', ':')).encode()).decode()

    def open(self, ciphertext, *, role, subject, now):
        now = _time(now)
        try:
            if not _opaque(ciphertext, 1, 32768):
                raise ValueError()
            data = json.loads(self._cipher.decrypt(ciphertext.encode()))
            if (data['purpose'] != 'sarsa:004:google-grant:v1'
                    or data['client_id'] != self._client_id
                    or data['role'] != role or data['subject'] != subject):
                raise ValueError()
            expiry = datetime.fromisoformat(data['refresh_expires_at']) if data['refresh_expires_at'] else None
            grant = Grant(role, subject, data['email'], data['refresh_token'], frozenset(data['scopes']), expiry)
            if expiry is not None and expiry <= now:
                raise GoogleFailure('google_reconnect_required')
            return grant
        except (InvalidToken, KeyError, TypeError, ValueError, UnicodeError):
            raise GoogleFailure('google_saved_grant_invalid') from None


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate response field')
        result[key] = value
    return result


class GoogleOAuth:
    def __init__(self, settings, *, transport=None):
        if not isinstance(settings, OAuthSettings):
            raise GoogleFailure('google_configuration_invalid')
        self.settings, self._transport = settings, transport

    def authorization_url(self, attempt, *, signin=False):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b'=').decode()
        return AUTH + '?' + urlencode(dict(
            client_id=self.settings.client_id,
            redirect_uri=self.settings.origin + SIGN_IN_CALLBACK if signin else self.settings.redirect_uri,
            response_type='code', scope='openid email' if signin else ' '.join(sorted(scopes_for(attempt.role))),
            access_type='online' if signin else 'offline',
            prompt='select_account' if signin else 'consent', include_granted_scopes='false',
            login_hint=OWNERS[attempt.role], state=attempt.state, nonce=attempt.nonce,
            code_challenge=challenge, code_challenge_method='S256'))

    def _request(self, url, *, data=None, access_token=None):
        if url not in (TOKEN, CERTS, USERINFO):
            raise GoogleFailure('google_endpoint_invalid')
        headers = {'Accept': 'application/json'}
        if access_token:
            headers['Authorization'] = 'Bearer ' + access_token
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False,
                              transport=self._transport) as client:
                with client.stream('POST' if data is not None else 'GET', url,
                                   data=data, headers=headers) as response:
                    if response.status_code != 200:
                        # No provider body/URL/token in logs or error text. A lost
                        # code exchange requires a NEW authorization, never retry.
                        raise GoogleFailure('google_request_failed')
                    body = bytearray()
                    for chunk in response.iter_bytes():
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
        except (httpx.HTTPError, ValueError, UnicodeError):
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

    def _scopes(self, value, role):
        if not isinstance(value, str):
            raise GoogleFailure('google_permissions_missing')
        scopes = frozenset(EMAIL_SCOPE if s == 'email' else s for s in value.split())
        if scopes != scopes_for(role):
            raise GoogleFailure('google_permissions_mismatch')
        return scopes

    def _access(self, tokens, grant, now):
        seconds = tokens.get('expires_in')
        if (not isinstance(tokens.get('token_type'), str)
                or tokens['token_type'].lower() != 'bearer'
                or not _opaque(tokens.get('access_token'))
                or type(seconds) is not int or not 0 < seconds <= 86400):
            raise GoogleFailure('google_token_invalid')
        return Access(tokens['access_token'], _time(now) + timedelta(seconds=seconds), grant)

    def _exchange_identity(self, attempt, code, *, signin=False, previous_subject=None):
        if not _opaque(code, 1, 4096):
            raise GoogleFailure('google_code_invalid')
        tokens = self._request(TOKEN, data=dict(client_id=self.settings.client_id,
            client_secret=self.settings.client_secret, code=code,
            redirect_uri=self.settings.origin + SIGN_IN_CALLBACK if signin else self.settings.redirect_uri,
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

    def exchange(self, attempt, code, *, now, previous_subject=None):
        """Called only after durable one-time attempt consumption by staff flow."""
        now = _time(now)
        tokens, subject = self._exchange_identity(attempt, code, previous_subject=previous_subject)
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
        grant = Grant(attempt.role, subject, OWNERS[attempt.role], tokens['refresh_token'], scopes, refresh_expiry)
        return self._access(tokens, grant, now)

    def refresh(self, grant, *, now):
        now = _time(now)
        if not isinstance(grant, Grant):
            raise GoogleFailure('google_grant_invalid')
        if grant.refresh_expires_at is not None and grant.refresh_expires_at <= now:
            raise GoogleFailure('google_reconnect_required')
        tokens = self._request(TOKEN, data=dict(client_id=self.settings.client_id,
            client_secret=self.settings.client_secret, refresh_token=grant.refresh_token,
            grant_type='refresh_token'))
        if 'scope' in tokens:
            self._scopes(tokens['scope'], grant.role)
        # Any returned replacement must be committed before this access is used.
        replacement = tokens.get('refresh_token', grant.refresh_token)
        expiry = grant.refresh_expires_at
        if 'refresh_token_expires_in' in tokens:
            seconds = tokens['refresh_token_expires_in']
            if type(seconds) is not int or not 0 < seconds <= 315360000:
                raise GoogleFailure('google_token_invalid')
            expiry = now + timedelta(seconds=seconds)
        refreshed = Grant(grant.role, grant.subject, grant.email, replacement, grant.scopes, expiry)
        access = self._access(tokens, refreshed, now)
        identity = self._request(USERINFO, access_token=access.token)
        self._identity(identity, grant.role, subject=grant.subject)
        return access
