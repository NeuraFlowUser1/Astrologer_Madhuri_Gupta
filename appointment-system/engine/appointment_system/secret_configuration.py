"""Protected, explicit key formats; no legacy environment-name discovery.

Historical bytes are supplied as base64 even when their original meaning was
text. Decoding that transport preserves the original bytes; it does not decode
the old text as a new cryptographic key or choose an algorithm from a client ID.
"""
import base64
import binascii
from .configuration import installation
from .credentials import ReceiptKeys,ContextKeys
from .errors import invalid
from .keys import KeyRing,KEY_ID,independent
from .serialization import decode,object_fields,integer


def ring(environment,name,purpose):
    facts=installation()
    try:value=environment[name]
    except KeyError:raise invalid(name) from None
    return KeyRing.parse(value,installation_id=facts['installation_id'],
                         environment=facts['environment'],purpose=purpose)


def historical(environment):
    raw=environment.get('BOOKING_LEGACY_PROTECTION')
    if raw is None:return {'receipt':{},'context':{}},()
    value=decode(raw)
    object_fields(value,{'version','installation_id','environment','readers','materials'})
    integer(value['version'],1,1)
    facts=installation()
    if value['installation_id']!=facts['installation_id'] or value['environment']!=facts['environment']:
        raise invalid('legacy_audience')
    definitions=object_fields(value['readers'],{'receipt','context'},{'recovery'})
    materials=value['materials']
    if type(materials) is not dict or len(materials)>8:raise invalid('legacy_materials')
    accepted=[]
    for name,text in materials.items():
        try:
            if type(name) is not str or not KEY_ID.fullmatch(name) or type(text) is not str or len(text)>1400:
                raise ValueError()
            material=base64.b64decode(text,altchars=b'-_',validate=True)
            if not 32<=len(material)<=1024 or base64.urlsafe_b64encode(material).decode()!=text:
                raise ValueError()
        except (ValueError,binascii.Error):raise invalid('legacy_materials') from None
        accepted.append((name,material))
    return definitions,tuple(accepted)


def booking_settings(environment):
    from .application import Settings
    definitions,materials=historical(environment)
    receipt=ReceiptKeys(ring(environment,'BOOKING_RECEIPT_KEYS','receipt'),definitions['receipt'],materials,definitions.get('recovery',{}))
    context=ContextKeys(ring(environment,'BOOKING_CONTEXT_KEYS','context'),definitions['context'],materials)
    risk=ring(environment,'BOOKING_RISK_KEYS','risk')
    independent((receipt.ring,context.ring,risk))
    return Settings(installation()['origin'],receipt,context,risk)
