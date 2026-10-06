"""Three executable duties with disjoint private credentials and exact run provenance."""
import argparse
import base64
import os
from pathlib import Path
import sys

_source=Path(__file__).absolute()
if any(path.is_symlink() for path in (_source,*_source.parents)):raise SystemExit('backup_package_path_invalid')
ROOT=_source.resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))

from tools.install.package import verify,PackageError
from tools.automation.eligibility import runner,source_run,repository_name
from appointment_system.configuration import load,installation
from appointment_system.backup.protocol import Identity,BackupError,unique_json,canonical,keyring
from appointment_system.backup import pipeline
from appointment_system.backup.retention import Policy

COMMON={'BOOKING_PROFILE','BOOKING_BACKUP_EXPORT_VERIFY_KEYS','BOOKING_BACKUP_VALIDATION_VERIFY_KEYS'}
PRIVATE={
 'export':{'BOOKING_BACKUP_DATABASE_URL','BOOKING_BACKUP_DRIVE_WRITER','BOOKING_BACKUP_AGE_RECIPIENT',
           'BOOKING_BACKUP_EXPORT_SIGNING_KEY','BOOKING_BACKUP_EXPORT_KEY_ID'},
 'validate':{'BOOKING_BACKUP_DRIVE_READER','BOOKING_BACKUP_AGE_IDENTITY',
             'BOOKING_BACKUP_VALIDATION_SIGNING_KEY','BOOKING_BACKUP_VALIDATION_KEY_ID'},
 'retain':{'BOOKING_BACKUP_DRIVE_WRITER','BOOKING_RESTORE_PROOF'},
}

def bounded_file(path,maximum):
    path=Path(path)
    if any(part.is_symlink() for part in (path,*path.parents)) or not path.is_file() or path.stat().st_size>maximum:raise BackupError('backup_input_file_invalid')
    with path.open('rb') as source:
        value=source.read(maximum+1)
    if len(value)>maximum:raise BackupError('backup_input_file_invalid')
    return value

def settings(source,mode):
    if mode not in PRIVATE or any(name.startswith('PG') and value for name,value in source.items()):raise BackupError('backup_ambient_authority_rejected')
    allowed=COMMON|PRIVATE[mode]
    if any(name.startswith('BOOKING_') and value and name not in allowed for name,value in source.items()):raise BackupError('backup_wrong_duty_authority')
    if any(type(source.get(name)) is not str or not 1<=len(source[name])<=65536 for name in allowed):raise BackupError('backup_setting_missing')
    export=keyring(unique_json(source['BOOKING_BACKUP_EXPORT_VERIFY_KEYS']));validation=keyring(unique_json(source['BOOKING_BACKUP_VALIDATION_VERIFY_KEYS']))
    if set(export.values())&set(validation.values()):raise BackupError('backup_signing_authority_not_separate')
    return export,validation

def public_settings(profile):
    path=Path(profile)
    # Operational public facts travel with the project, outside the hashed package.
    if (path.name!='project.json' or path.parent.name!='appointment-settings'
        or any(part.is_symlink() for part in (path,*path.parents))
        or path.resolve()!=ROOT.parent/'appointment-settings/project.json'):
        raise BackupError('backup_profile_path_invalid')
    load(path)
    value=unique_json(bounded_file(path.with_name('backup.json'),65536));facts=installation()
    if (type(value) is not dict or set(value)!={'version','installation_id','environment','owner_email','folder','folder_name','repository','cron','retention'}
        or type(value['version']) is not int or value['version']!=1 or value['installation_id']!=facts['installation_id']
        or value['environment']!=facts['environment'] or value['owner_email']!=facts['owners']['client_email']
        or type(value['cron']) is not str or value['cron'] not in ('37 1 * * *','2 3 * * *')):
        raise BackupError('backup_public_settings_invalid')
    repository_name(value['repository']);Policy.parse(value['retention'])
    from appointment_system.backup.drive import file_id
    file_id(value['folder'])
    if type(value['folder_name']) is not str or not 1<=len(value['folder_name'])<=180:raise BackupError('backup_public_settings_invalid')
    return value

