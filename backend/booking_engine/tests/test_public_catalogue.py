"""The marketing catalogue must remain identical to server-owned prices."""
import json
from pathlib import Path
import unittest
from backend.booking_engine.policy import policy_snapshot, policy_version

class PublicCatalogueTests(unittest.TestCase):
    def test_marketing_snapshot_matches_booking_policy(self):
        root=Path(__file__).resolve().parents[3]
        catalogue=json.loads((root/'frontend/src/site/catalogue.json').read_text())
        self.assertEqual(catalogue,{'quote_version':policy_version(),'services':policy_snapshot()['services']})
