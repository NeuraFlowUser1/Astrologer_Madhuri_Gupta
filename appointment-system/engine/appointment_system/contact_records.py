"""Enquiry records in separate owner-verified tabs; never impersonate bookings."""
from urllib.parse import quote
from uuid import UUID
from .google_records import workspace_for_record
from .google_workspace import WorkspaceFailure,PROJECT,DRIVE,SHEETS,FILE_FIELDS,resource_id,column_name,row_matches
from .receipt_view import timestamp
from .serialization import fingerprint

TAB='Enquiries'
TAB_ID=4005
HEADERS=['Project','Record ID','Enquiry ID','Verified at (UTC)','Name','Email','Mobile','Subject','Message','Status']
CONTEXT_HEADERS=HEADERS+['Source','Service interest']
FULL_HEADERS=CONTEXT_HEADERS+['Kind','Birth date','Location']
HISTORY_HEADERS=FULL_HEADERS+['Revision','Payload hash']


def enquiry_values(job,layout_version=1,*,project=PROJECT):
    try:
        data=job['payload']
        values=[project,str(UUID(str(job['id']))),str(UUID(str(job['request_id']))),
                timestamp(job['verified_at']).isoformat(),data['name'],data['email'],data['phone'],
                data['subject'],data['message'],'received']
        if layout_version in (2,3,4):values += [data.get('source','unknown'),data.get('service_interest') or '']
        elif layout_version!=1:raise ValueError()
        if layout_version in (3,4):values += [data.get('kind','contact'),data.get('dob',''),data.get('location','')]
        if layout_version==4:
            values.append('1');values.append(fingerprint(values))
        return values
    except (ValueError,TypeError,KeyError,AttributeError):
        raise WorkspaceFailure('google_row_invalid') from None


def verify_owner(workspace,identifier,intent):
    resource_id(identifier)
    _,file=workspace.request('GET',DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
    if workspace.validate_workbook(file,intent)!=identifier:
        raise WorkspaceFailure('google_workbook_owner_mismatch')


def prepare_enquiry_tab(workspace,identifier,intent,layout_version=1):
    if layout_version==4:
        from .sheet_layout import prepare_named_tab
        return prepare_named_tab(workspace,identifier,intent,'Enquiry history',TAB_ID,HISTORY_HEADERS)
    headers={1:HEADERS,2:CONTEXT_HEADERS,3:FULL_HEADERS}.get(layout_version)
    if headers is None:raise WorkspaceFailure('google_workbook_layout_changed')
    column=column_name(len(headers))
    verify_owner(workspace,identifier,intent)
    _,data=workspace.request('GET',SHEETS+identifier,params={'fields':'sheets(properties)'})
    try:
        tabs=[s['properties'] for s in data['sheets']]
        matching=[t for t in tabs if t.get('sheetId')==TAB_ID or t.get('title')==TAB]
        if not matching:
            workspace.request('POST',SHEETS+identifier+':batchUpdate',body={'requests':[{'addSheet':{'properties':{
                'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':len(headers),'frozenRowCount':1}}}}]})
        elif (len(matching)!=1 or matching[0].get('sheetId')!=TAB_ID or matching[0].get('title')!=TAB
              or matching[0].get('gridProperties',{}).get('rowCount',0)<10000
              or matching[0].get('gridProperties',{}).get('columnCount',0)<len(headers)):
            raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):
        raise WorkspaceFailure('google_workbook_layout_changed') from None
    url=SHEETS+identifier+'/values/'+quote(f"'Enquiries'!A1:{column}1",safe='')
    _,existing=workspace.request('GET',url)
    if existing.get('values',[]) not in ([],[headers]):
        raise WorkspaceFailure('google_workbook_layout_changed')
    if not existing.get('values'):
        workspace.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[headers]})


def write_enquiry_row(workspace,assigned):
    try:
        identifier=resource_id(assigned['spreadsheet_id']);row=assigned['row'];values=assigned['values']
        layout=workspace.volume['layout_version'] if workspace.volume else 1
        expected={1:10,2:12,3:15,4:17}.get(layout)
        if (type(row) is not int or not 2<=row<=10000 or not isinstance(values,list) or len(values)!=expected
            or values[0]!=workspace.workbook_project() or any(not isinstance(v,str) or len(v)>4000 for v in values)):
            raise ValueError()
        UUID(values[1]);UUID(values[2])
    except (KeyError,ValueError,TypeError):
        raise WorkspaceFailure('google_row_invalid') from None
    verify_owner(workspace,identifier,assigned['intent'])
    column=column_name(len(values))
    title='Enquiry history' if layout==4 else TAB
    url=SHEETS+identifier+'/values/'+quote(f"'{title}'!A{row}:{column}{row}",safe='')
    _,existing=workspace.request('GET',url)
    if not row_matches(existing.get('values',[]),values):
        workspace.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[values]})
        _,observed=workspace.request('GET',url)
        if not row_matches(observed.get('values',[]),values):
            raise WorkspaceFailure('google_sheet_readback_unresolved',uncertain=True)


def copy_enquiry_record(store,services,job,*,transport=None):
    roles={'client_sheet':'client','agency_sheet':'agency'}
    if job.get('kind') not in roles:raise WorkspaceFailure('google_record_job_invalid')
    role=roles[job['kind']]
    workspace,saved=workspace_for_record(store,services,role,job['id'],'enquiry',transport=transport)
    values=saved.get('values')
    if values is None:values=enquiry_values(job,saved.get('layout_version',1),project=workspace.workbook_project())
    assigned=store.assign_enquiry_row(role,job,values)
    if not assigned or assigned['spreadsheet_id']!=saved['spreadsheet_id'] or assigned['intent']!=saved['intent']:
        raise WorkspaceFailure('google_record_assignment_unavailable')
    prepare_enquiry_tab(workspace,assigned['spreadsheet_id'],assigned['intent'],saved.get('layout_version',1))
    write_enquiry_row(workspace,assigned)
    return assigned['spreadsheet_id']
