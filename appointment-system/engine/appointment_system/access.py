"""Purpose-separated anonymous contexts and receipt access checks.

A context groups attempts; it is never permission to read a booking. Neither
credential belongs in a URL, logs, provider metadata or a notification.
"""

import hmac
import re
from datetime import datetime
from .security import receipt_matches
from .credentials import ContextKeys
from .errors import Rejected

COOKIE_NAME = '__Host-appointment-checkout'
CONTEXT_SECONDS = 24 * 60 * 60


class AccessDenied(Exception):
    """Deliberately identical for missing, wrong, expired and revoked access."""


def new_context(key):
    if not isinstance(key,ContextKeys):raise ValueError('Declared context protection is required.')
    return key.issue()


def context_identifier(token,key):
    if not isinstance(key,ContextKeys):raise AccessDenied()
    try:return key.identifier(token)
    except Rejected:raise AccessDenied() from None


def parse_context(token, key,row=None):
    if not isinstance(key,ContextKeys) or row is None:raise AccessDenied()
    try:
        return key.identifier(token),key.digest(token,format=row.get("credential_format"),key_id=row.get("credential_key_id"))
    except Rejected:raise AccessDenied() from None


def _aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def authorize_receipt(row, request_id, secret, key, now):
    if not _aware(now):
        raise ValueError('Database time is required.')
    if (not row or row.get('request_id') != str(request_id)
            or not _aware(row.get('receipt_expires_at'))
            or row['receipt_expires_at'] <= now or row.get('receipt_revoked_at') is not None
            or not receipt_matches(request_id, secret, key, row.get('receipt_digest'),
                   format=row.get('receipt_format',"v1"),key_id=row.get('receipt_key_id'))):
        raise AccessDenied()


def authorize_context(row, expected_digest, now):
    if (not row or not _aware(now) or not _aware(row.get('expires_at'))
            or row['expires_at'] <= now or not isinstance(row.get('credential_digest'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', row['credential_digest'])
            or not hmac.compare_digest(row['credential_digest'], expected_digest)):
        raise AccessDenied()
