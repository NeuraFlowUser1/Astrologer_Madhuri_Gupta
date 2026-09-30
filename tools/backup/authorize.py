"""One-time local Google consent; verified grant goes only to Windows clipboard.

No tokens are printed, written to disk, or included in browser responses.
Uses Google's desktop loopback flow with PKCE and a random state.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import httpx
from drive import Drive, OWNER
from envelope import BackupError

SCOPE='https://www.googleapis.com/auth/drive.file'
PROJECT='sarsajyotish-backend'
POWERSHELL='/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'


def load_client(path):
    try:
        client=json.loads(Path(path).read_text())['installed']
        if (client.get('project_id')!=PROJECT or not client.get('client_id','').endswith('.apps.googleusercontent.com')
                or not isinstance(client.get('client_secret'),str) or not client['client_secret']):
            raise ValueError()
        return {'client_id':client['client_id'],'client_secret':client['client_secret']}
    except Exception:raise BackupError('backup_desktop_client_invalid') from None


def authorization_url(client,state,verifier,redirect):
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
        'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code',
        'scope':SCOPE,'state':state,'code_challenge':challenge,'code_challenge_method':'S256',
        'access_type':'offline','prompt':'consent','login_hint':OWNER})


def callback_code(path,state):
    parsed=urlsplit(path)
    values=parse_qs(parsed.query)
    received=values.get('state',[])
    if parsed.path!='/callback' or len(received)!=1 or not secrets.compare_digest(received[0],state):
        raise BackupError('backup_authorization_state_invalid')
    if 'error' in values:raise BackupError('backup_google_consent_denied')
    codes=values.get('code',[])
    if len(codes)!=1 or not codes[0]:raise BackupError('backup_authorization_code_missing')
    return codes[0]


def exchange(client,code,verifier,redirect):
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as http:
            response=http.post('https://oauth2.googleapis.com/token',data={**client,
                'code':code,'code_verifier':verifier,'redirect_uri':redirect,'grant_type':'authorization_code'})
            response.raise_for_status();value=response.json()
        if SCOPE not in value.get('scope','').split():raise BackupError('backup_drive_permission_missing')
        refresh=value.get('refresh_token')
        if not isinstance(refresh,str) or not refresh:raise BackupError('backup_offline_permission_missing')
        if value.get('refresh_token_expires_in'):
            raise BackupError('backup_google_grant_temporary_check_production_publishing')
        grant={**client,'refresh_token':refresh}
        # Fresh token refresh verifies durable access and the actual Drive owner.
        drive=Drive(grant)
        try:available=drive.available
        finally:drive.close()
        return grant,available
    except BackupError:raise
    except Exception:raise BackupError('backup_google_exchange_failed') from None


def copy_grant(grant):
    result=subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',
        "$ErrorActionPreference='Stop'; $sarsaGrant=[Console]::In.ReadToEnd(); Set-Clipboard -Value $sarsaGrant; $sarsaGrant=$null"],
        input=json.dumps(grant,separators=(',',':')).encode(),stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,timeout=20,check=False)
    if result.returncode:raise BackupError('backup_clipboard_unavailable')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--client',required=True)
    args=parser.parse_args();client=load_client(args.client)
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
    entry=secrets.token_urlsafe(24);completed=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,text):
            data=text.encode();self.send_response(status)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            nonlocal completed
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                self.reply(400,'Incorrect local address.');return
            if self.path=='/start/'+entry:
                self.send_response(302);self.send_header('Location',authorization_url(client,state,verifier,redirect))
                self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
                self.end_headers();return
            try:code=callback_code(self.path,state)
            except BackupError as error:
                self.reply(400,str(error));return
            try:
                grant,available=exchange(client,code,verifier,redirect)
                copy_grant(grant)
                print('Google owner verified:',OWNER,flush=True)
                print('Drive free bytes:',available,flush=True)
                print('Protected backup grant copied to Windows clipboard. Paste into SARSA_BACKUP_GOOGLE only. No files uploaded.',flush=True)
                self.reply(200,'Sarsa Drive verified. Backup permission is on your clipboard. Return to Codex for the protected GitHub setting. No backup has been uploaded yet.')
            except BackupError as error:
                print(str(error),flush=True);self.reply(400,str(error))
            except Exception:
                print('backup_authorization_failed',flush=True);self.reply(400,'Backup setup could not finish. Return to Codex.')
            completed=True
    with HTTPServer(('127.0.0.1',0),Handler) as server:
        server.timeout=1
        redirect=f'http://127.0.0.1:{server.server_port}/callback'
        print(f'Open http://127.0.0.1:{server.server_port}/start/{entry}',flush=True)
        print('Choose '+OWNER+'. This local approval window expires in 15 minutes.',flush=True)
        deadline=time.monotonic()+900
        while not completed and time.monotonic()<deadline:server.handle_request()
        if not completed:raise BackupError('backup_authorization_expired')

if __name__=='__main__':
    try:main()
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_authorization_setup_failed') from None
