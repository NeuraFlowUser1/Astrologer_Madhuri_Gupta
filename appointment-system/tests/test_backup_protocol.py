"""Independent signing and real standard age authentication failure checks."""
import base64
from copy import deepcopy
from datetime import datetime,timezone
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from appointment_system.backup.protocol import (Identity,BackupError,canonical,unique_json,digest,sign,verify,matched_proof,
    checked,decode,keyring,stamp,MAX_BYTES,invariant_digest)
from appointment_system.backup.age_stream import encrypt,hashed,authenticated_archive,restore_stream,checked_identity

def encoded(value):return base64.urlsafe_b64encode(value).decode()

def signing():
    private=Ed25519PrivateKey.generate()
    return encoded(private.private_bytes_raw()),encoded(private.public_key().public_bytes_raw())

class BackupProtocol(unittest.TestCase):
    def setUp(self):
        self.identity=Identity(str(uuid4()),'example-practice','test','practice@example.test','a'*64)
        self.private,self.public=signing();self.validator_private,self.validator_public=signing()
        self.export=dict(version=1,purpose='database-export',**self.identity.fields(),source_commit='b'*40,source_run='12345',source_attempt='1',
            archive_name='appointment-'+self.identity.installation_id+'-12345-1.dump.age',archive_sha256='c'*64,archive_bytes=123,
            created_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),postgres_major=18,schemas=['appointment_system'],
            migrations={'001_initial.sql':'d'*64},table_counts={'appointment_system.installation':1,'appointment_system.control_product_state':1},
            restore_generation=str(uuid4()),generation_sequence='1',database_contract=1)
        self.envelope=sign(self.export,'export',self.private,self.identity)
        self.proof=dict(version=1,purpose='restore-proof',**self.identity.fields(),manifest_sha256=digest(self.envelope),archive_sha256=self.export['archive_sha256'],
            source_run='12345',source_attempt='1',source_commit='b'*40,validator_commit='e'*40,verified_at=self.export['created_at'],migration_count=1,
            migration_digest=digest(self.export['migrations']),table_counts_digest=digest(self.export['table_counts']),invariants_digest=invariant_digest(),
            restored_authority='off_new_generation',archive_drive_id='archive_synthetic',archive_drive_version='1',manifest_drive_id='manifest_synthetic',manifest_drive_version='1')

    def test_independent_export_and_validator_signatures_bind_the_exact_attempt(self):
        signed=sign(self.proof,'validator',self.validator_private,self.identity)
        source,proof=matched_proof(self.envelope,signed,{'export':self.public},{'validator':self.validator_public},self.identity)
        self.assertEqual(source,self.export);self.assertEqual(proof,self.proof)
        with self.assertRaises(BackupError):matched_proof(self.envelope,signed,{'export':self.public},{'validator':self.public},self.identity)
        changed=deepcopy(self.proof);changed['source_attempt']='2'
        altered=sign(changed,'validator',self.validator_private,self.identity)
        with self.assertRaises(BackupError):matched_proof(self.envelope,altered,{'export':self.public},{'validator':self.validator_public},self.identity)

    def test_manifest_refuses_foreign_identity_wrong_major_count_and_ambiguous_values(self):
        for mutation in ({'installation_id':str(uuid4())},{'project':'foreign'},{'owner_email':'other@example.test'},
                {'release_digest':'1'*64},{'source_run':'0'},{'source_attempt':True},{'source_commit':'z'*40},
                {'archive_name':'../archive.age'},{'archive_bytes':True},{'archive_bytes':MAX_BYTES+1},{'postgres_major':17},
                {'database_contract':True},{'schemas':['public']},{'generation_sequence':str(2**63)},
                {'restore_generation':str(uuid4()).upper()},{'migrations':{}},
                {'table_counts':{'appointment_system.installation':1,'appointment_system.control_product_state':True}},
                {'created_at':'2099-01-01T00:00:00Z'},{'extra':'value'}):
            wrong=deepcopy(self.export);wrong.update(mutation)
            with self.assertRaises(BackupError,msg=str(mutation)):checked(wrong,'database-export',self.identity)
        for major in (16,18):
            good=self.export|{'postgres_major':major};self.assertEqual(checked(good,'database-export',self.identity),good)

    def test_attestation_cannot_supply_exporter_verified_flags_or_unbound_storage(self):
        for mutation in ({'verified':True},{'purpose':'database-export'},{'archive_drive_id':'foreign'},
                {'manifest_drive_version':'0'},{'restored_authority':'on'},{'migration_count':True},
                {'invariants_digest':'wrong'},{'validator_commit':'z'*40},{'verified_at':'bad'}):
            with self.assertRaises(BackupError):checked(self.proof|mutation,'restore-proof',self.identity)
        signed=sign(self.proof,'validator',self.validator_private,self.identity)
        wrong=deepcopy(signed);wrong['payload']['archive_sha256']='1'*64
        with self.assertRaises(BackupError):verify(wrong,{'validator':self.validator_public},'restore-proof',self.identity)

    def test_document_and_key_boundaries_do_not_guess_formats(self):
        for value in ('{"a":1,"a":2}','{"a":NaN}','x'*65537,b'\xff',None):
            with self.assertRaises(BackupError):unique_json(value)
        self.assertEqual(unique_json(canonical({'a':1})),{'a':1})
        for value in ({},{'UPPER':self.public},{'correct':'bad'},[],{'correct':encoded(b'x'*31)}):
            with self.assertRaises(BackupError):keyring(value)
        for envelope in ({},self.envelope|{'extra':True},self.envelope|{'version':True},self.envelope|{'key_id':'missing'},self.envelope|{'signature':'invalid'}):
            with self.assertRaises(BackupError):verify(envelope,{'export':self.public},'database-export',self.identity)
        with self.assertRaises(BackupError):decode('!',32)
        with self.assertRaises(BackupError):stamp('0000-01-01T00:00:00Z')

