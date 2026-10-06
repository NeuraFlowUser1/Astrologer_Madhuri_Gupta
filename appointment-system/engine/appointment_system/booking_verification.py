"""Booking-only email proof, bound to the owned context and current OTP policy."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import re,secrets
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator

from .access import AccessDenied,COOKIE_NAME,context_identifier,parse_context,authorize_context
from .connection import StorageUnavailable
from .keys import KeyRing,independent,encode,material
from .protected_records import ProtectedRecords
from .receipt_view import timestamp
from .serialization import canonical
from .errors import Rejected


@dataclass(frozen=True)
class VerificationSecrets:
    digest_key:KeyRing=field(repr=False)
    cipher:ProtectedRecords=field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.digest_key,KeyRing) or not isinstance(self.cipher,ProtectedRecords)
                or self.digest_key.purpose!='booking-verification-digest'
                or self.cipher.ring.purpose!='booking-verification-encryption'):
            raise ValueError('Booking verification requires separate keys.')
        independent((self.digest_key,self.cipher.ring))

    @classmethod
    def from_environment(cls,environment):
        from .secret_configuration import ring
        return cls(ring(environment,'BOOKING_VERIFICATION_DIGEST_KEYS','booking-verification-digest'),
                   ProtectedRecords(ring(environment,'BOOKING_VERIFICATION_ENCRYPTION_KEYS','booking-verification-encryption')))

    def digest(self,purpose,*values,key_id=None):
        if purpose not in ('code','recipient','grant','message'):raise ValueError('Invalid verification purpose.')
        return self.digest_key.digest('booking-verification:'+purpose,canonical([str(value) for value in values]),key_id=key_id)

    def challenge(self,reference,context,email,generation):
        code=f'{secrets.randbelow(1000000):06d}'
        value={'purpose':'appointment:v1:booking-code','reference':str(reference),'context_id':str(context),
               'email':email,'generation':generation,'code':code,'digest_key_id':self.digest_key.active}
        return self.digest('code',reference,context,email,generation,code),self.cipher.seal('booking-code:'+str(reference)+':'+str(generation),value)

    def open_code(self,job):
        value=self.cipher.open('booking-code:'+job['challenge_id']+':'+str(job['generation']),job['code_ciphertext'],
                               purpose='appointment:v1:booking-code')
        if (value['reference']!=job['challenge_id'] or value['context_id']!=job['context_id']
                or value['email']!=job['destination'] or type(value['generation']) is not int or value['generation']!=job['generation']
                or not isinstance(value['code'],str) or not re.fullmatch(r'[0-9]{6}',value['code'])):
            raise ValueError('Saved verification code is invalid.')
        self.digest_key.key(value['digest_key_id']);return value['code']

    def issue_grant(self):return 'bv1.'+self.digest_key.active+'.'+encode(secrets.token_bytes(32)).rstrip('=')

    def grant(self,token,context,email):
        try:
            prefix,key_id,value=token.split('.')
            if prefix!='bv1' or not re.fullmatch(r'[A-Za-z0-9_-]{43}',value):raise ValueError()
            raw=material(value+'=',32)
            return self.digest('grant',context,email,raw.hex(),key_id=key_id)
        except (ValueError,TypeError,AttributeError,Rejected):raise AccessDenied() from None


class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    email:EmailStr=Field(max_length=254)


class Verify(Start):
    challenge_id:UUID
    generation:int=Field(ge=1,le=3,strict=True)
    code:str=Field(pattern=r'^[0-9]{6}$')


class Resend(Start):
    challenge_id:UUID
    generation:int=Field(ge=1,le=3,strict=True)


def add_booking_verification_routes(app,store,settings,keys,browser_request,limit,wake=None,*,deliver=None):
    def context(request):
        browser_request(request);limit(request,'checkout',booking=True)
        if keys is None or deliver is None:raise StorageUnavailable('Email verification is unavailable.')
        token=request.cookies.get(COOKIE_NAME);identifier=context_identifier(token,settings.context_key)
        snapshot=store.context_snapshot(identifier);row=snapshot.get('context')
        if row:row=dict(row,expires_at=timestamp(row['expires_at']))
        identifier,digest=parse_context(token,settings.context_key,row)
        authorize_context(row,digest,timestamp(snapshot['server_now']))
        return str(identifier)

    def outcome(value):
        codes={'verification_unavailable':503,'verification_not_required':409,'context_expired':403,
          'request_conflict':409,'verification_changed':409,'please_wait':429,'verification_limit':429,
          'verification_expired':410,'verification_incorrect':422,'verification_locked':429,'request_unresolved':409}
        if not isinstance(value,dict):raise StorageUnavailable()
        code=value.get('code')
        if code in codes:return JSONResponse({'code':code},codes[code],headers={'Retry-After':'60'} if codes[code]==429 else None)
        if code!='ok':raise StorageUnavailable()
        public={name:value[name] for name in ('code','challenge_id','generation','expires_at','state') if name in value}
        if public.get('state')=='awaiting_verification' and wake is not None:wake.publish()
        return public

    @app.post('/api/booking-verification/start')
    def start(request:Request,body:Start):
        identifier=context(request);reference=str(body.operation_id)
        digest,encrypted=keys.challenge(reference,identifier,str(body.email),1)
        result=store.start_booking_verification(identifier,body.operation_id,str(body.email),digest,encrypted,
                       keys.digest('recipient',str(body.email).lower()),keys.digest_key.active)
        if isinstance(result,dict) and result.get('mail_job_id'):
            deliver(result['mail_job_id'])
        return outcome(result)

    @app.post('/api/booking-verification/resend')
    def resend(request:Request,body:Resend):
        identifier=context(request);generation=body.generation+1
        digest,encrypted=keys.challenge(body.challenge_id,identifier,str(body.email),generation)
        result=store.resend_booking_verification(identifier,body.operation_id,body.challenge_id,str(body.email),
                       body.generation,digest,encrypted,keys.digest_key.active)
        if isinstance(result,dict) and result.get('mail_job_id'):
            deliver(result['mail_job_id'])
        return outcome(result)

    @app.post('/api/booking-verification/verify')
    def verify(request:Request,body:Verify):
        identifier=context(request)
        saved=store.booking_verification_metadata(identifier,body.challenge_id,str(body.email))
        if not isinstance(saved,dict):raise AccessDenied()
        digest=keys.digest('code',body.challenge_id,identifier,str(body.email),body.generation,body.code,key_id=saved['digest_key_id'])
        token=keys.issue_grant();grant=keys.grant(token,identifier,str(body.email))
        encrypted=keys.cipher.seal('booking-grant:'+str(body.operation_id),{'purpose':'appointment:v1:booking-grant','token':token})
        value=store.verify_booking_code(identifier,body.operation_id,body.challenge_id,str(body.email),body.generation,digest,grant,encrypted)
        if isinstance(value,dict) and value.get('state')=='verified':
            # A matching retry returns the originally committed opaque grant.
            saved_token=keys.cipher.open('booking-grant:'+str(body.operation_id),value['grant_ciphertext'],purpose='appointment:v1:booking-grant')['token']
            return {'code':'ok','state':'verified','verification_grant':saved_token,'expires_at':value['expires_at']}
        return outcome(value)
