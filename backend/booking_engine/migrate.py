"""Checksum-tracked, atomic migrations using only an explicit maintenance URL.

No migration runs on import or during a customer request. Production application
roles must never have this schema-creation authority.
"""

import hashlib
import os
from pathlib import Path

import psycopg
from .connection import StorageUnavailable, checked_config

MIGRATIONS = Path(__file__).with_name('migrations')
LOCK_ID = 4004001


def migration_sources():
    return [(p.name, p.read_text(), hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'))]


def apply(connection):
    """One transaction owns all DDL and bookkeeping, including first bootstrap."""
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        exists = connection.execute("SELECT to_regclass('sarsa_booking.schema_migrations')").fetchone()[0]
        applied = dict(connection.execute('SELECT version, sha256 FROM sarsa_booking.schema_migrations').fetchall()) if exists else {}
        sources = migration_sources()
        if set(applied) - {name for name, _, _ in sources}:
            raise ValueError('Database has migrations unknown to this application')
        for name, sql, digest in sources:
            if name in applied:
                if applied[name] != digest:
                    raise ValueError('Applied migration checksum changed: ' + name)
                continue
            connection.execute(sql)
            connection.execute('INSERT INTO sarsa_booking.schema_migrations(version,sha256) VALUES (%s,%s)', (name,digest))


def main():
    # Exact host guard prevents accidental migrations against another client.
    dsn = os.environ.get('SARSA_MIGRATION_DATABASE_URL', '')
    expected_host = os.environ.get('SARSA_MIGRATION_EXPECTED_HOST', '')
    try:
        config = checked_config(dsn, expected_host)
        host = config.get('host', '')
        if not expected_host or host != expected_host or '-pooler' in host:
            raise ValueError('Set the Sarsa direct maintenance URL and matching expected host')
        if config.get('sslmode') not in ('require','verify-ca','verify-full'):
            raise ValueError('A TLS-protected database connection is required')
        with psycopg.connect(dsn, connect_timeout=10, autocommit=True) as connection:
            apply(connection)
    except (psycopg.Error, ValueError, StorageUnavailable):
        # Connection strings and SQL values must not enter output/error logs.
        raise SystemExit('Migration failed. Verify the Sarsa target, permissions and migration checksums.') from None
    print('Sarsa booking migrations verified and applied.')


if __name__ == '__main__':
    main()
