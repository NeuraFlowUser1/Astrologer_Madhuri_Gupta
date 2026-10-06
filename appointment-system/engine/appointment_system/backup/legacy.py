"""Historical archive authentication is distinct from new release acceptance.

The converter must additionally prove the old schema/account mapping. These
readers cannot authorize a live restore or sign a new restore attestation.
"""
from pathlib import Path
import os
import tempfile
from .protocol import BackupError
from .age_stream import hashed,CHUNK
from . import legacy_003,legacy_004

def export_manifest_003(envelope,keys):
    return legacy_003.verify(envelope,keys,'database-export')

def read_aes_004(path,encoded_key,destination=None):
    """Authenticate the complete copied ciphertext before any restore output."""
    key=legacy_004.decode_key(encoded_key);expected=hashed(path)
    with tempfile.TemporaryDirectory(prefix='appointment-legacy-read-') as directory:
        os.chmod(directory,0o700);frozen=Path(directory)/'legacy.aes'
        with Path(path).open('rb') as source,frozen.open('xb') as target:
            total=0
            for block in iter(lambda:source.read(CHUNK),b''):
                total+=len(block)
                if total>expected[1]:raise BackupError('backup_archive_mismatch')
                target.write(block)
        if hashed(frozen)!=expected:raise BackupError('backup_archive_mismatch')
        os.chmod(frozen,0o400)
        with frozen.open('rb') as source:metadata=legacy_004.decrypt(source,key)
        if destination is not None:
            with frozen.open('rb') as source:
                if legacy_004.decrypt(source,key,destination)!=metadata:raise BackupError('backup_archive_mismatch')
        return metadata