@unittest.skipUnless(os.environ.get('BOOKING_AGE_BINARY'),'Pinned native age binary required; no simulated crypto proof.')
class NativeAge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=os.environ['BOOKING_AGE_BINARY'];generator=str(Path(cls.binary).with_name('age-keygen'))
        cls.identity=subprocess.run([generator],capture_output=True,text=True,check=True,timeout=5).stdout
        cls.recipient=subprocess.run([generator,'-y'],input=cls.identity,capture_output=True,text=True,check=True,timeout=5).stdout.strip()

    def test_real_age_round_trip_keeps_private_recovery_material_out_of_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive.age';plain=b'isolated synthetic PostgreSQL archive\x00'*7000
            sha,size=encrypt(io.BytesIO(plain),path,self.recipient,self.binary)
            self.assertNotIn(plain[:256],path.read_bytes());self.assertEqual(hashed(path),(sha,size))
            output=io.BytesIO()
            with authenticated_archive(path,self.identity,self.binary,sha,size) as archive:
                self.assertNotIn(self.identity,repr(archive));restore_stream(archive,output)
            self.assertEqual(output.getvalue(),plain)
            with self.assertRaises(BackupError):restore_stream(archive,io.BytesIO())

    def test_corrupt_or_truncated_ciphertext_releases_no_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive.age';encrypt(io.BytesIO(b'synthetic\x00'*20000),path,self.recipient,self.binary)
            original=path.read_bytes()
            for corrupt in (original[:-1],original[:100],original[:-1]+bytes([original[-1]^1])):
                path.write_bytes(corrupt);sha,size=hashed(path);output=io.BytesIO()
                with self.assertRaises(BackupError):
                    with authenticated_archive(path,self.identity,self.binary,sha,size) as archive:restore_stream(archive,output)
                self.assertEqual(output.getvalue(),b'')
            path.write_bytes(original)
            with self.assertRaises(BackupError):
                with authenticated_archive(path,self.identity,self.binary,'0'*64,len(original)):pass

    def test_overwrite_and_invalid_identity_or_tool_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive.age';path.write_bytes(b'keep this')
            with self.assertRaises(BackupError):encrypt(io.BytesIO(b'other'),path,self.recipient,self.binary)
            self.assertEqual(path.read_bytes(),b'keep this')
            for identity in ('',None,self.identity+self.identity,'AGE-SECRET-KEY-1!'):
                with self.assertRaises(BackupError):checked_identity(identity)
            with self.assertRaises(BackupError):encrypt(io.BytesIO(b'data'),Path(directory)/'new','bad',self.binary)
            with self.assertRaises(BackupError):encrypt(io.BytesIO(b'data'),Path(directory)/'new',self.recipient,'/nonexistent/age')
