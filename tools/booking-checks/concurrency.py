"""Owner-run, development-only proof of the shared slot exclusion constraint.

The connection is entered at a hidden local prompt, never through Codex tools.
Only three new synthetic closure IDs can be written/deleted. No booking, payment,
provider request, intake switch, permission or customer record is changed.
"""
import concurrent.futures
import getpass
import sys
import time
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

HOST = 'ep-broad-cake-b3gre2bh.c-4.ap-southeast-1.aws.neon.tech'
LABEL = 'Sarsa004 development concurrency acceptance'
INSERT = """INSERT INTO sarsa_booking.slot_claims
 (id,closure_reason,starts_at,ends_at)
 VALUES(%s,%s,%s::timestamptz,%s::timestamptz)"""
START, END, NEXT = ('2035-01-02T10:00:00+05:30',
                    '2035-01-02T10:30:00+05:30', '2035-01-02T11:00:00+05:30')


def connection(value):
    parameters = conninfo_to_dict(value)
    if (len(value) > 32768
            or parameters.get('host') not in (HOST, HOST.replace('.c-4.', '-pooler.c-4.'))
            or parameters.get('dbname') != 'neondb'
            or parameters.get('user') != 'neondb_owner'
            or parameters.get('port', '5432') != '5432'
            or not parameters.get('password')
            or set(parameters) - {'host', 'dbname', 'user', 'password', 'port',
                                  'sslmode', 'channel_binding'}):
        raise ValueError('development_identity_rejected')
    return make_conninfo(value, host=HOST, sslmode='verify-full',
        sslrootcert='/etc/ssl/certs/ca-certificates.crt', channel_binding='require',
        connect_timeout=15, application_name='sarsa004-development-acceptance',
        options='-c statement_timeout=10000 -c lock_timeout=8000')


def prove(dsn):
    ids = [uuid4() for _ in range(3)]
    a = b = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    cleanup_ok = True
    result_ok = False
    try:
        a = psycopg.connect(dsn)
        b = psycopg.connect(dsn)
        pid_a = a.execute('SELECT pg_backend_pid()').fetchone()[0]
        pid_b = b.execute('SELECT pg_backend_pid()').fetchone()[0]
        if pid_a == pid_b:
            raise ValueError('independent_sessions_missing')
        if a.execute("""SELECT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims
          WHERE released_at IS NULL AND tstzrange(starts_at,ends_at,'[)')
          && tstzrange(%s::timestamptz,%s::timestamptz,'[)'))""",
          (START, NEXT)).fetchone()[0]:
            raise ValueError('synthetic_interval_not_empty')
        a.execute(INSERT, (ids[0], LABEL, START, END))

        def contender():
            try:
                b.execute(INSERT, (ids[1], LABEL, START, END))
                b.commit()
                return 'incorrectly_accepted'
            except psycopg.errors.ExclusionViolation:
                b.rollback()
                return 'overlap_rejected'

        waiting = pool.submit(contender)
        deadline = time.monotonic() + 5
        blocked = False
        while time.monotonic() < deadline and not waiting.done():
            blocked = a.execute('SELECT %s = ANY(pg_blocking_pids(%s))',
                                (pid_a, pid_b)).fetchone()[0]
            if blocked:
                break
            time.sleep(.1)
        if not blocked:
            raise ValueError('concurrent_contention_not_observed')
        a.commit()
        if waiting.result(timeout=12) != 'overlap_rejected':
            raise ValueError('overlap_was_accepted')
        b.execute(INSERT, (ids[2], LABEL, END, NEXT))
        b.commit()
        count = a.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE id=ANY(%s)',
                          (ids,)).fetchone()[0]
        if count != 2:
            raise ValueError('adjacent_interval_failed')
        result_ok = True
    finally:
        # Release the blocker before waiting for the other session. Time limits
        # bound a failed thread; always attempt narrowly scoped final cleanup.
        if a is not None:
            try:
                a.rollback()
            except Exception:
                # Closing a broken blocker still releases its transaction.
                a.close()
        if b is not None:
            try:
                b.cancel()
            except Exception:
                pass
        pool.shutdown(wait=True)
        if b is not None:
            try:
                b.rollback()
            except Exception:
                pass
            b.close()
        if a is not None:
            a.close()
        try:
            with psycopg.connect(dsn) as cleanup:
                cleanup.execute('''DELETE FROM sarsa_booking.slot_claims
                  WHERE id=ANY(%s) AND booking_id IS NULL AND closure_reason=%s''',
                  (ids, LABEL))
                if cleanup.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE id=ANY(%s)',
                                   (ids,)).fetchone()[0] != 0:
                    raise ValueError('cleanup_incomplete')
        except Exception:
            cleanup_ok = False
            print('Cleanup needs review for these synthetic IDs only: ' + ','.join(map(str, ids)))
    if not cleanup_ok:
        raise ValueError('cleanup_incomplete')
    if not result_ok:
        raise ValueError('acceptance_incomplete')
    print('PASS: separate sessions overlapped; duplicate time rejected; adjacent time accepted; synthetic rows removed.')


if __name__ == '__main__':
    try:
        if not sys.stdin.isatty():
            raise ValueError('private_local_prompt_required')
        print('Use Sarsa’s DEVELOPMENT branch connection only. Input is hidden; do not send it through chat or Codex.')
        supplied = getpass.getpass('Paste the development neondb_owner connection string: ')
        private_dsn = connection(supplied)
        supplied = None
        prove(private_dsn)
    except (Exception, KeyboardInterrupt):
        print('Check stopped. No credential or database error is displayed. Do not assume the check passed.')
        sys.exit(1)
    finally:
        supplied = private_dsn = None
