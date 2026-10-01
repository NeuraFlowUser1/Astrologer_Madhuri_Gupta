"""Loopback-only Chrome fixture with real application routes and disposable SQL.

Only Google's identity response is synthetic. The actual sign-in state, secure
cookies, staff permissions, support actions, receipt redemption and appointment
changes use the unchanged application. No provider credential is supplied.
"""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlencode

import uvicorn
from cryptography.fernet import Fernet
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database_drill import ROOT, LocalDatabase, apply, seed_booking
from backend.booking_engine.application import Settings, create_application
from backend.booking_engine.google_oauth import GrantCipher, SIGN_IN_CALLBACK
from backend.booking_engine.policy import IST
from backend.booking_engine.studio import StudioServices

ARTIFACTS = ROOT / 'tools/verification/artifacts'


def main():
    if not (ROOT / 'frontend/dist/booking.html').is_file():
        raise SystemExit('Build the frontend before starting the Chrome fixture.')
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    completed = ARTIFACTS / 'chrome-completed.json'
    completed.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='sarsa-chrome-') as directory:
        folder = Path(directory)
        os.chmod(folder, 0o700)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(folder/'server.key'), '-out', str(folder/'server.crt'),
                        '-subj', '/CN=localhost', '-days', '1'], check=True, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with LocalDatabase(folder, 'chrome') as database, socket.socket() as listener:
            with database.owner() as connection:
                apply(connection)
            database.prepare_login()
            reference, old_receipt, booking = seed_booking(database)
            listener.bind(('127.0.0.1', 0))
            origin = 'https://localhost:' + str(listener.getsockname()[1])
            client_id = '100-synthetic.apps.googleusercontent.com'

            class Identity:
                settings = SimpleNamespace(client_id=client_id, origin=origin)

                def authorization_url(self, attempt, *, signin=False):
                    if not signin:
                        raise RuntimeError('Real Google permissions are outside this fixture.')
                    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
                        'state': attempt.state, 'login_hint': attempt.role,
                        'redirect_uri': origin + SIGN_IN_CALLBACK})

                def sign_in(self, attempt, code):
                    if code != 'synthetic-' + attempt.role:
                        raise RuntimeError('Unexpected synthetic identity response.')
                    return 'synthetic-chrome-' + attempt.role

            store = database.store()
            settings = Settings(origin, b'a'*32, b'b'*32, b'c'*32)
            studio = StudioServices(Identity(), GrantCipher(client_id, [Fernet.generate_key()]), b'd'*32)
            app = create_application(store, settings, studio_services=studio,
                                     verified_client_address=lambda request: '127.0.0.1')
            app.mount('/assets', StaticFiles(directory=ROOT/'frontend/dist/assets'), name='fixture-assets')

            @app.get('/booking', include_in_schema=False)
            def booking_page():
                return FileResponse(ROOT/'frontend/dist/booking.html')

            with database.owner() as connection:
                original = connection.execute('SELECT starts_at FROM sarsa_booking.bookings WHERE id=%s', (booking,)).fetchone()[0].astimezone(IST)
            moved = original + timedelta(hours=1)
            closure = original + timedelta(hours=2)
            identifier = secrets.token_hex(16)
            fixture = {'id': identifier, 'origin': origin, 'reference': str(reference),
                       'old_receipt': old_receipt, 'payment': 'pay_drill',
                       'day': str(original.date()), 'moved': moved.strftime('%Y-%m-%dT%H:%M'),
                       'closure_start': closure.strftime('%Y-%m-%dT%H:%M'),
                       'closure_end': (closure+timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')}
            fixture_path = ARTIFACTS/'chrome-fixture.json'
            fixture_path.write_text(json.dumps(fixture))
            fixture_path.chmod(0o600)
            server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False,
                ssl_keyfile=str(folder/'server.key'), ssl_certfile=str(folder/'server.crt')))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
            thread.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(.05)
                if not server.started:
                    raise RuntimeError('Chrome fixture did not start.')
                print('Chrome fixture ready. Only the owned local database is connected.', flush=True)
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    if completed.is_file():
                        result = json.loads(completed.read_text())
                        if result.get('id') != identifier or not result.get('passed'):
                            raise RuntimeError('Chrome assertions failed or completion identity changed.')
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Chrome fixture timed out without completion proof.')
                with database.owner() as connection:
                    saved = connection.execute('SELECT state,revision,email,phone,starts_at FROM sarsa_booking.bookings WHERE id=%s', (booking,)).fetchone()
                    assert saved == ('cancelled', 4, 'corrected@example.com', '+919876543211', moved)
                    assert connection.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE booking_id=%s AND released_at IS NULL', (booking,)).fetchone()[0] == 0
                    assert connection.execute('SELECT count(*) FROM sarsa_booking.accepted_payments WHERE booking_id=%s', (booking,)).fetchone()[0] == 1
                    assert connection.execute('SELECT count(*) FROM sarsa_booking.receipt_recoveries WHERE request_id=%s AND redeemed_at IS NOT NULL', (reference,)).fetchone()[0] == 1
                    assert dict(connection.execute('SELECT action,count(*) FROM sarsa_booking.staff_calendar_actions GROUP BY action').fetchall()) == {'close': 1, 'reopen': 1}
                    assert connection.execute("SELECT count(*) FROM sarsa_booking.studio_audit WHERE action='signin'").fetchone()[0] == 1
                result.update(committed_sql_verified=True, providers_contacted=False,
                              measured_at=datetime.now().astimezone().isoformat())
                result.pop('id')
                (ARTIFACTS/'chrome-proof.json').write_text(json.dumps(result, indent=2)+'\n')
                print('PASS: Chrome sign-in, support correction, recovered receipt, reschedule, cancellation and blocked-time reopening match committed SQL.', flush=True)
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                fixture_path.unlink(missing_ok=True)
                completed.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
