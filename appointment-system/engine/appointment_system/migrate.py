"""Checksum-tracked, atomic schema installation with declared migration authority.

No migration runs on import or during a customer request. Production application
roles must never have this schema-creation authority.
"""

import hashlib
import os
from pathlib import Path

import psycopg
from .connection import StorageUnavailable, checked_config
from .errors import Rejected

MIGRATIONS = Path(__file__).with_name('migrations')
LOCK_ID = 4004001


def migration_sources():
    paths=sorted(MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'))
    if not paths or any(path.is_symlink() for path in paths):
        raise ValueError('Installed schema definitions are required.')
    sources=[]
    for path in paths:
        content=path.read_bytes()
        sources.append((path.name,content.decode('utf-8'),hashlib.sha256(content).hexdigest()))
    return sources


def apply(connection):
    """One transaction owns all DDL and bookkeeping, including first bootstrap."""
    with connection.transaction():
        connection.execute("SET LOCAL lock_timeout='2s'")
        connection.execute("SET LOCAL statement_timeout='30s'")
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        exists = connection.execute("SELECT to_regclass('appointment_system.schema_migrations')").fetchone()[0]
        applied = dict(connection.execute('SELECT version, sha256 FROM appointment_system.schema_migrations').fetchall()) if exists else {}
        sources = migration_sources()
        if set(applied) - {name for name, _, _ in sources}:
            raise ValueError('Database has migrations unknown to this application')
        for name, sql, digest in sources:
            if name in applied:
                if applied[name] != digest:
                    raise ValueError('Applied migration checksum changed: ' + name)
                continue
            connection.execute(sql)
            connection.execute('INSERT INTO appointment_system.schema_migrations(version,sha256) VALUES (%s,%s)', (name,digest))


def main():
    # Same independently contained release/settings binding as the serving host.
    try:
        from .runtime import contained_release
        from .configuration import load,installation
        import certifi
        root,_=contained_release();load(root.parent/'appointment-settings/project.json')
        target=installation()['database_targets']['migration']
        config=checked_config(os.environ.get('BOOKING_MIGRATION_DATABASE_URL',''),target['host'],purpose='migration')
        config.update(sslmode='verify-full',sslrootcert=certifi.where(),channel_binding='require',connect_timeout=3)
        with psycopg.connect(**config,autocommit=True) as connection:
            apply(connection)
    except (psycopg.Error,KeyError,ValueError,Rejected,StorageUnavailable):
        # Connection strings and SQL values must not enter output/error logs.
        raise SystemExit('Schema installation failed. Verify this project target, migration permissions and release checksums.') from None
    print('This project schema is verified and installed.')


if __name__ == '__main__':
    main()
