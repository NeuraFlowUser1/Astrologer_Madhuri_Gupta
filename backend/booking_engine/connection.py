"""Reject ambiguous database destinations before opening any connection."""

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict


class StorageUnavailable(Exception):
    pass


def checked_config(dsn, expected_host):
    try:
        config = conninfo_to_dict(dsn) if dsn else {}
    except psycopg.Error:
        raise StorageUnavailable('Booking storage is not configured.') from None
    host = config.get('host', '')
    if (not expected_host or host != expected_host or ',' in host or '/' in host
            or not config.get('dbname') or not config.get('user')
            or config.get('sslmode') not in ('require', 'verify-ca', 'verify-full')
            or any(config.get(k) for k in ('options', 'service', 'hostaddr'))
            or any(os.environ.get(k) for k in ('PGOPTIONS', 'PGSERVICE', 'PGHOSTADDR'))):
        raise StorageUnavailable('Booking storage requires its approved, protected connection.')
    return config
