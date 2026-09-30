"""Renew a saved owner connection before a Calendar/Sheets operation.

Only a confirmed database save releases the access token to its caller. Failure
leaves the previous encrypted grant intact and the bounded lease to expire. No
automatic retry after an uncertain provider response or database commit.
"""

from uuid import UUID

from .google_oauth import GoogleFailure, OWNERS
from .receipt_view import timestamp


def refresh_connection(store, services, role):
    if role not in OWNERS:
        raise GoogleFailure('google_account_mismatch')
    client = services.google.settings.client_id
    saved = store.claim_google_refresh(role, client)
    if saved is None:
        raise GoogleFailure('google_connection_unavailable')
    try:
        if (saved['role'] != role or saved['client_id'] != client
                or type(saved['revision']) is not int or saved['revision'] < 1):
            raise ValueError()
        lease = UUID(saved['lease'])
        now = timestamp(saved['server_now'])
        grant = services.cipher.open(saved['encrypted_grant'], role=role,
                                     subject=saved['subject'], now=now)
    except (KeyError, TypeError, ValueError):
        raise GoogleFailure('google_saved_grant_invalid') from None
    access = services.google.refresh(grant, now=now)
    if access.grant.role != role or access.grant.subject != saved['subject']:
        raise GoogleFailure('google_account_mismatch')
    encrypted = services.cipher.seal(access.grant)
    committed = store.finish_google_refresh(role, client, saved['subject'], saved['revision'],
        lease, encrypted, access.grant.refresh_expires_at)
    if committed is not True:
        raise GoogleFailure('google_connection_changed')
    return access
