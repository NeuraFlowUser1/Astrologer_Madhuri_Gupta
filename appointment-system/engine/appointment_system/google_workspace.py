"""Bounded Calendar/Drive/Sheets operations for Practice's two verified owners.

Durable callers own job leases, immutable payloads and creation intent. Nothing
here sends mail, shares a file, appends an untracked row or retries a POST.
"""
from .configuration import owners,sender,project_id,label,worker_origin,origin,installation
from .request_budget import observe_provider

from .request_budget import BudgetExpired,provider_timeout,chunks,remaining

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from .google_oauth import Access, OWNERS, _json_object
from .receipt_view import timestamp
from .google_sharing import approvals,check_permissions
from .serialization import MAX_DEPTH

PROJECT = project_id()
DRIVE = 'https://www.googleapis.com/drive/v3/files'
DRIVE_ABOUT = 'https://www.googleapis.com/drive/v3/about'
SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets/'
CALENDAR = 'https://www.googleapis.com/calendar/v3/calendars/' + quote(OWNERS['client'], safe='') + '/events'
FILE_FIELDS = 'id,mimeType,trashed,owners(emailAddress),appProperties,permissions(type,role,emailAddress,deleted,pendingOwner)'
TAB = 'Booking history'
TAB_ID = 4004
HEADERS = ['Project', 'Record ID', 'Booking ID', 'Revision', 'Status', 'Service',
           'Starts at (UTC)', 'Ends at (UTC)', 'Name', 'Email', 'Mobile', 'Amount (INR)']
FULL_HEADERS=HEADERS+['Currency','Questions','Birth date','Birth time','Birth place','Preparation notes',
 'Request ID','Payment account','Payment mode','Payment credential version','Order reference','Payment reference',
 'Meeting link','Original appointment start (UTC)','Created at (UTC)','Cancelled at (UTC)','Timezone',
 'Service ID','Quote version','Verification policy','Source']
HISTORY_HEADERS = FULL_HEADERS[:11] + ['Amount'] + FULL_HEADERS[12:] + ['Local date', 'Local time', 'Payload hash']

def response_document(data):
    result=json.loads(data,object_pairs_hook=_json_object)
    pending=[(result,0)]
    while pending:
        value,depth=pending.pop()
        if depth>MAX_DEPTH:raise ValueError('Google response nesting is invalid')
        if isinstance(value,dict):pending.extend((item,depth+1) for item in value.values())
        elif isinstance(value,list):pending.extend((item,depth+1) for item in value)
    return result

def row_matches(rows, values):
    """Sheets omits trailing empty cells; never ignore populated differences."""
    if rows == []:
        return False
    if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],list)
            or len(rows[0])>len(values) or any(not isinstance(v,str) for v in rows[0])):
        raise WorkspaceFailure('google_row_conflict')
    if rows[0]+['']*(len(values)-len(rows[0]))!=values:
        raise WorkspaceFailure('google_row_conflict')
    return True

def column_name(number):
    if type(number) is not int or not 1<=number<=64:raise WorkspaceFailure('google_column_invalid')
    result=''
    while number: number,remainder=divmod(number-1,26);result=chr(65+remainder)+result
    return result


class WorkspaceFailure(Exception):
    def __init__(self, code, *, uncertain=False):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


def resource_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise WorkspaceFailure('google_resource_invalid')
    return value


def event_id(booking_id, revision,protocol='v1'):
    if type(revision) is not int or revision < 1:
        raise WorkspaceFailure('google_revision_invalid')
    booking=UUID(str(booking_id))
    if protocol=='v1':return 'ab'+hashlib.sha256(f"{installation()['installation_id']}:{booking}:{revision}".encode()).hexdigest()
    if protocol=='legacy-sarsa004':
        # The historical event identifier is an external protocol, not a new
        # project setting. Changing its literal would create a second event.
        return 'sarsa'+hashlib.sha256(f'004-sarsa-jyotish-sansthan:{booking}:{revision}'.encode()).hexdigest()
    if protocol in ('legacy-astro003','legacy-astro003-unversioned'):
        return 'astro'+booking.hex+('' if revision==1 else 'r'+format(revision,'x'))
    raise WorkspaceFailure('google_calendar_protocol_invalid')


