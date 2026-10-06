"""Renew a saved owner connection before a Calendar/Sheets operation.

Only a confirmed database save releases the access token to its caller. Failure
leaves the previous encrypted grant intact and the bounded lease to expire. No
automatic retry after an uncertain provider response or database commit.
"""

from uuid import UUID

from .google_oauth import GoogleFailure, OWNERS
from .receipt_view import timestamp


def refresh_connection(store, services, role,*,resource=None,grant_id=None):
    if role not in OWNERS:
        raise GoogleFailure('google_account_mismatch')
    if getattr(services,'resources',None) is not None:
        selected=resource or ('agency_sheet' if role=='agency' else 'client_sheet')
        if (selected=='agency_sheet')!=(role=='agency'):raise GoogleFailure('google_account_mismatch')
        return refresh_resource_connection(store,services.resources,selected,grant_id=grant_id)
    # Historical grants are imported as explicitly bound resource readers.
    # Missing resource configuration cannot reactivate the superseded writer.
    raise GoogleFailure('google_connection_unavailable')


def refresh_resource_connection(store,resources,resource,*,grant_id=None):
    saved=store.claim_google_resource_refresh(resource,grant_id) if grant_id is not None else store.claim_google_resource_refresh(resource)
    if saved is None:raise GoogleFailure('google_connection_unavailable')
    if saved.get('code')=='google_reconnect_required':raise GoogleFailure('google_reconnect_required')
    try:
        if saved['resource']!=resource or type(saved['revision']) is not int or saved['revision']<1:
            raise GoogleFailure('google_saved_grant_invalid')
        UUID(saved['lease']);now=timestamp(saved['server_now'])
        grant=resources.cipher.open(saved,resource,now=now)
        provider=resources.provider(resource,client_id=saved['client_id'])
        access=provider.refresh(grant,now=now)
        if access.grant.subject!=saved['subject'] or access.grant.email!=saved['owner_email']:
            raise GoogleFailure('google_account_mismatch')
        encrypted=resources.cipher.seal(saved['grant_id'],saved['client_id'],access.grant)
    except (KeyError,TypeError,ValueError):
        store.finish_google_resource_refresh(saved,error='google_saved_grant_invalid')
        raise GoogleFailure('google_saved_grant_invalid') from None
    except GoogleFailure as failure:
        error=str(failure)
        allowed={'google_reconnect_required','google_request_failed','google_account_mismatch',
          'google_permissions_mismatch','google_token_invalid','google_saved_grant_invalid'}
        store.finish_google_resource_refresh(saved,error=error if error in allowed else 'google_saved_grant_invalid')
        raise
    if store.finish_google_resource_refresh(saved,encrypted,access.grant.refresh_expires_at,sorted(access.grant.scopes)) is not True:
        raise GoogleFailure('google_connection_changed')
    return access
