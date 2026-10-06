"""Explicit historical reader only; original literal formats must not change.
Source SHA256: 512e4430994ab0ebe0a69b46aea17382b26ef9c3efa22d497b89796eba30aa17
"""
from .protocol import BackupError
"""Streaming AES-256-GCM envelope; plaintext is never written to a backup file.

Restore authenticates a complete first pass before releasing any plaintext.
The format uses cryptography's standard GCM implementation, not custom crypto.
"""
import base64
import json
import os
import struct
import re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b'SARSA004-BACKUP-1\x00'
MAGIC_V2 = b'SARSA004-BACKUP-2\x00'
CHUNK = 1024 * 1024
MAX_BYTES = 512 * 1024 * 1024


def checked_v2(metadata):
    if (not isinstance(metadata,dict) or type(metadata.get('protocol_version')) is not int
        or metadata['protocol_version']!=2 or metadata.get('project')!='004-sarsa-jyotish-sansthan'
        or metadata.get('format')!='postgres-custom' or metadata.get('schemas')!=['sarsa_booking','booking_control']):
        raise BackupError('backup_identity_invalid')
    migrations=metadata.get('migrations');counts=metadata.get('table_counts')
    if (not isinstance(migrations,dict) or not 1<=len(migrations)<=500
        or any(not isinstance(name,str) or not re.fullmatch(r'[0-9]{3}_[a-z0-9_]+\.sql',name)
               or not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha) for name,sha in migrations.items())
        or not isinstance(counts,dict) or not 1<=len(counts)<=250
        or any(not isinstance(name,str) or not re.fullmatch(r'(?:sarsa_booking|booking_control)\.[a-z][a-z0-9_]{0,62}',name)
               or type(count) is not int or not 0<=count<=9223372036854775807 for name,count in counts.items())
        or counts.get('booking_control.product_state')!=1):
        raise BackupError('backup_identity_invalid')
    return metadata

def unique_json(value):
    def pairs(items):
        result={}
        for name,item in items:
            if name in result:raise ValueError()
            result[name]=item
        return result
    return json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))


def decode_key(value):
    try:
        key = base64.urlsafe_b64decode(value)
        if len(key) != 32 or base64.urlsafe_b64encode(key).decode() != value:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise BackupError('backup_key_invalid') from None




def decrypt(source, key, destination=None):
    """Verify only by default; caller makes a separate verified restore pass."""
    source.seek(0, 2)
    size = source.tell()
    source.seek(0)
    prefix = source.read(len(MAGIC) + 16)
    if len(prefix) != len(MAGIC) + 16 or prefix[:len(MAGIC)] not in (MAGIC,MAGIC_V2):
        raise BackupError('backup_header_invalid')
    nonce = prefix[len(MAGIC):len(MAGIC)+12]
    length = struct.unpack('>I', prefix[-4:])[0]
    version_two=prefix.startswith(MAGIC_V2)
    if length > (65536 if version_two else 4096):
        raise BackupError('backup_header_invalid')
    manifest = source.read(length)
    remaining = size - len(prefix) - length - 16
    if len(manifest) != length or remaining < 0 or remaining > MAX_BYTES:
        raise BackupError('backup_size_invalid')
    source.seek(-16, 2)
    tag = source.read(16)
    source.seek(len(prefix) + length)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    cipher.authenticate_additional_data(prefix + manifest)
    try:
        while remaining:
            data = source.read(min(CHUNK, remaining))
            if not data:
                raise BackupError('backup_truncated')
            remaining -= len(data)
            plain = cipher.update(data)
            if destination is not None:
                destination.write(plain)
        tail = cipher.finalize()
        if destination is not None:
            destination.write(tail)
        metadata = unique_json(manifest)
        if (metadata.get('project') != '004-sarsa-jyotish-sansthan'
                or metadata.get('format') != 'postgres-custom'):
            raise BackupError('backup_identity_invalid')
        if version_two:checked_v2(metadata)
        elif metadata.get('protocol_version')==2:raise BackupError('backup_identity_invalid')
        return metadata
    except BackupError:
        raise
    except Exception:
        raise BackupError('backup_authentication_failed') from None
