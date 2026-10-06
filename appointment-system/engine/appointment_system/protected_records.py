"""One authenticated record envelope, with named and purpose-bound old readers."""
from types import MappingProxyType
import re
from cryptography.fernet import Fernet,MultiFernet,InvalidToken
from .keys import KeyRing,material
from .errors import Rejected,invalid
from .serialization import canonical,decode,object_fields

class ProtectedRecords:
    def __init__(self,ring,readers=None):
        if not isinstance(ring,KeyRing):raise invalid('encryption_keys')
        self.ring=ring
        accepted={}
        if readers is not None:
            if type(readers) is not dict or len(readers)>8:raise invalid('legacy_cipher_readers')
            for name,value in readers.items():
                object_fields(value,{'algorithm','keys','purpose'})
                if (type(name) is not str or name=='v1' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name)
                    or value['algorithm']!='fernet-json' or type(value['purpose']) is not str
                    or not 1<=len(value['purpose'])<=200 or any(ord(c)<33 or ord(c)>126 for c in value['purpose'])
                    or type(value['keys']) is not list or not 1<=len(value['keys'])<=8):
                    raise invalid('legacy_cipher_readers')
                for key in value['keys']:material(key,32)
                if len(set(value['keys']))!=len(value['keys']):raise invalid('legacy_cipher_readers')
                accepted[name]=(MultiFernet([Fernet(key) for key in value['keys']]),value['purpose'])
        self.readers=MappingProxyType(accepted)

    def seal(self,record,value):
        if type(value) is not dict:raise invalid('protected_record')
        return 'e1.'+canonical(self.ring.seal(record,canonical(value))).decode()

    def read(self,record,encrypted,*,format='v1',purpose):
        try:
            if type(encrypted) is not str or not 1<=len(encrypted)<=90000:raise invalid('protected_record')
            if format=='v1':
                if not encrypted.startswith('e1.'):raise invalid('protected_record')
                raw=self.ring.open(record,decode(encrypted[3:],maximum=90000))
                value=decode(raw)
                expected=purpose
            else:
                selected=self.readers.get(format)
                if selected is None:raise invalid('protected_record')
                raw=selected[0].decrypt(encrypted.encode('ascii'))
                value=decode(raw)
                expected=selected[1]
            if type(value) is not dict or value.get('purpose')!=expected:raise invalid('protected_record')
            return value,raw
        except (Rejected,ValueError,TypeError,UnicodeError,InvalidToken):
            raise Rejected('encrypted_record_unavailable','This protected record cannot be opened.',503) from None

    def open(self,record,encrypted,*,format='v1',purpose):
        return self.read(record,encrypted,format=format,purpose=purpose)[0]
