"""Database-backed request limits with no raw IP storage.

The host adapter must supply a verified client address. Never trust arbitrary
X-Forwarded-For or browser headers. Limits are committed before the next action.
"""

import hashlib
import hmac
from ipaddress import ip_address, ip_network

from .connection import StorageUnavailable
from .keys import KeyRing


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = max(1,min(int(retry_after),3600))


def risk_digest(address,key):
    if isinstance(key,KeyRing) and key.purpose!="risk":
        raise StorageUnavailable('Request protection is not configured.')
    if not isinstance(key,KeyRing) and (not isinstance(key,bytes) or len(key)<32):
        raise StorageUnavailable('Request protection is not configured.')
    if address is None:
        return key.digest("request-risk",b"unverified-shared-source") if isinstance(key,KeyRing) else hmac.new(key,b'appointment:v1:request-risk:v1:unverified-shared-source',hashlib.sha256).hexdigest()
    try:
        parsed=ip_address(address)
    except (ValueError,TypeError):
        raise StorageUnavailable('The request source could not be verified.') from None
    if parsed.version==6 and parsed.ipv4_mapped:
        parsed=parsed.ipv4_mapped
    # IPv6 privacy-address rotation must not create a fresh quota per address.
    source=str(ip_network(f'{parsed}/64',strict=False)) if parsed.version==6 else str(parsed)
    return key.digest("request-risk",source.encode()) if isinstance(key,KeyRing) else hmac.new(key,b'appointment:v1:request-risk:v1:'+source.encode(),hashlib.sha256).hexdigest()


def consume_limit(store,scope,address,key,*,booking=False):
    digest=risk_digest(address,key)
    result=(store.consume_limit(scope,digest,booking=True) if booking else store.consume_limit(scope,digest))
    if not isinstance(result,dict) or type(result.get('allowed')) is not bool:
        raise StorageUnavailable('Request protection is temporarily unavailable.')
    if not result['allowed']:
        raise RateLimited(result.get('retry_after',60))
