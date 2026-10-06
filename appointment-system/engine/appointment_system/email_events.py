"""Verified, minimized Resend observations; this receiver never sends email.

Reports may precede send completion or arrive out of order. Persist evidence
before acknowledging it; a separate consumer must match the saved mail job and
provider ID before projecting delivery status. Acceptance is not inbox delivery.
"""

from .configuration import owners,sender,project_id,label,worker_origin,origin
import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from svix.webhooks import Webhook

from .webhook import InvalidWebhook, EventConflict, MAX_WEBHOOK_BYTES, _unique_object
from .mail_identity import MailIdentity

SENDER_ADDRESS = sender()['email']
SENDER = sender()['name']+' <'+SENDER_ADDRESS+'>'
PROJECT_TAG = project_id()
EVENTS = frozenset(('email.sent','email.delivered','email.delivery_delayed',
                    'email.bounced','email.complained','email.failed','email.suppressed'))


@dataclass(frozen=True)
class EmailWebhook:
    secrets: tuple[str,...] = field(repr=False)
    identities: tuple = field(default_factory=lambda:(MailIdentity.current(),))

    def __post_init__(self):
        try:
            if not isinstance(self.secrets,tuple) or not 1 <= len(self.secrets) <= 2:
                raise ValueError()
            for secret in self.secrets:
                if not isinstance(secret,str) or not secret.startswith('whsec_') or len(secret)>400:
                    raise ValueError()
                if not 24 <= len(base64.b64decode(secret[6:],validate=True)) <= 128:
                    raise ValueError()
            if (not isinstance(self.identities,tuple) or not 1<=len(self.identities)<=3
                    or any(not isinstance(item,MailIdentity) for item in self.identities)
                    or len({item.format for item in self.identities})!=len(self.identities)):
                raise ValueError()
        except (ValueError,binascii.Error):
            raise ValueError('Email report configuration is incomplete.') from None

    def receive(self, store, body, headers, *, on_saved=None):
        if not isinstance(body,bytes) or not 0 < len(body) <= MAX_WEBHOOK_BYTES:
            raise InvalidWebhook()
        signed_headers={}
        for name in ('svix-id','svix-timestamp','svix-signature'):
            values=headers.getlist(name)
            if len(values)!=1 or not 0<len(values[0])<=2048:
                raise InvalidWebhook()
            signed_headers[name]=values[0]
        event_id=signed_headers['svix-id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',event_id):
            raise InvalidWebhook()
        verified=False
        for secret in self.secrets:
            try:
                Webhook(secret).verify(body,signed_headers)
                verified=True
                break
            except Exception:
                # Provider verifier errors are not allowed into responses/logs.
                continue
        if not verified:
            raise InvalidWebhook()
        try:
            def invalid_constant(_):
                raise ValueError()
            event=json.loads(body,object_pairs_hook=_unique_object,parse_constant=invalid_constant)
            if not isinstance(event,dict):
                raise ValueError()
            journaling=getattr(store,'buffers_original_events',False) is True
            event_type=event.get('type')
            if type(event_type) is not str or not re.fullmatch(r'[a-z][a-z0-9_.]{0,119}',event_type):raise ValueError()
            if event_type not in EVENTS and not journaling:
                return {'received':True}
            data=event['data']
            if not isinstance(data,dict):
                raise ValueError()
            tags=data.get('tags',{})
            # The signature authenticates the account. Exact registered format,
            # sender and project authenticate the installation's message binding.
            identities=[identity for identity in self.identities
                if data.get('from') in (identity.sender,identity.address)
                and identity.binding(tags,event=True) is not None]
            untagged=False
            if not identities:
                # Older attempted messages cannot be given new tags. Keep
                # their signed report; the consumer requires the exact saved
                # provider ID, retained account and recipient digest.
                identities=[identity for identity in self.identities
                    if identity.format=='resend-legacy-untagged-job-v1'
                    and data.get('from') in (identity.sender,identity.address)
                    and tags in ({},[])]
                untagged=bool(identities)
            if not identities:
                owned=[identity for identity in self.identities if data.get('from') in (identity.sender,identity.address)
                       and identity.owns_event(tags)] if journaling else []
                if len(owned)>1:raise ValueError()
                if owned:
                    return self._save(store,owned[0],event_id,body,
                        {'event':event_type,'unmapped':True,'mail_format':owned[0].format},on_saved)
                return {'received':True}
            if len(identities)!=1:raise ValueError()
            identity=identities[0]
            provider_id=str(UUID(data['email_id']))
            job_id,version=(None,None) if untagged else identity.binding(tags,event=True)
            recipients=data.get('to')
            if not isinstance(recipients,list) or len(recipients)!=1 or not isinstance(recipients[0],str) or not 1<=len(recipients[0])<=254:
                raise ValueError()
            occurred=datetime.fromisoformat(event['created_at'].replace('Z','+00:00'))
            if occurred.tzinfo is None or occurred.utcoffset() is None:
                raise ValueError()
            minimal={'event':event['type'],'email_id':provider_id,'occurred_at':occurred.isoformat(),
                'binding_version':2,'mail_format':identity.format,
                'recipient_hash':hashlib.sha256(recipients[0].strip().lower().encode()).hexdigest()}
            if job_id is not None:minimal['job_id']=job_id
            if version is not None:minimal['message_version']=version
            if event_type not in EVENTS:minimal['unmapped']=True
        except (ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError):
            raise InvalidWebhook() from None
        return self._save(store,identity,event_id,body,minimal,on_saved)

    @staticmethod
    def _save(store,identity,event_id,body,minimal,on_saved):
        digest=hashlib.sha256(body).hexdigest()
        from .provider_ingress import persist_verified
        saved=persist_verified(store,'resend',identity.event_account_id,'live',event_id,digest,minimal,body)
        if saved != digest:
            raise EventConflict()
        if on_saved is not None:
            on_saved()
        return {'received':True}