def github_read(path,repository,token,client):
    import httpx
    try:
        if type(token) is not str or not 1<=len(token)<=8192:raise ValueError()
        body=bytearray()
        with client.stream('GET','https://api.github.com/repos/'+repository+('/'+path if path else ''),headers={
            'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}) as response:
            response.raise_for_status()
            for block in response.iter_bytes():
                body.extend(block)
                if len(body)>65536:raise ValueError()
        return unique_json(bytes(body))
    except BackupError:raise
    except Exception:raise BackupError('backup_github_identity_unavailable') from None

def checked_source(source,event,config,mode,arguments):
    import httpx
    from tools.automation.eligibility import eligible
    runner(source,config['repository'],event)
    event_name=source.get('GITHUB_EVENT_NAME')
    if mode=='export':
        if event_name not in ('schedule','workflow_dispatch') or event_name=='schedule' and event.get('schedule')!=config['cron']:
            raise BackupError('backup_export_trigger_rejected')
        result=pipeline.run_identity(source.get('GITHUB_RUN_ID'),source.get('GITHUB_RUN_ATTEMPT'),source.get('GITHUB_SHA'))
    else:
        if event_name not in ('workflow_run','workflow_dispatch'):raise BackupError('backup_validator_trigger_rejected')
        requested=event.get('workflow_run',{}).get('id') if event_name=='workflow_run' else event.get('inputs',{}).get('source_run')
        if str(requested)!=arguments.source_run:raise BackupError('backup_validator_trigger_rejected')
        result=pipeline.run_identity(arguments.source_run,arguments.source_attempt,arguments.source_commit)
    with httpx.Client(timeout=httpx.Timeout(10,connect=3),follow_redirects=False,trust_env=False) as client:
        repository=github_read('',config['repository'],source.get('GITHUB_TOKEN'),client);eligible(repository,config['repository'])
        if mode!='export':
            remote=github_read('actions/runs/'+result[0],config['repository'],source.get('GITHUB_TOKEN'),client)
            if source_run(remote,repository,config['repository'],result[0])!=result:raise BackupError('backup_source_identity_mismatch')
    return result

def main(argv=None,source=None):
    parser=argparse.ArgumentParser(description='Export, independently restore-check, or prune proven encrypted appointment backups.')
    parser.add_argument('mode',choices=PRIVATE);parser.add_argument('--source-run');parser.add_argument('--source-attempt');parser.add_argument('--source-commit')
    parser.add_argument('--age-binary',default=str(ROOT/'tools/automation/bin/age'))
    args=parser.parse_args(argv);source=os.environ if source is None else source
    os.umask(0o077)
    export_keys,validation_keys=settings(source,args.mode)
    release=verify(ROOT);config=public_settings(source['BOOKING_PROFILE'])
    event=unique_json(bounded_file(source.get('GITHUB_EVENT_PATH',''),65536))
    run,attempt,commit=checked_source(source,event,config,args.mode,args)
    facts=installation();identity=Identity(facts['installation_id'],facts['project_id'],facts['environment'],config['owner_email'],release['content_digest'])
    from appointment_system.backup.drive import Drive
    reader=args.mode=='validate';grant=unique_json(source['BOOKING_BACKUP_DRIVE_READER' if reader else 'BOOKING_BACKUP_DRIVE_WRITER'])
    store=Drive(identity,grant,config['folder'],config['folder_name'],reader=reader)
    try:
        if args.mode=='export':
            from appointment_system.backup.database import migration_hashes,export_age
            ledger=migration_hashes(ROOT/'engine/appointment_system/migrations')
            tables=unique_json(bounded_file(ROOT/'database/relations.json',65536))
            result=pipeline.export(identity,store,run,attempt,commit,export_key_id=source['BOOKING_BACKUP_EXPORT_KEY_ID'],export_private=source['BOOKING_BACKUP_EXPORT_SIGNING_KEY'],export_keys=export_keys,
                dump=lambda path:export_age(source['BOOKING_BACKUP_DATABASE_URL'],identity,ledger,tables,path,source['BOOKING_BACKUP_AGE_RECIPIENT'],args.age_binary))
        elif args.mode=='validate':
            from appointment_system.backup.database import migration_hashes
            signed=pipeline.validate(identity,store,run,attempt,commit,source.get('GITHUB_SHA'),export_keys=export_keys,validation_keys=validation_keys,
                validation_key_id=source['BOOKING_BACKUP_VALIDATION_KEY_ID'],validation_private=source['BOOKING_BACKUP_VALIDATION_SIGNING_KEY'],
                recovery_identity=source['BOOKING_BACKUP_AGE_IDENTITY'],binary=args.age_binary,ledger=migration_hashes(ROOT/'engine/appointment_system/migrations'))
            output=source.get('GITHUB_OUTPUT')
            if type(output) is not str or not output:raise BackupError('backup_output_missing')
            with open(output,'a',encoding='utf-8') as target:target.write('restore_proof='+base64.b64encode(canonical(signed)).decode()+'\n')
            result={'stored':True,'verified':True,'retention_completed':False}
        else:
            try:signed=unique_json(base64.b64decode(source['BOOKING_RESTORE_PROOF'],validate=True))
            except (ValueError,TypeError):raise BackupError('backup_restore_proof_invalid') from None
            result=pipeline.retain(identity,store,run,attempt,commit,signed,export_keys=export_keys,validation_keys=validation_keys,policy=Policy.parse(config['retention']))
        print(canonical(result).decode());return result
    finally:store.close()

if __name__=='__main__':
    try:main()
    except (BackupError,PackageError) as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_operation_failed') from None
