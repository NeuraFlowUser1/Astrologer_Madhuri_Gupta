"""Capture a short-lived clipboard connection and save only verified backup access."""
import subprocess
import time

from envelope import BackupError
from postgres import ROLE, ROOT_CA, database_environment

POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
REPO = 'NeuraFlowUser1/Astrologer_Madhuri_Gupta'


def read_clipboard():
    result = subprocess.run(
        [POWERSHELL, '-NoProfile', '-NonInteractive', '-Command', 'Get-Clipboard -Raw'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False,
    )
    if result.returncode:
        raise BackupError('backup_database_clipboard_unavailable')
    return result.stdout.decode().strip()


def acquire_connection(wait_seconds=0, *, reader=read_clipboard, clock=time.monotonic, pause=time.sleep):
    if not 0 <= wait_seconds <= 900:
        raise BackupError('backup_database_wait_invalid')
    deadline = clock() + wait_seconds
    while True:
        value = reader()
        if value.startswith(('postgres://', 'postgresql://')):
            database_environment(value)
            return value
        remaining = deadline - clock()
        if remaining <= 0:
            raise BackupError('backup_database_connection_not_on_clipboard')
        pause(min(2, remaining))


def connection_failure(error):
    # The provider message may contain credentials: return a fixed category only.
    message = str(error).lower()
    for needle, code in (
        ('password authentication failed', 'backup_database_authentication_failed'),
        ('certificate verify failed', 'backup_database_certificate_failed'),
        ('sslrootcert', 'backup_database_trust_configuration_failed'),
        ('could not translate host name', 'backup_database_dns_failed'),
        ('timeout expired', 'backup_database_connection_timeout'),
        ('channel binding', 'backup_database_channel_binding_failed'),
        ('permission denied', 'backup_database_permission_failed'),
        ('network is unreachable', 'backup_database_network_unavailable'),
    ):
        if needle in message:
            return code
    return 'backup_database_connection_failed'


def validate_connection(dsn):
    # This setup-only dependency is already installed with the booking engine.
    import psycopg

    try:
        with psycopg.connect(
            dsn, connect_timeout=10, sslmode='verify-full', sslrootcert=ROOT_CA,
            channel_binding='require',
            options='-c default_transaction_read_only=on -c statement_timeout=10000',
        ) as connection:
            result = connection.execute(
                "SELECT current_user,current_database(),"
                "has_table_privilege(current_user,'sarsa_booking.bookings','SELECT'),"
                "has_table_privilege(current_user,'sarsa_booking.bookings','INSERT,UPDATE,DELETE,TRUNCATE')"
            ).fetchone()
            if result != (ROLE, 'neondb', True, False):
                raise BackupError('backup_database_access_invalid')
            return connection.execute('SELECT count(*) FROM sarsa_booking.schema_migrations').fetchone()[0]
    except BackupError:
        raise
    except Exception as error:
        raise BackupError(connection_failure(error)) from None


def main(wait_seconds=0):
    if wait_seconds:
        print('Waiting for the Sarsa backup connection on Windows clipboard; no private values displayed.', flush=True)
    dsn = acquire_connection(wait_seconds)
    print('Sarsa backup connection captured privately; checking verified access.', flush=True)
    count = validate_connection(dsn)
    saved = subprocess.run(
        ['gh', 'secret', 'set', 'SARSA_BACKUP_DATABASE_URL', '--repo', REPO],
        input=dsn.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=30, check=False,
    )
    if saved.returncode:
        raise BackupError('backup_database_secret_save_failed')
    print('Backup login connected with verified TLS; read permissions verified. GitHub database setting saved.', flush=True)
    print('Readable migration records:', count, flush=True)
