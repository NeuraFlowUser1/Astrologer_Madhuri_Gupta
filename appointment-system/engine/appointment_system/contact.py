"""Purpose-bound enquiry inputs and secrets. No booking OTP or legacy cache."""
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass,field
from datetime import datetime,timezone
from uuid import UUID
from cryptography.fernet import Fernet,MultiFernet,InvalidToken
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator,model_validator
from .models import BookingInput
from .security import request_fingerprint
from .access import AccessDenied
from .receipt_view import timestamp
from typing import Literal


class EnquiryInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_id:UUID
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr=Field(max_length=254)
    phone:str=Field(default='',max_length=32)
    subject:str=Field(min_length=2,max_length=150)
    message:str=Field(min_length=2,max_length=4000)
    source:Literal['home','contact','prashna','service','booking','unknown']='unknown'
    service_interest:str|None=Field(default=None,max_length=50)
    kind:Literal['contact','prashna']='contact'
    dob:str=Field(default='',max_length=30)
    location:str=Field(default='',max_length=200)

    @field_validator('service_interest')
    @classmethod
    def own_service(cls,value):
        # Interest is enquiry context, not permission to reserve a service.
        # A retired or hidden booking catalogue must not stop general enquiries.
        if value is not None and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}',value):
            raise ValueError('Choose a valid service reference.')
        return value

    @field_validator('name','subject','message','dob','location')
    @classmethod
    def controls(cls,value):
        if any((ord(c)<32 and c not in '\n\t') or ord(c)==127 for c in value):
            raise ValueError('Unsupported characters.')
        return value

    @field_validator('phone')
    @classmethod
    def optional_phone(cls,value):
        return BookingInput.international_mobile(value) if value else ''

    @model_validator(mode='after')
    def prashna_details(self):
        if self.kind=='prashna' and (not self.phone or len(self.location)<2):
            raise ValueError('A mobile number and location are required for this question.')
        return self


