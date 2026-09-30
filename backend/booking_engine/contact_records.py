"""Enquiry records in separate owner-verified tabs; never impersonate bookings."""
from urllib.parse import quote
from uuid import UUID
from .google_records import prepare_owner_workbook
from .google_workspace import WorkspaceFailure,PROJECT,DRIVE,SHEETS,FILE_FIELDS,resource_id
from .receipt_view import timestamp

TAB='Enquiries'
TAB_ID=4005
HEADERS=['Project','Record ID','Enquiry ID','Verified at (UTC)','Name','Email','Mobile','Subject','Message','Status']


def enquiry_values(job):
    try:
        data=job['payload']
        return [PROJECT,str(UUID(str(job['id']))),str(UUID(str(job['request_id']))),
                timestamp(job['verified_at']).isoformat(),data['name'],data['email'],data['phone'],
                data['subject'],data['message'],'received']
    except (ValueError,TypeError,KeyError,AttributeError):
        raise WorkspaceFailure('google_row_invalid') from None


def verify_owner(workspace,identifier,intent):
    resource_id(identifier)
    _,file=workspace.request('GET',DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
    if workspace.validate_workbook(file,intent)!=identifier:
        raise WorkspaceFailure('google_workbook_owner_mismatch')


def prepare_enquiry_tab(workspace,identifier,intent):
    verify_owner(workspace,identifier,intent)
    _,data=workspace.request('GET',SHEETS+identifier,params={'fields':'sheets(properties)'})
    try:
        tabs=[s['properties'] for s in data['sheets']]
        matching=[t for t in tabs if t.get('sheetId')==TAB_ID or t.get('title')==TAB]
        if not matching:
            workspace.request('POST',SHEETS+identifier+':batchUpdate',body={'requests':[{'addSheet':{'properties':{
                'sheetId':TAB_ID,'title':TAB,'gridProperties':{'rowCount':10000,'columnCount':10,'frozenRowCount':1}}}}]})
        elif (len(matching)!=1 or matching[0].get('sheetId')!=TAB_ID or matching[0].get('title')!=TAB
              or matching[0].get('gridProperties',{}).get('rowCount',0)<10000
              or matching[0].get('gridProperties',{}).get('columnCount',0)<10):
            raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):
        raise WorkspaceFailure('google_workbook_layout_changed') from None
    url=SHEETS+identifier+'/values/'+quote("'Enquiries'!A1:J1",safe='')
    _,existing=workspace.request('GET',url)
    if existing.get('values',[]) not in ([],[HEADERS]):
        raise WorkspaceFailure('google_workbook_layout_changed')
    if not existing.get('values'):
        workspace.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[HEADERS]})


def write_enquiry_row(workspace,assigned):
    try:
        identifier=resource_id(assigned['spreadsheet_id']);row=assigned['row'];values=assigned['values']
        if (type(row) is not int or not 2<=row<=10000 or not isinstance(values,list) or len(values)!=10
            or values[0]!=PROJECT or any(not isinstance(v,str) or len(v)>4000 for v in values)):
            raise ValueError()
        UUID(values[1]);UUID(values[2])
    except (KeyError,ValueError,TypeError):
        raise WorkspaceFailure('google_row_invalid') from None
    verify_owner(workspace,identifier,assigned['intent'])
    url=SHEETS+identifier+'/values/'+quote(f"'Enquiries'!A{row}:J{row}",safe='')
    _,existing=workspace.request('GET',url)
    if existing.get('values',[]) not in ([],[values]):
        raise WorkspaceFailure('google_row_conflict')
    if not existing.get('values'):
        workspace.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[values]})


def copy_enquiry_record(store,services,job,*,transport=None):
    roles={'client_sheet':'client','agency_sheet':'agency'}
    if job.get('kind') not in roles:raise WorkspaceFailure('google_record_job_invalid')
    role=roles[job['kind']]
    workspace,saved=prepare_owner_workbook(store,services,role,transport=transport)
    assigned=store.assign_enquiry_row(role,UUID(str(job['id'])),enquiry_values(job))
    if not assigned or assigned['spreadsheet_id']!=saved['spreadsheet_id'] or assigned['intent']!=saved['intent']:
        raise WorkspaceFailure('google_record_assignment_unavailable')
    prepare_enquiry_tab(workspace,assigned['spreadsheet_id'],assigned['intent'])
    write_enquiry_row(workspace,assigned)
    return assigned['spreadsheet_id']
