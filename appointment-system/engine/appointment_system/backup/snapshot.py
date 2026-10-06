"""Counts, release and pg_dump share one exported read-only database snapshot."""
import re
import time
from psycopg import sql
from .protocol import BackupError,SCHEMAS

def capture(connection,identity,expected_migrations,expected_tables):
    """Caller holds this transaction open until the dump finishes."""
    deadline=time.monotonic()+30
    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    connection.execute("SET LOCAL statement_timeout='3s'")
    connection.execute("SET LOCAL lock_timeout='2s'")
    connection.execute("SET LOCAL idle_in_transaction_session_timeout='300s'")
    valid=connection.execute('SELECT appointment_system.validate_caller(%s,%s,%s,%s)',
        (identity.installation_id,identity.environment,'backup',1)).fetchone()[0]
    if valid is not True:raise BackupError('backup_database_identity_invalid')
    major=int(connection.execute('SHOW server_version_num').fetchone()[0])//10000
    if major not in (16,18):raise BackupError('backup_database_version_invalid')
    config=connection.execute('SELECT installation_id,project_id,environment FROM appointment_system.installation WHERE singleton').fetchone()
    if tuple(str(x) for x in config)!=(identity.installation_id,identity.project,identity.environment):raise BackupError('backup_database_identity_invalid')
    release=connection.execute('SELECT release_digest FROM appointment_system.worker_release WHERE singleton').fetchone()
    if release!=(identity.release_digest,):raise BackupError('backup_release_mismatch')
    migrations=dict(connection.execute('SELECT version,sha256 FROM appointment_system.schema_migrations ORDER BY version').fetchall())
    if migrations!=expected_migrations:raise BackupError('backup_source_migrations_mismatch')
    tables=connection.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p') AND NOT c.relispartition ORDER BY n.nspname,c.relname",(SCHEMAS,)).fetchall()
    names={schema+'.'+name for schema,name in tables}
    if not 1<=len(tables)<=250 or names!=set(expected_tables):raise BackupError('backup_relation_allowlist_mismatch')
    counts={}
    for schema,name in tables:
        if time.monotonic()>deadline or not re.fullmatch('[a-z][a-z0-9_]{0,62}',name):raise BackupError('backup_snapshot_limit')
        counts[schema+'.'+name]=connection.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(name))).fetchone()[0]
    control=connection.execute('SELECT restore_generation,generation_sequence FROM appointment_system.control_product_state WHERE singleton').fetchone()
    snapshot=connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
    if type(snapshot) is not str or not re.fullmatch('[a-fA-F0-9]{8}-[a-fA-F0-9]{8}-[1-9][0-9]*',snapshot):raise BackupError('backup_snapshot_invalid')
    return dict(snapshot=snapshot,postgres_major=major,migrations=migrations,table_counts=counts,
        restore_generation=str(control[0]),generation_sequence=str(control[1]))
