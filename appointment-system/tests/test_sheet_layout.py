"""Whole four-tab workbook preparation, exact history and lost-reply recovery."""
import copy
import json
import unittest
from urllib.parse import unquote
from uuid import uuid4

import httpx

from appointment_system.google_workspace import Workspace, WorkspaceFailure, HISTORY_HEADERS as BOOKING_HISTORY
from appointment_system.google_records import sheet_values
from appointment_system.contact_records import enquiry_values, HISTORY_HEADERS as ENQUIRY_HISTORY
from appointment_system.serialization import fingerprint
from appointment_system.sheet_layout import prepare_named_tab
from appointment_system.sheet_projection import BOOKING_HEADERS, ENQUIRY_HEADERS
from . import test_sheet_projection as projection_fixture


class FourTabWorkbook(unittest.TestCase):
    def setUp(self):
        fixture=projection_fixture.CurrentSheets();fixture.setUp()
        self.saved=fixture.job;self.saved['layout_version']=4
        self.file=fixture.file;self.file['appProperties']['layout']='4'
        self.access=fixture.access;self.requests=[];self.tabs=[];self.cells={}
        self.lose_add=False;self.lose_values=False
        self.expected={'Appointments':BOOKING_HEADERS,'Enquiries':ENQUIRY_HEADERS,
            'Appointment history':BOOKING_HISTORY,'Enquiry history':ENQUIRY_HISTORY}

    def handle(self,request):
        self.requests.append(request);path=unquote(request.url.path)
        if path.startswith('/drive/'):
            return httpx.Response(200,json=self.file)
        if path.endswith('/synthetic_sheet'):
            return httpx.Response(200,json={'sheets':[{'properties':p} for p in self.tabs]})
        if path.endswith('/synthetic_sheet:batchUpdate'):
            for change in json.loads(request.content)['requests']:
                value=change['addSheet']['properties']
                if any(p['sheetId']==value['sheetId'] for p in self.tabs):return httpx.Response(400,json={})
                self.tabs.append(value)
            if self.lose_add:
                self.lose_add=False;raise httpx.ReadTimeout('lost add result')
            return httpx.Response(200,json={})
        if path.endswith('/values:batchGet'):
            return httpx.Response(200,json={'valueRanges':[{'range':address,'values':self.cells.get(address,[])}
                for address in request.url.params.get_list('ranges')]})
        if path.endswith('/values:batchUpdate'):
            body=json.loads(request.content);self.assertEqual(body['valueInputOption'],'RAW')
            for part in body['data']:self.cells[part['range']]=part['values']
            if self.lose_values:
                self.lose_values=False;raise httpx.ReadTimeout('lost value result')
            return httpx.Response(200,json={})
        if '/values/' in path:
            address=path.split('/values/',1)[1]
            if request.method=='PUT':
                self.assertEqual(request.url.params['valueInputOption'],'RAW')
                self.cells[address]=json.loads(request.content)['values']
            return httpx.Response(200,json={'values':self.cells.get(address,[])})
        raise AssertionError('Unexpected synthetic request')

    def workspace(self):
        workspace=Workspace(self.access,transport=httpx.MockTransport(self.handle));workspace.bind_volume(self.saved)
        return workspace

    def prepare(self):self.workspace().prepare_workbook('synthetic_sheet',self.saved['intent'])

    def test_new_workbook_uses_four_tabs_and_batched_literal_headers_without_duplicate_creation(self):
        self.prepare();first=len(self.requests)
        self.assertEqual({tab['title'] for tab in self.tabs},set(self.expected))
        self.assertEqual(len(self.tabs),4)
        self.assertEqual(first,6)
        self.prepare()
        self.assertTrue(all(r.method=='GET' for r in self.requests[first:]))
        for address,values in self.cells.items():self.assertEqual(values,[self.expected[address.split('!')[0].strip("'")]])

    def test_lost_creation_and_header_replies_discover_the_same_tabs(self):
        for stage in ('lose_add','lose_values'):
            with self.subTest(stage=stage):
                self.setUp();setattr(self,stage,True)
                with self.assertRaises(WorkspaceFailure):self.prepare()
                self.prepare()
                self.assertEqual(len(self.tabs),4)
                self.assertEqual(sum(r.url.path.endswith('/synthetic_sheet:batchUpdate') for r in self.requests),1)
                self.assertEqual(sum(r.url.path.endswith('/values:batchUpdate') for r in self.requests),1)

    def test_header_or_tab_identity_conflicts_are_preserved_for_review(self):
        self.prepare()
        address=next(iter(self.cells));self.cells[address]=[['Foreign header']]
        previous=len(self.requests)
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):self.prepare()
        self.assertTrue(all(r.method=='GET' for r in self.requests[previous:]))
        self.tabs[0]['title']='Changed tab'
        with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):self.prepare()

    def test_invalid_dimensions_refuse_without_overwriting_cells_or_resizing_tabs(self):
        self.prepare()
        original=copy.deepcopy(self.tabs)
        for named in (False,True):
            for grid in (None,[],{'rowCount':10000.5,'columnCount':100},
                         {'rowCount':10000,'columnCount':100.5},
                         {'rowCount':9999,'columnCount':100}, {'rowCount':10000,'columnCount':0}):
                with self.subTest(named=named,grid=grid):
                    self.tabs=copy.deepcopy(original);self.tabs[0]['gridProperties']=grid
                    before=len(self.requests)
                    with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):
                        if named:prepare_named_tab(self.workspace(),'synthetic_sheet',self.saved['intent'],'Appointments',4010,BOOKING_HEADERS)
                        else:self.prepare()
                    self.assertTrue(all(r.method=='GET' for r in self.requests[before:]))

    def test_missing_header_readback_never_reports_a_prepared_workbook(self):
        original=self.handle
        def provider(request):
            if request.url.path.endswith('/values:batchUpdate'):
                self.requests.append(request)
                return httpx.Response(200,json={})
            return original(request)
        self.handle=provider
        with self.assertRaisesRegex(WorkspaceFailure,'google_sheet_readback_unresolved') as failure:self.prepare()
        self.assertTrue(failure.exception.uncertain)
        self.assertEqual(len(self.tabs),4)
        self.assertEqual(self.cells,{})

    def test_unexpected_header_range_or_count_is_rejected_before_writing(self):
        self.prepare();original=self.handle
        for ranges in ([],None,[{'range':'Wrong!A1','values':[]}]*4):
            with self.subTest(ranges=ranges):
                def provider(request):
                    if request.url.path.endswith('/values:batchGet'):
                        self.requests.append(request)
                        return httpx.Response(200,json={'valueRanges':ranges})
                    return original(request)
                self.handle=provider;before=len(self.requests)
                with self.assertRaisesRegex(WorkspaceFailure,'google_workbook_layout_changed'):self.prepare()
                self.assertTrue(all(r.method=='GET' for r in self.requests[before:]))

    def test_new_booking_history_keeps_exact_row_hash_and_local_time(self):
        self.prepare()
        booking=self.saved['snapshot']|dict(id=self.saved['record_id'],ends_at='2026-10-06T11:00:00Z',phone='+919876543210')
        row=sheet_values({'id':str(uuid4()),'payload':booking},4)
        self.assertEqual(len(row),len(BOOKING_HISTORY))
        self.assertEqual(row[-3:-1],['2026-10-06','16:00'])
        self.assertEqual(row[-1],fingerprint(row[:-1]))
        workspace=self.workspace();workspace.write_booking_row('synthetic_sheet',self.saved['intent'],2,row)
        before=len(self.requests);workspace.write_booking_row('synthetic_sheet',self.saved['intent'],2,row)
        self.assertTrue(all(r.method=='GET' for r in self.requests[before:]))
        self.assertEqual(self.cells["'Appointment history'!A2:AJ2"],[row])

    def test_enquiry_history_adds_revision_and_hash_without_losing_attribution(self):
        job=dict(id=str(uuid4()),request_id=str(uuid4()),verified_at='2026-10-01T12:00:00Z',
            payload=dict(name='Synthetic',email='person@example.invalid',phone='+919876543210',subject='Help',message='Call me.',
                source='services',service_interest='kundli',kind='contact',dob='',location='Delhi'))
        values=enquiry_values(job,4)
        self.assertEqual(len(values),len(ENQUIRY_HISTORY))
        self.assertEqual(values[10:12],['services','kundli'])
        self.assertEqual(values[-2],'1');self.assertEqual(values[-1],fingerprint(values[:-1]))
