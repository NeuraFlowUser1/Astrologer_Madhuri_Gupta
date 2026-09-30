"""Production Google boundary, synthetic HTTP only; real RSA/JWT verification."""

import base64
import hashlib
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from backend.booking_engine.google_oauth import (
    Attempt, CALENDAR_SCOPE, CERTS, FILE_SCOPE, GoogleFailure, GoogleOAuth,
    Grant, GrantCipher, MAX_RESPONSE, OAuthSettings, OWNERS, TOKEN, USERINFO,
    scopes_for,
)


CLIENT = '12345-synthetic.apps.googleusercontent.com'


class GoogleOAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic Google test')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(cls.key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
                .sign(cls.key, hashes.SHA256()))
        cls.cert = cert.public_bytes(serialization.Encoding.PEM).decode()

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.settings = OAuthSettings(CLIENT, 'synthetic-client-secret', 'https://sarsa.example')
        self.attempt = Attempt.new('client')
        self.claims = dict(iss='https://accounts.google.com', aud=CLIENT, sub='synthetic-subject',
                           email=OWNERS['client'], email_verified=True, nonce=self.attempt.nonce,
                           iat=int(time.time())-1, exp=int(time.time())+3600)
        self.calls = []

    def signed(self, claims):
        def encoded(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=')
        data = encoded(dict(alg='RS256', kid='synthetic')) + b'.' + encoded(claims)
        signature = self.key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        return (data + b'.' + base64.urlsafe_b64encode(signature).rstrip(b'=')).decode()

    def token_response(self, **changes):
        return dict(dict(id_token=self.signed(self.claims), access_token='synthetic-access',
                         refresh_token='synthetic-refresh', token_type='Bearer', expires_in=3600,
                         scope=' '.join(sorted(scopes_for(self.attempt.role)))), **changes)

    def provider(self, response=None, *, identity=None):
        def handler(request):
            self.calls.append(request)
            if str(request.url) == TOKEN:
                return response if isinstance(response, httpx.Response) else httpx.Response(
                    200, json=self.token_response() if response is None else response)
            if str(request.url) == CERTS:
                return httpx.Response(200, json={'synthetic': self.cert})
            if str(request.url) == USERINFO:
                return httpx.Response(200, json=self.claims if identity is None else identity)
            self.fail('Unexpected provider destination')
        return GoogleOAuth(self.settings, transport=httpx.MockTransport(handler))

    def test_role_scopes_and_pkce_bound_authorization(self):
        oauth = self.provider()
        query = parse_qs(urlsplit(oauth.authorization_url(self.attempt)).query)
        self.assertEqual(query['login_hint'], [OWNERS['client']])
        self.assertEqual(query['include_granted_scopes'], ['false'])
        self.assertEqual(query['access_type'], ['offline'])
        self.assertEqual(query['prompt'], ['consent'])
        self.assertEqual(query['redirect_uri'], ['https://sarsa.example/api/studio/google/callback'])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.attempt.verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(query['code_challenge'], [challenge])
        self.assertNotIn(self.attempt.verifier, oauth.authorization_url(self.attempt))
        agency = parse_qs(urlsplit(oauth.authorization_url(Attempt.new('agency'))).query)
        self.assertNotIn(CALENDAR_SCOPE, agency['scope'][0])
        self.assertIn(FILE_SCOPE, agency['scope'][0])

    def test_staff_signin_verifies_identity_without_offline_permission(self):
        response = self.token_response()
        response.pop('refresh_token')
        response['scope'] = 'openid email'
        self.assertEqual(self.provider(response).sign_in(self.attempt, 'code'), self.claims['sub'])
        body = parse_qs(self.calls[0].content.decode())
        self.assertEqual(body['redirect_uri'], ['https://sarsa.example/api/studio/sign-in/callback'])

    def test_encrypted_attempt_cannot_switch_flow_state_role_or_client(self):
        key = Fernet.generate_key()
        cipher = GrantCipher(CLIENT, [key])
        encoded = cipher.seal_attempt(self.attempt, 'signin')
        self.assertNotIn(self.attempt.verifier, encoded)
        self.assertEqual(cipher.open_attempt(encoded, state=self.attempt.state, role='client', purpose='signin'), self.attempt)
        for state, role, purpose, decryptor in (
            ('x'*43, 'client', 'signin', cipher), (self.attempt.state, 'agency', 'signin', cipher),
            (self.attempt.state, 'client', 'connect', cipher),
            (self.attempt.state, 'client', 'signin', GrantCipher('another-client', [key]))):
            with self.subTest(role=role, purpose=purpose), self.assertRaises(GoogleFailure):
                decryptor.open_attempt(encoded, state=state, role=role, purpose=purpose)

    def test_real_signed_exchange_and_secret_free_representations(self):
        access = self.provider().exchange(self.attempt, 'synthetic-code', now=self.now)
        self.assertEqual(access.grant.email, OWNERS['client'])
        self.assertEqual(access.expires_at, self.now+timedelta(hours=1))
        sent = parse_qs(self.calls[0].content.decode())
        self.assertEqual(sent['code_verifier'], [self.attempt.verifier])
        self.assertEqual(sent['client_secret'], ['synthetic-client-secret'])
        for value, secret in ((self.settings, 'synthetic-client-secret'),
                              (self.attempt, self.attempt.verifier),
                              (access, 'synthetic-access'), (access.grant, 'synthetic-refresh')):
            self.assertNotIn(secret, repr(value))

    def test_wrong_account_subject_and_unverified_email_rejected(self):
        for change in ({'email': OWNERS['agency']}, {'email_verified': False},
                       {'email_verified': 'true'}, {'email': []}, {'sub': ''}):
            with self.subTest(change=change), self.assertRaises(GoogleFailure):
                result = self.token_response(id_token=self.signed(dict(self.claims, **change)))
                self.provider(result).exchange(self.attempt, 'code', now=self.now)
        with self.assertRaises(GoogleFailure):
            self.provider().exchange(self.attempt, 'code', now=self.now, previous_subject='different')

    def test_signature_audience_issuer_nonce_expiry_and_authorized_party(self):
        for change in ({'aud': 'another-client'}, {'iss': 'https://evil.invalid'},
                       {'nonce': 'x'*43}, {'exp': int(time.time())-60},
                       {'azp': 'another-client'}, {'iat': int(time.time())+600}):
            with self.subTest(change=change), self.assertRaises(GoogleFailure):
                self.provider(self.token_response(id_token=self.signed(dict(self.claims, **change)))).exchange(
                    self.attempt, 'code', now=self.now)
        jwt = self.signed(self.claims)
        parts = jwt.split('.')
        parts[2] = ('A' if parts[2][0] != 'A' else 'B') + parts[2][1:]
        with self.assertRaises(GoogleFailure):
            self.provider(self.token_response(id_token='.'.join(parts))).exchange(self.attempt, 'code', now=self.now)

    def test_missing_or_excess_scopes_and_missing_refresh_are_rejected(self):
        for change in ({'scope': 'openid'}, {'scope': ' '.join(scopes_for('client'))+' https://www.googleapis.com/auth/drive'},
                       {'scope': None}, {'refresh_token': None}, {'expires_in': True},
                       {'token_type': []}, {'refresh_token_expires_in': -1}):
            with self.subTest(change=change), self.assertRaises(GoogleFailure):
                self.provider(self.token_response(**change)).exchange(self.attempt, 'code', now=self.now)

    def test_agency_exchange_cannot_receive_calendar_grant(self):
        self.attempt = Attempt.new('agency')
        self.claims.update(email=OWNERS['agency'], nonce=self.attempt.nonce)
        grant = self.provider().exchange(self.attempt, 'code', now=self.now).grant
        self.assertEqual(grant.role, 'agency')
        with self.assertRaises(GoogleFailure):
            self.provider(self.token_response(scope=' '.join(scopes_for('client')))).exchange(self.attempt, 'code', now=self.now)

    def test_failures_redirects_duplicate_fields_and_oversize_do_not_retry(self):
        for response in (httpx.Response(302, headers={'Location': 'https://evil.invalid'}),
                         httpx.Response(400, json={'error': 'sensitive-provider-detail'}),
                         httpx.Response(200, content=b'{"a":1,"a":2}', headers={'content-type': 'application/json'}),
                         httpx.Response(200, content=b'x'*(MAX_RESPONSE+1), headers={'content-type': 'application/json'}),
                         httpx.Response(200, json=['wrong-shape'])):
            self.calls.clear()
            with self.subTest(response=response), self.assertRaises(GoogleFailure) as error:
                self.provider(response).exchange(self.attempt, 'code', now=self.now)
            self.assertEqual(len(self.calls), 1)
            self.assertNotIn('sensitive-provider-detail', str(error.exception))
        calls = []
        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout('sensitive-timeout-detail')
        with self.assertRaises(GoogleFailure):
            GoogleOAuth(self.settings, transport=httpx.MockTransport(timeout)).exchange(self.attempt, 'code', now=self.now)
        self.assertEqual(len(calls), 1)

    def test_encryption_binds_role_subject_client_and_detects_tampering(self):
        grant = self.provider().exchange(self.attempt, 'code', now=self.now).grant
        key = Fernet.generate_key()
        cipher = GrantCipher(CLIENT, [key])
        sealed = cipher.seal(grant)
        self.assertNotIn(grant.refresh_token, sealed)
        self.assertEqual(cipher.open(sealed, role='client', subject=grant.subject, now=self.now), grant)
        for role, subject, decryptor, value in (
                ('agency', grant.subject, cipher, sealed), ('client', 'other', cipher, sealed),
                ('client', grant.subject, GrantCipher('other', [key]), sealed),
                ('client', grant.subject, GrantCipher(CLIENT, [Fernet.generate_key()]), sealed),
                ('client', grant.subject, cipher, sealed[:50]+('y' if sealed[50]=='x' else 'x')+sealed[51:])):
            with self.subTest(role=role, subject=subject), self.assertRaises(GoogleFailure):
                decryptor.open(value, role=role, subject=subject, now=self.now)

    def test_deliberate_key_rotation_and_refresh_expiration(self):
        grant = self.provider(self.token_response(refresh_token_expires_in=120)).exchange(self.attempt, 'code', now=self.now).grant
        old, new = Fernet.generate_key(), Fernet.generate_key()
        old_cipher = GrantCipher(CLIENT, [old])
        rotating = GrantCipher(CLIENT, [new, old])
        sealed = old_cipher.seal(grant)
        self.assertEqual(rotating.open(sealed, role='client', subject=grant.subject, now=self.now), grant)
        new_sealed = rotating.seal(grant)
        with self.assertRaises(GoogleFailure):
            old_cipher.open(new_sealed, role='client', subject=grant.subject, now=self.now)
        with self.assertRaises(GoogleFailure):
            rotating.open(sealed, role='client', subject=grant.subject, now=self.now+timedelta(seconds=120))

    def test_refresh_checks_identity_before_returning_access(self):
        grant = Grant('client', self.claims['sub'], OWNERS['client'], 'saved-refresh', scopes_for('client'))
        tokens = dict(access_token='new-access', token_type='Bearer', expires_in=3600)
        access = self.provider(tokens).refresh(grant, now=self.now)
        self.assertEqual(access.grant.refresh_token, 'saved-refresh')
        self.assertEqual(self.calls[-1].headers['authorization'], 'Bearer new-access')
        with self.assertRaises(GoogleFailure):
            self.provider(tokens, identity=dict(self.claims, sub='other')).refresh(grant, now=self.now)
        with self.assertRaises(GoogleFailure):
            self.provider(tokens, identity=dict(self.claims, email=OWNERS['agency'])).refresh(grant, now=self.now)

    def test_refresh_preserves_replacement_and_rejects_expired_grant_before_network(self):
        grant = Grant('client', self.claims['sub'], OWNERS['client'], 'old-refresh', scopes_for('client'))
        tokens = dict(access_token='new-access', token_type='Bearer', expires_in=3600,
                      refresh_token='replacement-refresh', refresh_token_expires_in=600)
        access = self.provider(tokens).refresh(grant, now=self.now)
        self.assertEqual(access.grant.refresh_token, 'replacement-refresh')
        self.assertEqual(access.grant.refresh_expires_at, self.now+timedelta(seconds=600))
        self.calls.clear()
        with self.assertRaises(GoogleFailure):
            self.provider(tokens).refresh(access.grant, now=self.now+timedelta(seconds=600))
        self.assertEqual(self.calls, [])

    def test_configuration_rejects_arbitrary_origins_and_unbounded_roles(self):
        config = dict(SARSA_GOOGLE_CLIENT_ID=CLIENT, SARSA_GOOGLE_CLIENT_SECRET='secret',
                      SARSA_PUBLIC_ORIGIN='https://sarsa.example')
        self.assertEqual(OAuthSettings.from_environment(config).client_id, CLIENT)
        with self.assertRaises(GoogleFailure):
            OAuthSettings.from_environment(dict(GOOGLE_CLIENT_ID=CLIENT, GOOGLE_CLIENT_SECRET='other-client-secret'))
        for origin in ('http://sarsa.example', 'https://sarsa.example/path',
                       'https://user@sarsa.example', 'https://sarsa.example#fragment',
                       'https://sarsa.example:444'):
            with self.subTest(origin=origin), self.assertRaises(GoogleFailure):
                OAuthSettings(CLIENT, 'secret', origin)
        with self.assertRaises(GoogleFailure):
            Attempt.new('another-client')
        with self.assertRaises(GoogleFailure):
            self.provider()._certificates('https://evil.invalid')


if __name__ == '__main__':
    unittest.main()