class EnquiryReference(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID


class EnquiryVerify(EnquiryReference):
    generation:int=Field(ge=1,le=3,strict=True)
    code:str=Field(pattern=r'^[0-9]{6}$')


class EnquiryResend(EnquiryReference):
    operation_id:UUID


@dataclass(frozen=True)
class ContactSecrets:
    digest_key:object=field(repr=False)
    cipher:object=field(repr=False)
    receipt_keys:object=field(default=None,repr=False)
    legacy_digests:tuple=field(default=(),repr=False)

    @classmethod
    def from_environment(cls,environment):
        from .secret_configuration import ring
        from .keys import independent
        from .credentials import ReceiptKeys
        from .protected_records import ProtectedRecords
        from .serialization import decode,object_fields,integer
        from .configuration import installation
        try:
            digest=ring(environment,'BOOKING_ENQUIRY_DIGEST_KEYS','enquiry-digest')
            encryption=ring(environment,'BOOKING_ENQUIRY_ENCRYPTION_KEYS','enquiry-encryption')
            independent((digest,encryption));facts=installation()
            value={'receipt_readers':{},'materials':{},'cipher_readers':{},'digest_readers':{}}
            if environment.get('BOOKING_LEGACY_ENQUIRY_PROTECTION') is not None:
                value=decode(environment['BOOKING_LEGACY_ENQUIRY_PROTECTION'])
                object_fields(value,{'version','installation_id','environment','receipt_readers','materials','cipher_readers','digest_readers'})
                integer(value['version'],1,1)
                if value['installation_id']!=facts['installation_id'] or value['environment']!=facts['environment']:raise ValueError()
            if type(value['materials']) is not dict or len(value['materials'])>8:raise ValueError()
            materials=[]
            for name,encoded in value['materials'].items():
                key=base64.b64decode(encoded,altchars=b'-_',validate=True)
                if not 32<=len(key)<=1024 or base64.urlsafe_b64encode(key).decode()!=encoded:raise ValueError()
                materials.append((name,key))
            if type(value['digest_readers']) is not dict or len(value['digest_readers'])>8:raise ValueError()
            readers=[]
            for name,definition in value['digest_readers'].items():
                object_fields(definition,{'key_id','audience'})
                if (type(name) is not str or name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name)
                    or definition['key_id'] not in dict(materials) or type(definition['audience']) is not str
                    or not 1<=len(definition['audience'])<=200):raise ValueError()
                readers.append((name,dict(materials)[definition['key_id']],definition['audience']))
            return cls(digest,ProtectedRecords(encryption,value['cipher_readers']),
                ReceiptKeys(digest,value['receipt_readers'],tuple(materials)),tuple(readers))
        except (KeyError,ValueError,TypeError,binascii.Error,RecursionError):
            raise ValueError('Contact protection is not configured.') from None

    def __post_init__(self):
        from .keys import KeyRing,independent
        from .credentials import ReceiptKeys
        from .protected_records import ProtectedRecords
        if (not isinstance(self.digest_key,KeyRing) or self.digest_key.purpose!='enquiry-digest'
            or not isinstance(self.cipher,ProtectedRecords) or self.cipher.ring.purpose!='enquiry-encryption'):
            raise ValueError('Contact protection is not configured.')
        independent((self.digest_key,self.cipher.ring))
        if self.receipt_keys is None:object.__setattr__(self,'receipt_keys',ReceiptKeys(self.digest_key))
        if not isinstance(self.receipt_keys,ReceiptKeys) or self.receipt_keys.ring!=self.digest_key:raise ValueError('Contact protection is not configured.')
        if (type(self.legacy_digests) is not tuple or len(self.legacy_digests)>8
            or any(type(v) is not tuple or len(v)!=3 for v in self.legacy_digests)):
            raise ValueError('Contact protection is not configured.')
        for name,key,audience in self.legacy_digests:
            if (type(name) is not str or name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name)
                or type(key) is not bytes or not 32<=len(key)<=1024 or type(audience) is not str
                or not 1<=len(audience)<=200 or any(ord(c)<33 or ord(c)>126 for c in audience)):
                raise ValueError('Contact protection is not configured.')
        if len({v[0] for v in self.legacy_digests})!=len(self.legacy_digests):
            raise ValueError('Contact protection is not configured.')

    def digest(self,purpose,*values,key_id=None,format='v1'):
        from .serialization import canonical
        if purpose not in ('code','email-quota','message'):raise ValueError('Invalid contact purpose.')
        if format=='v1':
            return self.digest_key.digest('enquiry:'+purpose,canonical([str(v) for v in values]),key_id=key_id)
        selected=next((value for value in self.legacy_digests if value[0]==format),None)
        if selected is None:raise ValueError('Unknown contact format.')
        return hmac.new(selected[1],canonical([selected[2],'contact-v1',purpose,*[str(v) for v in values]]),hashlib.sha256).hexdigest()

    def receipt(self,request_id,credential,*,format='v1',key_id=None):
        try:return self.receipt_keys.digest(request_id,credential,format=format,key_id=key_id)
        except (ValueError,TypeError):raise AccessDenied() from None

    def record(self,kind,*values):
        from .serialization import canonical
        return 'enquiry-'+kind+':'+hashlib.sha256(canonical([str(v) for v in values])).hexdigest()

    def challenge(self,request_id,email,generation):
        if type(generation) is not int or not 1<=generation<=3:raise ValueError('Invalid generation.')
        reference=str(UUID(str(request_id)));code=f'{secrets.randbelow(1000000):06d}'
        record={'purpose':'appointment:v1:enquiry-code','request_id':reference,'email':email,
                'generation':generation,'code':code,'digest_key_id':self.digest_key.active}
        encrypted=self.cipher.seal(self.record('code',reference,email,generation),record)
        return self.digest('code',reference,generation,email,code),encrypted

    def open_code(self,encrypted,request_id,email,generation,expires_at,*,now=None,format='v1'):
        try:
            instant=now or datetime.now(timezone.utc)
            if (not isinstance(instant,datetime) or instant.tzinfo is None
                or not isinstance(expires_at,datetime) or expires_at.tzinfo is None or expires_at<=instant):raise ValueError()
            data=self.cipher.open(self.record('code',request_id,email,generation),encrypted,
                format=format,purpose='appointment:v1:enquiry-code')
            expected={'purpose','request_id','email','generation','code'}|({'digest_key_id'} if format=='v1' else set())
            if (set(data)!=expected or data['request_id']!=str(request_id) or data['email']!=email
                or type(data['generation']) is not int or data['generation']!=generation
                or not isinstance(data['code'],str) or not re.fullmatch(r'[0-9]{6}',data['code'])):raise ValueError()
            if format=='v1':self.digest_key.key(data['digest_key_id'])
            return data['code']
        except (ValueError,TypeError,UnicodeError,KeyError):
            raise ValueError('Contact message could not be read safely.') from None


def enquiry_payload(body):
    value=body.model_dump(mode='json',exclude={'request_id'})
    # A retry from a pre-upgrade visitor must retain its original fingerprint.
    if not ({'source','service_interest'} & body.model_fields_set):
        value.pop('source');value.pop('service_interest')
    return value,request_fingerprint(value)


def public_enquiry(result):
    """Do not project DB payloads, destinations, verification material or jobs."""
    if not isinstance(result,dict):raise ValueError('Invalid enquiry result.')
    allowed={'code','request_id','state','generation','server_now','code_expires_at','resend_after','sends_remaining','verification_delivery'}
    if result.get('code')=='ok':
        try:
            if not allowed.issubset(result):raise ValueError()
            UUID(str(result['request_id']))
            if (result['state'] not in ('awaiting_verification','expired','locked','received')
                or type(result['generation']) is not int or not 1<=result['generation']<=3
                or type(result['sends_remaining']) is not int
                or result['sends_remaining']!=3-result['generation']
                or result['verification_delivery'] not in ('queued','accepted','delivered','delayed','failed','unavailable')):raise ValueError()
            for key in ('server_now','code_expires_at','resend_after'):
                if timestamp(result[key]) is None:raise ValueError()
        except (ValueError,TypeError,KeyError):
            raise ValueError('Invalid enquiry result.') from None
    return {key:value for key,value in result.items() if key in allowed}
