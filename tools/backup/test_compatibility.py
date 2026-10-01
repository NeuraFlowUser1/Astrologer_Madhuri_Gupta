"""Public synthetic vectors made with the previous library prove upgrade safety.

The deliberately published x*32 key protects only this invented test string;
it has never protected an operational credential, archive or customer record.
"""
import base64
import io
import json
from pathlib import Path
import unittest
from cryptography.fernet import Fernet
from envelope import decrypt


class CompatibilityTests(unittest.TestCase):
    def test_previous_version_backup_and_credential_cipher_remain_readable(self):
        vector=json.loads((Path(__file__).parent/'fixtures/cryptography-48-compatibility.json').read_text())
        self.assertEqual(vector['created_with'],'cryptography==48.0.1')
        key=base64.urlsafe_b64decode(vector['key']);destination=io.BytesIO()
        metadata=decrypt(io.BytesIO(base64.b64decode(vector['backup'])),key,destination)
        self.assertEqual(metadata,vector['metadata']);self.assertEqual(destination.getvalue(),vector['plaintext'].encode())
        self.assertEqual(Fernet(vector['key']).decrypt(vector['fernet']),destination.getvalue())
