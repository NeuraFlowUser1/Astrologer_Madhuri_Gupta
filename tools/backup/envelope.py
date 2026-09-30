"""Streaming AES-256-GCM envelope; plaintext is never written to a backup file.

Restore authenticates a complete first pass before releasing any plaintext.
The format uses cryptography's standard GCM implementation, not custom crypto.
"""
import base64
import json
import os
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b'SARSA004-BACKUP-1\x00'
CHUNK = 1024 * 1024
MAX_BYTES = 512 * 1024 * 1024

class BackupError(Exception):
    """A fixed diagnostic code safe for job logs."""


def decode_key(value):
    try:
        key = base64.urlsafe_b64decode(value)
        if len(key) != 32 or base64.urlsafe_b64encode(key).decode() != value:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise BackupError('backup_key_invalid') from None


def encrypt(source, destination, key, metadata):
    manifest = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
    if len(manifest) > 4096:
        raise BackupError('backup_manifest_too_large')
    nonce = os.urandom(12)
    header = MAGIC + nonce + struct.pack('>I', len(manifest)) + manifest
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(header)
    destination.write(header)
    total = 0
    while data := source.read(CHUNK):
        total += len(data)
        if total > MAX_BYTES:
            raise BackupError('backup_size_limit')
        destination.write(cipher.update(data))
    destination.write(cipher.finalize())
    destination.write(cipher.tag)
    return total


def decrypt(source, key, destination=None):
    """Verify only by default; caller makes a separate verified restore pass."""
    source.seek(0, 2)
    size = source.tell()
    source.seek(0)
    prefix = source.read(len(MAGIC) + 16)
    if len(prefix) != len(MAGIC) + 16 or not prefix.startswith(MAGIC):
        raise BackupError('backup_header_invalid')
    nonce = prefix[len(MAGIC):len(MAGIC)+12]
    length = struct.unpack('>I', prefix[-4:])[0]
    if length > 4096:
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
        metadata = json.loads(manifest)
        if (metadata.get('project') != '004-sarsa-jyotish-sansthan'
                or metadata.get('format') != 'postgres-custom'):
            raise BackupError('backup_identity_invalid')
        return metadata
    except BackupError:
        raise
    except Exception:
        raise BackupError('backup_authentication_failed') from None
