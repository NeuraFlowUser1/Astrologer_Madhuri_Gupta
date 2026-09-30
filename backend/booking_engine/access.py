"""Purpose-separated anonymous contexts and receipt access checks.

A context groups attempts; it is never permission to read a booking. Neither
credential belongs in a URL, logs, provider metadata or a notification.
"""

import hashlib
import hmac
import re
from datetime import datetime
from uuid import UUID, uuid4

from .security import new_secret, receipt_matches

_CONTEXT = re.compile(r'^([a-f0-9-]{36})\.([A-Za-z0-9_-]{43})$')
COOKIE_NAME = '__Host-sarsa-checkout'
CONTEXT_SECONDS = 24 * 60 * 60


class AccessDenied(Exception):
    """Deliberately identical for missing, wrong, expired and revoked access."""


def _key(key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError('A purpose-specific access key is required.')
    return key


def context_digest(context_id, secret, key):
    token = f'{UUID(str(context_id))}.{secret}'
    if not _CONTEXT.fullmatch(token):
        raise ValueError('Invalid checkout context.')
    return hmac.new(_key(key), b'sarsa:004:checkout-context:v1:' + token.encode(), hashlib.sha256).hexdigest()


def new_context(key):
    identifier, secret = uuid4(), new_secret()
    return identifier, f'{identifier}.{secret}', context_digest(identifier, secret, key)


def parse_context(token, key):
    if not isinstance(token, str) or not (match := _CONTEXT.fullmatch(token)):
        raise AccessDenied()
    try:
        identifier = UUID(match[1])
        return identifier, context_digest(identifier, match[2], key)
    except (ValueError, TypeError):
        raise AccessDenied() from None


def _aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def authorize_receipt(row, request_id, secret, key, now):
    if not _aware(now):
        raise ValueError('Database time is required.')
    if (not row or row.get('request_id') != str(request_id)
            or not _aware(row.get('receipt_expires_at'))
            or row['receipt_expires_at'] <= now or row.get('receipt_revoked_at') is not None
            or not receipt_matches(request_id, secret, key, row.get('receipt_digest'))):
        raise AccessDenied()


def authorize_context(row, expected_digest, now):
    if (not row or not _aware(now) or not _aware(row.get('expires_at'))
            or row['expires_at'] <= now or not isinstance(row.get('credential_digest'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', row['credential_digest'])
            or not hmac.compare_digest(row['credential_digest'], expected_digest)):
        raise AccessDenied()
