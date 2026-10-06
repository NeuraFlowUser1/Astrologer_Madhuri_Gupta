"""Maintenance-only restore reconciliation; never auto-enables or dispatches.

A lost reply resumes the saved SQL operation and exact expected generation.
The application does not construct this helper or receive its reconcile key.
"""
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass,field
from uuid import UUID
import httpx
from psycopg.types.json import Jsonb
from psycopg.pq import TransactionStatus
from .service_control import PROJECT,ControlError,canonical,snapshot,unique_json
from .control_publication import PublicationSettings,Publisher,signature
from .configuration import installation,worker_origin

@dataclass(frozen=True,repr=False)
class RecoverySettings:
    read_key:bytes=field(repr=False)
    reconcile_key:bytes=field(repr=False)
    publish_key:bytes=field(repr=False)
    origin:str
    def __post_init__(self):
        keys=(self.read_key,self.reconcile_key,self.publish_key)
        if self.origin!=worker_origin() or any(not isinstance(k,bytes) or len(k)!=32 for k in keys) or len(set(keys))!=3:
            raise ControlError('restore_configuration')

class RecoveryDatabase:
    """An explicitly supplied recovered-owner connection, outside serving paths.

    The operator must isolate this target before calling; this class never
    chooses or restores a SQL destination or starts any delivery worker.
    """
    def __init__(self,connection):
        if connection.info.transaction_status!=TransactionStatus.IDLE:raise ControlError('restore_connection_busy')
        # Each protected operation must commit before any external side effect.
        # A caller-owned outer transaction could otherwise leave an intent unsaved.
        connection.autocommit=True
        self.connection=connection
        with connection.transaction():
            connection.execute("SET LOCAL statement_timeout='3s'")
            facts=installation()
            accepted=connection.execute('SELECT appointment_system.validate_caller(%s,%s,%s,1)',
                (facts['installation_id'],facts['environment'],'maintenance')).fetchone()[0]
            if accepted is not True:raise ControlError('restore_maintenance_required')
            snapshot(connection.execute('SELECT appointment_system.restore_current()').fetchone()[0])
    def call(self,sql,args=()):
        with self.connection.transaction():
            self.connection.execute("SET LOCAL statement_timeout='3s'")
            self.connection.execute("SET LOCAL lock_timeout='2s'")
            facts=installation()
            accepted=self.connection.execute('SELECT appointment_system.validate_caller(%s,%s,%s,1)',
                (facts['installation_id'],facts['environment'],'maintenance')).fetchone()[0]
            if accepted is not True:raise ControlError('restore_maintenance_required')
            row=self.connection.execute(sql,args).fetchone()
            return row[0] if row else None
    def saved(self,operation):
        return self.call('SELECT appointment_system.restore_saved(%s)',(operation,))
    def barrier(self,operation,external):
        return self.call('SELECT appointment_system.control_restore_barrier(%s,%s)',(operation,Jsonb(external)))
    def current(self):return self.call('SELECT appointment_system.restore_current()')
    def claim_publication(self):return self.call('SELECT appointment_system.restore_claim_publication()')
    def finish_publication(self,job,ack,error):
        return self.call('SELECT appointment_system.restore_finish_publication(%s,%s,%s,%s)',
            (job['operation_id'],job['lease_token'],Jsonb(ack) if ack is not None else None,error))
    def claim_probe(self):return self.call('SELECT appointment_system.restore_claim_probe()')
    def record_probe(self,job,observed):return self.call('SELECT appointment_system.restore_record_probe(%s,%s)',(job['operation_id'],Jsonb(observed)))
    def probe_retry(self,job,error):return self.call('SELECT appointment_system.restore_probe_retry(%s,%s,%s)',(job['operation_id'],job['lease_token'],error))
    def confirm(self,operation,projection,privacy):
        return self.call('SELECT appointment_system.control_confirm_restore(%s,%s,%s,%s)',
            (operation,Jsonb(projection),privacy['sequence'],privacy['head_hash']))

