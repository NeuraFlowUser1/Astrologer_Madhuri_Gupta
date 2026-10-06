"""Explicit preservation of an unreadable calendar permission pending consent."""
from appointment_system.google_oauth import resource_scopes_valid
from appointment_system.serialization import record_id
from .records import stamp
from .source import ConversionError

FORMAT='reauthorization-required'
PURPOSE='appointment:v1:retained-google-permission'


def pending_calendar(transfer,row,client,owner,scopes):
    subject=row['google_subject'];encrypted=row['refresh_token_encrypted']
    if (transfer.resources.resources['calendar'].active_client!=client
            or type(subject) is not str or not 1<=len(subject)<=255
            or any(ord(char)<33 or ord(char)>126 for char in subject)
            or type(encrypted) is not str or not 100<=len(encrypted)<=32768
            or any(ord(char)<33 or ord(char)>126 for char in encrypted)
            or not resource_scopes_valid(('calendar',),scopes)):
        raise ConversionError('legacy_resource_reauthorization_identity_invalid')
    connected=stamp(row['connected_at']).isoformat()
    identifier=transfer.identifier('legacy-google-grant','astro-calendar:client:'+client+':'+subject+':1')
    # Protect the retained opaque value with the new installation envelope, but
    # give it a distinct purpose that cannot be opened as a usable refresh token.
    payload=dict(purpose=PURPOSE,source_layout='legacy-003-16',calendar_id=owner,
                 subject=subject,client_id=client,encrypted_legacy_grant=encrypted)
    sealed=transfer.resources.cipher.protected.seal('google-resource-grant:'+record_id(identifier),payload)
    if len(sealed)>32768:raise ConversionError('legacy_resource_reauthorization_envelope_too_large')
    record=dict(id=identifier,owner_role='client',owner_email=owner,subject=subject,client_id=client,
        resources=['calendar'],scopes=sorted(scopes),encrypted_grant=sealed,grant_format=FORMAT,
        revision=1,grant_expires_at=None,connected_at=connected,revoked_at=None,
        refresh_lease=None,refresh_lease_until=None,refresh_revision=None,last_error_code='google_reconnect_required')
    spec=transfer.resources.resources['calendar']
    return {'google_resource_grants':[record],'google_resources':[dict(resource='calendar',
        owner_email=owner,active_client=client,retained_clients=list(spec.retained_clients),
        grant_id=identifier,revision=1,updated_at=connected)]}
