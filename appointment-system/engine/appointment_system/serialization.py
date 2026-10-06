"""Bounded unique-key JSON and deterministic fingerprints, never repr hashes."""

import hashlib
import json
from uuid import UUID

from .errors import invalid

MAX_DOCUMENT_BYTES = 131072
MAX_DEPTH = 32


def _pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise invalid()
        result[name] = value
    return result


def _not_number(value):
    raise invalid()


def _bounded(value):
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise invalid()
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise invalid()
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is int:
            if not -(2**63) <= item < 2**63:
                raise invalid()
        elif type(item) not in (str, bool, type(None)):
            raise invalid()


def decode(value, *, maximum=MAX_DOCUMENT_BYTES):
    if type(maximum) is not int or not 1 <= maximum <= MAX_DOCUMENT_BYTES:
        raise invalid()
    try:
        encoded = value.encode("utf-8") if type(value) is str else value
        if type(encoded) is not bytes or len(encoded) > maximum:
            raise invalid()
        result = json.loads(encoded.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_float=_not_number, parse_constant=_not_number)
        _bounded(result)
        return result
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise invalid() from None


def canonical(value):
    _bounded(value)
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(result) > MAX_DOCUMENT_BYTES:
            raise invalid()
        return result
    except (UnicodeError, ValueError, RecursionError):
        raise invalid() from None


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def record_id(value, *, field="reference"):
    try:
        parsed = UUID(value) if type(value) is str else None
        if parsed is None or not parsed.int or str(parsed) != value:
            raise invalid(field)
        return str(parsed)
    except (ValueError, AttributeError):
        raise invalid(field) from None


def object_fields(value, required, optional=(), *, field="settings"):
    if (type(value) is not dict or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise invalid(field)
    return value


def integer(value, minimum, maximum, *, field="settings"):
    if type(value) is not int or not minimum <= value <= maximum:
        raise invalid(field)
    return value


def text(value, minimum, maximum, *, field="settings"):
    if (type(value) is not str or not minimum <= len(value) <= maximum
            or value.strip() != value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise invalid(field)
    return value