class Workspace:
    def __init__(self, access, *, transport=None):
        if (not isinstance(access, Access) or access.grant.email != OWNERS.get(access.grant.role)
                or access.expires_at <= datetime.now(timezone.utc)):
            raise WorkspaceFailure('google_access_unavailable')
        self.access, self.transport = access, transport
        self.volume = None

    @observe_provider('google')
    def request(self, method, url, *, params=None, body=None, statuses=(200,), headers=None):
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc not in ('www.googleapis.com', 'sheets.googleapis.com')
                or not (url.startswith(DRIVE) or url.startswith(SHEETS) or url.startswith(CALENDAR) or (url==DRIVE_ABOUT and method=='GET'))
                or parsed.query or parsed.fragment or method not in ('GET', 'POST', 'PUT', 'DELETE')):
            raise WorkspaceFailure('google_endpoint_invalid')
        if self.access.expires_at <= datetime.now(timezone.utc):
            raise WorkspaceFailure('google_access_unavailable')
        request_headers = dict(headers or {}, Authorization='Bearer '+self.access.token, Accept='application/json')
        try:
            with httpx.Client(transport=self.transport, timeout=provider_timeout(8), trust_env=False, follow_redirects=False) as client:
                with client.stream(method, url, params=params, json=body, headers=request_headers) as response:
                    if response.status_code not in statuses:
                        raise WorkspaceFailure('google_service_unavailable', uncertain=method!='GET')
                    if response.status_code in (204, 404, 409, 410):
                        return response.status_code, None
                    if response.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                        raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    data = bytearray()
                    for chunk in chunks(response):
                        data.extend(chunk)
                        if len(data)>262144:
                            raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    result = response_document(data)
                    if not isinstance(result, dict):
                        raise WorkspaceFailure('google_response_invalid', uncertain=method!='GET')
                    return response.status_code, result
        except (BudgetExpired,httpx.HTTPError, ValueError, UnicodeError,RecursionError):
            raise WorkspaceFailure('google_service_unavailable', uncertain=method!='GET') from None

    def _client(self):
        if self.access.grant.role != 'client':
            raise WorkspaceFailure('google_account_mismatch')

    def calendar_body(self, booking):
        self._client()
        protocol=booking.get('calendar_protocol','v1')
        identifier = event_id(booking['id'], booking['revision'],protocol)
        email=booking.get('email')
        if not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            raise WorkspaceFailure('google_customer_invalid')
        private={'installation':installation()['installation_id'],'project':PROJECT,'booking':str(booking['id']),'revision':str(booking['revision'])}
        conference=identifier
        if protocol=='legacy-sarsa004':
            private={'project':'004-sarsa-jyotish-sansthan','booking':str(booking['id']),'revision':str(booking['revision'])}
        elif protocol in ('legacy-astro003','legacy-astro003-unversioned'):
            private={'astroBookingId':str(UUID(str(booking['id'])))}
            if protocol=='legacy-astro003':private.update(project='003',revision=str(booking['revision']))
            conference='meet'+UUID(str(booking['id'])).hex+('' if booking['revision']==1 else 'r'+format(booking['revision'],'x'))
        return dict(id=identifier, summary=label()+' consultation · '+booking['service_snapshot']['name'],
            description=label()+' booking '+str(booking['id'])+'\nPersonal consultation details remain in the practice’s private record.',
            start={'dateTime': timestamp(booking['starts_at']).isoformat(), 'timeZone':booking['practice_timezone']},
            end={'dateTime': timestamp(booking['ends_at']).isoformat(), 'timeZone':booking['practice_timezone']},
            visibility='private', reminders={'useDefault':False},
            attendees=[] if email.lower()==OWNERS['client'] else [{'email':email}],
            guestsCanInviteOthers=False,guestsCanModify=False,guestsCanSeeOtherGuests=False,
            extendedProperties={'private':private},
            conferenceData={'createRequest':{'requestId':conference,'conferenceSolutionKey':{'type':'hangoutsMeet'}}})

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
                params={'conferenceDataVersion':1,'sendUpdates':'all'}, statuses=(200,201,409))
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
        url = CALENDAR+'/'+event_id(booking['id'], booking['revision'],booking.get('calendar_protocol','v1'))
        status, event = self.request('GET', url, statuses=(200,404,410))
        if status in (404,410) or event.get('status')=='cancelled':
            return
        self._validate_event(event, booking)
        if not isinstance(event.get('etag'),str):
            raise WorkspaceFailure('google_event_mismatch')
        self.request('DELETE', url, params={'sendUpdates':'all'}, headers={'If-Match':event['etag']}, statuses=(204,404,410))

    def bind_volume(self, saved):
        # Metadata comes only from the database registry, never from job input.
        try:
            if (saved['role'] != self.access.grant.role or type(saved['volume_number']) is not int
                    or saved['volume_number'] < 1 or type(saved['layout_version']) is not int
                    or saved['layout_version'] not in (1, 2,3,4)):
                raise ValueError()
            UUID(str(saved['generation'])); UUID(str(saved['intent']))
            approvals(saved.get('approved_permissions',[]),self.access.grant.email)
            protocol=saved.get('workbook_protocol','v1')
            if protocol not in ('v1','legacy-sarsa-workbook-v1','legacy-sarsa-workbook-v2'):
                raise ValueError()
            if protocol!='v1' and saved['layout_version']!=(1 if protocol.endswith('v1') else 2):
                raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise WorkspaceFailure('google_workbook_identity_invalid') from None
        self.volume = deepcopy(saved)

    def workbook_project(self):
        protocol=self.volume.get('workbook_protocol','v1') if self.volume else 'v1'
        return '004-sarsa-jyotish-sansthan' if protocol in ('legacy-sarsa-workbook-v1','legacy-sarsa-workbook-v2') else PROJECT

    def workbook_markers(self, intent):
        role = self.access.grant.role
        markers = {'project':self.workbook_project(),'role':role,'intent':str(UUID(str(intent)))}
        if self.volume is not None:
            if str(self.volume['intent']) != markers['intent']:
                raise WorkspaceFailure('google_workbook_identity_invalid')
            if self.volume['layout_version'] in (2,3,4):
                markers.update(generation=str(self.volume['generation']),volume=str(self.volume['volume_number']),layout=str(self.volume['layout_version']))
            if self.volume['layout_version'] in (3,4):
                markers['installation']=installation()['installation_id']
        return markers

    def validate_workbook(self, file, intent):
        role = self.access.grant.role
        try:
            identifier = resource_id(file['id'])
            if (file.get('trashed') is not False or file['mimeType'] != 'application/vnd.google-apps.spreadsheet'
                    or [o['emailAddress'].lower() for o in file['owners']] != [OWNERS[role]]
                    or file['appProperties'] != self.workbook_markers(intent)):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise WorkspaceFailure('google_workbook_owner_mismatch') from None
        try:
            check_permissions(file.get('permissions'),OWNERS[role],
                self.volume.get('approved_permissions',[]) if self.volume else [])
        except ValueError:
            raise WorkspaceFailure('google_workbook_sharing_mismatch') from None
        return identifier

    def find_workbook(self, intent):
        intent = str(UUID(str(intent)))
        _, data = self.request('GET', DRIVE, params={'q':"trashed=false and appProperties has { key='intent' and value='"+intent+"' }",
            'spaces':'drive','pageSize':2,'fields':'nextPageToken,files('+FILE_FIELDS+')'})
        files = data.get('files')
        if not isinstance(files,list) or len(files)>1 or data.get('nextPageToken'):
            raise WorkspaceFailure('google_workbook_ambiguous')
        return self.validate_workbook(files[0],intent) if files else None

    def check_capacity(self):
        _, result = self.request('GET',DRIVE_ABOUT,params={'fields':'storageQuota(limit,usage)'})
        quota = result.get('storageQuota')
        try:
            if not isinstance(quota,dict) or not str(quota['usage']).isdigit(): raise ValueError()
            usage = int(quota['usage']); limit = quota.get('limit')
            if limit is not None and (not str(limit).isdigit() or int(limit)-usage < 1048576): raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise WorkspaceFailure('google_drive_capacity_required') from None
        return {'used_bytes':usage,'limit_bytes':int(limit) if limit is not None else None}

    def create_workbook(self, intent):
        # Caller commits a once-only creation intent BEFORE invoking this. Sheets
        # creation has no reusable pre-generated Drive ID. Never retry blindly.
        intent = str(UUID(str(intent)))
        role = self.access.grant.role
        name = project_id()+' · '+label()+' · '+('Client records' if role=='client' else 'Agency records')
        if self.volume is not None and self.volume['volume_number'] > 1:
            name += ' · Volume '+str(self.volume['volume_number'])
        _, file = self.request('POST', DRIVE, params={'fields':FILE_FIELDS}, statuses=(200,201), body={
            'name':name,'mimeType':'application/vnd.google-apps.spreadsheet',
            'appProperties':self.workbook_markers(intent)})
        return self.validate_workbook(file,intent)

    def prepare_workbook(self, identifier, intent):
        if self.volume is not None and self.volume['layout_version']==4:
            from .sheet_layout import prepare_standard_workbook
            return prepare_standard_workbook(self, identifier, intent)
        headers=FULL_HEADERS if self.volume is not None and self.volume['layout_version']==3 else HEADERS
        columns=len(headers);last=column_name(columns)
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
                'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':columns,'frozenRowCount':1}}}}]})
        elif len(matching)!=1 or matching[0].get('sheetId')!=TAB_ID or matching[0].get('title')!=TAB:
            raise WorkspaceFailure('google_workbook_layout_changed')
        else:
            grid = matching[0].get('gridProperties')
            if (not isinstance(grid,dict) or type(grid.get('rowCount')) is not int
                    or type(grid.get('columnCount')) is not int
                    or grid['rowCount']<10000 or grid['columnCount']<columns):
                raise WorkspaceFailure('google_workbook_layout_changed')
        header_url = SHEETS+identifier+'/values/'+quote("'"+TAB+f"'!A1:{last}1",safe='')
        _, header = self.request('GET',header_url)
        if header.get('values',[]) not in ([],[headers]):
            raise WorkspaceFailure('google_workbook_layout_changed')
        if not header.get('values'):
            self.request('PUT',header_url,params={'valueInputOption':'RAW'},body={'values':[headers]})

    def write_booking_row(self, identifier, intent, row, values):
        identifier = resource_id(identifier)
        layout=self.volume['layout_version'] if self.volume else 1
        headers=HISTORY_HEADERS if layout==4 else FULL_HEADERS if layout==3 else HEADERS
        title='Appointment history' if layout==4 else TAB
        if (type(row) is not int or not 2<=row<=10000 or not isinstance(values,list)
                or len(values)!=len(headers)
                or values[0]!=self.workbook_project() or any(not isinstance(v,str) or len(v)>4000 for v in values)):
            raise WorkspaceFailure('google_row_invalid')
        try:
            UUID(values[1]); UUID(values[2])
        except ValueError:
            raise WorkspaceFailure('google_row_invalid') from None
        _, file = self.request('GET', DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
        if self.validate_workbook(file,intent)!=identifier:
            raise WorkspaceFailure('google_workbook_owner_mismatch')
        if layout==4:
            from .sheet_layout import prepare_named_tab
            prepare_named_tab(self,identifier,intent,title,TAB_ID,headers)
        url = SHEETS+identifier+'/values/'+quote("'"+title+f"'!A{row}:{column_name(len(values))}{row}",safe='')
        _, existing = self.request('GET',url)
        rows = existing.get('values',[])
        if not row_matches(rows,values):
            self.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[values]})
            _,observed=self.request('GET',url)
            if not row_matches(observed.get('values',[]),values):
                raise WorkspaceFailure('google_sheet_readback_unresolved',uncertain=True)
