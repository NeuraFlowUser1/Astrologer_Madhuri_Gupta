"""Bounded 004 release operator; secrets are read only from existing encrypted stores.

Not imported by the product or its build. Preflight reads configuration/status;
maintenance uses only the official revision-checked company switch. No customer,
mail, payment, calendar, settings-save or provider-dispatch endpoint is called.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
from uuid import uuid4
import httpx

FACTORY=next(p for p in Path(__file__).resolve().parents if p.name=='neuraflow-website-factory')
SHARED=FACTORY/'04-shared-tools/003-appointment-booking-system'
E=Path(__file__).resolve().parent
APP=E.parents[3]
ORIGIN='https://www.sarsajyotishsansthan.com'
INSTALLATION='87b35f80-71bc-4ee1-bf34-a7316006f95c'
OLD='54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a'
NEW='1bb6cb1cc00a2ead7cec70de052ea78330005d7644dfc0d2e2a40ea7c287b31f'

class Stop(ValueError):pass

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(name,value):
    (E/name).write_text(json.dumps(value,indent=2)+'\n')

def request(client,method,path,body=None,csrf=None):
    headers={'Origin':ORIGIN,'Content-Type':'application/json'}
    if csrf:headers['x-company-csrf']=csrf
    response=client.request(method,path,json=body,headers=headers)
    if response.status_code not in (200,202):
        raise Stop('official_endpoint_refused_'+str(response.status_code)+'_'+path)
    data=response.json()
    if type(data) is not dict:raise Stop('official_endpoint_shape_invalid')
    return data

def snapshot(state):
    snap=state.get('snapshot',{})
    if (snap.get('installation_id')!=INSTALLATION or snap.get('origin')!=ORIGIN
        or snap.get('environment')!='production' or snap.get('project')!='004'):
        raise Stop('official_installation_identity_mismatch')
    csrf=state.get('csrf_token')
    if type(csrf) is not str or not re.fullmatch('[a-f0-9]{64}',csrf):raise Stop('company_session_invalid')
    public={k:snap.get(k) for k in ('installation_id','project','origin','environment','enabled','restore_generation','revision')}
    public.update({k:state.get(k) for k in ('requested_mode','admission_mode','operation_id','progress')})
    return snap,csrf,public

def company(action):
    private=module('existing_company_credentials',SHARED/'001-implementation-evidence/2026-10-07-booking-experience/company-credential-store.py')
    with httpx.Client(base_url=ORIGIN,timeout=35,trust_env=False,follow_redirects=False) as client:
        signed=False;csrf=None
        try:
            values=private.access('004')
            try:login=request(client,'POST','/api/company/sign-in/start',values)
            finally:values.clear()
            if login.get('signed_in') is not True:raise Stop('company_signin_not_confirmed')
            signed=True
            state=request(client,'GET','/api/company/control/status')
            snap,csrf,public=snapshot(state)
            if action=='preflight':
                settings=request(client,'GET','/api/company/settings')
                return {'observed_at':now(),'status':public,'business_settings_revision':settings.get('revision'),
                        'business_settings_sha256':fingerprint(settings.get('settings'))}
            desired=action=='on'
            if desired:
                before=json.loads((E/'company-off.json').read_text())
                if (public['operation_id']!=before['operation_id'] or snap['restore_generation']!=before['snapshot']['restore_generation']
                    or str(snap['revision'])!=str(before['snapshot']['revision']) or public['requested_mode']!='off'):
                    raise Stop('newer_company_command_won_do_not_restore')
            elif (public['requested_mode']!='on' or public['admission_mode']!='on' or snap['enabled'] is not True):
                raise Stop('original_on_intent_not_confirmed_do_not_close')
            body={'operation_id':str(uuid4()),'generation':snap['restore_generation'],'revision':str(snap['revision']),
                  'enabled':desired,'reason':'Approved 22 October public-search and request-efficiency release: '+('restore original ON intent after matching readback' if desired else 'brief coordinated application and worker release')}
            intent={'observed_at':now(),'original_status':public,'body':body}
            path=E/('company-'+action+'-intent.json')
            with path.open('x') as handle:json.dump(intent,handle,indent=2);handle.write('\n')
            # Retry only the same idempotent operation if the reply is lost.
            for attempt in range(2):
                try:
                    reply=request(client,'POST','/api/company/control/change',body,csrf)
                    receipt=reply.get('receipt',{})
                    if receipt.get('operation_id')!=body['operation_id'] or receipt.get('requested_enabled') is not desired:
                        raise Stop('company_change_receipt_mismatch')
                    break
                except (httpx.TransportError,ValueError):
                    if attempt:raise Stop('company_change_unknown_read_saved_operation_before_retry') from None
            for attempt in range(30):
                state=request(client,'GET','/api/company/control/status');current,csrf,public=snapshot(state)
                if public['operation_id']!=body['operation_id']:raise Stop('different_company_operation_won')
                if public['requested_mode']==action and public['admission_mode']==action and current['enabled'] is desired and public['progress']=='effective':
                    result={'successful':True,'observed_at':now(),'operation_id':body['operation_id'],'snapshot':public}
                    save('company-'+action+'.json',result);return result
                time.sleep(2)
            raise Stop('company_change_not_effective_yet')
        finally:
            if signed and csrf:
                try:request(client,'POST','/api/company/sign-out',{},csrf)
                except Exception:pass
            client.cookies.clear()

def protected():
    helper=module('existing_encrypted_access',SHARED/'001-implementation-evidence/2026-10-04-complete-local-checks/validate-sarsa-access-settings.py')
    bundle=helper.private_bundle()
    try:
        with httpx.Client(timeout=35,trust_env=False,follow_redirects=False) as client:
            response=client.post(ORIGIN+'/api/internal/recovery/configuration',json={},headers={'Authorization':'Bearer '+bundle['settings']['BOOKING_RECOVERY_WORKER_KEY']})
            data=response.json()
            expected={'application','version','release_digest','provider_acceptance','configured'}
            if response.status_code!=200 or set(data)!=expected or data.get('application')!='004':raise Stop('protected_configuration_refused')
            if type(data['configured']) is not dict or not all(type(v) is bool for v in data['configured'].values()):raise Stop('protected_configuration_shape_invalid')
            health=client.get('https://sarsa-booking-recovery.neuraflowindia.workers.dev/health',headers={'Authorization':'Bearer '+bundle['settings']['BOOKING_MONITOR_KEY']})
            return {'observed_at':now(),'application':'004','release_digest':data['release_digest'],
                    'configured':data['configured'],'worker_health_status':health.status_code,'worker_health':health.json(),
                    'customer_actions':False,'provider_dispatch':False,'private_values_printed':False}
    finally:bundle.clear()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['preflight','protected','off','on']);args=parser.parse_args()
    try:
        result=protected() if args.action=='protected' else company(args.action)
        save('operator-'+args.action+'.json',result);print(json.dumps(result))
    except Exception as error:
        value={'successful':False,'checked_at':now(),'safe_error':str(error) if isinstance(error,Stop) else type(error).__name__,
               'private_values_printed':False,'action':args.action}
        save('operator-'+args.action+'-blocked.json',value);print(json.dumps(value));raise SystemExit(1) from None
