"""Retained archive evidence cannot become valid by borrowing a new namespace."""
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from appointment_system.backup import legacy_003 as reader
from appointment_system.backup.protocol import BackupError


class HistoricalBackupBoundaries(unittest.TestCase):
    def manifest(self):
        return dict(version=1,purpose='database-export',project='003-astroadvice-by-kundan-singh',environment='production',source_commit='a'*40,
            source_run='123',source_attempt='2',archive_name='astro-advice-20261002T000000Z-123-2.dump.age',archive_sha256='b'*64,archive_bytes=123,
            created_at='2026-10-02T00:00:00Z',postgres_major=16,schemas=['public','booking_control'],migrations={'001_initial.sql':'c'*64},table_counts={'booking_control.product_state':1})

    def proof(self):
        return dict(version=1,purpose='restore-proof',project='003-astroadvice-by-kundan-singh',environment='production',
            manifest_sha256='a'*64,archive_sha256='b'*64,source_run='123',source_attempt='2',source_commit='c'*40,validator_commit='d'*40,
            verified_at='2026-10-02T00:00:00Z',migration_count=1,migration_digest='e'*64,table_counts_digest='f'*64,control_included=True,
            restored_authority='off_new_generation',archive_drive_id='fixture-archive-id',archive_drive_version='1',manifest_drive_id='fixture-manifest-id',manifest_drive_version='2')

    def envelope(self,value):
        key=Ed25519PrivateKey.generate();keys={'historic':base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode()}
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
        signature=key.sign(b'neuraflow-booking-backup:003:production:v1:'+value['purpose'].encode()+b':'+raw)
        return {'version':1,'key_id':'historic','payload':value,'signature':base64.urlsafe_b64encode(signature).decode()},keys

    def test_independent_original_export_and_restore_signatures_are_verified_without_new_scope(self):
        for value in (self.manifest(),self.proof()):
            envelope,keys=self.envelope(value);self.assertEqual(reader.verify(envelope,keys,value['purpose']),value)
            for changed in ({'key_id':'missing'},{'version':True},{'signature':base64.urlsafe_b64encode(b'x'*64).decode()}):
                with self.subTest(changed=changed),self.assertRaises(BackupError):reader.verify(envelope|changed,keys,value['purpose'])
            for keymap in ({},[],{'historic':'bad'}):
                with self.assertRaises(BackupError):reader.verify(envelope,keymap,value['purpose'])
            with self.assertRaisesRegex(BackupError,'purpose_invalid'):reader.checked(value,'other-purpose')

    def test_manifest_rejects_foreign_identity_inconsistent_run_and_invalid_saved_counts(self):
        changes=[{'version':True},{'purpose':'restore-proof'},{'environment':'test'},{'source_commit':'bad'},{'source_run':'0'},
            {'archive_bytes':True},{'archive_bytes':0},{'archive_bytes':reader.MAX_BYTES+1},{'archive_sha256':'bad'},
            {'postgres_major':True},{'schemas':['public']},{'archive_name':'../backup.dump.age'},{'source_attempt':'0'},{'source_attempt':'3'},
            {'migrations':{}},{'migrations':{'foreign.sql':'c'*64}},{'migrations':{'001_initial.sql':'bad'}},
            {'table_counts':{}},{'table_counts':{'booking_control.product_state':0}},
            {'table_counts':{'booking_control.product_state':1,'public.bookings':True}},
            {'table_counts':{'booking_control.product_state':1,'foreign.bookings':1}},
            {'table_counts':{'booking_control.product_state':1,'public.bookings':-1}}]
        for changed in changes:
            with self.subTest(changed=changed),self.assertRaises(BackupError):reader.checked_manifest(self.manifest()|changed)
        with self.assertRaises(BackupError):reader.checked_manifest([])

    def test_restore_proof_binds_saved_drive_versions_and_requires_off_authority(self):
        changes=[{'version':True},{'project':'foreign'},{'manifest_sha256':'bad'},{'validator_commit':'bad'},{'source_run':123},
            {'migration_count':True},{'migration_count':501},{'control_included':1},{'restored_authority':'on'},
            {'source_attempt':'0'},{'archive_drive_id':'bad'},{'manifest_drive_id':'bad'},{'archive_drive_version':'0'},{'manifest_drive_version':1}]
        for changed in changes:
            with self.subTest(changed=changed),self.assertRaises(BackupError):reader.checked_attestation(self.proof()|changed)
        with self.assertRaises(BackupError):reader.checked_attestation(None)

    def test_historical_json_rejects_ambiguous_input_and_nested_non_manifest_data(self):
        self.assertEqual(reader.unique_json(b'{"saved":"value"}'),{'saved':'value'})
        for value in (None,b'\xff','x'*(reader.MAX_MANIFEST+1),'{"a":1,"a":2}','{"a":NaN}'):
            with self.subTest(kind=type(value).__name__),self.assertRaises(BackupError):reader.unique_json(value)
        # Python versions differ in whether their JSON parser rejects nesting.
        # The retained format promises a bounded, strictly shaped manifest,
        # not a parser-specific recursion limit. Neither route accepts this
        # malformed archive description as a usable signed manifest.
        with self.assertRaises(BackupError):
            reader.checked_manifest(reader.unique_json('['*3000+'0'+']'*3000))
        self.assertEqual(reader.digest({'a':1}),hashlib.sha256(b'{"a":1}').hexdigest())

    def test_key_time_and_name_checks_reject_noncanonical_or_future_values(self):
        self.assertEqual(reader.decode(base64.urlsafe_b64encode(b'x'*32).decode(),32),b'x'*32)
        for value in (None,'bad',base64.urlsafe_b64encode(b'x'*31).decode(),base64.urlsafe_b64encode(b'x'*32).decode().rstrip('=')):
            with self.assertRaises(BackupError):reader.decode(value,32)
        for value in ('Uppercase','../reader','',None):
            with self.assertRaises(BackupError):reader.identifier(value)
        self.assertEqual(reader.identifier('historic-v1'),'historic-v1')
        for value in (None,'2026-02-30T00:00:00Z','2026-10-02T00:00:00+00:00',(datetime.now(timezone.utc)+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')):
            with self.assertRaises(BackupError):reader.stamp(value)
