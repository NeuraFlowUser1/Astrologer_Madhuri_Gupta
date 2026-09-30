"""Verified, minimized Resend observations; this receiver never sends email.

Reports may precede send completion or arrive out of order. Persist evidence
before acknowledging it; a separate consumer must match the saved mail job and
provider ID before projecting delivery status. Acceptance is not inbox delivery.
"""

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

SENDER_ADDRESS = 'bookings@mail.sarsajyotishsansthan.com'
SENDER = 'Sarsa Jyotish Sansthan <'+SENDER_ADDRESS+'>'
PROJECT_TAG = 'sarsa004'
EVENTS = frozenset(('email.sent','email.delivered','email.delivery_delayed',
                    'email.bounced','email.complained','email.failed','email.suppressed'))


@dataclass(frozen=True)
class EmailWebhook:
    secrets: tuple[str,...] = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.secrets,tuple) or not 1 <= len(self.secrets) <= 2:
                raise ValueError()
            for secret in self.secrets:
                if not isinstance(secret,str) or not secret.startswith('whsec_') or len(secret)>400:
                    raise ValueError()
                if not 24 <= len(base64.b64decode(secret[6:],validate=True)) <= 128:
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
            if event.get('type') not in EVENTS:
                return {'received':True}
            data=event['data']
            if not isinstance(data,dict):
                raise ValueError()
            # A team may also send unrelated mail. Do not retain its contacts or
            # treat it as Sarsa booking evidence merely because it was signed.
            if data.get('from') not in (SENDER,SENDER_ADDRESS):
                return {'received':True}
            tags=data.get('tags',{})
            if not isinstance(tags,dict) or tags.get('project')!=PROJECT_TAG:
                return {'received':True}
            provider_id=str(UUID(data['email_id']))
            job_id=str(UUID(tags['job_id']))
            occurred=datetime.fromisoformat(event['created_at'].replace('Z','+00:00'))
            if occurred.tzinfo is None or occurred.utcoffset() is None:
                raise ValueError()
            minimal={'event':event['type'],'email_id':provider_id,'job_id':job_id,'occurred_at':occurred.isoformat()}
        except (ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError):
            raise InvalidWebhook() from None
        digest=hashlib.sha256(body).hexdigest()
        saved=store.save_provider_event('resend',SENDER_ADDRESS,'live',event_id,digest,minimal)
        if saved != digest:
            raise EventConflict()
        if on_saved is not None:
            on_saved()
        return {'received':True}
