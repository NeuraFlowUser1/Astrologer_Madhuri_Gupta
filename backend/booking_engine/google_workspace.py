"""Bounded Calendar/Drive/Sheets operations for Sarsa's two verified owners.

Durable callers own job leases, immutable payloads and creation intent. Nothing
here sends mail, shares a file, appends an untracked row or retries a POST.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from .google_oauth import Access, OWNERS
from .receipt_view import timestamp

PROJECT = '004-sarsa-jyotish-sansthan'
DRIVE = 'https://www.googleapis.com/drive/v3/files'
SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets/'
CALENDAR = 'https://www.googleapis.com/calendar/v3/calendars/' + quote(OWNERS['client'], safe='') + '/events'
FILE_FIELDS = 'id,mimeType,trashed,owners(emailAddress),appProperties'
TAB = 'Booking history'
TAB_ID = 4004
HEADERS = ['Project', 'Record ID', 'Booking ID', 'Revision', 'Status', 'Service',
           'Starts at (UTC)', 'Ends at (UTC)', 'Name', 'Email', 'Mobile', 'Amount (INR)']


class WorkspaceFailure(Exception):
    def __init__(self, code, *, uncertain=False):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


def resource_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise WorkspaceFailure('google_resource_invalid')
    return value


def event_id(booking_id, revision):
    if type(revision) is not int or revision < 1:
        raise WorkspaceFailure('google_revision_invalid')
    identity = f'{PROJECT}:{UUID(str(booking_id))}:{revision}'.encode()
    return 'sarsa' + hashlib.sha256(identity).hexdigest()


class Workspace:
    def __init__(self, access, *, transport=None):
        if (not isinstance(access, Access) or access.grant.email != OWNERS.get(access.grant.role)
                or access.expires_at <= datetime.now(timezone.utc)):
            raise WorkspaceFailure('google_access_unavailable')
        self.access, self.transport = access, transport

    def request(self, method, url, *, params=None, body=None, statuses=(200,), headers=None):
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc not in ('www.googleapis.com', 'sheets.googleapis.com')
                or not (url.startswith(DRIVE) or url.startswith(SHEETS) or url.startswith(CALENDAR))
                or parsed.query or parsed.fragment or method not in ('GET', 'POST', 'PUT', 'DELETE')):
            raise WorkspaceFailure('google_endpoint_invalid')
        if self.access.expires_at <= datetime.now(timezone.utc):
            raise WorkspaceFailure('google_access_unavailable')
        request_headers = dict(headers or {}, Authorization='Bearer '+self.access.token, Accept='application/json')
        try:
            with httpx.Client(transport=self.transport, timeout=8, trust_env=False, follow_redirects=False) as client:
                with client.stream(method, url, params=params, json=body, headers=request_headers) as response:
                    if response.status_code not in statuses:
                        raise WorkspaceFailure('google_service_unavailable', uncertain=method!='GET')
                    if response.status_code in (204, 404, 409, 410):
                        return response.status_code, None
                    if response.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                        raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data)>262144:
                            raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    return response.status_code, result
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise WorkspaceFailure('google_service_unavailable', uncertain=method!='GET') from None

    def _client(self):
        if self.access.grant.role != 'client':
            raise WorkspaceFailure('google_account_mismatch')

    def calendar_body(self, booking):
        self._client()
        identifier = event_id(booking['id'], booking['revision'])
        return dict(id=identifier, summary='Sarsa consultation · '+booking['service_snapshot']['name'],
            description='Sarsa booking '+str(booking['id']),
            start={'dateTime': timestamp(booking['starts_at']).isoformat(), 'timeZone':'Asia/Kolkata'},
            end={'dateTime': timestamp(booking['ends_at']).isoformat(), 'timeZone':'Asia/Kolkata'},
            visibility='private', reminders={'useDefault':False},
            extendedProperties={'private':{'project':PROJECT,'booking':str(booking['id']), 'revision':str(booking['revision'])}},
            conferenceData={'createRequest':{'requestId':identifier,'conferenceSolutionKey':{'type':'hangoutsMeet'}}})

    def _validate_event(self, event, booking):
        expected = self.calendar_body(booking)
        try:
            if (event['id'] != expected['id'] or event.get('status') == 'cancelled'
                    or event['extendedProperties']['private'] != expected['extendedProperties']['private']
                    or event['organizer']['email'].lower() != OWNERS['client']
                    or timestamp(event['start']['dateTime']) != timestamp(booking['starts_at'])
                    or timestamp(event['end']['dateTime']) != timestamp(booking['ends_at'])):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise WorkspaceFailure('google_event_mismatch') from None

    def ensure_meeting(self, booking):
        if timestamp(booking['ends_at']) <= datetime.now(timezone.utc):
            raise WorkspaceFailure('google_appointment_ended')
        body = self.calendar_body(booking)
        url = CALENDAR+'/'+body['id']
        status, event = self.request('GET', url, statuses=(200,404))
        if status == 404:
            status, event = self.request('POST', CALENDAR, body=body,
                params={'conferenceDataVersion':1,'sendUpdates':'none'}, statuses=(200,201,409))
            if status == 409:
                _, event = self.request('GET', url)
        self._validate_event(event, booking)
        try:
            conference = event.get('conferenceData', {})
            state = conference.get('createRequest', {}).get('status', {}).get('statusCode')
            if state == 'pending':
                return {'state':'waiting','event_id':body['id'],'meet_url':None}
            if state != 'success' or conference.get('conferenceSolution', {}).get('key', {}).get('type') != 'hangoutsMeet':
                raise WorkspaceFailure('google_meeting_unavailable')
            videos = [p.get('uri') for p in conference.get('entryPoints', []) if p.get('entryPointType')=='video']
            if len(videos)!=1 or not isinstance(videos[0],str) or not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}', videos[0]):
                raise WorkspaceFailure('google_meeting_invalid')
        except (AttributeError, TypeError):
            raise WorkspaceFailure('google_meeting_invalid') from None
        return {'state':'ready','event_id':body['id'],'meet_url':videos[0]}

    def cancel_meeting(self, booking):
        self._client()
        url = CALENDAR+'/'+event_id(booking['id'], booking['revision'])
        status, event = self.request('GET', url, statuses=(200,404,410))
        if status in (404,410) or event.get('status')=='cancelled':
            return
        self._validate_event(event, booking)
        if not isinstance(event.get('etag'),str):
            raise WorkspaceFailure('google_event_mismatch')
        self.request('DELETE', url, params={'sendUpdates':'none'}, headers={'If-Match':event['etag']}, statuses=(204,404,410))

    def validate_workbook(self, file, intent):
        role = self.access.grant.role
        try:
            identifier = resource_id(file['id'])
            if (file.get('trashed') is not False or file['mimeType'] != 'application/vnd.google-apps.spreadsheet'
                    or [o['emailAddress'].lower() for o in file['owners']] != [OWNERS[role]]
                    or file['appProperties'] != {'project':PROJECT,'role':role,'intent':str(UUID(str(intent)))}):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise WorkspaceFailure('google_workbook_owner_mismatch') from None
        return identifier

    def find_workbook(self, intent):
        intent = str(UUID(str(intent)))
        _, data = self.request('GET', DRIVE, params={'q':"trashed=false and appProperties has { key='intent' and value='"+intent+"' }",
            'spaces':'drive','pageSize':2,'fields':'nextPageToken,files('+FILE_FIELDS+')'})
        files = data.get('files')
        if not isinstance(files,list) or len(files)>1 or data.get('nextPageToken'):
            raise WorkspaceFailure('google_workbook_ambiguous')
        return self.validate_workbook(files[0],intent) if files else None

    def create_workbook(self, intent):
        # Caller commits a once-only creation intent BEFORE invoking this. Sheets
        # creation has no reusable pre-generated Drive ID. Never retry blindly.
        intent = str(UUID(str(intent)))
        role = self.access.grant.role
        name = '004 · Sarsa Jyotish Sansthan · '+('Client records' if role=='client' else 'NeuraFlow records')
        _, file = self.request('POST', DRIVE, params={'fields':FILE_FIELDS}, statuses=(200,201), body={
            'name':name,'mimeType':'application/vnd.google-apps.spreadsheet',
            'appProperties':{'project':PROJECT,'role':role,'intent':intent}})
        return self.validate_workbook(file,intent)

    def prepare_workbook(self, identifier, intent):
        identifier = resource_id(identifier)
        _, file = self.request('GET', DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
        if self.validate_workbook(file,intent)!=identifier:
            raise WorkspaceFailure('google_workbook_owner_mismatch')
        _, data = self.request('GET', SHEETS+identifier,params={'fields':'sheets(properties)'})
        try:
            tabs = [s['properties'] for s in data.get('sheets', [])]
            if any(not isinstance(t, dict) for t in tabs):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise WorkspaceFailure('google_workbook_layout_changed') from None
        matching = [t for t in tabs if t.get('sheetId')==TAB_ID or t.get('title')==TAB]
        if not matching:
            self.request('POST', SHEETS+identifier+':batchUpdate',body={'requests':[{'addSheet':{'properties':{
                'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':12,'frozenRowCount':1}}}}]})
        elif len(matching)!=1 or matching[0].get('sheetId')!=TAB_ID or matching[0].get('title')!=TAB:
            raise WorkspaceFailure('google_workbook_layout_changed')
        elif (matching[0].get('gridProperties', {}).get('rowCount', 0)<10000
              or matching[0].get('gridProperties', {}).get('columnCount', 0)<12):
            raise WorkspaceFailure('google_workbook_layout_changed')
        self.request('PUT', SHEETS+identifier+'/values/'+quote("'"+TAB+"'!A1:L1",safe=''),
            params={'valueInputOption':'RAW'},body={'values':[HEADERS]})

    def write_booking_row(self, identifier, intent, row, values):
        identifier = resource_id(identifier)
        if (type(row) is not int or not 2<=row<=10000 or not isinstance(values,list)
                or len(values)!=12 or values[0]!=PROJECT or any(not isinstance(v,str) or len(v)>500 for v in values)):
            raise WorkspaceFailure('google_row_invalid')
        try:
            UUID(values[1]); UUID(values[2])
        except ValueError:
            raise WorkspaceFailure('google_row_invalid') from None
        _, file = self.request('GET', DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
        if self.validate_workbook(file,intent)!=identifier:
            raise WorkspaceFailure('google_workbook_owner_mismatch')
        url = SHEETS+identifier+'/values/'+quote("'"+TAB+f"'!A{row}:L{row}",safe='')
        _, existing = self.request('GET',url)
        rows = existing.get('values',[])
        if rows and rows != [values]:
            raise WorkspaceFailure('google_row_conflict')
        if not rows:
            self.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[values]})
