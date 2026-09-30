"""Daily encrypted backup with approved-owner check, Drive readback and isolated restore."""
from datetime import datetime,timezone,date
import json
import os
from pathlib import Path
import tempfile
import re
from envelope import BackupError,decode_key,decrypt
from drive import Drive
from postgres import dump_encrypted,restore_check
from retention import checked_record


def main():
    os.umask(0o077)
    key=decode_key(os.environ['SARSA_BACKUP_ENCRYPTION_KEY'])
    grant=json.loads(os.environ['SARSA_BACKUP_GOOGLE'])
    day=datetime.now(timezone.utc).date().isoformat()
    kind=os.environ.get('SARSA_BACKUP_KIND','daily') or 'daily'
    revision=os.environ.get('GITHUB_SHA','')
    if kind not in ('daily','checkpoint') or (kind=='checkpoint' and not re.fullmatch(r'[a-f0-9]{40}',revision)):
        raise BackupError('backup_kind_invalid')
    drive=Drive(grant)
    try:
        folder=drive.folder()
        with tempfile.TemporaryDirectory(prefix='sarsa-004-encrypted-') as temporary:
            path=Path(temporary)/'backup.aesgcm'
            existing=drive.existing(folder,day,kind,revision)
            if existing:
                checked_record(existing,folder)
                drive.download(existing,path)
                with path.open('rb') as source:manifest=decrypt(source,key)
                if manifest.get('day')!=day:raise BackupError('backup_day_mismatch')
                if kind=='checkpoint' and (manifest.get('kind')!=kind or manifest.get('source_commit')!=revision):
                    raise BackupError('backup_checkpoint_mismatch')
                proof=restore_check(path,key,require_current=kind=='checkpoint')
                record=existing
                print('Existing backup verified; isolated restore passed. No second copy created.')
            else:
                metadata={'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':day,
                    'created_at':datetime.now(timezone.utc).isoformat(),'kind':kind}
                if kind=='checkpoint':metadata['source_commit']=revision
                dump_encrypted(os.environ['SARSA_BACKUP_DATABASE_URL'],path,key,metadata)
                proof=restore_check(path,key,require_current=True)
                record=drive.upload(path,folder,day,kind,revision)
                # Independent readback verifies the stored encrypted bytes and tag.
                readback=Path(temporary)/'readback.aesgcm'
                drive.download(record,readback)
                with readback.open('rb') as source:confirmed=decrypt(source,key)
                if confirmed!=metadata:raise BackupError('backup_readback_mismatch')
                print('Encrypted Sarsa backup uploaded and read back; isolated restore passed.')
            print('Restored migration records:',proof['restored_migrations'])
            record=drive.mark_verified(record,folder,proof)
            removed=drive.retain(folder,date.fromisoformat(day),record)
            print('Approved retention completed; older verified copies removed:',removed)
    finally:drive.close()

if __name__=='__main__':
    try:main()
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_failed: inspect protected configuration and service availability; no private data logged') from None
