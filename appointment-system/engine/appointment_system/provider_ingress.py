"""Authenticated original notifications, saved durably with minimal authority."""
import hashlib
from .keys import KeyRing
from .errors import Rejected,invalid
from .serialization import canonical
from .storage import Store
from psycopg.types.json import Jsonb

MAXIMUM=131072

def reference(provider,account,mode,event):
    return 'provider-journal:'+hashlib.sha256(canonical([provider,account,mode,event])).hexdigest()

class JournalCipher:
    def __init__(self,ring):
        if not isinstance(ring,KeyRing) or ring.purpose!='provider-journal':raise invalid('journal_keys')
        self.ring=ring

    def seal(self,provider,account,mode,event,body):
        if type(body) is not bytes or not 1<=len(body)<=MAXIMUM:raise invalid('journal_body')
        record=reference(provider,account,mode,event)
        return {'version':1,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
            'chunks':[self.ring.seal(record+':'+str(index),body[offset:offset+65536])
                for index,offset in enumerate(range(0,len(body),65536))]}

    def open(self,provider,account,mode,event,envelope,body_hash):
        try:
            if (type(envelope) is not dict or set(envelope)!={'version','bytes','sha256','chunks'}
                or type(envelope['version']) is not int or envelope['version']!=1
                or type(envelope['bytes']) is not int or not 1<=envelope['bytes']<=MAXIMUM
                or envelope['sha256']!=body_hash or type(envelope['chunks']) is not list
                or len(envelope['chunks'])!=(envelope['bytes']+65535)//65536):raise ValueError()
            record=reference(provider,account,mode,event)
            pieces=[self.ring.open(record+':'+str(index),chunk) for index,chunk in enumerate(envelope['chunks'])]
            if any(len(piece)!=65536 for piece in pieces[:-1]):raise ValueError()
            body=b''.join(pieces)
            if len(body)!=envelope['bytes'] or hashlib.sha256(body).hexdigest()!=body_hash:raise ValueError()
            return body
        except (Rejected,ValueError,TypeError,KeyError,UnicodeError):
            raise Rejected('journal_unavailable','This saved provider notification cannot be opened.',503) from None

class JournalStore(Store):
    buffers_original_events=True
    def __init__(self,dsn,*,expected_host,cipher):
        super().__init__(dsn,expected_host=expected_host,purpose='journal')
        if not isinstance(cipher,JournalCipher):raise invalid('journal_keys')
        self.cipher=cipher

    def save_verified_provider_event(self,provider,account,mode,event,body_hash,payload,body):
        if hashlib.sha256(body).hexdigest()!=body_hash:raise invalid('journal_body')
        envelope=self.cipher.seal(provider,account,mode,event,body)
        return self._call('SELECT appointment_system.journal_provider_event(%s,%s,%s,%s,%s,%s,%s)',
            (provider,account,mode,event,body_hash,Jsonb(payload),Jsonb(envelope)))

    def readiness(self,nonce,release_digest):
        return self._call('SELECT appointment_system.journal_readiness(%s,%s)',(nonce,release_digest))

def persist_verified(store,provider,account,mode,event,body_hash,payload,body):
    if getattr(store,'buffers_original_events',False) is True:
        return store.save_verified_provider_event(provider,account,mode,event,body_hash,payload,body)
    return store.save_provider_event(provider,account,mode,event,body_hash,payload)
