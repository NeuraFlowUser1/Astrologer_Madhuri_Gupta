"""Receive the approved backup URL without echo; verify access and save to GitHub."""
import subprocess
import psycopg
from postgres import database_environment,HOST,ROLE
from envelope import BackupError


def main():
    # Clipboard is captured inside the local process, never in a tool argument.
    clipboard=subprocess.run(['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
        '-NoProfile','-NonInteractive','-Command','Get-Clipboard -Raw'],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=False)
    if clipboard.returncode:raise BackupError('backup_database_clipboard_unavailable')
    dsn=clipboard.stdout.decode().strip()
    database_environment(dsn)
    with psycopg.connect(dsn,connect_timeout=10,sslmode='verify-full',sslrootcert='system',
            channel_binding='require',options='-c default_transaction_read_only=on -c statement_timeout=10000') as connection:
        result=connection.execute("SELECT current_user,current_database(),has_table_privilege(current_user,'sarsa_booking.bookings','SELECT'),has_table_privilege(current_user,'sarsa_booking.bookings','INSERT,UPDATE,DELETE,TRUNCATE')").fetchone()
        if result!=(ROLE,'neondb',True,False):raise BackupError('backup_database_access_invalid')
        count=connection.execute('SELECT count(*) FROM sarsa_booking.schema_migrations').fetchone()[0]
    saved=subprocess.run(['gh','secret','set','SARSA_BACKUP_DATABASE_URL','--repo',
        'NeuraFlowUser1/Astrologer_Madhuri_Gupta'],input=dsn.encode(),
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=False)
    if saved.returncode:raise BackupError('backup_database_secret_save_failed')
    print('Backup login connected with verified TLS; read permissions verified. GitHub database setting saved.',flush=True)
    print('Readable migration records:',count,flush=True)

if __name__=='__main__':
    try:main()
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_database_setup_failed_no_private_values_logged') from None
