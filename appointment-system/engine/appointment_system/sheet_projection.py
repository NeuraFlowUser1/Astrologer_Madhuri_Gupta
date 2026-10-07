"""Latest-record rows, separately mapped from immutable delivery history.

The database owns addresses, version claims and previously attempted digests.
Remote writes are not atomic with that database: settled rows remain scheduled
for later readback so a delayed old request cannot stay silently authoritative.
"""
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .google_access import refresh_connection
from .google_oauth import GoogleFailure
from .google_workspace import Workspace, WorkspaceFailure, SHEETS, column_name, resource_id
from .receipt_view import timestamp
from .serialization import fingerprint

BOOKING_HEADERS = ['Reference', 'Status', 'Created at (UTC)', 'Name', 'Email', 'Phone',
    'Service', 'Questions', 'Amount', 'Currency', 'Date', 'Time', 'Timezone',
    'Birth date', 'Birth time', 'Birth place', 'Notes', 'Meeting link',
    'Payment reference', 'Cancelled at (UTC)', 'Revision']
ENQUIRY_HEADERS = ['Reference', 'Received at (UTC)', 'Source', 'Kind', 'Name', 'Email',
    'Phone', 'Birth date', 'Location', 'Subject', 'Message', 'Service interest', 'Status', 'Revision']


def definition(kind, layout):
    if kind == 'booking':
        return 'Appointments', 4010, BOOKING_HEADERS
    if kind == 'enquiry':
        return ('Enquiries' if layout == 4 else 'Enquiry current'), 4011, ENQUIRY_HEADERS
    raise WorkspaceFailure('google_record_job_invalid')


def values_for(job):
    try:
        data = job['snapshot']
        if job['record_kind'] == 'booking':
            local = timestamp(data['starts_at']).astimezone(ZoneInfo(data['practice_timezone']))
            preparation = data.get('preparation') or {}
            values = [data['request_id'], data['state'], data['created_at'], data['full_name'],
                '' if data['email'] is None else data['email'], data['phone'], data['service_snapshot']['name'], str(data['questions']),
                str(Decimal(data['amount_paise']) / 100), data['currency'], local.date().isoformat(),
                local.strftime('%H:%M'), data['practice_timezone'], preparation.get('birth_date') or '',
                preparation.get('birth_time') or '', preparation.get('birth_place') or '',
                preparation.get('notes') or '', data.get('meet_url') or '',
                data.get('payment_reference') or '', data.get('cancelled_at') or '', str(data['revision'])]
        elif job['record_kind'] == 'enquiry':
            payload = data['payload']
            values = [data['request_id'], data['verified_at'], payload.get('source', 'unknown'),
                payload.get('kind', 'contact'), payload['name'], payload['email'], payload['phone'],
                payload.get('dob', ''), payload.get('location', ''), payload['subject'], payload['message'],
                payload.get('service_interest') or '', 'received', str(job['sequence'])]
        else:
            raise ValueError()
        if any(type(value) is not str or len(value) > 4000 for value in values):
            raise ValueError()
        return values
    except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
        raise WorkspaceFailure('google_row_invalid') from None


def normalized(rows, length):
    if rows == []:
        return None
    if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not list
            or len(rows[0]) > length or any(type(v) is not str for v in rows[0])):
        raise WorkspaceFailure('google_row_conflict')
    return rows[0] + [''] * (length - len(rows[0]))


def prepare_tab(workspace, job):
    from .sheet_layout import prepare_named_tab
    title, sheet_id, headers = definition(job['record_kind'], job['layout_version'])
    return prepare_named_tab(workspace, job['spreadsheet_id'], job['intent'], title, sheet_id, headers)


def synchronize(store, services, job, *, transport=None):
    access = refresh_connection(store, services, job['role'], grant_id=job['grant_id'])
    if (job['subject'] != access.grant.subject
            or job['client_id'] != (access.client_id or services.google.settings.client_id)):
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    workspace = Workspace(access, transport=transport)
    workspace.bind_volume(job)
    if type(job['row_number']) is not int or not 2 <= job['row_number'] < 9000:
        raise WorkspaceFailure('google_row_invalid')
    values = values_for(job)
    digest = fingerprint(values)
    title = prepare_tab(workspace, job)
    url = SHEETS + resource_id(job['spreadsheet_id']) + '/values/' + quote(
        f"'{title}'!A{job['row_number']}:{column_name(len(values))}{job['row_number']}", safe='')
    _, result = workspace.request('GET', url, params={'valueRenderOption': 'UNFORMATTED_VALUE'})
    observed = normalized(result.get('values', []), len(values))
    # Commit the attempted digest before IO. The SQL operation also checks the
    # latest sequence, exact lease, restore generation and release. Unknown
    # occupied rows cannot be overwritten by treating a new reference as ours.
    approved = store.approve_sheet_projection(job, values, digest,
        fingerprint(observed) if observed is not None else None)
    if approved != 'ok':
        raise WorkspaceFailure('google_row_conflict' if approved == 'conflict' else 'google_sheet_revision_changed')
    if observed != values:
        workspace.request('PUT', url, params={'valueInputOption': 'RAW'}, body={'values': [values]})
    _, result = workspace.request('GET', url, params={'valueRenderOption': 'UNFORMATTED_VALUE'})
    if normalized(result.get('values', []), len(values)) != values:
        raise WorkspaceFailure('google_sheet_readback_unresolved', uncertain=True)
    return digest


ATTENTION = frozenset({'google_row_conflict', 'google_row_invalid', 'google_workbook_owner_mismatch',
    'google_workbook_identity_invalid', 'google_workbook_layout_changed', 'google_workbook_sharing_mismatch'})


def run_projection_once(store, services, kind, resource, *, transport=None):
    """None means history should take this fair turn; a dict means work taken."""
    if resource not in ('client_sheet', 'agency_sheet'):
        return None
    job = store.claim_sheet_projection(kind, resource.removesuffix('_sheet'))
    if job is None:
        return None
    digest, error = None, None
    try:
        digest = synchronize(store, services, job, transport=transport)
    except (GoogleFailure, WorkspaceFailure) as failure:
        error = str(failure)
    saved = store.finish_sheet_projection(job, digest, error, error in ATTENTION)
    return {'processed': int(saved), 'retry': not saved, 'attention': error in ATTENTION}
