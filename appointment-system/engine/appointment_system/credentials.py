"""Versioned anonymous credentials and explicit historical readers.

The saved record selects a historical format. Token length never selects an
old authority. Old algorithms keep their exact byte audience during conversion.
"""
from dataclasses import dataclass,field
import hashlib
import hmac
import re
import secrets
from uuid import UUID,uuid4
from types import MappingProxyType
from .keys import KeyRing,KEY_ID
from .serialization import canonical,object_fields,record_id
from .errors import Rejected,invalid

SECRET=re.compile(r"[A-Za-z0-9_-]{43}\Z")
HEX_SECRET=re.compile(r"[a-f0-9]{64}\Z")


def readers(value):
    if type(value) not in (dict,MappingProxyType) or len(value)>8:raise invalid("legacy_readers")
    accepted={}
    for name,definition in value.items():
        if type(definition) is MappingProxyType:definition=dict(definition)
        if name=="v1" or type(name) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}",name):
            raise invalid("legacy_readers")
        object_fields(definition,{"algorithm","audience","purpose","key_id","encoding"})
        if (definition["algorithm"] not in ("json-sha256","hmac-sha256","contact-json-hmac-sha256")
            or definition["purpose"] not in ("booking","inquiry","context")
            or definition["encoding"] not in ("hex64","url43","uuid-hex64","uuid-url43")
            or type(definition["audience"]) is not str or len(definition["audience"])>200
            or any(ord(c)<32 or ord(c)>126 for c in definition["audience"])):
            raise invalid("legacy_readers")
        if definition["algorithm"] in ("hmac-sha256","contact-json-hmac-sha256") and (type(definition["key_id"]) is not str or not KEY_ID.fullmatch(definition["key_id"])):
            raise invalid("legacy_readers")
        if definition["algorithm"]=="json-sha256" and definition["key_id"] is not None:
            raise invalid("legacy_readers")
        accepted[name]=MappingProxyType(dict(definition))
    return MappingProxyType(accepted)


def historical_keys(value):
    if type(value) is not tuple or len(value)>8:raise invalid("legacy_keys")
    accepted={}
    for name,material in value:
        if (type(name) is not str or not KEY_ID.fullmatch(name) or name in accepted
            or type(material) is not bytes or not 32<=len(material)<=1024):
            raise invalid("legacy_keys")
        accepted[name]=material
    return accepted


def recovery_readers(value, materials):
    if type(value) not in (dict,MappingProxyType) or len(value)>8:raise invalid('legacy_recovery_readers')
    result={}
    for name,reader in value.items():
        if type(reader) is MappingProxyType:reader=dict(reader)
        if type(name) is not str or name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name):
            raise invalid('legacy_recovery_readers')
        object_fields(reader,{'key_id','code_audience','digest_audience'})
        if type(reader['key_id']) is not str or not KEY_ID.fullmatch(reader['key_id']) or reader['key_id'] not in materials:raise invalid('legacy_recovery_keys')
        for field_name in ('code_audience','digest_audience'):
            audience=reader[field_name]
            if type(audience) is not str or not 1<=len(audience)<=128 or not re.fullmatch(r'[a-zA-Z0-9:-]+',audience) or not audience.endswith(':'):
                raise invalid('legacy_recovery_readers')
        if reader['code_audience']==reader['digest_audience']:raise invalid('legacy_recovery_readers')
        result[name]=MappingProxyType(dict(reader))
    return MappingProxyType(result)


