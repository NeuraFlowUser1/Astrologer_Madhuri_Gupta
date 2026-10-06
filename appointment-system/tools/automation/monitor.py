"""Independent, standard-library-only observer. No database/client credentials."""
import json,os,re,sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler
from uuid import UUID

_file=Path(__file__).absolute()
if any(part.is_symlink() for part in (_file,*_file.parents)):raise SystemExit('monitor_package_path_invalid')
ROOT=_file.resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.install.package import verify
CRON='8,23,38,53 * * * *'

class MonitorError(ValueError):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise MonitorError('monitor_redirect_rejected')

def pairs(items):
    result={}
    for name,value in items:
        if name in result:raise MonitorError('monitor_document_invalid')
        result[name]=value
    return result

def document(raw):
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(MonitorError('monitor_document_invalid')))
    except (ValueError,UnicodeError,TypeError,RecursionError):raise MonitorError('monitor_document_invalid') from None

def file(path,maximum):
    path=Path(path)
    if any(part.is_symlink() for part in (path,*path.parents)) or not path.is_file():raise MonitorError('monitor_file_invalid')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    if len(raw)>maximum:raise MonitorError('monitor_file_invalid')
    return document(raw)

def public(profile):
    path=Path(profile)
    if path.resolve()!=ROOT.parent/'appointment-settings/project.json':raise MonitorError('monitor_profile_path_invalid')
    facts=file(path,131072);config=file(path.with_name('monitor.json'),4096)
    if (type(config) is not dict or set(config)!={'version','installation_id','environment','repository','cron'}
        or type(config['version']) is not int or config['version']!=1 or config['cron']!=CRON
        or type(facts) is not dict or config['installation_id']!=facts.get('installation_id')
        or config['environment']!=facts.get('environment') or config['environment']!='production'
        or type(config['repository']) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',config['repository'])):
        raise MonitorError('monitor_profile_invalid')
    try:
        if str(UUID(config['installation_id']))!=config['installation_id'] or not UUID(config['installation_id']).int:raise ValueError()
        origins=[facts['origin'],facts['worker']['origin']]
        for origin in origins:
            parsed=urlsplit(origin)
            if (type(origin) is not str or parsed.scheme!='https' or parsed.username or parsed.password or parsed.port
                or parsed.path or parsed.query or parsed.fragment or not parsed.hostname or parsed.netloc!=parsed.hostname
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',parsed.hostname) or '.' not in parsed.hostname):raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError):raise MonitorError('monitor_profile_invalid') from None
    return config,origins

def eligible(value,repository):
    if (type(value) is not dict or value.get('full_name')!=repository or value.get('default_branch')!='main'
        or value.get('visibility')!='public' or any(value.get(name) is not False for name in ('private','fork','archived','disabled'))):
        raise MonitorError('monitor_repository_ineligible')

def read(url,headers=None,*,maximum=4096,opener=None):
    opener=opener or build_opener(NoRedirect(),ProxyHandler({}))
    try:
        with opener.open(Request(url,headers=headers or {}),timeout=10) as response:
            if response.status!=200 or response.geturl()!=url:raise MonitorError('monitor_read_failed')
            raw=response.read(maximum+1)
        if len(raw)>maximum:raise MonitorError('monitor_response_too_large')
        return raw
    except MonitorError:raise
    except Exception:raise MonitorError('monitor_read_failed') from None

def run(source=None,*,opener=None):
    source=os.environ if source is None else source
    if any((name.startswith('PG') or name.startswith('BOOKING_') and name not in ('BOOKING_PROFILE','BOOKING_MONITOR_KEY')) and value for name,value in source.items()):
        raise MonitorError('monitor_private_authority_rejected')
    verify(ROOT);config,origins=public(source.get('BOOKING_PROFILE',''))
    if (source.get('GITHUB_REPOSITORY')!=config['repository'] or source.get('GITHUB_REF')!='refs/heads/main'
        or source.get('RUNNER_ENVIRONMENT')!='github-hosted' or source.get('RUNNER_OS')!='Linux'
        or source.get('GITHUB_EVENT_NAME') not in ('schedule','workflow_dispatch')):raise MonitorError('monitor_runner_ineligible')
    event=file(source.get('GITHUB_EVENT_PATH',''),65536)
    if type(event) is not dict:raise MonitorError('monitor_event_invalid')
    eligible(event.get('repository'),config['repository'])
    if source['GITHUB_EVENT_NAME']=='schedule' and event.get('schedule')!=CRON:raise MonitorError('monitor_schedule_rejected')
    token=source.get('GITHUB_TOKEN');key=source.get('BOOKING_MONITOR_KEY')
    if (type(token) is not str or not 1<=len(token)<=8192 or '\n' in token or '\r' in token
        or type(key) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}=',key)):
        raise MonitorError('monitor_credential_invalid')
    remote=document(read('https://api.github.com/repos/'+config['repository'],{
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'appointment-system-monitor'},maximum=65536,opener=opener))
    eligible(remote,config['repository'])
    health=document(read(origins[1]+'/health',{'Authorization':'Bearer '+key},opener=opener))
    if health!={'status':'healthy'}:raise MonitorError('monitor_recovery_attention')
    process=document(read(origins[0]+'/api/health',opener=opener))
    if process!={'status':'online'}:raise MonitorError('monitor_process_attention')
    state=document(read(origins[0]+'/api/service-state',opener=opener))
    if type(state) is not dict or set(state)!={'enabled','activation_epoch'} or type(state['enabled']) is not bool:
        raise MonitorError('monitor_projection_attention')
    try:
        if str(UUID(state['activation_epoch']))!=state['activation_epoch'] or not UUID(state['activation_epoch']).int:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise MonitorError('monitor_projection_attention') from None
    page=read(origins[0]+'/',maximum=524288,opener=opener)
    if not page or b'<html' not in page.lower()[:4096]:raise MonitorError('monitor_website_attention')
    return {'status':'healthy','booking_enabled':state['enabled']}

if __name__=='__main__':
    try:print(json.dumps(run(),sort_keys=True))
    except (MonitorError,ValueError,OSError) as error:
        code=str(error) if isinstance(error,MonitorError) and re.fullmatch(r'monitor_[a-z_]{1,80}',str(error)) else 'monitor_package_or_runtime_invalid'
        raise SystemExit('::error::'+code+'. Inspect this run and the private company controls.') from None
