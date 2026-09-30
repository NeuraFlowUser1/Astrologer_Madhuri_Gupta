"""Private Windows-DPAPI handoff to the existing Sarsa Cloudflare Worker.

Keys travel only through captured process output and the Wrangler input pipe.
Never display provider output, send keys as arguments, or write plaintext files.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / 'workers/booking-recovery'
ORIGIN = 'https://www.sarsajyotishsansthan.com'
ACCOUNT = '162c1ab1ba0619c1c78d9495f3260f18'
NAMES = ('SARSA_GOOGLE_WORKER_KEY', 'SARSA_EMAIL_WORKER_KEY',
         'SARSA_RECOVERY_WORKER_KEY', 'SARSA_WAKE_KEY')
LANES = {'contact_email', 'payment_events', 'payment', 'google',
         'email_events', 'email', 'contact_google'}
POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
NODE = '/home/anan/.nvm/versions/node/v24.19.0/bin/node'
WRANGLER = '/home/anan/.npm/_npx/e0df58cf71169f23/node_modules/wrangler/bin/wrangler.js'


class SafeFailure(Exception):
    pass


def checked_keys(values):
    if not isinstance(values, dict) or set(values) != set(NAMES):
        raise SafeFailure('private_copy_invalid')
    for value in values.values():
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=', value):
            raise SafeFailure('private_copy_invalid')
        data = base64.b64decode(value, altchars=b'-_', validate=True)
        if len(data) != 32 or base64.urlsafe_b64encode(data).decode() != value:
            raise SafeFailure('private_copy_invalid')
    if len(set(values.values())) != 4:
        raise SafeFailure('private_copy_duplicate')
    return values


def private_keys():
    # Static public paths/names only in arguments. Windows decrypts the local
    # operational copies; the enclosing process captures the output privately.
    script = r"""
