"""Independent historical-format fixtures; no legacy writer in the running engine."""
import base64
from copy import deepcopy
import io
from pathlib import Path
import secrets
import struct
import tempfile
import unittest
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from appointment_system.backup import legacy_003,legacy_004
from appointment_system.backup.legacy import export_manifest_003,read_aes_004
from appointment_system.backup.protocol import BackupError,canonical

class LegacyArchiveTests(unittest.TestCase):
    def aes(self,metadata,plain,version):
        key=secrets.token_bytes(32);nonce=secrets.token_bytes(12);document=canonical(metadata)
        prefix=(legacy_004.MAGIC_V2 if version==2 else legacy_004.MAGIC)+nonce+struct.pack('>I',len(document))
        writer=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();writer.authenticate_additional_data(prefix+document)
        return base64.urlsafe_b64encode(key).decode(),prefix+document+writer.update(plain)+writer.finalize()+writer.tag
    def test_sarsa_both_literal_envelopes_authenticate_before_any_restore_output(self):
        for version in (1,2):
            metadata={'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom'}
            if version==2:metadata.update(protocol_version=2,schemas=['sarsa_booking','booking_control'],migrations={'001_initial.sql':'a'*64},table_counts={'booking_control.product_state':1})
            key,body=self.aes(metadata,b'synthetic old database\x00'*100,version)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'legacy.aes';path.write_bytes(body);output=io.BytesIO()
                self.assertEqual(read_aes_004(path,key,output),metadata);self.assertEqual(output.getvalue(),b'synthetic old database\x00'*100)
                for corrupt in (body[:-1],body[:-1]+bytes([body[-1]^1]),body[:30]):
                    path.write_bytes(corrupt);output=io.BytesIO()
                    with self.assertRaises(BackupError):read_aes_004(path,key,output)
                    self.assertEqual(output.getvalue(),b'')
    def test_foreign_legacy_metadata_does_not_release_authenticated_plaintext(self):
        for metadata in ({'project':'foreign','format':'postgres-custom'},{'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','protocol_version':2}):
            key,body=self.aes(metadata,b'private old data',1)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'legacy.aes';path.write_bytes(body);output=io.BytesIO()
                with self.assertRaises(BackupError):read_aes_004(path,key,output)
                self.assertEqual(output.getvalue(),b'')
    def test_astro_manifest_keeps_exact_legacy_signature_namespace_and_scope(self):
        value=dict(version=1,purpose='database-export',project='003-astroadvice-by-kundan-singh',environment='production',source_commit='a'*40,
            source_run='1',source_attempt='1',archive_name='astro-advice-20261002T000000Z-1-1.dump.age',archive_sha256='b'*64,archive_bytes=123,
            created_at='2026-10-02T00:00:00Z',postgres_major=16,schemas=['public','booking_control'],migrations={'001_initial.sql':'c'*64},table_counts={'booking_control.product_state':1})
        key=Ed25519PrivateKey.generate();keys={'historic':base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode()}
        signature=key.sign(b'neuraflow-booking-backup:003:production:v1:database-export:'+canonical(value))
        envelope={'version':1,'key_id':'historic','payload':value,'signature':base64.urlsafe_b64encode(signature).decode()}
        self.assertEqual(export_manifest_003(envelope,keys),value)
        for change in ({'project':'example-practice'},{'schemas':['appointment_system']},{'postgres_major':18}):
            wrong=deepcopy(envelope);wrong['payload'].update(change)
            with self.assertRaises(BackupError):export_manifest_003(wrong,keys)
        wrong=deepcopy(envelope);wrong['signature']='invalid'
        with self.assertRaises(BackupError):export_manifest_003(wrong,keys)

if __name__=='__main__':unittest.main()
