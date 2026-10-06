"""Consistent read-only export and network-isolated independent restore proof."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import re
import secrets
import subprocess
import threading
import time
from uuid import uuid4
import certifi
import psycopg
from psycopg import sql
from ..configuration import installation
from ..connection import checked_config,StorageUnavailable
from .protocol import BackupError,checked,canonical,digest,unique_json
from .snapshot import capture
from .age_stream import encrypt,hashed,stop,authenticated_archive,restore_stream

IMAGES={16:'postgres@sha256:efedf3595f1d6f415c08568ba171029bf54052e754cc9f030e3f2412b21f3d67',
        18:'postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'}
DOCKER=['docker','--host','unix:///var/run/docker.sock']
LABEL='appointment.backup.validator'
SAFE_ENV=lambda:{key:os.environ[key] for key in ('PATH','LANG','LC_ALL') if key in os.environ}

def migration_hashes(root):
    paths=sorted(Path(root).glob('[0-9][0-9][0-9]_*.sql'))
    if not paths or any(path.is_symlink() for path in paths):raise BackupError('backup_release_migrations_invalid')
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

@contextmanager
def source_connection(dsn):
    try:
        target=installation()['database_targets']['backup'];config=checked_config(dsn,target['host'],purpose='backup')
        config.update(sslmode='verify-full',sslrootcert=certifi.where(),channel_binding='require',connect_timeout=3,
            options='-c default_transaction_read_only=on -c lock_timeout=2000',prepare_threshold=None)
        with psycopg.connect(**config) as connection:
            with connection.transaction():yield connection,config
    except BackupError:raise
    except (StorageUnavailable,psycopg.Error):raise BackupError('backup_snapshot_unavailable') from None

def start_dump(config,snapshot):
    major=snapshot['postgres_major'];certificate=Path(config['sslrootcert']).resolve()
    if major not in IMAGES or not certificate.is_file():raise BackupError('backup_dump_tool_invalid')
    settings={'PGHOST':config['host'],'PGPORT':config.get('port','5432'),'PGDATABASE':config['dbname'],
        'PGUSER':config['user'],'PGPASSWORD':config['password'],'PGSSLMODE':'verify-full',
        'PGSSLROOTCERT':'/run/appointment-ca.pem','PGCHANNELBINDING':'require','PGCONNECT_TIMEOUT':'3',
        'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=120000 -c lock_timeout=2000'}
    args=DOCKER+['run','--rm','--read-only','--memory=256m','--cpus=1','--pids-limit=64',
        '--cap-drop=ALL','--security-opt=no-new-privileges','--mount','type=bind,src='+str(certificate)+',dst=/run/appointment-ca.pem,readonly']
    for name in settings:args+=['-e',name]
    args+=[IMAGES[major],'pg_dump','--format=custom','--compress=gzip:6','--schema=appointment_system',
        '--snapshot='+snapshot['snapshot'],'--no-owner','--no-privileges','--no-password','--lock-wait-timeout=2000']
    try:return subprocess.Popen(args,env=SAFE_ENV()|settings,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    except OSError:raise BackupError('backup_dump_start_failed') from None

def export_connection(connection,identity,ledger,tables,destination,recipient,binary,*,dump_factory):
    """Native proof may supply its labelled local dump process; serving cannot."""
    snapshot=capture(connection,identity,ledger,tables)
    process=dump_factory(snapshot);timer=threading.Timer(240,stop,args=(process,));timer.start()
    try:
        encrypt(process.stdout,destination,recipient,binary)
        if process.wait(timeout=10):raise BackupError('backup_dump_failed')
        return snapshot
    except BackupError:
        Path(destination).unlink(missing_ok=True);raise
    except (OSError,subprocess.SubprocessError):
        Path(destination).unlink(missing_ok=True);raise BackupError('backup_dump_failed') from None
    finally:timer.cancel();process.stdout.close();stop(process);process.wait(timeout=10)

def export_age(dsn,identity,ledger,tables,destination,recipient,binary):
    with source_connection(dsn) as (connection,config):
        return export_connection(connection,identity,ledger,tables,destination,recipient,binary,
            dump_factory=lambda snapshot:start_dump(config,snapshot))

class IsolatedPostgres:
    """Always a new owned container: no host DSN or arbitrary cleanup target."""
    def __init__(self,major):
        if type(major) is not int or major not in IMAGES:raise BackupError('backup_database_version_invalid')
        self.major=major;self.name='appointment-restore-'+secrets.token_hex(8);self.owner=secrets.token_hex(16)
        self.started=False

    def run(self,args,*,body=None,capture=False,timeout=30,limit=65536):
        try:
            result=subprocess.run(DOCKER+args,input=body,env=SAFE_ENV(),stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=timeout)
            if result.returncode or capture and len(result.stdout)>limit:raise BackupError('backup_restore_command_failed')
            return result.stdout if capture else None
        except (OSError,subprocess.SubprocessError):raise BackupError('backup_restore_command_failed') from None

    def query(self,statement):
        output=self.run(['exec','--user','postgres',self.name,'psql','-X','-U','postgres','-d','appointment_restore',
            '-v','ON_ERROR_STOP=1','-Atq','-c',statement],capture=True)
        return output.decode().strip()

    def __enter__(self):
        try:
            password=secrets.token_urlsafe(32)
            args=DOCKER+['run','--detach','--name',self.name,'--label',LABEL+'='+self.owner,'--network','none',
                '--user=postgres','--read-only','--memory=1g','--cpus=1','--pids-limit=128','--shm-size=64m',
                '--cap-drop=ALL','--security-opt=no-new-privileges',
                '--tmpfs','/tmp:rw,noexec,nosuid,size=1073741824,mode=1777',
                '--tmpfs','/var/run/postgresql:rw,noexec,nosuid,size=16777216,mode=1777',
                '-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=appointment_restore','-e','PGDATA=/tmp/appointment-data',IMAGES[self.major]]
            created=subprocess.run(args,env=SAFE_ENV()|{'POSTGRES_PASSWORD':password},stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=45)
            if created.returncode:raise BackupError('backup_restore_start_failed')
            self.started=True;deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                logs=self.run(['logs',self.name],capture=True,limit=262144)
                ready=subprocess.run(DOCKER+['exec',self.name,'pg_isready','-U','postgres','-d','appointment_restore'],
                    env=SAFE_ENV(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                if b'init process complete' in logs and ready.returncode==0:break
                time.sleep(.25)
            else:raise BackupError('backup_restore_not_ready')
            self.query('CREATE EXTENSION btree_gist; CREATE ROLE appointment_system_owner NOLOGIN;')
            return self
        except (OSError,subprocess.SubprocessError):
            self.close();raise BackupError('backup_restore_start_failed') from None
        except BackupError:self.close();raise

    def close(self):
        inspected=subprocess.run(DOCKER+['inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',self.name],
            env=SAFE_ENV(),capture_output=True,timeout=15)
        if inspected.returncode==0:
            if inspected.stdout.decode().strip()!=self.owner:raise BackupError('backup_restore_cleanup_refused')
            self.run(['rm','--force','--volumes',self.name])
        remaining=self.run(['ps','--all','--filter','name=^/'+self.name+'$','--format','{{.Names}}'],capture=True)
        if remaining:raise BackupError('backup_restore_cleanup_unconfirmed')
        self.started=False

    def __exit__(self,*_):self.close()

    def load(self,archive):
        try:
            process=subprocess.Popen(DOCKER+['exec','-i','--user','postgres',self.name,'pg_restore','-U','postgres',
                '-d','appointment_restore','--no-owner','--no-privileges','--single-transaction','--exit-on-error'],
                env=SAFE_ENV(),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:raise BackupError('backup_restore_command_failed') from None
        timer=threading.Timer(240,stop,args=(process,));timer.start()
        try:
            restore_stream(archive,process.stdin);process.stdin.close()
            if process.wait(timeout=10):raise BackupError('backup_restore_failed')
        finally:
            timer.cancel()
            if not process.stdin.closed:
                try:process.stdin.close()
                except OSError:pass
            stop(process);process.wait(timeout=10)

INVARIANTS="""SELECT jsonb_build_object(
 'confirmed_without_matching_payment',(SELECT count(*) FROM appointment_system.bookings b
  WHERE b.state='confirmed' AND NOT EXISTS(SELECT 1 FROM appointment_system.accepted_payments a
   JOIN appointment_system.payment_observations p ON p.id=a.observation_id
   WHERE a.booking_id=b.id AND p.amount_paise=b.amount_paise AND p.currency=b.currency AND p.status='captured')),
 'active_claim_wrong_state',(SELECT count(*) FROM appointment_system.slot_claims c JOIN appointment_system.bookings b ON b.id=c.booking_id
  WHERE c.released_at IS NULL AND b.state NOT IN ('held','confirmed')),
 'live_booking_missing_claim',(SELECT count(*) FROM appointment_system.bookings b WHERE b.state IN ('held','confirmed')
  AND NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims c WHERE c.booking_id=b.id AND c.released_at IS NULL)),
 'overlapping_claims',(SELECT count(*) FROM appointment_system.slot_claims a JOIN appointment_system.slot_claims b ON a.id<b.id
  AND a.released_at IS NULL AND b.released_at IS NULL AND tstzrange(a.starts_at,a.ends_at,'[)')&&tstzrange(b.starts_at,b.ends_at,'[)')),
 'foreign_context_pointer',(SELECT count(*) FROM appointment_system.checkout_contexts c JOIN appointment_system.bookings b ON b.id=c.active_checkout_id WHERE c.id<>b.context_id),
 'unvalidated_constraints',(SELECT count(*) FROM pg_constraint WHERE connamespace='appointment_system'::regnamespace AND NOT convalidated)
);"""

def validate_archive(path,identity,manifest,private_identity,binary,ledger):
    checked(manifest,'database-export',identity)
    if manifest['migrations']!=ledger:raise BackupError('backup_release_migrations_mismatch')
    with authenticated_archive(path,private_identity,binary,manifest['archive_sha256'],manifest['archive_bytes']) as archive:
        with IsolatedPostgres(manifest['postgres_major']) as target:
            target.load(archive)
            restored=unique_json(target.query("SELECT coalesce(jsonb_object_agg(version,sha256),'{}'::jsonb) FROM appointment_system.schema_migrations;"))
            if restored!=ledger:raise BackupError('backup_restored_migrations_mismatch')
            names=unique_json(target.query("SELECT jsonb_agg(n.nspname||'.'||c.relname ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='appointment_system' AND c.relkind IN ('r','p') AND NOT c.relispartition;"))
            if set(names)!=set(manifest['table_counts']):raise BackupError('backup_restored_relations_mismatch')
            deadline=time.monotonic()+30
            for table,count in manifest['table_counts'].items():
                if time.monotonic()>deadline:raise BackupError('backup_restore_count_timeout')
                schema,name=table.split('.')
                query=sql.SQL("SET statement_timeout='3s'; SELECT count(*) FROM {}.{}").format(sql.Identifier(schema),sql.Identifier(name)).as_string()
                if target.query(query)!=str(count):raise BackupError('backup_restore_counts_mismatch')
            invariants=unique_json(target.query(INVARIANTS))
            from .protocol import INVARIANT_NAMES
            if (type(invariants) is not dict or set(invariants)!=set(INVARIANT_NAMES)
                or any(type(n) is not int or n!=0 for n in invariants.values())):raise BackupError('backup_restored_invariants_failed')
            config=unique_json(target.query('SELECT appointment_system.control_snapshot();'))
            if (config['installation_id']!=identity.installation_id or config['project']!=identity.project or config['environment']!=identity.environment
                or config['restore_generation']!=manifest['restore_generation'] or config['generation_sequence']!=manifest['generation_sequence']):
                raise BackupError('backup_restored_identity_mismatch')
            target.query('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA appointment_system FROM PUBLIC; REVOKE ALL ON SCHEMA appointment_system FROM PUBLIC;')
            operation=str(uuid4())
            query=sql.SQL('SELECT appointment_system.control_restore_barrier({},{}::jsonb)').format(sql.Literal(operation),sql.Literal(canonical(config).decode())).as_string()
            recovered=unique_json(target.query(query))['snapshot']
            if (recovered['enabled'] is not False or recovered['restore_generation']==config['restore_generation']
                or int(recovered['generation_sequence'])!=int(config['generation_sequence'])+1
                or target.query('SELECT enabled OR requested_enabled FROM appointment_system.control_product_state WHERE singleton;')!='f'):
                raise BackupError('backup_restore_barrier_failed')
            return {'migration_count':len(ledger),'invariants_digest':digest(invariants),'restored_authority':'off_new_generation'}
