"""Google record responses cannot select conflicting identities or wrong cells."""
import unittest
import httpx
from appointment_system.google_workspace import Workspace,WorkspaceFailure,DRIVE,resource_id,event_id,row_matches,column_name
from . import test_google_workspace as fixtures


class GoogleDocumentBoundaries(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.WorkspaceTests();self.fixture.setUp()

    def test_duplicate_identity_fields_and_unbounded_nesting_preserve_write_uncertainty(self):
        for body in (b'{"id":"first","id":"different"}',
                     b'{"owners":[{"emailAddress":"other@example.test","emailAddress":"owner@example.test"}]}',
                     b'{"nested":'+b'['*1100+b'0'+b']'*1100+b'}'):
            for method in ('GET','POST'):
                with self.subTest(method=method,body_kind=body[:20]):
                    requests=[]
                    def provider(request):
                        requests.append(request)
                        return httpx.Response(200,content=body,headers={'content-type':'application/json'})
                    workspace=Workspace(self.fixture.access,transport=httpx.MockTransport(provider))
                    with self.assertRaises(WorkspaceFailure) as failure:workspace.request(method,DRIVE)
                    self.assertEqual(failure.exception.uncertain,method=='POST')
                    self.assertEqual(len(requests),1)

    def test_malformed_saved_resource_revision_and_customer_refuse_before_provider_io(self):
        for value in (None,False,'','/outside','x'*201):
            with self.assertRaisesRegex(WorkspaceFailure,'google_resource_invalid'):resource_id(value)
        for revision in (False,0,-1,1.0,'1'):
            with self.assertRaisesRegex(WorkspaceFailure,'google_revision_invalid'):event_id(self.fixture.booking['id'],revision)
        with self.assertRaisesRegex(WorkspaceFailure,'google_calendar_protocol_invalid'):event_id(self.fixture.booking['id'],1,'guess-from-project')
        workspace=self.fixture.workspace([])
        self.assertEqual(workspace.calendar_body(self.fixture.booking|{'email':None})['attendees'],[])
        for email in (False,'',{},[],'missing-domain','a@b','a b@example.test'):
            with self.assertRaisesRegex(WorkspaceFailure,'google_customer_invalid'):workspace.calendar_body(self.fixture.booking|{'email':email})
        self.assertEqual(self.fixture.requests,[])

    def test_existing_rows_reject_extra_cells_types_and_multiple_rows_without_ignoring_conflicts(self):
        self.assertTrue(row_matches([['a']],['a','']))
        self.assertFalse(row_matches([],['a','']))
        for rows in (None,{},[None],[['a'],['a']],[['a','','extra']],[[1]],[['other']]):
            with self.assertRaisesRegex(WorkspaceFailure,'google_row_conflict'):row_matches(rows,['a',''])
        for number in (0,65,False,1.0,'1'):
            with self.assertRaisesRegex(WorkspaceFailure,'google_column_invalid'):column_name(number)
        self.assertEqual(column_name(1),'A');self.assertEqual(column_name(64),'BL')
