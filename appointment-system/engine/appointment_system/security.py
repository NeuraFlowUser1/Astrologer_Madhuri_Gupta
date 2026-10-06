"""Purpose-bound receipt credentials; never use contact details as identity."""

import hashlib
import json
import secrets
from .credentials import ReceiptKeys


def new_secret():
    return secrets.token_urlsafe(32)


def receipt_digest(request_id, secret, key):
    if not isinstance(key,ReceiptKeys):raise ValueError('Declared receipt protection is required.')
    return key.digest(request_id,secret)


def receipt_matches(request_id, secret, key, expected,*,format="v1",key_id=None):
    return isinstance(key,ReceiptKeys) and key.matches(request_id,secret,expected,format=format,key_id=key_id)


def request_fingerprint(validated_payload):
    """Call on normalized server-validated input, not raw request bytes."""
    body = json.dumps(validated_payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()
