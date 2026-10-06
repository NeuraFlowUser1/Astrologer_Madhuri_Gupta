"""Provider ambiguity cannot authorize deletion or claim a durable privacy record."""
from unittest.mock import patch
import unittest
from appointment_system.privacy import store as module
from appointment_system.privacy.ledger import PrivacyError,MAXIMUM
from . import test_privacy_store as fixtures

class PrivacyStorageBoundaries(unittest.TestCase):
 def setUp(self):
  self.drive=fixtures.CapturedDrive();self.addCleanup(self.drive.client.close)
  self.store=module.DriveStore(self.drive,fixtures.FOLDER,fixtures.HEAD,fixtures.PROBE,folder_name=fixtures.FOLDER_NAME)

 def test_bad_folder_names_and_immutable_entry_names_are_refused(self):
  for name in [None,'','x'*181]:
   with self.assertRaisesRegex(PrivacyError,'folder_invalid'):module.DriveStore(self.drive,fixtures.FOLDER,fixtures.HEAD,fixtures.PROBE,folder_name=name)
  self.drive.add(fixtures.ENTRY,'privacy-entry','unexpected-name',b'ciphertext')
  with self.assertRaisesRegex(PrivacyError,'identity_invalid'):self.store.read_entry(fixtures.ENTRY)

 def test_slow_or_short_media_never_counts_as_a_readback(self):
  with patch.object(module.time,'monotonic',side_effect=[0,11]):
   with self.assertRaisesRegex(PrivacyError,'readback_unconfirmed'):self.store.read_head()
  self.drive.records[fixtures.HEAD]['size']=str(len(self.drive.data[fixtures.HEAD])+1)
  with self.assertRaisesRegex(PrivacyError,'readback_unconfirmed'):self.store.read_head()

 def test_invalid_head_data_does_not_make_a_provider_write(self):
  before=len(self.drive.calls)
  for body in [None,'plaintext',b'',b'x'*(MAXIMUM+1)]:
   with self.assertRaisesRegex(PrivacyError,'document_limit'):self.store.conditional_write(fixtures.HEAD,'"version-1"',body)
  self.assertEqual(len(self.drive.calls),before)

 def test_success_status_without_new_probe_version_or_exact_bytes_is_not_proof(self):
  for confirmed,version in [(b'wrong-bytes','"version-2"'),(b'candidate','"version-1"')]:
   with patch.object(self.store,'read',side_effect=[(b'old','"version-1"'),(confirmed,version)]),patch.object(module,'canonical',return_value=b'candidate'),patch.object(self.store,'conditional_write',side_effect=[412,200]):
    with self.assertRaisesRegex(PrivacyError,'compare_and_swap_unproved'):self.store.preflight()
   self.assertFalse(self.store.checked_concurrency)
  with patch.object(self.store,'read',side_effect=[(b'old','"version-1"'),(b'candidate','"version-2"')]),patch.object(module,'canonical',return_value=b'candidate'),patch.object(self.store,'conditional_write',side_effect=[412,200,200]):
   with self.assertRaisesRegex(PrivacyError,'compare_and_swap_unproved'):self.store.preflight()

 def test_head_write_refusal_and_changed_readback_cannot_be_accepted(self):
  self.store.checked_concurrency=True
  with patch.object(self.store,'conditional_write',side_effect=PrivacyError('privacy_document_limit')):
   with self.assertRaisesRegex(PrivacyError,'document_limit'):self.store.compare_and_swap_head('"version-1"',b'candidate')
  with patch.object(self.store,'conditional_write',return_value=200),patch.object(self.store,'read_head',return_value=(b'another-writer','"version-2"')):
   with self.assertRaisesRegex(PrivacyError,'head_changed'):self.store.compare_and_swap_head('"version-1"',b'candidate')

 def test_entry_upload_must_be_read_back_exactly_before_consuming_capacity(self):
  available=self.drive.available
  with patch.object(self.store,'read_entry',return_value=b'changed'):
   with self.assertRaisesRegex(PrivacyError,'entry_unconfirmed'):self.store.create_entry(b'encrypted',1,'a'*64)
  self.assertEqual(self.drive.available,available)
  self.assertEqual(sum(request.method=='POST' for request in self.drive.calls),1)
