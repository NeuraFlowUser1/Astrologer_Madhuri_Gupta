"""Signature/storage orchestration and recovery-policy failures, without real Drive writes."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,datetime,timezone
from pathlib import Path
import tempfile
import unittest
from appointment_system.backup import pipeline
from appointment_system.backup.protocol import BackupError,canonical,sign,invariant_digest
from appointment_system.backup.retention import Policy
from .backup_fixtures import SCOPE,manifest,record,attestation,proven
from . import test_backup_protocol as crypto_tests

class Storage:
    def __init__(self,reader=False):
        self.identity=SCOPE;self.reader=reader;self.objects={};self.removed=[];self.uploads=[]
    def files(self):return [deepcopy(value[0]) for value in self.objects.values()]
    def checked(self,value):
        from appointment_system.backup.drive import properties,checked_name
        props=value['properties']
        if props!=properties(SCOPE,props['purpose'],props['sourceRun'],props['sourceAttempt']):raise BackupError('wrong_record')
        checked_name(SCOPE,value['name'],props['purpose'],props['sourceRun'],props['sourceAttempt']);return value
    def private(self,identity):
        if identity not in self.objects:raise BackupError('missing_record')
    def find(self,purpose,run,attempt):
        values=[value for value,_ in self.objects.values() if value['properties']['purpose']==purpose and value['properties']['sourceRun']==run and value['properties']['sourceAttempt']==attempt]
        if len(values)>1:raise BackupError('backup_drive_run_ambiguous')
        return deepcopy(values[0]) if values else None
    def download(self,value,path,limit=512*1024*1024):
        body=self.objects[value['id']][1]
        if len(body)>limit:raise BackupError('excess')
        with path.open('xb') as target:target.write(body)
    def upload(self,path,name,purpose,run,attempt):
        if self.reader:raise AssertionError('validator tried a write')
        body=path.read_bytes();value=record(name,purpose,run,attempt,body=body)
        self.objects[value['id']]=(deepcopy(value),body);self.uploads.append(purpose);return deepcopy(value)
    def remove(self,value):
        if self.reader:raise AssertionError('validator tried a delete')
        if self.objects[value['id']][0]!=value:raise BackupError('changed_file')
        self.removed.append(value['id']);del self.objects[value['id']]

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.export_private,self.export_public=crypto_tests.signing();self.validator_private,self.validator_public=crypto_tests.signing()
        self.export_keys={'export':self.export_public};self.validation_keys={'validator':self.validator_public};self.store=Storage()
    def add(self,run,day):
        for value,body in proven(run,day,self.export_private,self.validator_private):self.store.objects[value['id']]=(value,body)
    def export(self):
        self.dumped=0
        def dump(path):
            self.dumped+=1;path.write_bytes(b'synthetic-ciphertext');value=manifest()
            return {'snapshot':'synthetic-snapshot',**{k:value[k] for k in ('postgres_major','migrations','table_counts','restore_generation','generation_sequence')}}
        return pipeline.export(SCOPE,self.store,'1','1','b'*40,export_key_id='export',export_private=self.export_private,export_keys=self.export_keys,dump=dump)
    def proof(self):
        description=self.store.find('backup-manifest','1','1');archive=self.store.find('encrypted-backup','1','1')
        from appointment_system.backup.protocol import unique_json
        envelope=unique_json(self.store.objects[description['id']][1]);return sign(attestation(envelope,archive,description),'validator',self.validator_private,SCOPE)
    def retain(self,proof,policy=None):
        return pipeline.retain(SCOPE,self.store,'1','1','b'*40,proof,export_keys=self.export_keys,validation_keys=self.validation_keys,policy=policy or Policy('recent',15))
    def test_export_readback_is_stored_but_never_its_own_restore_proof(self):
        result=self.export();self.assertEqual(result,{'stored':True,'verified':False,'retention_completed':False})
        self.assertEqual(self.store.uploads,['encrypted-backup','backup-manifest'])
        self.store.uploads.clear();self.assertEqual(self.export(),result);self.assertEqual(self.dumped,0);self.assertFalse(self.store.uploads)
    def test_orphan_and_changed_archive_do_not_create_or_prune(self):
        self.export();archive=self.store.find('encrypted-backup','1','1');del self.store.objects[archive['id']]
        with self.assertRaisesRegex(BackupError,'orphan'):self.export()
        self.assertEqual(self.dumped,0);self.assertFalse(self.store.removed)
        self.store=Storage();self.export();archive=self.store.find('encrypted-backup','1','1')
        self.store.objects[archive['id']]=(archive,b'changed ciphertext!!')
        with self.assertRaises(BackupError):self.export()
    def test_validator_reads_only_and_signs_exact_restore_and_drive_versions(self):
        self.export();self.store.reader=True;calls=[]
        def restore(path,identity,value,key,binary,ledger):
            calls.append((path.read_bytes(),identity,key,ledger));return {'migration_count':1,'invariants_digest':invariant_digest(),'restored_authority':'off_new_generation'}
        signed=pipeline.validate(SCOPE,self.store,'1','1','b'*40,'d'*40,export_keys=self.export_keys,validation_keys=self.validation_keys,
            validation_key_id='validator',validation_private=self.validator_private,recovery_identity='private synthetic recovery authority',binary='synthetic-age',ledger=manifest()['migrations'],restore=restore)
        self.assertEqual(len(calls),1);self.assertEqual(signed['payload']['archive_drive_version'],'1');self.assertEqual(self.store.uploads,['encrypted-backup','backup-manifest'])
        self.assertFalse(self.store.removed)
    def test_failed_restore_or_exporter_signature_cannot_authorize_retention(self):
        self.export();self.store.reader=True
        def fail(*args):raise BackupError('restore_failed')
        with self.assertRaisesRegex(BackupError,'restore_failed'):
            pipeline.validate(SCOPE,self.store,'1','1','b'*40,'d'*40,export_keys=self.export_keys,validation_keys=self.validation_keys,
                validation_key_id='validator',validation_private=self.validator_private,recovery_identity='never exported',binary='synthetic-age',ledger={},restore=fail)
        self.store.reader=False;proof=self.proof();proof['signature']='invalid'
        with self.assertRaises(BackupError):self.retain(proof)
        self.assertFalse(self.store.removed)
    def test_drive_version_change_or_public_key_overlap_cannot_authorize_delete(self):
        self.export();proof=self.proof();archive=self.store.find('encrypted-backup','1','1')
        changed=dict(archive,version='2');self.store.objects[archive['id']]=(changed,self.store.objects[archive['id']][1])
        with self.assertRaisesRegex(BackupError,'file_changed'):self.retain(proof)
        self.validation_keys={'validator':self.export_public}
        with self.assertRaisesRegex(BackupError,'not_separate'):self.retain(proof)
        self.assertFalse(self.store.removed)
    def test_unverified_unknown_or_foreign_backups_are_never_retention_survivors(self):
        self.export();self.retain(self.proof());self.add('2','20250101')
        proof=self.store.find('backup-restore-proof','2','1');self.store.objects[proof['id']]=(proof,b'corrupt unsigned proof')
        with tempfile.TemporaryDirectory() as directory:
            values=pipeline.verified_inventory(SCOPE,self.store,Path(directory),self.export_keys,self.validation_keys)
        self.assertEqual([(value[1],value[2]) for value in values],[('1','1')]);self.assertFalse(self.store.removed)
    def test_prior_release_proof_remains_exact_and_usable_without_allowing_foreign_identity(self):
        from appointment_system.backup.protocol import unique_json
        self.add('2','20250101')
        description=self.store.find('backup-manifest','2','1');archive=self.store.find('encrypted-backup','2','1')
        proof_record=self.store.find('backup-restore-proof','2','1')
        payload=unique_json(self.store.objects[description['id']][1])['payload']
        prior=replace(SCOPE,release_digest='f'*64);payload['release_digest']=prior.release_digest
        envelope=sign(payload,'export',self.export_private,prior)
        proof=attestation(envelope,archive,description);proof['release_digest']=prior.release_digest
        signed=sign(proof,'validator',self.validator_private,prior)
        self.store.objects[description['id']]=(description,canonical(envelope))
        self.store.objects[proof_record['id']]=(proof_record,canonical(signed))
        with tempfile.TemporaryDirectory() as directory:
            values=pipeline.verified_inventory(SCOPE,self.store,Path(directory),self.export_keys,self.validation_keys)
        self.assertEqual([value[1] for value in values],['2'])
        self.assertEqual(signed['payload']['release_digest'],'f'*64)
        foreign=replace(prior,project='other-practice');payload['project']=foreign.project
        # Even independently valid signatures do not make another practice ours.
        envelope=sign(payload,'export',self.export_private,foreign)
        proof=attestation(envelope,archive,description);proof.update(project=foreign.project,release_digest=foreign.release_digest)
        signed=sign(proof,'validator',self.validator_private,foreign)
        self.store.objects[description['id']]=(description,canonical(envelope))
        self.store.objects[proof_record['id']]=(proof_record,canonical(signed))
        with tempfile.TemporaryDirectory() as directory:
            values=pipeline.verified_inventory(SCOPE,self.store,Path(directory),self.export_keys,self.validation_keys)
        self.assertEqual(values,[]);self.assertFalse(self.store.removed)
    def test_retention_needs_newest_proven_copy_and_preserves_two_good_copies(self):
        self.export();self.add('2','20250101');self.add('3','20250102')
        result=self.retain(self.proof(),Policy('recent',2));self.assertEqual(result['removed'],1)
        self.assertTrue(all('-2' in identity for identity in self.store.removed));self.assertEqual(len(self.store.objects),6)
    def test_old_resumed_run_saves_proof_but_cannot_prune_newer_copies(self):
        self.add('1','20250101');self.add('2','20260101');self.add('3','20260201')
        result=self.retain(self.proof(),Policy('recent',2));self.assertFalse(result['retention_completed']);self.assertFalse(self.store.removed)

class RetentionTests(unittest.TestCase):
    def copy(self,run,day):return (datetime.strptime(day,'%Y%m%d').replace(tzinfo=timezone.utc),str(run),'1',{})
    def test_calendar_keeps_30_days_12_month_representatives_and_two_newest(self):
        copies=[self.copy(1,'20261002'),self.copy(2,'20261001'),self.copy(3,'20260903'),self.copy(4,'20260902'),
            self.copy(5,'20260901'),self.copy(6,'20260831'),self.copy(7,'20260801'),self.copy(8,'20251101'),self.copy(9,'20251031')]
        removed=Policy('calendar',2,30,12).remove(copies,('1','1'),date(2026,10,2))
        self.assertEqual([item[1] for item in removed],['9','7','5','4'])
    def test_future_duplicate_absent_and_invalid_policy_cannot_prune(self):
        for values in ({'mode':'unknown','recent_copies':2,'daily_days':0,'monthly_months':0},
            {'mode':'recent','recent_copies':True,'daily_days':0,'monthly_months':0},
            {'mode':'calendar','recent_copies':1,'daily_days':30,'monthly_months':12},{'extra':True}):
            with self.assertRaises(BackupError):Policy.parse(values)
        policy=Policy('recent',2);one=self.copy(1,'20261002')
        for copies,current,today in [([],('1','1'),date(2026,10,2)),([one,one],('1','1'),date(2026,10,2)),
            ([one],('2','1'),date(2026,10,2)),([one],('1','1'),date(2026,10,1))]:
            with self.assertRaises(BackupError):policy.remove(copies,current,today)

if __name__=='__main__':unittest.main()