@dataclass(frozen=True,repr=False)
class ReceiptKeys:
    ring:KeyRing=field(repr=False)
    legacy:dict=field(default_factory=dict,repr=False)
    legacy_keys:tuple=field(default_factory=tuple,repr=False)
    recovery_readers:dict=field(default_factory=dict,repr=False)

    def __post_init__(self):
        if not isinstance(self.ring,KeyRing) or self.ring.purpose not in ("receipt","enquiry-digest"):raise invalid("receipt_keys")
        object.__setattr__(self,"legacy",readers(self.legacy))
        materials=historical_keys(self.legacy_keys)
        if self.ring.purpose!='receipt' and self.recovery_readers:raise invalid('legacy_recovery_readers')
        object.__setattr__(self,'recovery_readers',recovery_readers(self.recovery_readers,materials))
        for value in self.legacy.values():
            if value["purpose"] not in ("booking","inquiry") or value["encoding"] not in ("hex64","url43"):raise invalid("legacy_readers")
            if value["key_id"] is not None and value["key_id"] not in materials:raise invalid("legacy_keys")

    def issue(self):
        return self.prefix+"."+self.ring.active+"."+secrets.token_urlsafe(32)

    @property
    def prefix(self):return 'r1' if self.ring.purpose=='receipt' else 'q1'

    def metadata(self,credential):
        if type(credential) is not str:raise invalid("receipt")
        parts=credential.split(".")
        if len(parts)!=3 or parts[0]!=self.prefix or not KEY_ID.fullmatch(parts[1]) or not SECRET.fullmatch(parts[2]):
            raise invalid("receipt")
        self.ring.key(parts[1])
        return {"format":"v1","key_id":parts[1],"secret":parts[2]}

    def digest(self,request,credential,*,format="v1",key_id=None):
        identifier=str(UUID(str(request)));record_id(identifier)
        if format=="v1":
            parsed=self.metadata(credential)
            if key_id is not None and parsed["key_id"]!=key_id:raise invalid("receipt")
            return self.ring.digest("receipt:"+identifier,parsed["secret"].encode(),key_id=parsed["key_id"])
        historical=self.legacy.get(format)
        if historical is None or key_id is not None and historical["key_id"]!=key_id:raise invalid("receipt")
        pattern=HEX_SECRET if historical["encoding"]=="hex64" else SECRET
        if type(credential) is not str or not pattern.fullmatch(credential):raise invalid("receipt")
        if historical["algorithm"]=="json-sha256":
            return hashlib.sha256(canonical([historical["purpose"],identifier,credential])).hexdigest()
        if historical['algorithm']=='contact-json-hmac-sha256':
            if self.ring.purpose!='enquiry-digest' or historical['purpose']!='inquiry':raise invalid('receipt')
            message=canonical([historical['audience'],'contact-v1','receipt',identifier,credential])
            return hmac.new(dict(self.legacy_keys)[historical['key_id']],message,hashlib.sha256).hexdigest()
        message=(historical["audience"]+identifier+":"+credential).encode()
        return hmac.new(dict(self.legacy_keys)[historical["key_id"]],message,hashlib.sha256).hexdigest()

    def matches(self,request,credential,expected,*,format="v1",key_id=None):
        try:
            actual=self.digest(request,credential,format=format,key_id=key_id)
            return type(expected) is str and re.fullmatch(r"[a-f0-9]{64}",expected) is not None and hmac.compare_digest(actual,expected)
        except (Rejected,ValueError,TypeError,AttributeError):return False


@dataclass(frozen=True,repr=False)
class ContextKeys:
    ring:KeyRing=field(repr=False)
    legacy:dict=field(default_factory=dict,repr=False)
    legacy_keys:tuple=field(default_factory=tuple,repr=False)

    def __post_init__(self):
        if not isinstance(self.ring,KeyRing) or self.ring.purpose!="context":raise invalid("context_keys")
        object.__setattr__(self,"legacy",readers(self.legacy))
        materials=historical_keys(self.legacy_keys)
        for value in self.legacy.values():
            if (value["purpose"]!="context" or value["algorithm"]!="hmac-sha256"
                or value["encoding"] not in ("uuid-hex64","uuid-url43")):raise invalid("legacy_readers")
            if value["key_id"] not in materials:raise invalid("legacy_keys")

    def issue(self):
        identifier=uuid4();secret=secrets.token_urlsafe(32)
        token="c1."+self.ring.active+"."+str(identifier)+"."+secret
        return identifier,token,self.digest(token,format="v1")

    def identifier(self,token):
        if type(token) is not str or len(token)>250:raise invalid("context")
        parts=token.split(".")
        identifier=parts[2] if len(parts)==4 and parts[0]=="c1" else parts[0] if len(parts)==2 else None
        try:value=UUID(identifier)
        except (ValueError,TypeError,AttributeError):raise invalid("context") from None
        if value.int==0:raise invalid("context")
        return value

    def metadata(self,token):
        identifier=self.identifier(token);parts=token.split(".")
        if (len(parts)!=4 or parts[0]!="c1" or parts[2]!=str(identifier)
            or not KEY_ID.fullmatch(parts[1]) or not SECRET.fullmatch(parts[3])):raise invalid("context")
        self.ring.key(parts[1])
        return {"format":"v1","key_id":parts[1],"identifier":identifier,"secret":parts[3]}

    def digest(self,token,*,format,key_id=None):
        if format=="v1":
            parsed=self.metadata(token)
            if key_id is not None and key_id!=parsed["key_id"]:raise invalid("context")
            return self.ring.digest("context:"+str(parsed["identifier"]),parsed["secret"].encode(),key_id=parsed["key_id"])
        historical=self.legacy.get(format)
        if historical is None or key_id is not None and key_id!=historical["key_id"]:raise invalid("context")
        identifier=self.identifier(token);parts=token.split(".")
        expected_id=str(identifier)
        pattern=HEX_SECRET if historical["encoding"]=="uuid-hex64" else SECRET
        if len(parts)!=2 or parts[0]!=expected_id or not pattern.fullmatch(parts[1]):raise invalid("context")
        return hmac.new(dict(self.legacy_keys)[historical["key_id"]],(historical["audience"]+token).encode(),hashlib.sha256).hexdigest()
