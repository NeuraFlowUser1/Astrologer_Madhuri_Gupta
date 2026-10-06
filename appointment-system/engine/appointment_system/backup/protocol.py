"""Public-key backup provenance. Export and validation are separate authorities.

Uses the inspected AstroAdvice protocol with installation-bound identity and
both supported PostgreSQL majors. A signed export is never a restore proof.
"""
import base64
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import hashlib
import json
import re
from uuid import UUID
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

MAX_BYTES=512*1024*1024
MAX_DOCUMENT=65536
PREFIX=b'appointment-system:backup:v1:'
SCHEMAS=['appointment_system']
INVARIANT_NAMES=('confirmed_without_matching_payment','active_claim_wrong_state','live_booking_missing_claim',
                 'overlapping_claims','foreign_context_pointer','unvalidated_constraints')

class BackupError(Exception):
    """Only fixed safe diagnostic codes; no credential/provider response text."""

def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    except (ValueError,TypeError,UnicodeError,RecursionError):raise BackupError('backup_document_invalid') from None

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def invariant_digest():return digest(dict.fromkeys(INVARIANT_NAMES,0))

def unique_json(value):
    def pairs(items):
        result={}
        for key,item in items:
            if key in result:raise ValueError()
            result[key]=item
        return result
    try:
        if not isinstance(value,(bytes,str)) or len(value)>MAX_DOCUMENT:raise ValueError()
        result=json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if len(canonical(result))>MAX_DOCUMENT:raise ValueError()
        return result
    except (ValueError,TypeError,UnicodeError,RecursionError):raise BackupError('backup_document_invalid') from None

def hex_value(value,size=64):return type(value) is str and re.fullmatch('[a-f0-9]{'+str(size)+'}',value) is not None

def uuid_value(value):
    try:return type(value) is str and str(UUID(value))==value and bool(UUID(value).int)
    except (ValueError,TypeError,AttributeError):return False

def integer(value,minimum,maximum):return type(value) is int and minimum<=value<=maximum

def run_number(value,maximum=20):return type(value) is str and re.fullmatch('[1-9][0-9]{0,'+str(maximum-1)+'}',value) is not None

def stamp(value):
    try:
        if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value):raise ValueError()
        instant=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        if instant>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError()
        return instant
    except (ValueError,TypeError):raise BackupError('backup_time_invalid') from None

def decode(value,size):
    try:
        if type(value) is not str:raise ValueError()
        result=base64.b64decode(value,altchars=b'-_',validate=True)
        if len(result)!=size or base64.urlsafe_b64encode(result).decode()!=value:raise ValueError()
        return result
    except (ValueError,TypeError):raise BackupError('backup_key_invalid') from None

def keyring(value):
    if type(value) is not dict or not 1<=len(value)<=8:raise BackupError('backup_keyring_invalid')
    for name,item in value.items():
        if type(name) is not str or not re.fullmatch('[a-z][a-z0-9_-]{0,47}',name):raise BackupError('backup_keyring_invalid')
        decode(item,32)
    return value

@dataclass(frozen=True)
class Identity:
    installation_id:str
    project:str
    environment:str
    owner_email:str
    release_digest:str

    def __post_init__(self):
        if (not uuid_value(self.installation_id) or type(self.project) is not str or not re.fullmatch('[a-z0-9][a-z0-9-]{0,74}',self.project)
            or self.environment not in ('production','development','test') or not hex_value(self.release_digest)
            or type(self.owner_email) is not str or not re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,189}',self.owner_email)
            or self.owner_email!=self.owner_email.lower()):raise BackupError('backup_identity_invalid')

    def fields(self):return dict(installation_id=self.installation_id,project=self.project,environment=self.environment,
                                 owner_email=self.owner_email,release_digest=self.release_digest)

EXPORT_FIELDS={'version','purpose','installation_id','project','environment','owner_email','release_digest',
 'source_commit','source_run','source_attempt','archive_name','archive_sha256','archive_bytes','created_at',
 'postgres_major','schemas','migrations','table_counts','restore_generation','generation_sequence','database_contract'}
PROOF_FIELDS={'version','purpose','installation_id','project','environment','owner_email','release_digest',
 'manifest_sha256','archive_sha256','source_run','source_attempt','source_commit','validator_commit','verified_at',
 'migration_count','migration_digest','table_counts_digest','invariants_digest','restored_authority',
 'archive_drive_id','archive_drive_version','manifest_drive_id','manifest_drive_version'}

