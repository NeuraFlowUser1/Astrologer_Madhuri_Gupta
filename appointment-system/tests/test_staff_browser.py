"""Staff storage settings stay scoped and do not depend on Google authorization."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.connection import StorageUnavailable
from appointment_system.secret_configuration import booking_settings
from appointment_system.staff_browser import configuration, script
from appointment_system.configuration import installation
from .test_application import PublicStore, Reader, environment

class StaffBrowser(unittest.TestCase):
    def setUp(self):
        facts=installation()
        self.ring=SimpleNamespace(installation_id=facts['installation_id'],environment=facts['environment'])
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)
        self.path=self.directory/'staff-browser.json'
        self.value=configuration(self.ring,self.directory)

    def test_fresh_installation_declares_no_legacy_and_only_public_scope_is_rendered(self):
        self.assertEqual(self.value['legacy'],dict(client=[],company=[],calendar=[],inbox=[],enquiry=[]))
        with patch('appointment_system.staff_browser.configuration',return_value=self.value):
            response=script(self.ring)
        self.assertIn(self.ring.installation_id,response.body.decode())
        self.assertNotIn('/*STAFF_BROWSER_CONFIGURATION*/null',response.body.decode())
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_exact_legacy_settings_are_optional_but_malformed_or_foreign_settings_are_rejected(self):
        good=self.value|{'legacy':self.value['legacy']|{'client':['old:client']}}
        self.path.write_text(json.dumps(good));self.assertEqual(configuration(self.ring,self.directory),good)
        variants=[good|{'installation_id':'foreign'},good|{'environment':'foreign'},good|{'version':True},
            good|{'extra':1},good|{'legacy':[]},good|{'legacy':{'client':[]}},
            good|{'legacy':good['legacy']|{'client':['appointment-system:other']}},
            good|{'legacy':good['legacy']|{'client':['old:client']*5}},
            good|{'legacy':good['legacy']|{'client':['old:client'],'company':['old:client']}},
            good|{'legacy':good['legacy']|{'client':['../secret']}},
            good|{'legacy':good['legacy']|{'client':'not-list'}}]
        for value in variants:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value))
                with self.assertRaises(StorageUnavailable):configuration(self.ring,self.directory)
        for content in ('{broken','x'*8193,'[]'):
            self.path.write_text(content)
            with self.assertRaises(StorageUnavailable):configuration(self.ring,self.directory)

    def test_links_are_rejected_even_if_their_target_is_missing(self):
        self.path.symlink_to(self.directory/'absent')
        with self.assertRaises(StorageUnavailable):configuration(self.ring,self.directory)

    def test_company_script_available_without_google_while_staff_script_follows_off(self):
        facts=installation();reader=Reader(False)
        client=TestClient(create_application(PublicStore(),booking_settings(environment()),
            verified_client_address=lambda request:'198.51.100.9',projection_reader=reader),base_url=facts['origin'])
        with patch('appointment_system.staff_browser.configuration',return_value=self.value):
            self.assertEqual(client.get('/api/company/staff-actions.js').status_code,200)
            self.assertEqual(client.get('/api/studio/staff-actions.js').status_code,404)
            self.assertEqual(client.get('/api/staff-actions.js').status_code,404)
            reader.enabled=True
            self.assertEqual(client.get('/api/studio/staff-actions.js').status_code,200)
