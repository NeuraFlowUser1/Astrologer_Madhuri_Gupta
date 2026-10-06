"""Local worker preparation preserves account/queue ownership and atomically pins the release."""
import hashlib,json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.install import worker,package
from . import test_package as package_fixtures
from . import test_worker_install as worker_fixtures

class WorkerPreparationBoundaries(unittest.TestCase):
 setUp=package_fixtures.PackageTests.setUp
 run_install=package_fixtures.PackageTests.run_install
 def setup_worker(self):
  self.run_install();fixture=worker_fixtures.WorkerConfiguration();fixture.setUp();self.config=self.target/'wrangler.json';self.config.write_text(json.dumps(fixture.previous));return self.config
 def prepare(self):
  return worker.prepare(self.target,self.config,expected_root=self.target,expected_digest=hashlib.sha256(self.config.read_bytes()).hexdigest())
 def test_preparation_is_idempotent_preserves_owned_queue_and_uses_contained_entry(self):
  self.setup_worker();result=self.prepare();self.assertEqual(result['status'],'prepared');saved=self.config.read_bytes();self.assertEqual(self.prepare()['status'],'existing');self.assertEqual(self.config.read_bytes(),saved)
  value=json.loads(saved);self.assertEqual(value['main'],'appointment-system/worker/index.mjs');self.assertEqual(value['vars']['BOOKING_RELEASE_DIGEST'],self.release['content_digest']);self.assertEqual(value['queues']['consumers'][0]['queue'],'existing-owned-queue')
 def test_changed_file_wrong_location_and_linked_configuration_are_refused(self):
  self.setup_worker()
  with self.assertRaisesRegex(package.PackageError,'changed since review'):worker.prepare(self.target,self.config,expected_root=self.target,expected_digest='a'*64)
  external=self.root/'foreign.json';external.write_bytes(self.config.read_bytes())
  with self.assertRaisesRegex(package.PackageError,'real file'):worker.prepare(self.target,external,expected_root=self.target,expected_digest=hashlib.sha256(external.read_bytes()).hexdigest())
  self.config.unlink();self.config.symlink_to(external)
  with self.assertRaisesRegex(package.PackageError,'real file'):self.prepare()
 def test_settings_links_and_concurrent_config_changes_never_overwrite_user_work(self):
  self.setup_worker();profile=self.target/'appointment-settings/project.json';saved=profile.read_bytes();other=self.root/'other.json';other.write_bytes(saved);profile.unlink();profile.symlink_to(other)
  with self.assertRaisesRegex(package.PackageError,'settings'):self.prepare()
  profile.unlink();profile.write_bytes(saved);original=worker.configuration
  def changed(*args):
   result=original(*args);self.config.write_text('{"concurrent":"user change"}');return result
  with patch.object(worker,'configuration',side_effect=changed):
   with self.assertRaisesRegex(package.PackageError,'changed since review'):self.prepare()
  self.assertEqual(json.loads(self.config.read_text()),{'concurrent':'user change'})
 def test_failed_atomic_replacement_keeps_old_configuration_and_removes_only_its_temporary_file(self):
  self.setup_worker();previous=self.config.read_bytes()
  with patch.object(worker.os,'replace',side_effect=OSError('Synthetic interruption')):
   with self.assertRaises(OSError):self.prepare()
  self.assertEqual(self.config.read_bytes(),previous);self.assertEqual(list(self.target.glob('.appointment-worker-*')),[])
