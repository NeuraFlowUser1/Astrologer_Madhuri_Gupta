"""Refuse ambiguous or altered backup evidence before any retention deletion."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from appointment_system.backup import pipeline
from appointment_system.backup.protocol import BackupError,canonical
from .backup_fixtures import SCOPE
from . import test_backup_pipeline as fixtures
Storage=fixtures.Storage

class BackupEvidenceBoundaries(unittest.TestCase):
    setUp=fixtures.PipelineTests.setUp
    export=fixtures.PipelineTests.export
    proof=fixtures.PipelineTests.proof
    retain=fixtures.PipelineTests.retain
    add=fixtures.PipelineTests.add

    def inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            return pipeline.verified_inventory(SCOPE,self.store,Path(directory),self.export_keys,self.validation_keys)

    def test_missing_misnamed_or_resized_archive_pair_never_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(BackupError,'export_not_complete'):
                pipeline.archive_pair(SCOPE,self.store,'1','1','b'*40,Path(directory),self.export_keys)
        self.export();original=deepcopy(self.store.objects)
        for field,value,expected in [('name','another.dump.age','archive_identity'),('size','999','archive_size')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                self.store.objects=deepcopy(original);archive=self.store.find('encrypted-backup','1','1')
                record,body=self.store.objects[archive['id']];record[field]=value
                with self.assertRaisesRegex(BackupError,expected):
                    pipeline.archive_pair(SCOPE,self.store,'1','1','b'*40,Path(directory),self.export_keys)
        self.assertFalse(self.store.removed)

    def test_invalid_snapshot_and_corrupt_readbacks_never_claim_stored_or_delete(self):
        args=dict(export_key_id='export',export_private=self.export_private,export_keys=self.export_keys)
        with self.assertRaisesRegex(BackupError,'snapshot_invalid'):
            pipeline.export(SCOPE,self.store,'1','1','b'*40,**args,dump=lambda path:{'snapshot':'incomplete'})
        self.assertEqual(self.store.uploads,[])
        for corrupt_purpose,expected in [('encrypted-backup','upload_readback_mismatch'),('backup-manifest','manifest_readback_mismatch')]:
            self.store=Storage();original=self.store.download
            def download(record,path,limit=512*1024*1024):
                if record['properties']['purpose']==corrupt_purpose:path.write_bytes(b'{}' if corrupt_purpose=='backup-manifest' else b'corrupt')
                else:original(record,path,limit)
            with patch.object(self.store,'download',side_effect=download):
                with self.assertRaisesRegex(BackupError,expected):self.export()
            self.assertFalse(self.store.removed)

    def test_wrong_authority_and_incomplete_restore_result_never_sign_proof(self):
        self.export();options=dict(export_keys=self.export_keys,validation_keys=self.validation_keys,validation_key_id='validator',validation_private=self.validator_private,recovery_identity='synthetic',binary='synthetic',ledger={})
        with self.assertRaisesRegex(BackupError,'validation_authority'):
            pipeline.validate(SCOPE,self.store,'1','1','b'*40,'c'*40,**options)
        self.store.reader=True
        with self.assertRaisesRegex(BackupError,'restore_result_invalid'):
            pipeline.validate(SCOPE,self.store,'1','1','b'*40,'c'*40,**options,restore=lambda *args:{'migration_count':1})
        self.assertEqual(self.store.uploads,['encrypted-backup','backup-manifest']);self.assertFalse(self.store.removed)
        with self.assertRaisesRegex(BackupError,'export_authority'):self.export()
        with self.assertRaisesRegex(BackupError,'retention_authority'):self.retain(self.proof())

    def test_foreign_malformed_incomplete_and_duplicate_inventory_is_never_deletion_evidence(self):
        self.add('2','20250101');original=deepcopy(self.store.objects)
        for change in ['foreign','malformed','incomplete','bad_manifest','bad_archive']:
            with self.subTest(change=change):
                self.store.objects=deepcopy(original)
                archive=self.store.find('encrypted-backup','2','1');description=self.store.find('backup-manifest','2','1')
                if change=='foreign':self.store.objects[archive['id']][0]['properties']['bookingInstallation']='other'
                elif change=='malformed':self.store.objects[archive['id']][0]['properties']=None
                elif change=='incomplete':del self.store.objects[archive['id']]
                elif change=='bad_manifest':self.store.objects[description['id']]=(description,canonical([]))
                else:self.store.objects[archive['id']][0]['size']='9999'
                self.assertEqual(self.inventory(),[]);self.assertFalse(self.store.removed)
        self.store.objects=deepcopy(original);record,body=next(iter(self.store.objects.values()));duplicate=deepcopy(record);duplicate['id']='duplicate-file';self.store.objects['duplicate-file']=(duplicate,body)
        with self.assertRaisesRegex(BackupError,'run_ambiguous'):self.inventory()

    def test_existing_proof_is_revalidated_and_changed_uploaded_proof_never_prunes(self):
        self.export();proof=self.proof();first=self.retain(proof);uploads=list(self.store.uploads)
        self.assertEqual(self.retain(proof),first);self.assertEqual(self.store.uploads,uploads)
        saved=self.store.find('backup-restore-proof','1','1');del self.store.objects[saved['id']]
        original=self.store.download
        def download(record,path,limit=512*1024*1024):
            if record['properties']['purpose']=='backup-restore-proof':path.write_bytes(b'{}')
            else:original(record,path,limit)
        with patch.object(self.store,'download',side_effect=download):
            with self.assertRaisesRegex(BackupError,'proof_readback_mismatch'):self.retain(proof)
        self.assertFalse(self.store.removed)

    def test_document_limit_is_enforced_before_writing(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(pipeline,'MAX_DOCUMENT',8):
            path=Path(directory)/'document.json'
            with self.assertRaisesRegex(BackupError,'document_invalid'):pipeline.save_document(path,{'large':'value'})
            self.assertFalse(path.exists())
