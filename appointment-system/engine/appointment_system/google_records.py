"""Durable workbook provisioning and immutable per-revision booking snapshots."""

from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo
from .serialization import fingerprint

from .google_access import refresh_connection
from .google_workspace import PROJECT, Workspace, WorkspaceFailure
from .receipt_view import timestamp


def prepare_owner_workbook(store, services, role, *, transport=None):
    access = refresh_connection(store, services, role)
    workspace = Workspace(access, transport=transport)
    saved = store.claim_google_workbook(role, access.client_id or services.google.settings.client_id)
    if not saved:
        raise WorkspaceFailure('google_workbook_unavailable')
    if saved['subject'] != access.grant.subject:
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    workspace.bind_volume(saved)
    if saved['action']=='ready':
        return workspace, saved
    if saved['action']=='review':
        raise WorkspaceFailure(saved['code'],uncertain=True)
    if saved['action']=='create':
        workspace.check_capacity()
        if store.begin_google_workbook_create(role,UUID(saved['lease']),UUID(saved['intent'])) is not True:
            raise WorkspaceFailure('google_workbook_creation_unresolved',uncertain=True)
        identifier = workspace.create_workbook(saved['intent'])
    elif saved['action']=='discover':
        identifier = workspace.find_workbook(saved['intent'])
        if identifier is None:
            raise WorkspaceFailure('google_workbook_creation_unresolved', uncertain=True)
    else:
        raise WorkspaceFailure('google_workbook_unavailable')
    workspace.prepare_workbook(identifier, saved['intent'])
    if store.finish_google_workbook(role, UUID(saved['lease']), identifier) is not True:
        raise WorkspaceFailure('google_workbook_save_uncertain', uncertain=True)
    return workspace, dict(saved, spreadsheet_id=identifier)


def workspace_for_record(store, services, role, job_id, kind, *, transport=None):
    mapped = store.mapped_google_row(role, UUID(str(job_id)), kind)
    if mapped is None:
        return prepare_owner_workbook(store,services,role,transport=transport)
    access = refresh_connection(store,services,role,grant_id=mapped.get('grant_id'))
    if mapped['subject'] != access.grant.subject or mapped['client_id'] != (access.client_id or services.google.settings.client_id):
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    workspace = Workspace(access,transport=transport)
    workspace.bind_volume(mapped)
    return workspace,mapped


def sheet_values(job,layout_version=3,*,project=PROJECT):
    booking = job['payload']
    base=[project,str(UUID(job['id'])),str(UUID(booking['id'])),str(booking['revision']),
        booking['state'],booking['service_snapshot']['name'],
        timestamp(booking['starts_at']).isoformat(),timestamp(booking['ends_at']).isoformat(),
        booking['full_name'],booking['email'] or '',booking['phone'],str(Decimal(booking['amount_paise'])/100)]
    if layout_version in (1,2):return base
    if layout_version not in (3,4):raise WorkspaceFailure('google_workbook_layout_changed')
    preparation=booking.get('preparation') or {};payment=booking.get('payment_identity') or {}
    values=base+[
        booking.get('currency','INR'),str(booking.get('questions',1)),preparation.get('birth_date') or '',
        preparation.get('birth_time') or '',preparation.get('birth_place') or '',preparation.get('notes') or '',
        booking.get('request_id') or '',payment.get('merchant_id') or '',payment.get('mode') or '',
        payment.get('credential_version') or '',payment.get('provider_order_id') or '',booking.get('payment_reference') or '',
        booking.get('meet_url') or '',booking.get('original_starts_at') or '',booking.get('created_at') or '',
        booking.get('cancelled_at') or '',booking.get('practice_timezone') or '',booking['service_snapshot'].get('id') or '',
        booking.get('policy_version') or '',str(booking.get('verification_policy_revision') or ''),booking.get('source') or 'booking']
    if layout_version==4:
        local=timestamp(booking['starts_at']).astimezone(ZoneInfo(booking['practice_timezone']))
        values += [local.date().isoformat(),local.strftime('%H:%M')]
        values.append(fingerprint(values))
    return values


def copy_booking_record(store, services, job, *, transport=None):
    roles = {'client_sheet':'client','agency_sheet':'agency'}
    if job['kind']!='sheet_booking' or job['recipient_role'] not in roles:
        raise WorkspaceFailure('google_record_job_invalid')
    role = roles[job['recipient_role']]
    workspace, saved = workspace_for_record(store, services, role, job['id'], 'booking', transport=transport)
    values=saved.get('values')
    if values is None:values=sheet_values(job,saved.get('layout_version',3),project=workspace.workbook_project())
    assigned = store.assign_sheet_row(role, job, values)
    if not assigned or assigned['spreadsheet_id']!=saved['spreadsheet_id'] or assigned['intent']!=saved['intent']:
        raise WorkspaceFailure('google_record_assignment_unavailable')
    workspace.write_booking_row(assigned['spreadsheet_id'],assigned['intent'],assigned['row'],assigned['values'])
    return assigned['spreadsheet_id']
