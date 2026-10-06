"""Explicit historical reader only; original literal formats must not change.
Source SHA256: 4f395c5cccc8f411d28977ebaf108974016317b89275824ec777c68eb0762d6f
"""
from .protocol import BackupError
"""Canonical Ed25519 provenance and restore proofs; never accepts archive code."""
import base64
from datetime import datetime,timezone,timedelta
import hashlib
import json
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PROJECT='003-astroadvice-by-kundan-singh'
PURPOSE='database-export'
MAX_BYTES=512*1024*1024
MAX_MANIFEST=65536
SCHEMAS=['public','booking_control']
PREFIX=b'neuraflow-booking-backup:003:production:v1:'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def unique_json(value):
    def pairs(values):
        result={}
        for name,item in values:
            if name in result:raise ValueError()
            result[name]=item
        return result
    try:
        if not isinstance(value,(str,bytes)) or len(value)>MAX_MANIFEST:raise ValueError()
        return json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,TypeError,UnicodeError,RecursionError):raise BackupError('backup_document_invalid') from None

def decode(value,size):
    try:
        if not isinstance(value,str):raise ValueError()
        result=base64.b64decode(value,altchars=b'-_',validate=True)
        if len(result)!=size or base64.urlsafe_b64encode(result).decode()!=value:raise ValueError()
        return result
    except Exception:raise BackupError('backup_key_invalid') from None

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}',value):raise BackupError('backup_key_identity_invalid')
    return value

def stamp(value):
    try:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value):raise ValueError()
        instant=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        if instant>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError()
        return instant
    except (ValueError,TypeError):raise BackupError('backup_time_invalid') from None

def hexadecimal(value,size=64):
    return isinstance(value,str) and re.fullmatch(r'[a-f0-9]{'+str(size)+'}',value) is not None

def filename(value):
    if not isinstance(value,str) or not re.fullmatch(r'astro-advice-\d{8}T\d{6}Z-[1-9][0-9]{0,19}-[1-9][0-9]{0,3}\.dump\.age',value):raise BackupError('backup_filename_invalid')
    return value

def checked_manifest(value):
    fields={'version','purpose','project','environment','source_commit','source_run','source_attempt','archive_name','archive_sha256','archive_bytes','created_at','postgres_major','schemas','migrations','table_counts'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['version']) is not int or value['version']!=1 or value['purpose']!=PURPOSE or value['project']!=PROJECT or value['environment']!='production':raise BackupError('backup_identity_invalid')
    if (not hexadecimal(value['source_commit'],40) or not isinstance(value['source_run'],str) or not re.fullmatch(r'[1-9][0-9]{0,19}',value['source_run']) or not hexadecimal(value['archive_sha256']) or type(value['archive_bytes']) is not int or not 0<value['archive_bytes']<=MAX_BYTES or type(value['postgres_major']) is not int or value['postgres_major']!=16 or value['schemas']!=SCHEMAS):raise BackupError('backup_manifest_invalid')
    filename(value['archive_name']);stamp(value['created_at'])
    if not isinstance(value['source_attempt'],str) or not re.fullmatch(r'[1-9][0-9]{0,3}',value['source_attempt']) or not value['archive_name'].endswith('-'+value['source_run']+'-'+value['source_attempt']+'.dump.age'):raise BackupError('backup_run_identity_invalid')
    migrations=value['migrations'];counts=value['table_counts']
    if not isinstance(migrations,dict) or not 1<=len(migrations)<=500 or not all(isinstance(name,str) and re.fullmatch(r'\d{3}_[a-z0-9_]+\.sql',name) and hexadecimal(sha) for name,sha in migrations.items()):raise BackupError('backup_migrations_invalid')
    if not isinstance(counts,dict) or not 1<=len(counts)<=250 or counts.get('booking_control.product_state')!=1 or not all(isinstance(name,str) and re.fullmatch(r'(?:public|booking_control)\.[a-z][a-z0-9_]{0,62}',name) and type(count) is int and 0<=count<=9223372036854775807 for name,count in counts.items()):raise BackupError('backup_counts_invalid')
    if len(canonical(value))>MAX_MANIFEST-512:raise BackupError('backup_document_invalid')
    return value

def checked_attestation(value):
    fields={'version','purpose','project','environment','manifest_sha256','archive_sha256','source_run','source_attempt','source_commit','validator_commit','verified_at','migration_count','migration_digest','table_counts_digest','control_included','restored_authority','archive_drive_id','archive_drive_version','manifest_drive_id','manifest_drive_version'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['version']) is not int or value['version']!=1 or value['purpose']!='restore-proof' or value['project']!=PROJECT or value['environment']!='production':raise BackupError('backup_attestation_invalid')
    if any(not hexadecimal(value[n]) for n in ('manifest_sha256','archive_sha256','migration_digest','table_counts_digest')) or any(not hexadecimal(value[n],40) for n in ('source_commit','validator_commit')) or not isinstance(value['source_run'],str) or not re.fullmatch(r'[1-9][0-9]{0,19}',value['source_run']) or type(value['migration_count']) is not int or not 1<=value['migration_count']<=500 or value['control_included'] is not True or value['restored_authority']!='off_new_generation':raise BackupError('backup_attestation_invalid')
    if not isinstance(value['source_attempt'],str) or not re.fullmatch(r'[1-9][0-9]{0,3}',value['source_attempt']):raise BackupError('backup_run_identity_invalid')
    if any(not isinstance(value[n],str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,180}',value[n]) for n in ('archive_drive_id','manifest_drive_id')) or any(not isinstance(value[n],str) or not re.fullmatch(r'[1-9][0-9]{0,19}',value[n]) for n in ('archive_drive_version','manifest_drive_version')):raise BackupError('backup_attestation_storage_invalid')
    stamp(value['verified_at']);return value

def checked(value,purpose):
    if purpose==PURPOSE:return checked_manifest(value)
    if purpose=='restore-proof':return checked_attestation(value)
    raise BackupError('backup_purpose_invalid')


def verify(envelope,keyring,purpose):
    try:
        if not isinstance(envelope,dict) or set(envelope)!={'version','key_id','payload','signature'} or type(envelope['version']) is not int or envelope['version']!=1:raise ValueError()
        identifier(envelope['key_id']);value=checked(envelope['payload'],purpose)
        if not isinstance(keyring,dict) or not 1<=len(keyring)<=8 or any(identifier(k)!=k for k in keyring):raise ValueError()
        public=Ed25519PublicKey.from_public_bytes(decode(keyring[envelope['key_id']],32))
        public.verify(decode(envelope['signature'],64),PREFIX+purpose.encode()+b':'+canonical(value))
        return value
    except BackupError:raise
    except (ValueError,KeyError,TypeError,InvalidSignature):raise BackupError('backup_signature_invalid') from None

