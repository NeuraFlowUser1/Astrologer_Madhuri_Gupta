"""Installation-, environment-, purpose- and record-bound rotating key contracts."""
import base64
import binascii
from dataclasses import dataclass,field
import hashlib
import hmac
import re
import secrets
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .errors import Rejected,invalid
from .serialization import canonical,decode,integer,object_fields,record_id,text

KEY_ID=re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")
PURPOSE=re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


def encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii")


def material(value,size,field_name="keys"):
    try:
        if type(value) is not str or len(value)>100000:
            raise ValueError()
        decoded=base64.b64decode(value,altchars=b"-_",validate=True)
        if len(decoded)!=size or encode(decoded)!=value:
            raise ValueError()
        return decoded
    except (ValueError,binascii.Error):
        raise invalid(field_name) from None


@dataclass(frozen=True,repr=False)
class KeyRing:
    installation_id:str
    environment:str
    purpose:str
    active:str
    keys:tuple[tuple[str,bytes],...]=field(repr=False)

    def __post_init__(self):
        record_id(self.installation_id)
        if (self.environment not in ("development","test","production")
                or type(self.purpose) is not str or not PURPOSE.fullmatch(self.purpose)
                or type(self.active) is not str or not KEY_ID.fullmatch(self.active)
                or type(self.keys) is not tuple or not 1<=len(self.keys)<=8):
            raise invalid("keys")
        seen=set();materials=set()
        for entry in self.keys:
            if type(entry) is not tuple or len(entry)!=2:
                raise invalid("keys")
            identifier,value=entry
            if (type(identifier) is not str or not KEY_ID.fullmatch(identifier) or identifier in seen
                    or type(value) is not bytes or len(value)!=32 or value in materials):
                raise invalid("keys")
            seen.add(identifier);materials.add(value)
        if self.active not in seen:raise invalid("keys")

    @classmethod
    def parse(cls,raw,*,installation_id,environment,purpose):
        value=decode(raw) if isinstance(raw,(bytes,str)) else decode(canonical(raw))
        object_fields(value,{"version","installation_id","environment","purpose","active","keys"})
        integer(value["version"],1,1)
        record_id(value["installation_id"])
        if (value["installation_id"]!=installation_id or value["environment"]!=environment
                or value["purpose"]!=purpose or type(purpose) is not str or not PURPOSE.fullmatch(purpose)
                or environment not in ("development","test","production")):
            raise invalid("key_audience")
        if type(value["keys"]) is not dict or not 1<=len(value["keys"])<=8:
            raise invalid("keys")
        decoded=[]
        for key_id,encoded in value["keys"].items():
            if not KEY_ID.fullmatch(key_id):
                raise invalid("key_id")
            decoded.append((key_id,material(encoded,32)))
        if (type(value["active"]) is not str or value["active"] not in value["keys"]
                or len({key for _,key in decoded})!=len(decoded)):
            raise invalid("keys")
        return cls(installation_id,environment,purpose,value["active"],tuple(decoded))

    def key(self,key_id=None):
        requested=self.active if key_id is None else key_id
        for identifier,value in self.keys:
            if requested==identifier:
                return value
        raise invalid("key_id")

    def binding(self,record,key_id=None):
        text(record,1,256,field="record")
        identifier=self.active if key_id is None else key_id
        self.key(identifier)
        return canonical({"version":1,"installation_id":self.installation_id,"environment":self.environment,
                          "purpose":self.purpose,"record":record,"key_id":identifier})

    def digest(self,record,value,*,key_id=None):
        if type(value) is not bytes or len(value)>131072:
            raise invalid("digest_input")
        return hmac.new(self.key(key_id),self.binding(record,key_id)+b"\0"+value,hashlib.sha256).hexdigest()

    def matches(self,record,value,expected,*,key_id=None):
        if type(expected) is not str or not re.fullmatch(r"[a-f0-9]{64}",expected):
            return False
        try:
            return hmac.compare_digest(self.digest(record,value,key_id=key_id),expected)
        except Rejected:
            return False

    def seal(self,record,plaintext):
        if type(plaintext) is not bytes or len(plaintext)>65536:
            raise invalid("plaintext")
        nonce=secrets.token_bytes(12)
        encrypted=AESGCM(self.key()).encrypt(nonce,plaintext,self.binding(record))
        return {"version":1,"installation_id":self.installation_id,"environment":self.environment,
                "purpose":self.purpose,"record":record,"key_id":self.active,
                "nonce":encode(nonce),"ciphertext":encode(encrypted)}

    def open(self,record,envelope):
        try:
            value=decode(envelope) if isinstance(envelope,(bytes,str)) else decode(canonical(envelope))
            object_fields(value,{"version","installation_id","environment","purpose","record","key_id","nonce","ciphertext"})
            if (type(value["version"]) is not int or value["version"]!=1
                    or value["installation_id"]!=self.installation_id or value["environment"]!=self.environment
                    or value["purpose"]!=self.purpose or value["record"]!=record):
                raise invalid("envelope")
            nonce=material(value["nonce"],12,"envelope")
            encoded=value["ciphertext"]
            if type(encoded) is not str or not 24<=len(encoded)<=87408:
                raise invalid("envelope")
            encrypted=base64.b64decode(encoded,altchars=b"-_",validate=True)
            if not 16<=len(encrypted)<=65552 or encode(encrypted)!=encoded:
                raise invalid("envelope")
            return AESGCM(self.key(value["key_id"])).decrypt(
                nonce,encrypted,self.binding(record,value["key_id"]))
        except (Rejected,InvalidTag,ValueError,binascii.Error):
            raise Rejected("encrypted_record_unavailable","This protected record cannot be opened.",503) from None


def independent(rings):
    if not rings or any(not isinstance(ring,KeyRing) for ring in rings):
        raise invalid("keys")
    identities={(ring.installation_id,ring.environment) for ring in rings}
    purposes={ring.purpose for ring in rings}
    if (len(identities)!=1 or len(purposes)!=len(rings)
            or len({key for ring in rings for _,key in ring.keys})!=sum(len(ring.keys) for ring in rings)):
        raise invalid("key_separation")