def checked(value,purpose,identity):
    fields=EXPORT_FIELDS if purpose=='database-export' else PROOF_FIELDS if purpose=='restore-proof' else None
    if (fields is None or type(value) is not dict or set(value)!=fields or type(value['version']) is not int or value['version']!=1
        or value['purpose']!=purpose or any(value[name]!=item for name,item in identity.fields().items())):
        raise BackupError('backup_identity_invalid')
    if not run_number(value['source_run']) or not run_number(value['source_attempt'],4) or not hex_value(value['source_commit'],40):
        raise BackupError('backup_run_identity_invalid')
    if purpose=='database-export':
        expected='appointment-'+identity.installation_id+'-'+value['source_run']+'-'+value['source_attempt']+'.dump.age'
        if (value['archive_name']!=expected or not hex_value(value['archive_sha256']) or not integer(value['archive_bytes'],1,MAX_BYTES)
            or type(value['postgres_major']) is not int or value['postgres_major'] not in (16,18)
            or value['schemas']!=SCHEMAS or type(value['database_contract']) is not int or value['database_contract']!=1
            or not uuid_value(value['restore_generation']) or not run_number(value['generation_sequence'],19)
            or int(value['generation_sequence'])>2**63-1):raise BackupError('backup_manifest_invalid')
        stamp(value['created_at'])
        migrations=value['migrations'];counts=value['table_counts']
        if (type(migrations) is not dict or not 1<=len(migrations)<=500
            or any(type(n) is not str or not re.fullmatch(r'[0-9]{3}_[a-z0-9_]+\.sql',n) or not hex_value(h) for n,h in migrations.items())):
            raise BackupError('backup_migrations_invalid')
        if (type(counts) is not dict or not 1<=len(counts)<=250
            or any(type(n) is not str or not re.fullmatch(r'appointment_system\.[a-z][a-z0-9_]{0,62}',n)
                   or not integer(count,0,2**63-1) for n,count in counts.items())
            or counts.get('appointment_system.installation')!=1 or counts.get('appointment_system.control_product_state')!=1):
            raise BackupError('backup_counts_invalid')
    else:
        if (any(not hex_value(value[name]) for name in ('manifest_sha256','archive_sha256','migration_digest','table_counts_digest','invariants_digest'))
            or not hex_value(value['validator_commit'],40) or not integer(value['migration_count'],1,500)
            or value['invariants_digest']!=invariant_digest() or value['restored_authority']!='off_new_generation'
            or any(type(value[n]) is not str or not re.fullmatch('[A-Za-z0-9_-]{10,180}',value[n]) for n in ('archive_drive_id','manifest_drive_id'))
            or any(not run_number(value[n]) for n in ('archive_drive_version','manifest_drive_version'))):raise BackupError('backup_attestation_invalid')
        stamp(value['verified_at'])
    if len(canonical(value))>MAX_DOCUMENT-512:raise BackupError('backup_document_invalid')
    return value

def sign(value,key_id,private_key,identity):
    keyring({key_id:private_key});purpose=value.get('purpose') if type(value) is dict else None
    checked(value,purpose,identity)
    signature=Ed25519PrivateKey.from_private_bytes(decode(private_key,32)).sign(PREFIX+purpose.encode()+b':'+canonical(value))
    return {'version':1,'key_id':key_id,'payload':value,'signature':base64.urlsafe_b64encode(signature).decode()}

def verify(envelope,keys,purpose,identity):
    keyring(keys)
    try:
        if (type(envelope) is not dict or set(envelope)!={'version','key_id','payload','signature'}
            or type(envelope['version']) is not int or envelope['version']!=1 or type(envelope['key_id']) is not str):raise ValueError()
        value=checked(envelope['payload'],purpose,identity)
        Ed25519PublicKey.from_public_bytes(decode(keys[envelope['key_id']],32)).verify(
            decode(envelope['signature'],64),PREFIX+purpose.encode()+b':'+canonical(value))
        return value
    except BackupError:raise
    except (ValueError,TypeError,KeyError,InvalidSignature):raise BackupError('backup_signature_invalid') from None

def matched_proof(export,validation,export_keys,validation_keys,identity):
    keyring(export_keys);keyring(validation_keys)
    if set(export_keys.values())&set(validation_keys.values()):raise BackupError('backup_signing_authority_not_separate')
    source=verify(export,export_keys,'database-export',identity)
    proof=verify(validation,validation_keys,'restore-proof',identity)
    expected={'manifest_sha256':digest(export),'archive_sha256':source['archive_sha256'],
        'source_run':source['source_run'],'source_attempt':source['source_attempt'],'source_commit':source['source_commit'],
        'migration_count':len(source['migrations']),'migration_digest':digest(source['migrations']),
        'table_counts_digest':digest(source['table_counts'])}
    if any(proof[name]!=item for name,item in expected.items()) or stamp(proof['verified_at'])<stamp(source['created_at']):
        raise BackupError('backup_proof_mismatch')
    return source,proof
