"""Separated export, independent validation and proof-dependent retention.

No operation constructs another operation's private keys. The deployment job
supplies only that operation's authority; no archive enters GitHub artifacts.
"""
from datetime import datetime,timezone
from dataclasses import replace
from pathlib import Path
import re
import tempfile
from .protocol import BackupError,MAX_DOCUMENT,canonical,digest,unique_json,stamp,sign,verify,matched_proof
from .age_stream import hashed
from .database import validate_archive
from .retention import Policy

def run_identity(run,attempt,commit):
    if (type(run) is not str or not re.fullmatch('[1-9][0-9]{0,19}',run)
        or type(attempt) is not str or not re.fullmatch('[1-9][0-9]{0,3}',attempt)
        or type(commit) is not str or not re.fullmatch('[a-f0-9]{40}',commit)):
        raise BackupError('backup_source_identity_invalid')
    return run,attempt,commit

def now():return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def document(store,record,directory,label):
    path=directory/label;store.download(record,path,limit=MAX_DOCUMENT)
    return unique_json(path.read_bytes())

def save_document(path,value):
    content=canonical(value)
    if len(content)>MAX_DOCUMENT:raise BackupError('backup_document_invalid')
    with path.open('xb') as target:target.write(content)

def archive_pair(identity,store,run,attempt,commit,directory,keys):
    run_identity(run,attempt,commit)
    archive=store.find('encrypted-backup',run,attempt);description=store.find('backup-manifest',run,attempt)
    if not archive or not description:raise BackupError('backup_export_not_complete')
    envelope=document(store,description,directory,'manifest.json');manifest=verify(envelope,keys,'database-export',identity)
    if (manifest['source_run'],manifest['source_attempt'],manifest['source_commit'])!=(run,attempt,commit):raise BackupError('backup_source_identity_mismatch')
    if archive['name']!=manifest['archive_name'] or description['name']!=archive['name']+'.manifest.json':raise BackupError('backup_archive_identity_mismatch')
    if str(archive.get('size'))!=str(manifest['archive_bytes']):raise BackupError('backup_archive_size_mismatch')
    return archive,description,envelope,manifest

def bound_storage(archive,description,proof):
    expected={'archive_drive_id':archive['id'],'archive_drive_version':archive['version'],
              'manifest_drive_id':description['id'],'manifest_drive_version':description['version']}
    if any(proof.get(key)!=value for key,value in expected.items()):raise BackupError('backup_verified_file_changed')

def export(identity,store,run,attempt,commit,*,export_key_id,export_private,export_keys,dump):
    """dump(path) has read-only DB and public age recipient, no recovery key."""
    run_identity(run,attempt,commit)
    if store.reader or store.identity!=identity:raise BackupError('backup_export_authority_invalid')
    with tempfile.TemporaryDirectory(prefix='appointment-export-') as scratch:
        directory=Path(scratch)
        if store.find('encrypted-backup',run,attempt):
            archive,_,_,manifest=archive_pair(identity,store,run,attempt,commit,directory,export_keys)
            path=directory/'readback.age';store.download(archive,path)
            if hashed(path)!=(manifest['archive_sha256'],manifest['archive_bytes']):raise BackupError('backup_archive_mismatch')
            return {'stored':True,'verified':False,'retention_completed':False}
        if store.find('backup-manifest',run,attempt):raise BackupError('backup_export_orphan_manifest')
        name='appointment-'+identity.installation_id+'-'+run+'-'+attempt+'.dump.age';path=directory/name
        snapshot=dump(path)
        if (type(snapshot) is not dict or set(snapshot)!={'snapshot','postgres_major','migrations','table_counts','restore_generation','generation_sequence'}):
            raise BackupError('backup_snapshot_invalid')
        sha,size=hashed(path)
        manifest=dict(version=1,purpose='database-export',**identity.fields(),source_run=run,source_attempt=attempt,source_commit=commit,
            archive_name=name,archive_sha256=sha,archive_bytes=size,created_at=now(),schemas=['appointment_system'],database_contract=1,
            **{name:value for name,value in snapshot.items() if name!='snapshot'})
        envelope=sign(manifest,export_key_id,export_private,identity);verify(envelope,export_keys,'database-export',identity)
        manifest_path=directory/'new-manifest.json';save_document(manifest_path,envelope)
        archive=store.upload(path,name,'encrypted-backup',run,attempt)
        readback=directory/'readback.age';store.download(archive,readback)
        if hashed(readback)!=(sha,size):raise BackupError('backup_upload_readback_mismatch')
        saved=store.upload(manifest_path,name+'.manifest.json','backup-manifest',run,attempt)
        if document(store,saved,directory,'manifest-readback.json')!=envelope:raise BackupError('backup_manifest_readback_mismatch')
        return {'stored':True,'verified':False,'retention_completed':False}