class RestoreReconciliation:
    def __init__(self,database,settings,privacy_replay,*,transport=None,clock=None):
        if not callable(privacy_replay):raise ControlError('restore_privacy_replay_required')
        settings.__post_init__()
        self.database,self.settings,self.privacy_replay=database,settings,privacy_replay
        self.transport,self.clock=transport,clock or (lambda:int(time.time()*1000))
    def exchange(self,path,*,body=None,nonce=None):
        try:
            self.settings.__post_init__()
            headers={'X-Booking-State-Nonce':nonce} if body is None else {'Content-Type':'application/json',
                'X-Booking-Control-Signature':signature(self.settings.reconcile_key,'reconcile',body)}
            with httpx.Client(timeout=httpx.Timeout(3,connect=2),follow_redirects=False,trust_env=False,transport=self.transport) as client:
                with client.stream('GET' if body is None else 'POST',self.settings.origin+path,headers=headers,
                                   **({} if body is None else {'content':canonical(body)})) as response:
                    if response.status_code!=200:raise ControlError('restore_external_state_unavailable')
                    if response.headers.get('content-type','').split(';')[0]!='application/json':raise ValueError()
                    data=bytearray();started=time.monotonic()
                    for block in response.iter_bytes():
                        data.extend(block)
                        if len(data)>4096 or time.monotonic()-started>3:raise ValueError()
                    return unique_json(bytes(data))
        except ControlError:raise
        except (httpx.HTTPError,ValueError,TypeError,KeyError):raise ControlError('restore_external_state_unavailable') from None
    def checked(self,value,purpose,operation,expected,nonce=None):
        facts=installation()
        names={'version','installation_id','project','environment','purpose','operation_id','issued_at_ms','published_at_ms','snapshot','snapshot_hash','reconcile_pending','signature'}
        if nonce is not None:names.add('nonce')
        if (not isinstance(value,dict) or set(value)!=names or type(value['version']) is not int or value['version']!=1
            or value['installation_id']!=facts['installation_id'] or value['project']!=PROJECT or value['environment']!=facts['environment'] or value['purpose']!=purpose
            or value['operation_id']!=operation or type(value['issued_at_ms']) is not int
            or abs(self.clock()-value['issued_at_ms'])>60000 or type(value['published_at_ms']) is not int or not 0<value['published_at_ms']<=value['issued_at_ms'] or type(value['reconcile_pending']) is not bool
            or not isinstance(value['signature'],str) or not re.fullmatch(r'[a-f0-9]{64}',value['signature'])
            or (nonce is not None and value['nonce']!=nonce)):
            raise ControlError('restore_external_proof_invalid')
        raw=value['snapshot']
        pending=value['reconcile_pending']
        if pending:
            if purpose!='reconcile-ack' or not isinstance(raw,dict) or raw.get('enabled') is not False or raw.get('revision')!='0':
                raise ControlError('restore_external_proof_invalid')
            accepted=snapshot(raw|{'revision':'1'})|{'revision':'0'}
        else:accepted=snapshot(raw)
        secret=self.settings.read_key if purpose=='read' else self.settings.reconcile_key
        if (value['snapshot_hash']!=hashlib.sha256(canonical(accepted)).hexdigest()
            or not hmac.compare_digest(value['signature'],signature(secret,purpose,{k:v for k,v in value.items() if k!='signature'}))
            or (expected is not None and accepted!=expected)):
            raise ControlError('restore_external_proof_invalid')
        return accepted
    def read(self):
        nonce=secrets.token_hex(32);value=self.exchange('/service-state',nonce=nonce)
        return self.checked(value,'read',None,None,nonce)
    def run(self,operation):
        try:
            if not isinstance(operation,str) or str(UUID(operation))!=operation:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ControlError('restore_operation_invalid') from None
        saved=self.database.saved(operation)
        if saved is None:
            external=self.read()
            saved=self.database.barrier(operation,external)
        else:external=snapshot(saved['external_snapshot'])
        recovered=snapshot(saved['snapshot'])
        if (saved['operation_id']!=operation or recovered['enabled'] or recovered['revision']!='1'
            or recovered['restore_generation']==external['restore_generation']
            or int(recovered['generation_sequence'])!=int(external['generation_sequence'])+1
            or snapshot(self.database.current())!=recovered):
            raise ControlError('restore_saved_state_changed')
        barrier=recovered|{'revision':'0'}
        facts=installation()
        body={'version':1,'installation_id':facts['installation_id'],'project':PROJECT,'environment':facts['environment'],'purpose':'reconcile',
              'operation_id':operation,'issued_at_ms':self.clock(),'snapshot':barrier,
              'action':'advance_generation','expected_generation':external['restore_generation']}
        value=self.exchange('/service-control/reconcile',body=body)
        if not isinstance(value,dict):raise ControlError('restore_external_proof_invalid')
        expected=barrier if value.get('reconcile_pending') is True else recovered
        self.checked(value,'reconcile-ack',operation,expected)
        # Ordinary signed OFF publication finishes the reserved revision-zero
        # barrier. It cannot initialize or reset a generation.
        Publisher(self.database,PublicationSettings(self.settings.publish_key,self.settings.read_key,self.settings.origin),transport=self.transport,clock=self.clock)._publish()
        current=self.read()
        if current!=recovered:raise ControlError('restore_publication_unconfirmed')
        privacy=self.privacy_replay(operation,recovered['restore_generation'])
        if (not isinstance(privacy,dict) or set(privacy)!={'project','environment','restore_generation','sequence','head_hash','unresolved'}
            or privacy['project']!=PROJECT or privacy['environment']!=facts['environment']
            or privacy['restore_generation']!=recovered['restore_generation'] or type(privacy['sequence']) is not int
            or not 0<=privacy['sequence']<=9223372036854775807 or privacy['unresolved']!=0 or type(privacy['unresolved']) is not int
            or not isinstance(privacy['head_hash'],str) or not re.fullmatch(r'[a-f0-9]{64}',privacy['head_hash'])):
            raise ControlError('restore_privacy_replay_unconfirmed')
        result=self.database.confirm(operation,current,privacy)
        if not isinstance(result,dict) or result.get('verified') is not True or result.get('operation_id')!=operation:
            raise ControlError('restore_completion_unconfirmed')
        return {'operation_id':operation,'verified':True,'enabled':False}
