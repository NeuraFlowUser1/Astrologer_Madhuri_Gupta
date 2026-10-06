"""Resolve an actual successful owned export before exposing validation secrets."""
import os
from pathlib import Path
import re
import sys
_source=Path(__file__).absolute()
if any(path.is_symlink() for path in (_source,*_source.parents)):raise SystemExit('backup_package_path_invalid')
ROOT=_source.resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))
from tools.automation.backup import public_settings,bounded_file,github_read
from tools.automation.eligibility import runner,source_run
from appointment_system.backup.protocol import BackupError,unique_json
from tools.install.package import verify

def main(source=None):
    import httpx
    source=os.environ if source is None else source
    if any(name.startswith('BOOKING_') and value and name!='BOOKING_PROFILE' for name,value in source.items()):raise BackupError('backup_trigger_private_authority_rejected')
    verify(ROOT)
    config=public_settings(source.get('BOOKING_PROFILE',''));event=unique_json(bounded_file(source.get('GITHUB_EVENT_PATH',''),65536))
    runner(source,config['repository'],event)
    if source.get('GITHUB_EVENT_NAME')=='workflow_run':run=str(event.get('workflow_run',{}).get('id',''))
    elif source.get('GITHUB_EVENT_NAME')=='workflow_dispatch':run=event.get('inputs',{}).get('source_run','')
    else:raise BackupError('backup_validator_trigger_rejected')
    if type(run) is not str or not re.fullmatch('[1-9][0-9]{0,19}',run):raise BackupError('backup_validator_trigger_rejected')
    with httpx.Client(timeout=httpx.Timeout(10,connect=3),follow_redirects=False,trust_env=False) as client:
        repository=github_read('',config['repository'],source.get('GITHUB_TOKEN'),client)
        record=github_read('actions/runs/'+run,config['repository'],source.get('GITHUB_TOKEN'),client)
        run,attempt,commit=source_run(record,repository,config['repository'],run)
    output=source.get('GITHUB_OUTPUT')
    if type(output) is not str or not output:raise BackupError('backup_output_missing')
    with open(output,'a',encoding='utf-8') as target:target.write('source_run='+run+'\nsource_attempt='+attempt+'\nsource_commit='+commit+'\n')
    print('Owned successful export verified. No archive-selected code will execute.')

if __name__=='__main__':
    try:main()
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_trigger_check_failed') from None
