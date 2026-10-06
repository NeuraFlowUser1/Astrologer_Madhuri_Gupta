"""Prepare an existing project's worker config locally; never deploy or delete storage."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import date
from .package import PackageError,git_root,verify,locked

CLASSES=('BookingProductState','BookingRecoveryState')
TAGS=('booking-product-sqlite-v1','appointment-recovery-sqlite-v1')

def configuration(previous,project,release,entry):
    if (type(previous) is not dict or previous.get('name')!=project['worker']['name']
        or type(previous.get('account_id')) is not str or not re.fullmatch('[a-f0-9]{32}',previous['account_id'])
        or type(previous.get('compatibility_date')) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',previous['compatibility_date'])):
        raise PackageError('Explicit matching worker and account facts are required.')
    try:date.fromisoformat(previous['compatibility_date'])
    except ValueError:raise PackageError('Invalid worker compatibility date.') from None
    queues=previous.get('queues');consumers=queues.get('consumers') if type(queues) is dict else None
    if (type(consumers) is not list or len(consumers)!=1 or type(consumers[0]) is not dict
        or type(consumers[0].get('queue')) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}',consumers[0]['queue'])):
        raise PackageError('One existing owned wake queue is required.')
    migrations=previous.get('migrations',[])
    if type(migrations) is not list:raise PackageError('Worker migration history is required.')
    migrations=json.loads(json.dumps(migrations));seen=set();tags=set()
    for row in migrations:
        if (type(row) is not dict or set(row)!={'tag','new_sqlite_classes'}
            or type(row['tag']) is not str or not row['tag'] or row['tag'] in tags
            or type(row['new_sqlite_classes']) is not list or not row['new_sqlite_classes']):
            raise PackageError('Worker history requires explicit review; destructive migrations are not generated.')
        tags.add(row['tag'])
        for name in row['new_sqlite_classes']:
            if name not in CLASSES or name in seen:raise PackageError('Unknown or repeated worker storage class.')
            seen.add(name)
    for name,tag in zip(CLASSES,TAGS):
        if name not in seen:
            if tag in tags:raise PackageError('Worker migration tag conflict.')
            migrations.append({'tag':tag,'new_sqlite_classes':[name]})
    queue=consumers[0]['queue']
    return {'name':project['worker']['name'],'account_id':previous['account_id'],'main':entry,
        'compatibility_date':previous['compatibility_date'],'workers_dev':True,'preview_urls':False,
        'vars':{'BOOKING_INSTALLATION_ID':project['installation_id'],'BOOKING_PROJECT_ID':project['project_id'],
            'BOOKING_ENVIRONMENT':project['environment'],'BOOKING_PUBLIC_ORIGIN':project['origin'],
            'BOOKING_RELEASE_DIGEST':release['content_digest']},
        'triggers':{'crons':['*/15 * * * *']},
        'queues':{'producers':[{'binding':'BOOKING_WAKE_QUEUE','queue':queue}],
            'consumers':[{'queue':queue,'max_batch_size':1,'max_batch_timeout':1,'max_retries':5,'retry_delay':60,'max_concurrency':1}]},
        'observability':{'enabled':True},
        'durable_objects':{'bindings':[{'name':'BOOKING_PRODUCT_STATE','class_name':CLASSES[0]},
            {'name':'BOOKING_RECOVERY_STATE','class_name':CLASSES[1]}]},'migrations':migrations}

def prepare(target,config,*,expected_root,expected_digest):
    root=git_root(target,expected_root)
    with locked(root):return _prepare(root,config,expected_digest)

def _prepare(root,config,expected_digest):
    config=Path(config).absolute()
    if root not in config.parents or any(p.is_symlink() for p in (config,*config.parents)) or not config.is_file():
        raise PackageError('Worker configuration must be a real file in its own project.')
    raw=config.read_bytes()
    if len(raw)>32768 or hashlib.sha256(raw).hexdigest()!=expected_digest:raise PackageError('Worker configuration changed since review.')
    from appointment_system.serialization import decode
    from appointment_system.settings import Installation
    profile=root/'appointment-settings/project.json'
    if profile.is_symlink() or profile.parent.is_symlink() or profile.stat().st_size>131072:raise PackageError('Invalid project settings file.')
    project=Installation.parse(decode(profile.read_bytes())).document
    release=verify(root/'appointment-system')
    generated=configuration(decode(raw),project,release,Path(os.path.relpath(root/'appointment-system/worker/index.mjs',config.parent)).as_posix())
    encoded=(json.dumps(generated,indent=2)+'\n').encode()
    if config.read_bytes()!=raw:raise PackageError('Worker configuration changed since review.')
    if encoded!=raw:
        descriptor,temporary=tempfile.mkstemp(prefix='.appointment-worker-',dir=config.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,config)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    return {'status':'existing' if encoded==raw else 'prepared','worker':project['worker']['name'],'release_digest':release['content_digest']}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Prepare local worker configuration; no deployment or provider change.')
    parser.add_argument('target',type=Path);parser.add_argument('config',type=Path)
    parser.add_argument('--expected-root',required=True,type=Path);parser.add_argument('--expected-digest',required=True)
    args=parser.parse_args()
    try:result=prepare(args.target,args.config,expected_root=args.expected_root,expected_digest=args.expected_digest)
    except (PackageError,OSError,ValueError):raise SystemExit('Worker preparation refused. Review the owned project, queue and migration history.') from None
    print(json.dumps(result,sort_keys=True))