def validate(identity,store,run,attempt,commit,validator_commit,*,export_keys,validation_keys,
             validation_key_id,validation_private,recovery_identity,binary,ledger,restore=validate_archive):
    run_identity(run,attempt,commit);run_identity(run,attempt,validator_commit)
    if store.reader is not True or store.identity!=identity:raise BackupError('backup_validation_authority_invalid')
    with tempfile.TemporaryDirectory(prefix='appointment-validator-') as scratch:
        directory=Path(scratch)
        archive,description,envelope,manifest=archive_pair(identity,store,run,attempt,commit,directory,export_keys)
        path=directory/'archive.age';store.download(archive,path)
        result=restore(path,identity,manifest,recovery_identity,binary,ledger)
        if type(result) is not dict or set(result)!={'migration_count','invariants_digest','restored_authority'}:
            raise BackupError('backup_restore_result_invalid')
        proof=dict(version=1,purpose='restore-proof',**identity.fields(),manifest_sha256=digest(envelope),archive_sha256=manifest['archive_sha256'],
            source_run=run,source_attempt=attempt,source_commit=commit,validator_commit=validator_commit,verified_at=now(),
            migration_count=result['migration_count'],migration_digest=digest(manifest['migrations']),table_counts_digest=digest(manifest['table_counts']),
            invariants_digest=result['invariants_digest'],restored_authority=result['restored_authority'],
            archive_drive_id=archive['id'],archive_drive_version=archive['version'],manifest_drive_id=description['id'],manifest_drive_version=description['version'])
        signed=sign(proof,validation_key_id,validation_private,identity)
        matched_proof(envelope,signed,export_keys,validation_keys,identity)
        return signed

def verified_inventory(identity,store,directory,export_keys,validation_keys):
    groups={}
    for record in store.files():
        props=record.get('properties')
        if type(props) is not dict or props.get('bookingInstallation')!=identity.installation_id:continue
        try:store.checked(record)
        except BackupError:continue
        group=groups.setdefault((props['sourceRun'],props['sourceAttempt']),{})
        if props['purpose'] in group:raise BackupError('backup_drive_run_ambiguous')
        group[props['purpose']]=record
    verified=[]
    for index,group in enumerate(groups.values()):
        if set(group)!={'encrypted-backup','backup-manifest','backup-restore-proof'}:continue
        try:
            manifest=document(store,group['backup-manifest'],directory,'inventory-'+str(index)+'-manifest.json')
            proof=document(store,group['backup-restore-proof'],directory,'inventory-'+str(index)+'-proof.json')
            # Prior code releases of this explicit database/proof contract can
            # survive retention. Their signed exact release remains in proof;
            # restore promotion still needs its compatible installed reader.
            # Only the release digest varies; owner/install/environment cannot.
            payload=manifest.get('payload') if type(manifest) is dict else None
            if type(payload) is not dict:raise BackupError('backup_manifest_invalid')
            prior_identity=replace(identity,release_digest=payload.get('release_digest'))
            source,validation=matched_proof(manifest,proof,export_keys,validation_keys,prior_identity)
            archive=group['encrypted-backup'];description=group['backup-manifest'];bound_storage(archive,description,validation)
            if archive['name']!=source['archive_name'] or str(archive.get('size'))!=str(source['archive_bytes']):raise BackupError('backup_archive_identity_mismatch')
            for record in group.values():store.private(record['id'])
            verified.append((stamp(source['created_at']),source['source_run'],source['source_attempt'],group))
        except BackupError:continue  # Invalid and older unsupported copies stay stored.
    return sorted(verified,key=lambda item:(item[0],int(item[1]),int(item[2])),reverse=True)

def retain(identity,store,run,attempt,commit,signed,*,export_keys,validation_keys,policy):
    run_identity(run,attempt,commit)
    if (store.reader or store.identity!=identity or type(policy) is not Policy):
        raise BackupError('backup_retention_authority_invalid')
    with tempfile.TemporaryDirectory(prefix='appointment-retention-') as scratch:
        directory=Path(scratch)
        archive,description,envelope,_=archive_pair(identity,store,run,attempt,commit,directory,export_keys)
        _,proof=matched_proof(envelope,signed,export_keys,validation_keys,identity);bound_storage(archive,description,proof)
        saved=store.find('backup-restore-proof',run,attempt)
        if saved:
            prior=document(store,saved,directory,'previous-proof.json')
            _,prior_proof=matched_proof(envelope,prior,export_keys,validation_keys,identity);bound_storage(archive,description,prior_proof)
        else:
            path=directory/'new-proof.json';save_document(path,signed)
            saved=store.upload(path,archive['name']+'.restore.json','backup-restore-proof',run,attempt)
            if document(store,saved,directory,'proof-readback.json')!=signed:raise BackupError('backup_restore_proof_readback_mismatch')
        candidates=verified_inventory(identity,store,directory,export_keys,validation_keys)
        current=(run,attempt)
        removals=policy.remove(candidates,current,datetime.now(timezone.utc).date())
        if removals is None:
            return {'stored':True,'verified':True,'retention_completed':False,'removed':0}
        removed=0
        for _,_,_,group in removals:
            for purpose in ('encrypted-backup','backup-manifest','backup-restore-proof'):store.remove(group[purpose])
            removed+=1
        return {'stored':True,'verified':True,'retention_completed':True,'removed':removed}
