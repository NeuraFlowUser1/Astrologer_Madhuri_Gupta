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
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator
from .models import BookingInput
from .security import receipt_digest,request_fingerprint
from .access import AccessDenied
from .receipt_view import timestamp


class EnquiryInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_id:UUID
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr=Field(max_length=254)
    phone:str=Field(default='',max_length=32)
    subject:str=Field(min_length=2,max_length=150)
    message:str=Field(min_length=5,max_length=4000)

    @field_validator('name','subject','message')
    @classmethod
    def controls(cls,value):
        if any((ord(c)<32 and c not in '\n\t') or ord(c)==127 for c in value):
            raise ValueError('Unsupported characters.')
        return value

    @field_validator('phone')
    @classmethod
    def optional_phone(cls,value):
        return BookingInput.international_mobile(value) if value else ''


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
    digest_key:bytes=field(repr=False)
    cipher:object=field(repr=False)

    @classmethod
    def from_environment(cls,environment):
        try:
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise ValueError()
                    result[key]=value
                return result
            raw=json.loads(environment['SARSA_CONTACT_KEYS'],object_pairs_hook=unique)
            if not isinstance(raw,dict) or set(raw)!={'digest','encryption'}:raise ValueError()
            encoded=raw['digest']
            if not isinstance(encoded,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=',encoded):raise ValueError()
            key=base64.b64decode(encoded,altchars=b'-_',validate=True)
            if len(key)!=32 or base64.urlsafe_b64encode(key).decode()!=encoded:raise ValueError()
            enc=raw['encryption']
            if not isinstance(enc,list) or not 1<=len(enc)<=3 or any(not isinstance(k,str) for k in enc):raise ValueError()
            if encoded in enc or len(set(enc))!=len(enc):raise ValueError()
            for item in enc:
                if not re.fullmatch(r'[A-Za-z0-9_-]{43}=',item):raise ValueError()
                decoded=base64.b64decode(item,altchars=b'-_',validate=True)
                if len(decoded)!=32 or base64.urlsafe_b64encode(decoded).decode()!=item:raise ValueError()
            return cls(key,MultiFernet([Fernet(k.encode()) for k in enc]))
        except (KeyError,ValueError,TypeError,binascii.Error,RecursionError):
            raise ValueError('Contact protection is not configured.') from None

    def __post_init__(self):
        if not isinstance(self.digest_key,bytes) or len(self.digest_key)!=32:
            raise ValueError('Contact protection is not configured.')

    def digest(self,purpose,*values):
        raw=json.dumps(['sarsa004','contact-v1',purpose,*[str(v) for v in values]],ensure_ascii=False,separators=(',',':')).encode()
        return hmac.new(self.digest_key,raw,hashlib.sha256).hexdigest()

    def receipt(self,request_id,credential):
        # Validate UUID and high-entropy credential before domain-separated HMAC.
        try:receipt_digest(request_id,credential,self.digest_key)
        except (ValueError,TypeError):raise AccessDenied() from None
        return self.digest('receipt',str(UUID(str(request_id))),credential)

    def challenge(self,request_id,email,generation):
        if not isinstance(generation,int) or not 1<=generation<=3:raise ValueError('Invalid generation.')
        code=f'{secrets.randbelow(1000000):06d}'
        record={'purpose':'sarsa004-contact-code-v1','request_id':str(request_id),'email':email,
                'generation':generation,'code':code}
        encrypted=self.cipher.encrypt(json.dumps(record,separators=(',',':')).encode()).decode()
        return self.digest('code',request_id,generation,email,code),encrypted

    def open_code(self,encrypted,request_id,email,generation,expires_at,*,now=None):
        try:
            instant=now or datetime.now(timezone.utc)
            if not isinstance(expires_at,datetime) or expires_at.tzinfo is None or expires_at<=instant:raise ValueError()
            if not isinstance(encrypted,str) or len(encrypted)>8192:raise ValueError()
            data=json.loads(self.cipher.decrypt(encrypted.encode()))
            if (set(data)!={'purpose','request_id','email','generation','code'}
                or data['purpose']!='sarsa004-contact-code-v1' or data['request_id']!=str(request_id)
                or data['email']!=email or data['generation']!=generation
                or not isinstance(data['code'],str) or not re.fullmatch(r'[0-9]{6}',data['code'])):raise ValueError()
            return data['code']
        except (InvalidToken,ValueError,TypeError,UnicodeError,KeyError):
            raise ValueError('Contact message could not be read safely.') from None


def enquiry_payload(body):
    value=body.model_dump(mode='json',exclude={'request_id'})
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
