"""Reserved example identities and synthetic encrypted archive bytes only."""
from datetime import datetime,timezone
import hashlib
from appointment_system.backup.protocol import Identity,digest,sign,canonical,invariant_digest
from appointment_system.backup.drive import properties
from .test_backup_protocol import signing

OWNER='practice@example.test'
SCOPE=Identity('891d05ec-8ab2-4a87-b537-1c30f2b694b6','example-practice','test',OWNER,'a'*64)
FOLDER='synthetic-folder'
FOLDER_NAME='Example Practice encrypted backups'

def manifest(run='1',attempt='1',day='20260101'):
    return dict(version=1,purpose='database-export',**SCOPE.fields(),source_run=run,source_attempt=attempt,source_commit='b'*40,
        archive_name='appointment-'+SCOPE.installation_id+'-'+run+'-'+attempt+'.dump.age',
        archive_sha256=hashlib.sha256(b'synthetic-ciphertext').hexdigest(),archive_bytes=20,
        created_at=day[:4]+'-'+day[4:6]+'-'+day[6:]+'T00:00:00Z',postgres_major=16,schemas=['appointment_system'],
        migrations={'001_initial.sql':'c'*64},table_counts={'appointment_system.installation':1,'appointment_system.control_product_state':1},
        restore_generation='f9f99e48-9c93-4c5e-8786-ab58aa81637d',generation_sequence='1',database_contract=1)

def record(name,purpose,run='1',attempt='1',identity=None,body=b'synthetic-ciphertext'):
    return {'id':identity or 'synthetic-'+purpose+'-'+run,'name':name,'mimeType':'application/octet-stream',
        'parents':[FOLDER],'owners':[{'emailAddress':OWNER}],'trashed':False,
        'properties':properties(SCOPE,purpose,run,attempt),'size':str(len(body)),
        'md5Checksum':hashlib.md5(body,usedforsecurity=False).hexdigest(),'version':'1'}

def attestation(envelope,archive,manifest_record):
    value=envelope['payload']
    return dict(version=1,purpose='restore-proof',**SCOPE.fields(),manifest_sha256=digest(envelope),archive_sha256=value['archive_sha256'],
        source_run=value['source_run'],source_attempt=value['source_attempt'],source_commit=value['source_commit'],validator_commit='d'*40,
        verified_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),migration_count=len(value['migrations']),
        migration_digest=digest(value['migrations']),table_counts_digest=digest(value['table_counts']),invariants_digest=invariant_digest(),
        restored_authority='off_new_generation',archive_drive_id=archive['id'],archive_drive_version=archive['version'],
        manifest_drive_id=manifest_record['id'],manifest_drive_version=manifest_record['version'])

def proven(run,day,export_private,validation_private):
    value=manifest(run,day=day);name=value['archive_name']
    archive=record(name,'encrypted-backup',run);value['archive_bytes']=int(archive['size'])
    export=sign(value,'export',export_private,SCOPE)
    description=record(name+'.manifest.json','backup-manifest',run,body=canonical(export))
    proof=sign(attestation(export,archive,description),'validator',validation_private,SCOPE)
    validation=record(name+'.restore.json','backup-restore-proof',run,body=canonical(proof))
    return [(archive,b'synthetic-ciphertext'),(description,canonical(export)),(validation,canonical(proof))]
