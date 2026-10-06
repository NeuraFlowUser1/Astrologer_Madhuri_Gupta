"""Bounded standard age processes; authenticate before releasing restore bytes."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from .protocol import BackupError,MAX_BYTES

CHUNK=65536

def hashed(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise BackupError('backup_archive_invalid')
    size=path.stat().st_size
    if not 0<size<=MAX_BYTES:raise BackupError('backup_size_limit')
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(CHUNK),b''):value.update(block)
    return value.hexdigest(),size

def stop(*processes):
    for process in processes:
        if process.poll() is None:
            try:process.kill()
            except ProcessLookupError:pass

def tool(binary):
    path=Path(binary)
    if path.is_symlink() or not path.is_file() or not os.access(path,os.X_OK):raise BackupError('backup_tool_unavailable')
    try:
        result=subprocess.run([str(path),'--version'],capture_output=True,timeout=5,check=True)
        if result.stdout.strip()!=b'v1.3.2':raise ValueError()
    except (OSError,subprocess.SubprocessError,ValueError):raise BackupError('backup_tool_version_invalid') from None
    return str(path.resolve())

def encrypt(source,destination,recipient,binary,*,timeout=240):
    if type(recipient) is not str or not re.fullmatch('age1[0-9a-z]{40,90}',recipient):raise BackupError('backup_recipient_invalid')
    command=tool(binary)
    path=Path(destination)
    if path.exists() or path.is_symlink():raise BackupError('backup_destination_exists')
    process=None;timer=None;complete=False
    try:
        process=subprocess.Popen([command,'--recipient',recipient,'--output',str(path)],stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        timer=threading.Timer(timeout,stop,args=(process,));timer.start()
        total=0
        while block:=source.read(CHUNK):
            if not isinstance(block,bytes):raise BackupError('backup_stream_invalid')
            total+=len(block)
            if total>MAX_BYTES:raise BackupError('backup_size_limit')
            process.stdin.write(block)
        process.stdin.close()
        if total==0 or process.wait(timeout=10):raise BackupError('backup_encryption_failed')
        result=hashed(path);complete=True;return result
    except BackupError:raise
    except (OSError,subprocess.SubprocessError):raise BackupError('backup_encryption_failed') from None
    finally:
        if timer is not None:timer.cancel()
        if process is not None:
            if not process.stdin.closed:
                try:process.stdin.close()
                except OSError:pass
            stop(process);process.wait(timeout=10)
        if not complete:path.unlink(missing_ok=True)

def checked_identity(identity):
    if type(identity) is not str or len(identity)>8192:raise BackupError('backup_decryption_identity_invalid')
    lines=[line.strip() for line in identity.splitlines() if line.strip() and not line.strip().startswith('#')]
    if (not 1<=len(lines)<=8 or len(lines)!=len(set(lines))
        or any(not re.fullmatch('AGE-SECRET-KEY-1[0-9A-Z]{40,90}',line) for line in lines)):
        raise BackupError('backup_decryption_identity_invalid')
    return ('\n'.join(lines)+'\n').encode()

def decrypt_process(path,identity,binary,stdout):
    material=checked_identity(identity)
    try:
        process=subprocess.Popen([binary,'--decrypt','--identity','-',str(path)],stdin=subprocess.PIPE,
            stdout=stdout,stderr=subprocess.DEVNULL)
        process.stdin.write(material);process.stdin.close();return process
    except (OSError,subprocess.SubprocessError):
        if 'process' in locals():stop(process);process.wait(timeout=10)
        raise BackupError('backup_decryption_failed') from None

class _Authenticated:
    def __init__(self,path,binary,identity):
        self.path,self.binary,self._identity=path,binary,identity
        self.active=True
    def __repr__(self):return '<authenticated backup archive>'

@contextmanager
def authenticated_archive(path,identity,binary,expected_sha256,expected_bytes):
    """Freeze into an owned private directory, then verify all authentication.

    Callers may stream a second decrypt pass only from the yielded immutable
    owned file. The original download can never change between proof and SQL.
    """
    command=tool(binary)
    if hashed(path)!=(expected_sha256,expected_bytes):raise BackupError('backup_archive_mismatch')
    with tempfile.TemporaryDirectory(prefix='appointment-validated-') as directory:
        os.chmod(directory,0o700);frozen=Path(directory)/'archive.age'
        try:
            with Path(path).open('rb') as source,frozen.open('xb') as target:
                total=0
                for block in iter(lambda:source.read(CHUNK),b''):
                    total+=len(block)
                    if total>MAX_BYTES:raise BackupError('backup_size_limit')
                    target.write(block)
            if hashed(frozen)!=(expected_sha256,expected_bytes):raise BackupError('backup_archive_mismatch')
            os.chmod(frozen,0o400)
            process=decrypt_process(frozen,identity,command,subprocess.DEVNULL)
            try:
                if process.wait(timeout=120):raise BackupError('backup_authentication_failed')
            except subprocess.TimeoutExpired:raise BackupError('backup_authentication_timeout') from None
            finally:stop(process);process.wait(timeout=10)
            archive=_Authenticated(frozen,command,identity)
            try:yield archive
            finally:archive.active=False
        except BackupError:raise
        except OSError:raise BackupError('backup_archive_unavailable') from None

def restore_stream(archive,destination,*,timeout=240):
    """Use only the frozen path yielded inside authenticated_archive."""
    if not isinstance(archive,_Authenticated) or not archive.active:raise BackupError('backup_authentication_required')
    process=decrypt_process(archive.path,archive._identity,archive.binary,subprocess.PIPE)
    timer=threading.Timer(timeout,stop,args=(process,));timer.start()
    try:
        total=0
        for block in iter(lambda:process.stdout.read(CHUNK),b''):
            total+=len(block)
            if total>MAX_BYTES:raise BackupError('backup_size_limit')
            destination.write(block)
        if total==0 or process.wait(timeout=10):raise BackupError('backup_decryption_failed')
        return total
    except BackupError:raise
    except (OSError,subprocess.SubprocessError):raise BackupError('backup_restore_stream_failed') from None
    finally:timer.cancel();process.stdout.close();stop(process);process.wait(timeout=10)
