"""Create one recovery key; send only to GitHub's secret API and Windows clipboard."""
import argparse
import base64
import json
import os
import subprocess
import signal
import time
from authorize import POWERSHELL
from envelope import BackupError

REPO='NeuraFlowUser1/Astrologer_Madhuri_Gupta'
NAME='SARSA_BACKUP_ENCRYPTION_KEY'


def main(replace_unused=False):
    checked=subprocess.run(['gh','api','repos/'+REPO+'/actions/secrets'],stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,timeout=30,check=False)
    if checked.returncode:raise BackupError('github_secret_names_unavailable')
    names=[item['name'] for item in json.loads(checked.stdout)['secrets']]
    if NAME in names:
        if not replace_unused:raise BackupError('backup_key_already_saved_do_not_rotate')
        if 'SARSA_BACKUP_DATABASE_URL' in names:raise BackupError('backup_replacement_requires_archived_key_review')
        workflows=subprocess.run(['gh','api','repos/'+REPO+'/actions/workflows'],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=False)
        if workflows.returncode or json.loads(workflows.stdout).get('total_count')!=0:
            raise BackupError('backup_replacement_requires_archived_key_review')
    key=base64.urlsafe_b64encode(os.urandom(32))
    clipboard=subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',
        "$ErrorActionPreference='Stop'; $sarsaKey=[Console]::In.ReadToEnd(); Set-Clipboard -Value $sarsaKey; $sarsaKey=$null"],
        input=key,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
    if clipboard.returncode:raise BackupError('backup_key_clipboard_failed')
    saved=subprocess.run(['gh','secret','set',NAME,'--repo',REPO],input=key,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=False)
    if saved.returncode:
        print('Recovery key is on the Windows clipboard. GitHub write permission was unavailable; owner must save the matching secret manually.')
    else:
        print('Recovery key saved in GitHub and copied to Windows clipboard. Owner must preserve it in the password manager before backup activation.')
    return key

if __name__=='__main__':
    try:
        parser=argparse.ArgumentParser()
        parser.add_argument('--replace-unused-key',action='store_true')
        parser.add_argument('--hold',action='store_true')
        args=parser.parse_args()
        protected_key=main(args.replace_unused_key)
        if args.hold:
            def recopy(signum,frame):
                subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',
                    "$ErrorActionPreference='Stop'; $sarsaKey=[Console]::In.ReadToEnd(); Set-Clipboard -Value $sarsaKey; $sarsaKey=$null"],
                    input=protected_key,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=True)
                print('Recovery key copied again; no private values displayed.',flush=True)
            signal.signal(signal.SIGUSR1,recopy)
            print('Temporary key holder PID:',os.getpid(),flush=True)
            print('Key retained in process memory for 30 minutes for another clipboard handoff.',flush=True)
            time.sleep(1800)
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_key_setup_failed_no_private_values_logged') from None
