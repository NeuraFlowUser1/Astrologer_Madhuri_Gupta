"""Installation-bound payment writers and retained historical readers; no requests."""
import re
from types import MappingProxyType
from .configuration import installation
from .serialization import decode,object_fields,text
from .razorpay import Credentials,Razorpay,merchant_identity
from .recovery import Accounts
from .webhook import WebhookAccount,WebhookRegistry

IDENTIFIER=re.compile(r'[A-Za-z0-9_-]{1,80}\Z')

def scoped(value,fields):
    if type(value) is not str or not 0<len(value.encode('utf8'))<=65536:
        raise ValueError('Payment configuration is missing or oversized.')
    config=object_fields(decode(value),fields)
    facts=installation()
    if (type(config['version']) is not int or config['version']!=1
        or config['installation_id']!=facts['installation_id']
        or config['environment']!=facts['environment'] or config['provider']!='razorpay'):
        raise ValueError('Payment configuration belongs to a different installation.')
    return config

def identifier(value,maximum=80):
    if type(value) is not str or not IDENTIFIER.fullmatch(value) or len(value)>maximum:
        raise ValueError('Invalid payment credential identifier.')
    return value

def payment_accounts(value):
    config=scoped(value,{'version','installation_id','environment','provider','active_account_version','accounts'})
    if type(config['accounts']) is not list or not 1<=len(config['accounts'])<=8:
        raise ValueError('Invalid number of retained payment accounts.')
    adapters=[];versions={};key_ids=set();active=[]
    for record in config['accounts']:
        object_fields(record,{'account_version','merchant_id','mode','key_id','key_secret','state'})
        version=identifier(record['account_version']);merchant=merchant_identity(record['merchant_id'])
        if type(record['key_id']) is not str:raise ValueError('Invalid payment key identity.')
        text(record['key_secret'],16,8192)
        if (merchant is None or record['merchant_id']!=merchant or record['mode'] not in ('test','live')
            or record['state'] not in ('active','retired') or version in versions or record['key_id'] in key_ids
            or any(ord(char)<33 or ord(char)>126 for char in record['key_secret'])):
            raise ValueError('Invalid or repeated payment account identity.')
        adapter=Razorpay(Credentials(merchant,record['mode'],version,record['key_id'],record['key_secret']))
        adapter.creation_allowed=record['state']=='active'
        versions[version]=adapter;key_ids.add(record['key_id']);adapters.append(adapter)
        if adapter.creation_allowed:active.append(version)
    selected=identifier(config['active_account_version'])
    if active!=[selected] or selected not in versions:
        raise ValueError('Exactly one payment account must have create authority.')
    writer=versions[selected].credentials
    if installation()['environment']=='production' and writer.mode!='live':
        raise ValueError('Production requires a live payment account.')
    accounts=Accounts(adapters,current_versions={(writer.merchant_id,writer.mode):selected})
    accounts.versions=MappingProxyType(versions)
    return accounts

def payment_webhook(value,accounts):
    config=scoped(value,{'version','installation_id','environment','provider','purpose','key_map'})
    if config['purpose']!='razorpay-webhook' or accounts is None or type(config['key_map']) is not dict:
        raise ValueError('Payment webhook configuration is invalid.')
    if not 1<=len(config['key_map'])<=8:
        raise ValueError('Invalid number of webhook identities.')
    retained=[];key_ids=set();secrets=set()
    for version,record in config['key_map'].items():
        identifier(version);object_fields(record,{'merchant_id','keys'})
        adapter=accounts.versions.get(version)
        if (adapter is None or record['merchant_id']!=adapter.credentials.merchant_id
            or type(record['keys']) is not list or not 1<=len(record['keys'])<=2):
            raise ValueError('Webhook account does not match its retained payment account.')
        keys=[]
        for key in record['keys']:
            object_fields(key,{'key_id','secret'});key_id=identifier(key['key_id'],64);text(key['secret'],16,8192)
            if key_id in key_ids or key['secret'] in secrets or any(ord(c)<33 or ord(c)>126 for c in key['secret']):
                raise ValueError('Webhook keys must have distinct bounded identities and secrets.')
            keys.append(key['secret']);key_ids.add(key_id);secrets.add(key['secret'])
        retained.append(WebhookAccount(record['merchant_id'],adapter.credentials.mode,tuple(keys)))
    return WebhookRegistry(tuple(retained))
