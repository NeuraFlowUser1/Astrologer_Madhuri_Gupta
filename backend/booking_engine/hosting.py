"""Vercel-only composition root. Never imports the legacy application.

No migrations, database connections, provider calls or secret logging on import.
The production address and database are deliberately pinned to client 004.
"""

import base64
import binascii
import json
import re
from ipaddress import ip_address

import certifi
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg.conninfo import make_conninfo

from .application import Settings, create_application
from .connection import StorageUnavailable, checked_config
from .storage import Store
from .studio import StudioServices

ORIGIN = 'https://www.sarsajyotishsansthan.com'
HOST = 'www.sarsajyotishsansthan.com'
DATABASE_HOST = 'ep-dry-hill-b3ujpil7-pooler.c-4.ap-southeast-1.aws.neon.tech'
DATABASE_USER = 'sarsa_booking_web'


def booking_keys(value):
    def unique(pairs):
        result = {}
        for name, item in pairs:
            if name in result:
                raise ValueError('Repeated key name.')
            result[name] = item
        return result

    try:
        values = json.loads(value, object_pairs_hook=unique)
        if not isinstance(values, dict) or set(values) != {'receipt', 'context', 'risk'}:
            raise ValueError()
        decoded = {}
        for name, item in values.items():
            if not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=', item):
                raise ValueError()
            key = base64.b64decode(item, altchars=b'-_', validate=True)
            if len(key) != 32 or base64.urlsafe_b64encode(key).decode() != item:
                raise ValueError()
            decoded[name] = key
        if len(set(decoded.values())) != 3:
            raise ValueError()
        return decoded
    except (ValueError, TypeError, binascii.Error):
        raise ValueError('Booking protection configuration is missing.') from None


def vercel_client_address(request):
    """Only used behind Vercel's production proxy by create_hosted_application.

    Vercel supplies x-vercel-forwarded-for; do not fall back to browser supplied
    forwarding headers or the shared proxy address if that contract is absent.
    """
    values = request.headers.getlist('x-vercel-forwarded-for')
    try:
        if len(values) != 1 or '%' in values[0]:
            raise ValueError()
        return str(ip_address(values[0]))
    except (ValueError, TypeError):
        raise StorageUnavailable('The request source could not be verified.') from None


class CanonicalHost:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            hosts = [v for k, v in scope.get('headers', []) if k.lower() == b'host']
            if hosts != [HOST.encode()]:
                # Do not forward authorization codes or cookies via redirects.
                response = JSONResponse({'code': 'website_address_required'}, 421,
                    headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
                return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def unavailable_application():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
    async def unavailable(path):
        return JSONResponse({'code': 'temporarily_unavailable',
            'message': 'This service is not available yet. Please try again later.'}, 503,
            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                     'X-Content-Type-Options': 'nosniff'})

    return app


