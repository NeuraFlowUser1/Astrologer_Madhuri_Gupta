"""Existing external events must be reused rather than recreated at handover."""
import copy
import unittest
from appointment_system.google_workspace import Workspace,WorkspaceFailure,event_id
from . import test_google_workspace as fixtures

class HistoricalCalendar(unittest.TestCase):
 def setUp(self):
  self.proof=fixtures.WorkspaceTests();self.proof.setUp()
  self.proof.booking.update(id='11111111-1111-4111-8111-111111111111',revision=2,calendar_protocol='legacy-sarsa004')
  # Captured from the frozen 004 event_id / calendar_body contract. It is
  # deliberately not derived by the new event_id under test.
  self.external_id='sarsac7d1e9725d33f0604c27e21eb8166c914a65bea1c723d7810148c76d9f341601'
  self.properties={'project':'004-sarsa-jyotish-sansthan','booking':self.proof.booking['id'],'revision':'2'}

 def saved_event(self):
  result=self.proof.event();result.update(id=self.external_id)
  result['extendedProperties']={'private':copy.deepcopy(self.properties)}
  return result

 def test_original_external_id_tags_and_meeting_request_survive(self):
  body=Workspace(self.proof.access).calendar_body(self.proof.booking)
  self.assertEqual(body['id'],self.external_id)
  self.assertEqual(body['extendedProperties']['private'],self.properties)
  self.assertEqual(body['conferenceData']['createRequest']['requestId'],self.external_id)
  self.assertNotEqual(event_id(self.proof.booking['id'],2),self.external_id)

 def test_existing_remote_meeting_is_read_without_a_second_create(self):
  workspace=self.proof.workspace([(200,self.saved_event())])
  self.assertEqual(workspace.ensure_meeting(self.proof.booking)['event_id'],self.external_id)
  self.assertEqual([request.method for request in self.proof.requests],['GET'])
  self.assertTrue(str(self.proof.requests[0].url).endswith('/'+self.external_id))

 def test_existing_remote_meeting_is_deleted_conditionally_and_foreign_tags_are_refused(self):
  workspace=self.proof.workspace([(200,self.saved_event()),(204,None)])
  workspace.cancel_meeting(self.proof.booking)
  self.assertEqual(self.proof.requests[1].headers['if-match'],'"synthetic"')
  self.assertTrue(str(self.proof.requests[1].url).split('?')[0].endswith('/'+self.external_id))
  event=self.saved_event();event['extendedProperties']['private']['project']='foreign'
  with self.assertRaisesRegex(WorkspaceFailure,'google_event_mismatch'):
   self.proof.workspace([(200,event)]).cancel_meeting(self.proof.booking)
  self.assertEqual(len(self.proof.requests),3)


class HistoricalAstroEvents(unittest.TestCase):
 def test_both_saved_marker_versions_reuse_the_exact_external_event_and_meeting_request(self):
  for protocol,revision,identifier,conference,properties in (
   ('legacy-astro003-unversioned',1,'astro11111111111141118111111111111111','meet11111111111141118111111111111111',{'astroBookingId':'11111111-1111-4111-8111-111111111111'}),
   ('legacy-astro003',2,'astro11111111111141118111111111111111r2','meet11111111111141118111111111111111r2',{'astroBookingId':'11111111-1111-4111-8111-111111111111','project':'003','revision':'2'})):
   with self.subTest(protocol=protocol):
    proof=fixtures.WorkspaceTests();proof.setUp()
    proof.booking.update(id='11111111-1111-4111-8111-111111111111',revision=revision,calendar_protocol=protocol)
    body=Workspace(proof.access).calendar_body(proof.booking)
    self.assertEqual(body['id'],identifier);self.assertEqual(body['conferenceData']['createRequest']['requestId'],conference)
    self.assertEqual(body['extendedProperties']['private'],properties)
    saved=proof.event();saved['id']=identifier;saved['extendedProperties']={'private':properties.copy()}
    result=proof.workspace([(200,saved)]).ensure_meeting(proof.booking)
    self.assertEqual(result['event_id'],identifier);self.assertEqual([request.method for request in proof.requests],['GET'])
    proof.requests.clear();saved['extendedProperties']['private']['astroBookingId']='22222222-2222-4222-8222-222222222222'
    with self.assertRaisesRegex(WorkspaceFailure,'google_event_mismatch'):
     proof.workspace([(200,saved)]).ensure_meeting(proof.booking)
    self.assertEqual([request.method for request in proof.requests],['GET'])
