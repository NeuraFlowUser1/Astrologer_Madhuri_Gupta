"""Purpose-bound receipt credentials; never use contact details as identity."""

import hashlib
import hmac
import json
import re
import secrets
from uuid import UUID

_SECRET = re.compile(r"^[A-Za-z0-9_-]{43}$")


def new_secret():
    return secrets.token_urlsafe(32)


def receipt_digest(request_id, secret, key):
    if not isinstance(secret, str) or not _SECRET.fullmatch(secret):
        raise ValueError("Invalid receipt credential")
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("Receipt signing key must contain at least 32 bytes")
    identifier = str(UUID(str(request_id)))
    message = f"sarsa:004:booking-receipt:v1:{identifier}:{secret}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def receipt_matches(request_id, secret, key, expected):
    try:
        actual = receipt_digest(request_id, secret, key)
    except (ValueError, TypeError, AttributeError):
        return False
    return (isinstance(expected, str) and re.fullmatch(r"[a-f0-9]{64}", expected) is not None
            and hmac.compare_digest(actual, expected))


def request_fingerprint(validated_payload):
    """Call on normalized server-validated input, not raw request bytes."""
    body = json.dumps(validated_payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()