def studio_configuration_checks(environment, booking_protection):
    """Safe local-format evidence only; no provider requests or private values."""
    from .google_oauth import GrantCipher, GoogleFailure
    checks = {}
    client_id = environment.get('SARSA_GOOGLE_CLIENT_ID')
    secret = environment.get('SARSA_GOOGLE_CLIENT_SECRET')
    checks['google_client_id_format'] = isinstance(client_id, str) and bool(
        re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', client_id))
    checks['google_client_secret_format'] = (isinstance(secret, str)
        and 1 <= len(secret) <= 8192 and all(33 <= ord(c) <= 126 for c in secret))
    try:
        GrantCipher(client_id, json.loads(environment.get('SARSA_GOOGLE_TOKEN_KEYS', 'null')))
        checks['google_token_keys_format'] = True
    except (ValueError, TypeError, RecursionError, GoogleFailure):
        checks['google_token_keys_format'] = False
    try:
        encoded = environment.get('SARSA_STUDIO_SIGNING_KEY')
        if not isinstance(encoded, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=', encoded):
            raise ValueError()
        signing = base64.b64decode(encoded, altchars=b'-_', validate=True)
        checks['studio_signing_key_format'] = len(signing) == 32
        checks['studio_signing_key_independent'] = signing not in booking_protection.values()
    except (ValueError, TypeError, binascii.Error):
        checks['studio_signing_key_format'] = False
        checks['studio_signing_key_independent'] = False
    return checks


def create_hosted_application(environment):
    try:
        if (environment.get('VERCEL') != '1' or environment.get('VERCEL_ENV') != 'production'
                or environment.get('SARSA_PUBLIC_ORIGIN') != ORIGIN):
            raise ValueError()
        dsn = environment['SARSA_DATABASE_URL']
        config = checked_config(dsn, DATABASE_HOST)
        if (config.get('user') != DATABASE_USER or config.get('dbname') != 'neondb'
                or config.get('sslmode') not in ('require', 'verify-full') or not config.get('password')
                or config.get('port', '5432') != '5432'
                or config.get('sslrootcert', 'system') != 'system'
                or config.get('channel_binding', 'prefer') not in ('prefer', 'require')
                or set(config) - {'host', 'port', 'dbname', 'user', 'password',
                                  'sslmode', 'sslrootcert', 'channel_binding'}):
            raise ValueError()
        # Accept Neon's normal copied URL without asking the owner to edit it.
        # Binary libpq builds may have no usable system trust path. Use the
        # packaged Mozilla CA bundle explicitly across local and Vercel runtimes;
        # retain certificate/hostname verification without owner-edited URLs.
        dsn = make_conninfo(dsn, sslmode='verify-full', sslrootcert=certifi.where())
        keys = booking_keys(environment['SARSA_BOOKING_KEYS'])
        settings = Settings(ORIGIN, keys['receipt'], keys['context'], keys['risk'])
        try:
            studio = StudioServices.from_environment(environment)
            if studio.signing_key in keys.values():
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            studio = None
        try:
            token_keys = json.loads(environment.get('SARSA_GOOGLE_TOKEN_KEYS', '[]'))
            if not isinstance(token_keys, list) or any(not isinstance(v, str) for v in token_keys):
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            token_keys = []
        protected_keys = (environment.get('SARSA_STUDIO_SIGNING_KEY'),
            *json.loads(environment['SARSA_BOOKING_KEYS']).values(), *token_keys)
        from .email_events import EmailWebhook
        # Optional mail configuration cannot take down existing payment/status access.
        try:
            email_webhook = EmailWebhook((environment['SARSA_RESEND_WEBHOOK_SECRET'],)) if environment.get('SARSA_RESEND_WEBHOOK_SECRET') else None
        except ValueError:
            email_webhook = None
        from .google_worker import WorkerKey
        try:
            worker_key = WorkerKey(environment['SARSA_GOOGLE_WORKER_KEY']) if environment.get('SARSA_GOOGLE_WORKER_KEY') else None
            if worker_key and worker_key.value in protected_keys:
                raise ValueError('Worker key must be independent.')
        except ValueError:
            worker_key = None
        from .resend_email import ResendSender
        try:
            email_sender = ResendSender.from_environment(environment)
        except ValueError:
            email_sender = None
        try:
            email_worker_key = WorkerKey(environment['SARSA_EMAIL_WORKER_KEY']) if environment.get('SARSA_EMAIL_WORKER_KEY') else None
            reserved = (*protected_keys,environment.get('SARSA_GOOGLE_WORKER_KEY'))
            if email_worker_key and email_worker_key.value in reserved:
                raise ValueError('Worker key must be independent.')
        except ValueError:
            email_worker_key = None
        # Optional recovery/wake faults are isolated from receipt and owner access.
        reserved_worker_keys = (*protected_keys,
            environment.get('SARSA_GOOGLE_WORKER_KEY'),environment.get('SARSA_EMAIL_WORKER_KEY'),
        )
        try:
            recovery_key = WorkerKey(environment['SARSA_RECOVERY_WORKER_KEY']) if environment.get('SARSA_RECOVERY_WORKER_KEY') else None
            if recovery_key and recovery_key.value in reserved_worker_keys:
                raise ValueError('Worker key must be independent.')
        except ValueError:
            recovery_key = None
        from .wake import WakePublisher, WAKE_URL
        try:
            wake = WakePublisher(WAKE_URL,environment.get('SARSA_WAKE_KEY',''))
            if wake.key in (*reserved_worker_keys,environment.get('SARSA_RECOVERY_WORKER_KEY')):
                raise ValueError('Wake key must be independent.')
        except ValueError:
            wake = None
        from .payment_configuration import payment_accounts, payment_webhook
        from .razorpay import RazorpayFailure
        try:
            accounts = payment_accounts(environment.get('SARSA_RAZORPAY_ACCOUNTS', ''))
        except (ValueError, TypeError, RecursionError, RazorpayFailure):
            accounts = None
        try:
            webhook_account = payment_webhook(environment.get('SARSA_RAZORPAY_WEBHOOK', ''), accounts)
        except (ValueError, TypeError, RecursionError, RazorpayFailure):
            webhook_account = None
        from .contact import ContactSecrets
        try:
            contact = ContactSecrets.from_environment(environment)
            configured = json.loads(environment['SARSA_CONTACT_KEYS'])
            reused = (*protected_keys,environment.get('SARSA_GOOGLE_WORKER_KEY'),
                environment.get('SARSA_EMAIL_WORKER_KEY'),environment.get('SARSA_RECOVERY_WORKER_KEY'),environment.get('SARSA_WAKE_KEY'))
            if configured['digest'] in reused or any(value in reused for value in configured['encryption']):
                raise ValueError('Contact protection must be independent.')
        except (ValueError,KeyError,TypeError,RecursionError):
            contact = None
        # Explicit operational switch plus every required consumer credential.
        # Database intake still stays closed until hosted acceptance is complete.
        contact_ready = environment.get('SARSA_CONTACT_DELIVERY_ENABLED') == 'true' and all((
            contact,studio,worker_key,email_sender,email_worker_key,email_webhook,recovery_key,wake))
        store = Store(dsn, expected_host=DATABASE_HOST)
        app = create_application(store, settings, verified_client_address=vercel_client_address,
                                 studio_services=studio, worker_key=worker_key, email_webhook=email_webhook,
                                 email_worker_key=email_worker_key,email_sender=email_sender,
                                 recovery_worker_key=recovery_key,wake_publisher=wake,
                                 payment_accounts=accounts,webhook_account=webhook_account,contact_secrets=contact,contact_delivery_ready=contact_ready)
        from .recovery_worker import add_configuration_route
        add_configuration_route(app, recovery_key, {
            'checks': studio_configuration_checks(environment, keys),
            'configured': {
                'studio': studio is not None,
                'google_worker': worker_key is not None,
                'email_sender': email_sender is not None,
                'email_worker': email_worker_key is not None,
                'email_webhook': email_webhook is not None,
                'recovery_worker': recovery_key is not None,
                'wake_publisher': wake is not None,
                'contact_protection': contact is not None,
                'contact_delivery': bool(contact_ready),
                'payment_accounts': accounts is not None,
                'payment_webhook': webhook_account is not None,
            },
        })
        app.add_middleware(CanonicalHost)
        return app
    except (KeyError, ValueError, TypeError, StorageUnavailable):
        # No raw configuration or traceback reaches the response or application log.
        # Payment events remain unavailable until the pinned merchant is configured.
        return unavailable_application()
