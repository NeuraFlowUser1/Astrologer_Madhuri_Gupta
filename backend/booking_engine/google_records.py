"""Durable workbook provisioning and immutable per-revision booking snapshots."""

from decimal import Decimal
from uuid import UUID

from .google_access import refresh_connection
from .google_workspace import PROJECT, Workspace, WorkspaceFailure
from .receipt_view import timestamp


def prepare_owner_workbook(store, services, role, *, transport=None):
    access = refresh_connection(store, services, role)
    workspace = Workspace(access, transport=transport)
    saved = store.claim_google_workbook(role, services.google.settings.client_id)
    if not saved:
        raise WorkspaceFailure('google_workbook_unavailable')
    if saved['subject'] != access.grant.subject:
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    if saved['action']=='ready':
        return workspace, saved
    if saved['action']=='create':
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


def sheet_values(job):
    booking = job['payload']
    return [PROJECT,str(UUID(job['id'])),str(UUID(booking['id'])),str(booking['revision']),
        booking['state'],booking['service_snapshot']['name'],
        timestamp(booking['starts_at']).isoformat(),timestamp(booking['ends_at']).isoformat(),
        booking['full_name'],booking['email'],booking['phone'],str(Decimal(booking['amount_paise'])/100)]


def copy_booking_record(store, services, job, *, transport=None):
    roles = {'client_sheet':'client','agency_sheet':'agency'}
    if job['kind']!='sheet_booking' or job['recipient_role'] not in roles:
        raise WorkspaceFailure('google_record_job_invalid')
    role = roles[job['recipient_role']]
    workspace, saved = prepare_owner_workbook(store, services, role, transport=transport)
    assigned = store.assign_sheet_row(role, UUID(job['id']), sheet_values(job))
    if not assigned or assigned['spreadsheet_id']!=saved['spreadsheet_id']:
        raise WorkspaceFailure('google_record_assignment_unavailable')
    workspace.write_booking_row(assigned['spreadsheet_id'],assigned['intent'],assigned['row'],assigned['values'])
    return assigned['spreadsheet_id']
