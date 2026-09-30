"""Official pinned PostgreSQL tools; restore checks have no network or app process."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit,parse_qs,unquote
from envelope import BackupError,encrypt,decrypt
from diagnostics import PrivateErrors

IMAGE='postgres@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722'
HOST='ep-dry-hill-b3ujpil7.c-4.ap-southeast-1.aws.neon.tech'
ROLE='sarsa_booking_backup'
ROOT_CA='/etc/ssl/certs/ca-certificates.crt'
CONTAINER_CA='/run/sarsa-backup-ca.pem'
ROOT=Path(__file__).resolve().parents[2]


def database_environment(value):
    try:
        url=urlsplit(value)
        if (url.scheme not in ('postgres','postgresql') or url.hostname!=HOST
                or unquote(url.username or '')!=ROLE or not url.password
                or url.path!='/neondb' or url.port not in (None,5432) or url.fragment
                or set(parse_qs(url.query))-{'sslmode','channel_binding','sslrootcert'}):
            raise ValueError()
        return {'PGHOST':HOST,'PGPORT':'5432','PGDATABASE':'neondb','PGUSER':ROLE,
            'PGPASSWORD':unquote(url.password),'PGSSLMODE':'verify-full','PGSSLROOTCERT':ROOT_CA,
            'PGCHANNELBINDING':'require','PGCONNECT_TIMEOUT':'10',
            'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=120000'}
    except Exception:raise BackupError('backup_database_identity_invalid') from None


def dump_encrypted(dsn,path,key,metadata):
    settings=database_environment(dsn)
    if not Path(ROOT_CA).is_file():raise BackupError('backup_certificate_bundle_unavailable')
    # Slim PostgreSQL images need not contain ca-certificates. Supply the
    # runner's trusted public bundle read-only rather than weakening TLS.
    settings['PGSSLROOTCERT']=CONTAINER_CA
    command=['docker','run','--rm','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
        '--mount','type=bind,src='+ROOT_CA+',dst='+CONTAINER_CA+',readonly']
    for name in settings:command+=['-e',name]
    command += [IMAGE,'pg_dump','--format=custom','--schema=sarsa_booking','--no-owner',
                '--no-privileges','--compress=gzip:6','--lock-wait-timeout=10000','--no-password']
    process=subprocess.Popen(command,env={**os.environ,**settings},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    errors=PrivateErrors(process.stderr)
    deadline=threading.Timer(240,process.kill);deadline.start()
    try:
        with path.open('xb') as output:encrypt(process.stdout,output,key,metadata)
        result=process.wait(timeout=10)
        errors.finish()
        if result!=0:
            print('Export exit status:',result,'; fixed diagnostic clues:',errors.clues(),flush=True)
            raise BackupError(errors.code('dump'))
    finally:
        deadline.cancel();process.stdout.close()
        if process.poll() is None:process.kill();process.wait()
        errors.finish();process.stderr.close()
    with path.open('rb') as source:decrypt(source,key)


def command(args,*,capture=False):
    result=subprocess.run(args,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,timeout=180,check=False)
    if result.returncode:raise BackupError('restore_check_command_failed')
    return result.stdout if capture else None


def restore_check(path,key):
    # Authenticate everything before pg_restore is permitted to receive bytes.
    with path.open('rb') as source:metadata=decrypt(source,key)
    name='sarsa-004-restore-'+secrets.token_hex(8)
    ownership=secrets.token_hex(16)
    try:
        environment={**os.environ,'POSTGRES_PASSWORD':secrets.token_urlsafe(32)}
        result=subprocess.run(['docker','run','--detach','--name',name,'--label','sarsa.backup.restore='+ownership,'--network','none',
            '-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=sarsa_restore_check',IMAGE],env=environment,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120,check=False)
        if result.returncode:raise BackupError('restore_container_start_failed')
        for _ in range(60):
            ready=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres','-d','sarsa_restore_check'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode
            if ready==0:break
            time.sleep(1)
        else:raise BackupError('restore_container_not_ready')
        sql=['docker','exec',name,'psql','-U','postgres','-d','sarsa_restore_check','-v','ON_ERROR_STOP=1','-At','-c']
        command(sql+['CREATE EXTENSION btree_gist'])
        process=subprocess.Popen(['docker','exec','-i',name,'pg_restore','-U','postgres',
            '--dbname=sarsa_restore_check','--no-owner','--no-privileges','--single-transaction','--exit-on-error'],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=threading.Timer(240,process.kill);deadline.start()
        try:
            with path.open('rb') as source:decrypt(source,key,process.stdin)
            process.stdin.close()
            if process.wait(timeout=30)!=0:raise BackupError('postgres_restore_failed')
        finally:
            deadline.cancel()
            if process.poll() is None:process.kill();process.wait()
        raw=command(sql+["SELECT version||'|'||sha256 FROM sarsa_booking.schema_migrations ORDER BY version"],capture=True)
        versions={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/booking_engine/migrations').glob('*.sql')}
        restored=[line.split('|',1) for line in raw.decode().splitlines()]
        if not restored or any(len(row)!=2 or versions.get(row[0])!=row[1] for row in restored):
            raise BackupError('restored_migrations_mismatch')
        # No HTTP worker is started. No provider keys are supplied to the container.
        return {'restored_migrations':len(restored),'day':metadata['day']}
    finally:
        # A timed-out start may still create a container. Verify its exact owner.
        inspection=subprocess.run(['docker','inspect','--format',
            '{{index .Config.Labels "sarsa.backup.restore"}}',name],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=False)
        if inspection.returncode==0 and inspection.stdout.decode().strip()==ownership:
            cleanup=subprocess.run(['docker','rm','--force','--volumes',name],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=30,check=False)
            if cleanup.returncode:raise BackupError('restore_container_cleanup_failed')
