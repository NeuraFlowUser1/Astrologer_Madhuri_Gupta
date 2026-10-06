"""Old spreadsheet work retains completion and never guesses a lost row."""
from copy import deepcopy
import unittest
from uuid import uuid4
from tools.conversion.source import catalogue,ConversionError
from tools.conversion.transport import TransportTransfer
from .test_conversion_records import bindings


class HistoricalSheetJobs(unittest.TestCase):
 def setUp(self):
  self.layout=next(item for item in catalogue() if item.project=='003' and len(item.ledger)==16)
  self.transfer=TransportTransfer(bindings());self.parent=str(uuid4());self.request=str(uuid4())
  self.source={'public.inquiries':[{'id':self.parent,'request_id':self.request,'email':'fixture@example.test'}]}

 def row(self,**changes):
  return dict(id=str(uuid4()),kind='sheet_inquiry',recipient_role='client_sheet',record_id=self.parent,
   state='sent',attempts=1,created_at='2026-10-01T10:00:00Z',next_attempt_at='2026-10-01T10:00:00Z',
   first_attempt_at='2026-10-01T10:00:00Z',provider_id=None,last_error_code=None,message_version=1,
   send_uncertain=False,message_payload=None)|changes

 def translated(self,row):
  return self.transfer(self.layout,'delivery_jobs',[row],self.source)['enquiry_delivery_jobs'][0]

 def test_completed_enquiry_copies_retain_their_own_parent_and_cannot_become_mail(self):
  for role in ('client_sheet','agency_sheet'):
   with self.subTest(role=role):
    row=self.row(recipient_role=role);before=deepcopy(row);saved=self.translated(row)
    self.assertEqual((saved['id'],saved['request_id'],saved['kind'],saved['state']),
     (row['id'],self.request,role,'completed'))
    self.assertEqual(saved['first_attempt_at'],row['first_attempt_at']);self.assertEqual(saved['attempts'],1)
    self.assertIsNone(saved['destination']);self.assertNotIn('message_snapshot',saved)
    self.assertNotIn('booking_id',saved);self.assertNotIn('email_reservations',saved)
    self.assertEqual(row,before)

 def test_only_unattempted_sheet_jobs_can_start_without_a_known_original_row(self):
  row=self.row(state='pending',attempts=0,first_attempt_at=None)
  self.assertEqual(self.translated(row)['state'],'pending')
  for state in ('pending','processing','failed'):
   with self.subTest(state=state):
    saved=self.translated(self.row(state=state,send_uncertain=True))
    self.assertEqual((saved['state'],saved['last_error_code']),('needs_review','legacy_sheet_address_unresolved'))
  self.assertEqual(self.translated(self.row(last_error_code='superseded_by_cancellation'))['state'],'suppressed')

 def test_unrelated_saved_sheet_address_cannot_authorize_a_repeat_write(self):
  row=self.row(state='processing')
  for identity in ({'job_id':str(uuid4()),'role':row['recipient_role']},
    {'job_id':row['id'],'role':'agency_sheet'}):
   self.source['public.sheet_history_rows']=[identity]
   self.assertEqual(self.translated(row)['state'],'needs_review')
  self.source['public.sheet_history_rows']=[{'job_id':row['id'],'role':row['recipient_role']}]
  self.assertEqual(self.translated(row)['state'],'retry_wait')

 def test_wrong_parent_or_recipient_role_cannot_be_adopted_as_a_sheet_copy(self):
  for changes in ({'record_id':str(uuid4())},{'recipient_role':'customer'},{'recipient_role':'calendar'}):
   with self.subTest(changes=changes),self.assertRaisesRegex(ConversionError,'enquiry_job_identity_missing'):
    self.translated(self.row(**changes))
