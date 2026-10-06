"""Explicit tabs for new workbooks; retained layouts keep their exact names."""
from urllib.parse import quote
from .google_workspace import (DRIVE, FILE_FIELDS, SHEETS, WorkspaceFailure,
    resource_id, row_matches, column_name)


def adequate_grid(tab,columns):
    grid=tab.get('gridProperties')
    return (type(grid) is dict and type(grid.get('rowCount')) is int
            and type(grid.get('columnCount')) is int
            and grid['rowCount']>=10000 and grid['columnCount']>=columns)


def prepare_named_tab(workspace, identifier, intent, title, tab_id, headers):
    identifier=resource_id(identifier)
    _,file=workspace.request('GET',DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
    if workspace.validate_workbook(file,intent)!=identifier:
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    _,data=workspace.request('GET',SHEETS+identifier,params={'fields':'sheets(properties)'})
    try:
        tabs=[s['properties'] for s in data['sheets']]
        matching=[t for t in tabs if t.get('sheetId')==tab_id or t.get('title')==title]
        if not matching:
            workspace.request('POST',SHEETS+identifier+':batchUpdate',body={'requests':[{'addSheet':{'properties':{
                'sheetId':tab_id,'title':title,'gridProperties':{'rowCount':10000,'columnCount':len(headers),'frozenRowCount':1}}}}]})
        elif (len(matching)!=1 or matching[0].get('sheetId')!=tab_id or matching[0].get('title')!=title
              or not adequate_grid(matching[0],len(headers))):
            raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):
        raise WorkspaceFailure('google_workbook_layout_changed') from None
    url=SHEETS+identifier+'/values/'+quote(f"'{title}'!A1:{column_name(len(headers))}1",safe='')
    _,existing=workspace.request('GET',url)
    if not row_matches(existing.get('values',[]),headers):
        workspace.request('PUT',url,params={'valueInputOption':'RAW'},body={'values':[headers]})
        _,observed=workspace.request('GET',url)
        if not row_matches(observed.get('values',[]),headers):
            raise WorkspaceFailure('google_sheet_readback_unresolved',uncertain=True)
    return title


def prepare_standard_workbook(workspace, identifier, intent):
    from .sheet_projection import BOOKING_HEADERS,ENQUIRY_HEADERS
    from .google_workspace import HISTORY_HEADERS as BOOKING_HISTORY
    from .contact_records import HISTORY_HEADERS as ENQUIRY_HISTORY
    definitions=[('Appointments',4010,BOOKING_HEADERS),('Enquiries',4011,ENQUIRY_HEADERS),
        ('Appointment history',4004,BOOKING_HISTORY),('Enquiry history',4005,ENQUIRY_HISTORY)]
    identifier=resource_id(identifier)
    _,file=workspace.request('GET',DRIVE+'/'+identifier,params={'fields':FILE_FIELDS})
    if workspace.validate_workbook(file,intent)!=identifier:
        raise WorkspaceFailure('google_workbook_owner_mismatch')
    _,data=workspace.request('GET',SHEETS+identifier,params={'fields':'sheets(properties)'})
    missing=[]
    try:
        tabs=[s['properties'] for s in data['sheets']]
        for title,tab,headers in definitions:
            matches=[t for t in tabs if t.get('sheetId')==tab or t.get('title')==title]
            if not matches:
                missing.append({'addSheet':{'properties':{'sheetId':tab,'title':title,
                    'gridProperties':{'rowCount':10000,'columnCount':len(headers),'frozenRowCount':1}}}})
            elif (len(matches)!=1 or matches[0].get('sheetId')!=tab or matches[0].get('title')!=title
                or not adequate_grid(matches[0],len(headers))):
                raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):
        raise WorkspaceFailure('google_workbook_layout_changed') from None
    if missing:
        workspace.request('POST',SHEETS+identifier+':batchUpdate',body={'requests':missing})
    ranges=[f"'{title}'!A1:{column_name(len(headers))}1" for title,_,headers in definitions]
    def read_headers():
        _,result=workspace.request('GET',SHEETS+identifier+'/values:batchGet',params={'ranges':ranges})
        try:
            rows=result['valueRanges']
            if len(rows)!=len(definitions):raise ValueError()
            for row,address,(_,_,headers) in zip(rows,ranges,definitions):
                if row.get('range') not in (address,address.replace("'",'')):raise ValueError()
                row_matches(row.get('values',[]),headers)
        except (KeyError,ValueError,TypeError,AttributeError,WorkspaceFailure):
            raise WorkspaceFailure('google_workbook_layout_changed') from None
        return rows
    rows=read_headers()
    writes=[{'range':address,'values':[headers]} for row,address,(_,_,headers) in zip(rows,ranges,definitions)
            if not row.get('values')]
    if writes:
        workspace.request('POST',SHEETS+identifier+'/values:batchUpdate',body={'valueInputOption':'RAW','data':writes})
        if any(not row.get('values') for row in read_headers()):
            raise WorkspaceFailure('google_sheet_readback_unresolved',uncertain=True)
