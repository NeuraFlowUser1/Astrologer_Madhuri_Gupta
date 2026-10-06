"""Fixed common worker contract. Selected customer work never comes from HTTP."""
from dataclasses import dataclass
import re
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field

LANES=('verification_email','payment_events','payment','booking_records','email_events',
       'notification_email','enquiry_records','maintenance','control_publication')
ACK_FIELDS={'contract','application','environment','installation_id','generation','release_digest',
            'run_id','lane','code','evaluated_at','processed','remaining_due','next_due_at','attention'}

@dataclass(frozen=True)
class RecoveryRuntime:
    release_digest: str
    def __post_init__(self):
        if not isinstance(self.release_digest,str) or not re.fullmatch('[a-f0-9]{64}',self.release_digest):
            raise ValueError('Worker release identity is required.')

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    run_id: str
    release_digest: str

class PlanInput(Input):
    scheduled_at: int=Field(ge=0,le=2**63-1)

class TurnInput(Input):
    generation: str

def checked_identifier(value):
    parsed=UUID(value)
    if not parsed.int or str(parsed)!=value:raise ValueError('worker_identity_invalid')
    return parsed

def checked_ack(value,body,lane,runtime):
    from .configuration import installation
    facts=installation()
    if (not isinstance(value,dict) or set(value)!=ACK_FIELDS or type(value['contract']) is not int or value['contract']!=1
        or value['application']!=facts['project_id'] or value['environment']!=facts['environment']
        or value['installation_id']!=facts['installation_id'] or value['release_digest']!=runtime.release_digest
        or value['run_id']!=body.run_id or value['generation']!=body.generation or value['lane']!=lane
        or value['code'] not in ('evaluated-empty','completed-work','deferred')
        or type(value['processed']) is not int or value['processed'] not in (0,1)
        or type(value['evaluated_at']) is not int or value['evaluated_at']<0
        or type(value['remaining_due']) is not int or not 0<=value['remaining_due']<=10000
        or (value['next_due_at'] is not None and (type(value['next_due_at']) is not int or value['next_due_at']<0))
        or type(value['attention']) is not bool):raise ValueError('worker_result_invalid')
    return value

def operation(store,lane,resource,*,sender,code_keys,contact_keys,google,accounts,publisher):
    from .booking_verification_delivery import run_booking_code_once
    from .contact_delivery import run_contact_email_once,run_contact_google_once
    from .email_delivery import run_email_delivery_once
    from .google_delivery import run_google_delivery_once
    from .recovery import run_payment_event_once,run_payment_recovery_once
    if lane=='verification_email':
        if sender is None or (code_keys if resource=='booking_code' else contact_keys) is None:raise ValueError('mail_connection_unavailable')
        return (run_booking_code_once(store,sender,code_keys) if resource=='booking_code'
                else run_contact_email_once(store,sender,contact_keys,kind='verification'))
    if lane=='notification_email':
        if sender is None or resource=='enquiry' and contact_keys is None:raise ValueError('mail_connection_unavailable')
        return (run_email_delivery_once(store,sender) if resource=='booking'
                else run_contact_email_once(store,sender,contact_keys,kind='notification'))
    if lane=='email_events':
        methods={'booking':store.reconcile_email_event,'enquiry':store.reconcile_enquiry_email_event,
                 'verification':store.reconcile_booking_code_email_event}
        return {'processed':int(methods[resource]())}
    if lane=='payment_events':
        if accounts is None:raise ValueError('payment_connection_unavailable')
        return run_payment_event_once(store,accounts,source=resource)
    if lane=='payment':
        if accounts is None:raise ValueError('payment_connection_unavailable')
        return run_payment_recovery_once(store,accounts)
    if lane in ('booking_records','enquiry_records'):
        if google is None:raise ValueError('google_connection_unavailable')
        from .sheet_projection import run_projection_once
        projected=run_projection_once(store,google,'booking' if lane=='booking_records' else 'enquiry',resource)
        if projected is not None:return projected
        return (run_google_delivery_once(store,google,resource=resource) if lane=='booking_records'
                else run_contact_google_once(store,google,resource=resource))
    if lane=='control_publication':
        if publisher is None:raise ValueError('publication_connection_unavailable')
        return publisher()
    store.expire_enquiry_codes()
    result=store.cleanup_temporary_records()
    if not isinstance(result,dict) or type(result.get('processed')) is not int or result['processed'] not in (0,1):
        raise ValueError('maintenance_result_invalid')
    return result