$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security
$sarsaNames=@('SARSA_GOOGLE_WORKER_KEY','SARSA_EMAIL_WORKER_KEY','SARSA_RECOVERY_WORKER_KEY','SARSA_WAKE_KEY')
$sarsaBase='D:\coding\business\neuraflow-website-factory\03-client-projects\004-sarsa-jyotish-sansthan\tools\worker-settings\private'
$sarsaValues=@{}
try {
  foreach($sarsaName in $sarsaNames) {
    $sarsaBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $sarsaBase ($sarsaName+'.dpapi'))),[Text.Encoding]::UTF8.GetBytes('Sarsa Project 004 worker key v1/'+$sarsaName),[Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {
      if($sarsaBytes.Length -ne 32){throw 'invalid_copy'}
      $sarsaValues[$sarsaName]=[Convert]::ToBase64String($sarsaBytes).Replace('+','-').Replace('/','_')
    } finally {[Array]::Clear($sarsaBytes,0,$sarsaBytes.Length)}
  }
  Write-Output ($sarsaValues | ConvertTo-Json -Compress)
} catch {exit 1}
finally {$sarsaValues=$null}
"""
    result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive',
        '-EncodedCommand', base64.b64encode(script.encode('utf-16le')).decode()],
        capture_output=True, text=True, timeout=30)
    if result.returncode or len(result.stdout) > 1024:
        raise SafeFailure('private_copy_unavailable')
    try:
        return checked_keys(json.loads(result.stdout))
    finally:
        result.stdout = result.stderr = ''


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise SafeFailure('canonical_route_redirected')


def hosted_plan(keys):
    # Sole hosted request is a read-only scheduling snapshot: no consumer,
    # payment, email, Google request, customer admission or queue publication.
    request = urllib.request.Request(ORIGIN + '/api/internal/recovery/plan',
        data=b'{}', method='POST', headers={'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + keys['SARSA_RECOVERY_WORKER_KEY']})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/json':
                raise SafeFailure('canonical_plan_unavailable')
            body = response.read(8193)
    except urllib.error.HTTPError as error:
        raise SafeFailure('canonical_plan_http_' + str(error.code)) from None
    if len(body) > 8192:
        raise SafeFailure('canonical_plan_invalid')
    value = json.loads(body)
    if (not isinstance(value, dict) or set(value) != {'application', 'version', 'attention', 'lanes'}
            or value['application'] != '004-sarsa-jyotish-sansthan'
            or type(value['version']) is not int or value['version'] != 1
            or type(value['attention']) is not bool or not isinstance(value['lanes'], dict)
            or set(value['lanes']) not in (LANES,LANES | {'maintenance'})
            or any(v is not None and (type(v) is not int or not 0 <= v <= 900)
                   for v in value['lanes'].values())):
        raise SafeFailure('canonical_plan_invalid')
    return value


def wrangler(arguments, *, payload=None):
    # Wrangler interprets a path without .log as a directory. Use a unique
    # .log symlink to the null device, not /dev/null as a directory name.
    with tempfile.TemporaryDirectory(prefix='sarsa-worker-log-', dir='/tmp') as temporary:
        sink = Path(temporary) / 'private-discard.log'
        sink.symlink_to('/dev/null')
        environment = dict(os.environ, CLOUDFLARE_ACCOUNT_ID=ACCOUNT,
            CLOUDFLARE_API_BASE_URL='https://api.cloudflare.com/client/v4',
            WRANGLER_API_ENVIRONMENT='production', CLOUDFLARE_COMPLIANCE_REGION='public',
            WRANGLER_SEND_ERROR_REPORTS='false', WRANGLER_LOG_PATH=str(sink),
            WRANGLER_LOG_SANITIZE='true', WRANGLER_LOG='log', CI='true',
            WRANGLER_SEND_METRICS='false')
        result = subprocess.run([NODE, WRANGLER, *arguments], cwd=WORKER,
            env=environment, input=payload, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Do not disclose exceptions/provider output from a credential operation.
        raise SafeFailure('cloudflare_operation_failed')
    return result


def configure(keys):
    config = json.loads((WORKER / 'wrangler.json').read_text())
    if (config['account_id'] != ACCOUNT or config['name'] != 'sarsa-booking-recovery'
            or config['triggers']['crons'] != ['*/15 * * * *']
            or config['kv_namespaces'] != [{'binding': 'HEARTBEATS',
                'id': '927be5fbe5c54002ae03e55c48a0a2e5'}]
            or [v['queue'] for v in config['queues']['producers']] != ['sarsa-booking-recovery']
            or [v['queue'] for v in config['queues']['consumers']] != ['sarsa-booking-recovery']):
        raise SafeFailure('cloudflare_identity_mismatch')
    identity = json.loads(wrangler(['whoami', '--json']).stdout)
    if (identity.get('loggedIn') is not True or identity.get('email') != 'neuraflowindia@gmail.com'
            or ACCOUNT not in {v.get('id') for v in identity.get('accounts', [])}):
        raise SafeFailure('cloudflare_identity_mismatch')
    queue = wrangler(['queues', 'list']).stdout
    if not any('8d602c4b56f44eca8ae5bcfa6cde1fab' in line
               and 'sarsa-booking-recovery' in line for line in queue.splitlines()):
        raise SafeFailure('cloudflare_queue_missing')
    namespaces = json.loads(wrangler(['kv', 'namespace', 'list']).stdout)
    if not any(v.get('id') == '927be5fbe5c54002ae03e55c48a0a2e5'
               and v.get('title') == 'sarsa-booking-recovery-heartbeats' for v in namespaces):
        raise SafeFailure('cloudflare_namespace_missing')
    # Not present in input => untouched. No null/delete, rotation or other client.
    result = wrangler(['secret', 'bulk'], payload=json.dumps(keys))
    result.stdout = result.stderr = ''
    result = wrangler(['secret', 'list'])
    bindings = json.loads(result.stdout)
    if not set(NAMES).issubset({v['name'] for v in bindings if v.get('type') == 'secret_text'}):
        raise SafeFailure('cloudflare_binding_missing')
    print('Four existing protected settings configured on the dedicated Sarsa Worker. No scheduled code deployed by this action.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify-local', 'verify-hosted', 'configure-worker'])
    args = parser.parse_args()
    keys = None
    try:
        keys = private_keys()
        print('Four private operational copies are valid and distinct; no values displayed.')
        if args.action != 'verify-local':
            plan = hosted_plan(keys)
            print('Canonical authenticated scheduling snapshot accepted: ' + json.dumps(plan, sort_keys=True))
            if args.action == 'configure-worker':
                configure(keys)
    except SafeFailure as error:
        print('Sarsa handoff stopped: ' + str(error) + '. Check current state before retrying; an interrupted Cloudflare operation may already have succeeded.')
        return 1
    except Exception:
        print('Sarsa handoff stopped: local_or_network_failure. No private error output disclosed; inspect current provider state before retrying.')
        return 1
    finally:
        if keys is not None:
            keys.clear()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
