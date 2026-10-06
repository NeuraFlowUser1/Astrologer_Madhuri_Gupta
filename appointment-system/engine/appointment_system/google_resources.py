"""Exact resource/owner/client bindings and one current encrypted grant protocol."""
from dataclasses import dataclass,field
from datetime import datetime
import re
from types import MappingProxyType
from cryptography.fernet import Fernet,MultiFernet,InvalidToken
from .configuration import installation,owners,origin
from .errors import Rejected,invalid
from .google_oauth import OAuthSettings,GoogleOAuth,Grant,GoogleFailure,RESOURCE_ROLES,EMAIL_SCOPE
from .keys import KeyRing,material
from .protected_records import ProtectedRecords
from .serialization import canonical,decode,object_fields,record_id,integer

CLIENT=re.compile(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com\Z')
PURPOSE='appointment:v1:google-resource-grant'

def normalized_scopes(values):
    if (type(values) is not list or not values or len(values)>8 or any(type(x) is not str for x in values)
        or len(set(values))!=len(values)):raise invalid('google_scopes')
    result=frozenset(EMAIL_SCOPE if item=='email' else item for item in values)
    if len(result)!=len(values):raise invalid('google_scopes')
    return result

@dataclass(frozen=True)
class Client:
    client_id: str
    secret: str=field(repr=False)
    kind: str
    def __post_init__(self):
        OAuthSettings(self.client_id,self.secret,origin())
        if self.kind not in ('web','desktop'):raise invalid('google_client_kind')

@dataclass(frozen=True)
class Resource:
    name: str
    owner_email: str
    active_client: str
    retained_clients: tuple

class Resources:
    def __init__(self,document,cipher,*,transport=None):
        value=decode(canonical(document) if type(document) is dict else document);facts=installation()
        object_fields(value,{'version','installation_id','environment','purpose','clients','resources'})
        integer(value['version'],1,1)
        if (value['installation_id']!=facts['installation_id'] or value['environment']!=facts['environment']
            or value['purpose']!='google-resource-connections' or type(value['clients']) is not list
            or not 1<=len(value['clients'])<=8 or type(value['resources']) is not dict
            or set(value['resources'])-set(RESOURCE_ROLES) or not value['resources']):raise invalid('google_resource_connections')
        clients={}
        for item in value['clients']:
            object_fields(item,{'client_id','client_secret','kind'})
            client=Client(item['client_id'],item['client_secret'],item['kind'])
            if client.client_id in clients:raise invalid('google_client_duplicate')
            clients[client.client_id]=client
        resources={}
        for name,spec in value['resources'].items():
            object_fields(spec,{'owner_email','active_client','retained_clients'})
            if (spec['owner_email']!=owners()[RESOURCE_ROLES[name]] or type(spec['retained_clients']) is not list
                or not 1<=len(spec['retained_clients'])<=8
                or any(type(x) is not str or x not in clients for x in spec['retained_clients'])
                or len(set(spec['retained_clients']))!=len(spec['retained_clients'])
                or spec['active_client'] not in spec['retained_clients'] or clients[spec['active_client']].kind!='web'):
                raise invalid('google_resource_owner_or_client')
            resources[name]=Resource(name,spec['owner_email'],spec['active_client'],tuple(spec['retained_clients']))
        if not isinstance(cipher,ResourceCipher):raise invalid('google_resource_cipher')
        self.clients=MappingProxyType(clients);self.resources=MappingProxyType(resources);self.cipher=cipher;self.transport=transport

    @classmethod
    def from_environment(cls,environment,*,transport=None):
        from .secret_configuration import ring
        return cls(environment['BOOKING_GOOGLE_RESOURCES'],ResourceCipher(ring(environment,'BOOKING_GOOGLE_RESOURCE_KEYS','google-resource-grant'),
                    environment.get('BOOKING_LEGACY_RESOURCE_READERS')),transport=transport)

    def provider(self,name,*,client_id=None,callback='/api/company/resources/callback'):
        selected=self.resources.get(name)
        if selected is None:raise GoogleFailure('google_resource_setup_required')
        pinned=client_id or selected.active_client
        if pinned not in selected.retained_clients:raise GoogleFailure('google_client_mismatch')
        client=self.clients[pinned]
        return GoogleOAuth(OAuthSettings(client.client_id,client.secret,origin(),callback),transport=self.transport,resource=name)

    def metadata(self):
        return {name:{'owner_email':spec.owner_email,'active_client':spec.active_client,
                     'retained_clients':list(spec.retained_clients)} for name,spec in self.resources.items()}

class ResourceCipher:
    def __init__(self,ring,legacy=None):
        if not isinstance(ring,KeyRing) or ring.purpose!='google-resource-grant':raise invalid('google_resource_keys')
        self.protected=ProtectedRecords(ring);self.ring=ring;readers={}
        if legacy is not None:
            value=decode(canonical(legacy) if type(legacy) is dict else legacy);object_fields(value,{'version','installation_id','environment','purpose','readers'})
            facts=installation();integer(value['version'],1,1)
            if (value['installation_id']!=facts['installation_id'] or value['environment']!=facts['environment']
                or value['purpose']!='google-resource-grant' or type(value['readers']) is not dict or len(value['readers'])>8):
                raise invalid('google_resource_readers')
            for name,spec in value['readers'].items():
                object_fields(spec,{'algorithm','prefix','version','project','environment','purpose','role','keys'})
                raw=spec['algorithm']=='fernet-token-raw'
                if (type(name) is not str or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',name) or name in ('v1','reauthorization-required')
                    or spec['algorithm'] not in ('fernet-token-json','fernet-token-raw') or type(spec['prefix']) is not str
                    or (spec['prefix']!='' if raw else not re.fullmatch('[A-Za-z0-9_-]{1,40}\\.',spec['prefix']))
                    or spec['role'] not in ('client','client_sheet','agency_sheet')
                    or spec['purpose'] not in ('calendar_refresh','drive_refresh','drive_client_secret')
                    or raw and (spec['purpose']!='calendar_refresh' or spec['role']!='client' or spec['version']!=1)
                    or type(spec['version']) is not int or spec['version'] not in (1,2)
                    or type(spec['project']) is not str or not 1<=len(spec['project'])<=75
                    or spec['environment'] not in ('production','test','development')
                    or type(spec['keys']) is not list or not 1<=len(spec['keys'])<=8 or len(set(spec['keys']))!=len(spec['keys'])):
                    raise invalid('google_resource_readers')
                for key in spec['keys']:material(key,32)
                readers[name]=(MultiFernet([Fernet(key) for key in spec['keys']]),MappingProxyType({k:v for k,v in spec.items() if k!='keys'}))
        self.readers=MappingProxyType(readers)

    def record(self,identifier):return 'google-resource-grant:'+record_id(str(identifier))

    def seal(self,identifier,client_id,grant):
        if not isinstance(grant,Grant) or not grant.resources or type(client_id) is not str or not CLIENT.fullmatch(client_id):raise GoogleFailure('google_grant_invalid')
        value={'purpose':PURPOSE,'grant_id':record_id(str(identifier)),'client_id':client_id,'resources':list(grant.resources),
         'role':grant.role,'subject':grant.subject,'email':grant.email,'refresh_token':grant.refresh_token,
         'scopes':sorted(grant.scopes),'refresh_expires_at':grant.refresh_expires_at.isoformat() if grant.refresh_expires_at else None}
        return self.protected.seal(self.record(identifier),value)

    def open(self,saved,resource,*,now):
        try:
            if (resource not in RESOURCE_ROLES or saved['owner_email']!=owners()[RESOURCE_ROLES[resource]]
                or resource not in saved['resources'] or not CLIENT.fullmatch(saved['client_id'])):raise ValueError()
            if saved['grant_format']=='reauthorization-required':
                raise GoogleFailure('google_reconnect_required')
            if saved['grant_format']=='v1':
                value=self.protected.open(self.record(saved['grant_id']),saved['encrypted_grant'],purpose=PURPOSE)
                object_fields(value,{'purpose','grant_id','client_id','resources','role','subject','email','refresh_token','scopes','refresh_expires_at'})
                if (value['grant_id']!=saved['grant_id'] or value['client_id']!=saved['client_id'] or value['resources']!=saved['resources']
                    or value['subject']!=saved['subject'] or value['email']!=saved['owner_email'] or value['role']!=RESOURCE_ROLES[resource]
                    or value['scopes']!=saved['scopes']):raise ValueError()
                token=value['refresh_token'];expiry=datetime.fromisoformat(value['refresh_expires_at']) if value['refresh_expires_at'] else None
            else:
                selected=self.readers.get(saved['grant_format'])
                expected='calendar_refresh' if resource=='calendar' else 'drive_refresh'
                if selected is None or selected[1]['purpose']!=expected:raise ValueError()
                token=self.legacy_value(saved,saved['encrypted_grant'],saved['grant_format'])
                expiry=datetime.fromisoformat(saved['grant_expires_at']) if saved.get('grant_expires_at') else None
            grant=Grant(RESOURCE_ROLES[resource],saved['subject'],saved['owner_email'],token,normalized_scopes(saved['scopes']),expiry,tuple(saved['resources']))
            if grant.refresh_expires_at is not None and grant.refresh_expires_at<=now:raise GoogleFailure('google_reconnect_required')
            return grant
        except (KeyError,TypeError,ValueError,Rejected):raise GoogleFailure('google_saved_grant_invalid') from None

    def legacy_value(self,saved,encrypted,format):
        try:
            selected=self.readers.get(format)
            if selected is None or type(encrypted) is not str or len(encrypted)>32768:raise ValueError()
            crypt,spec=selected
            if not encrypted.startswith(spec['prefix']):raise ValueError()
            raw=crypt.decrypt(encrypted[len(spec['prefix']):].encode())
            if spec['algorithm']=='fernet-token-raw':
                # This is a retained, unbound token, not proof of its owner.
                # refresh_resource_connection verifies the account with Google
                # and commits the bound replacement BEFORE releasing access.
                token=raw.decode()
                if not 1<=len(token)<=8192 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError()
                return token
            value=decode(raw)
            binding={'version':spec['version'],'project':spec['project'],'environment':spec['environment'],
             'role':spec['role'],'purpose':spec['purpose'],'subject':saved['subject'],'identity':saved['owner_email'],
             'audience':saved['client_id'],'scopes':sorted(saved['scopes'])}
            token=value.pop('value')
            if value!=binding or type(token) is not str or not 1<=len(token)<=8192 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError()
            return token
        except (KeyError,TypeError,ValueError,UnicodeError,InvalidToken,Rejected):
            raise GoogleFailure('google_saved_grant_invalid') from None

    def seal_attempt(self,identifier,resource,client_id,attempt):
        from .google_oauth import Attempt
        if (resource not in RESOURCE_ROLES or not isinstance(attempt,Attempt) or attempt.role!=RESOURCE_ROLES[resource]
            or type(client_id) is not str or not CLIENT.fullmatch(client_id)):raise GoogleFailure('google_attempt_invalid')
        return self.protected.seal('google-resource-attempt:'+record_id(str(identifier)),dict(
          purpose='appointment:v1:google-resource-attempt',resource=resource,client_id=client_id,
          role=attempt.role,state=attempt.state,nonce=attempt.nonce,verifier=attempt.verifier))

    def open_attempt(self,saved,state):
        from .google_oauth import Attempt
        try:
            value=self.protected.open('google-resource-attempt:'+record_id(saved['id']),saved['encrypted_attempt'],
              purpose='appointment:v1:google-resource-attempt')
            object_fields(value,{'purpose','resource','client_id','role','state','nonce','verifier'})
            if (value['resource']!=saved['resource'] or value['client_id']!=saved['client_id'] or value['state']!=state
                or value['role']!=RESOURCE_ROLES[saved['resource']]):raise ValueError()
            return Attempt(value['role'],state,value['nonce'],value['verifier'])
        except (KeyError,TypeError,ValueError,Rejected):raise GoogleFailure('google_attempt_invalid') from None