def add_routes(app,store,runtime,*,recovery_key,email_key,google_key,sender,code_keys,contact_keys,google,accounts,publisher):
    def authorize(request,body,key):
        if runtime is None or key is None:return JSONResponse({'code':'worker_unavailable'},503)
        if not key.accepts(request.headers):return JSONResponse({'code':'unauthorized'},401)
        try:
            checked_identifier(body.run_id)
            if isinstance(body,TurnInput):checked_identifier(body.generation)
        except ValueError:return JSONResponse({'code':'worker_identity_invalid'},422)
        if body.release_digest!=runtime.release_digest:return JSONResponse({'code':'release_mismatch'},409)

    @app.post('/api/internal/worker/plan',include_in_schema=False)
    def plan(request:Request,body:PlanInput):
        refusal=authorize(request,body,recovery_key)
        if refusal is not None:return refusal
        result=store.begin_recovery_run(body.run_id,body.release_digest,body.scheduled_at)
        if result.get('code'):return JSONResponse({'code':result['code']},409)
        from .serialization import canonical
        return Response(canonical(result),media_type='application/json')

    @app.post('/api/internal/worker/end',include_in_schema=False)
    def end(request:Request,body:Input):
        refusal=authorize(request,body,recovery_key)
        if refusal is not None:return refusal
        from .serialization import canonical
        return Response(canonical(store.end_recovery_run(body.run_id,body.release_digest)),media_type='application/json')

    def handler(lane):
        def turn(request:Request,body:TurnInput):
            key=(email_key if lane in ('verification_email','notification_email','email_events')
                 else google_key if lane in ('booking_records','enquiry_records') else recovery_key)
            refusal=authorize(request,body,key)
            if refusal is not None:return refusal
            chosen=store.claim_recovery_turn(body.run_id,lane,body.generation,body.release_digest)
            if chosen.get('code')!='ok':return JSONResponse({'code':chosen.get('code','turn_unavailable')},409)
            from .worker_authority import admitted,Turn
            with admitted(Turn(body.run_id,lane,body.generation,body.release_digest,chosen['lease_token'])):
                try:
                    result=operation(store,lane,chosen['resource'],sender=sender,code_keys=code_keys,contact_keys=contact_keys,
                                     google=google,accounts=accounts,publisher=publisher)
                    if (not isinstance(result,dict) or type(result.get('processed')) is not int or result['processed'] not in (0,1)
                        or any(n in result and type(result[n]) is not bool for n in ('retry','attention','deferred'))):
                        raise ValueError('worker_result_invalid')
                    retry=result.get('retry',False) or result.get('deferred',False) or result.get('state') in ('waiting','failed')
                    attention=result.get('attention',False) or result.get('state')=='attention'
                    acknowledgement=store.complete_recovery_turn(body.run_id,lane,chosen['lease_token'],body.generation,
                        body.release_digest,result['processed'],retry,attention)
                    from .serialization import canonical
                    return Response(canonical(checked_ack(acknowledgement,body,lane,runtime)),media_type='application/json')
                except Exception:
                    # Provider/business facts already committed remain authoritative.
                    # A failed diagnostic cannot erase them or manufacture completion.
                    try:store.complete_recovery_turn(body.run_id,lane,chosen['lease_token'],body.generation,body.release_digest,0,True,True)
                    except Exception:pass
                    raise
        turn.__name__='worker_'+lane
        return turn
    for lane in LANES:app.post('/api/internal/worker/'+lane,include_in_schema=False)(handler(lane))
