"""Saved mail acceptance and deadlines prevent duplicate or late provider sends."""
from unittest.mock import Mock,patch
import unittest
from appointment_system import email_delivery as booking,contact_delivery as contact
from appointment_system.email_messages import message_hash

class MailDispatchBoundaries(unittest.TestCase):
 def test_no_work_and_accepted_or_conflicting_work_never_resend(self):
  sender=Mock();store=Mock();store.claim_email_delivery.return_value=None
  self.assertEqual(booking.run_email_delivery_once(store,sender),{'processed':0})
  for accepted in ['accepted','conflict']:
   store.claim_email_delivery.return_value={'id':'synthetic'};store.mail_acceptance.return_value=accepted
   self.assertEqual(booking.run_email_delivery_once(store,sender),{'processed':1,'attention':accepted=='conflict'})
   store.claim_enquiry_delivery.return_value={'id':'synthetic'}
   self.assertEqual(contact.run_contact_email_once(store,sender,None),{'processed':1,'attention':accepted=='conflict'})
  sender.send.assert_not_called()

 def test_mismatched_saved_payload_and_expired_send_deadline_are_attention_items_not_sends(self):
  payload={'subject':'Synthetic message','reply_to':'reply@example.test'}
  for changed,code in [({'message_hash':'wrong'},'email_snapshot_conflict'),({},'email_deadline_passed')]:
   store=Mock();sender=Mock();job={'id':'synthetic','attempts':1,'message_snapshot':payload,**changed};store.claim_email_delivery.return_value=job;store.mail_acceptance.return_value=None
   store.begin_email_send.return_value={'send_deadline_at':'2001-01-01T00:00:00Z','message_snapshot':payload,'first_attempt_at':'2001-01-01T00:00:00Z'};store.finish_email_delivery.return_value=True
   with patch.object(booking,'message_hash',return_value='synthetic-digest'):self.assertEqual(booking.run_email_delivery_once(store,sender),{'processed':1,'retry':False})
   sender.send.assert_not_called();self.assertEqual(store.finish_email_delivery.call_args.args[2:4],(code,True))

 def test_deferred_email_and_wrong_contact_lane_never_call_sender(self):
  store=Mock();sender=Mock();store.claim_email_delivery.return_value={'id':'synthetic','attempts':1,'message_snapshot':{'reply_to':'reply@example.test'}};store.mail_acceptance.return_value=None;store.begin_email_send.return_value=None
  with patch.object(booking,'message_hash',return_value='synthetic-digest'):self.assertEqual(booking.run_email_delivery_once(store,sender),{'processed':0,'deferred':True})
  for value in ['unknown',False]:
   with self.assertRaisesRegex(ValueError,'lane_invalid'):contact.run_contact_email_once(store,sender,None,kind=value)
  sender.send.assert_not_called();store.finish_email_delivery.assert_not_called()
