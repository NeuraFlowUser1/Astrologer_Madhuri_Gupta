"""Preserve owned legacy delivery observations without replaying notifications.

Retired verification receipts and unlinked reports remain typed, non-actionable
history. They never become current challenges, jobs or guessed deliveries.
"""
import re
from uuid import UUID

from appointment_system.email_events import EVENTS
from .records import private_reference, stamp
from .source import ConversionError
from .transport import TransportTransfer


class MailEventTransfer:
    def __init__(self, transport):
        if not isinstance(transport, TransportTransfer) or transport.mail is None:
            raise ConversionError('legacy_mail_event_binding_invalid')
        self.transport = transport

    def __call__(self, layout, table, rows, source=None):
        if layout.project != '003' or table not in ('email_events','verification_emails') or type(source) is not dict:
            raise ConversionError('legacy_mail_event_table_unprepared')
        if table == 'verification_emails': return self.verification(rows, source, layout.schema)
        jobs = source.get(layout.schema+'.delivery_jobs', [])
        verification = source.get(layout.schema+'.verification_emails', [])
        owners = source.get(layout.schema+'.mail_provider_ownership', [])
        converted, claims, result = {}, {}, {}
        try:
            by_provider = {}
            for job in jobs:
                if job.get('provider_id') is not None:
                    by_provider.setdefault(str(UUID(job['provider_id'])), []).append(job)
            verification_records = self.verification(verification, source, layout.schema)['historical_verification_receipts']
            verification_providers = {item['provider_id']:item for item in verification_records}
            registered = {}
            for owner in owners: registered.setdefault(str(UUID(owner['provider_id'])), []).append(owner)
            selected = {}
            retired = {}
            for row in rows:
                provider = str(UUID(row['provider_id']))
                matches = by_provider.get(provider, [])
                if provider in verification_providers and matches:
                    raise ConversionError('legacy_mail_event_owner_conflict')
                if not matches:
                    # The old receiver retained reports even after an old
                    # challenge/message disappeared. Missing parent identity
                    # is not permission to manufacture an actionable job.
                    receipt = verification_providers.get(provider)
                    if registered.get(provider) and receipt is None:
                        raise ConversionError('legacy_mail_event_owner_unresolved')
                    retired[row['event_id']] = dict(classification='verification' if receipt else 'unmatched',
                        challenge_id=receipt['challenge_id'] if receipt else None)
                    continue
                if len(matches) != 1:
                    raise ConversionError('legacy_mail_event_owner_unresolved')
                original = matches[0]
                if (original['recipient_role'] not in ('customer', 'client') or
                    original['first_attempt_at'] is None or
                    any(item['purpose'] != 'delivery' or item['intent_id'] != original['id']
                        for item in registered.get(provider, []))):
                    raise ConversionError('legacy_mail_event_owner_conflict')
                selected[original['id']] = original
            # Translate selected jobs together. Re-scanning every booking and
            # allowance for each event would make a large handover quadratic.
            translated = self.transport.jobs(layout, list(selected.values()), source)
            for kind, name in (('booking', 'delivery_jobs'), ('contact', 'enquiry_delivery_jobs')):
                for job in translated.get(name, []):
                    original = selected.get(job['id'])
                    if original is None or job['id'] in converted or job['provider_id'] != original['provider_id']:
                        raise ConversionError('legacy_mail_event_owner_conflict')
                    converted[job['id']] = (kind, job)
            if len(converted) != len(selected): raise ConversionError('legacy_mail_event_owner_conflict')
            for row in rows:
                provider = str(UUID(row['provider_id']))
                if (type(row['event_id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', row['event_id'])
                    or row['event_type'] not in EVENTS):
                    raise ConversionError('legacy_mail_event_invalid')
                stamp(row['occurred_at']); observed = stamp(row['received_at'])
                if row['event_id'] in retired:
                    result.setdefault('historical_email_observations', []).append(dict(
                        event_id=row['event_id'],provider_id=provider,event_type=row['event_type'],
                        occurred_at=row['occurred_at'],recorded_at=row['received_at'],
                        mail_account_id=self.transport.mail.connection.account_id,**retired[row['event_id']]))
                    continue
                kind, job = converted[by_provider[provider][0]['id']]
                name = 'enquiry_email_observations' if kind == 'contact' else 'email_observations'
                result.setdefault(name, []).append(dict(event_id=row['event_id'], job_id=job['id'],
                    provider_id=provider, event_type=row['event_type'], occurred_at=row['occurred_at'],
                    recorded_at=row['received_at']))
                # An authenticated delivery report proves provider acceptance,
                # not inbox delivery. Use the translated exact frozen-message
                # digest, so the common consumer can adopt it before any send.
                digest = job.get('message_hash') or job.get('message_digest')
                if digest is not None:
                    identity = (kind, job['id'], provider, digest)
                    previous = claims.get(identity)
                    if previous is None or observed < stamp(previous['observed_at']):
                        claims[identity] = dict(id=private_reference(self.transport.bindings.installation.installation_id,
                            'historical-mail-acceptance', ':'.join(identity)), kind=kind, job_id=job['id'],
                            provider_id=provider, message_hash=digest, result='accepted', observed_at=row['received_at'])
            if claims: result['mail_acceptance_claims'] = list(claims.values())
            return result
        except ConversionError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ConversionError('legacy_mail_event_invalid') from None

    def verification(self, rows, source, schema):
        result=[];providers=set();challenges=set()
        try:
            jobs={str(UUID(item['provider_id'])) for item in source.get(schema+'.delivery_jobs',[])
                if item.get('provider_id') is not None}
            for row in rows:
                if set(row)!={'challenge_id','provider_id','purpose','accepted_at'}:
                    raise ConversionError('legacy_verification_receipt_invalid')
                provider=str(UUID(row['provider_id']));challenge=str(UUID(row['challenge_id']))
                if provider in providers or challenge in challenges or provider in jobs:
                    raise ConversionError('legacy_mail_event_owner_conflict')
                if row['purpose'] not in ('booking','contact','prashna'):
                    raise ConversionError('legacy_verification_receipt_invalid')
                stamp(row['accepted_at']);providers.add(provider);challenges.add(challenge)
                result.append(dict(challenge_id=challenge,provider_id=provider,purpose=row['purpose'],
                    accepted_at=row['accepted_at'],mail_account_id=self.transport.mail.connection.account_id))
            return {'historical_verification_receipts':result}
        except ConversionError:
            raise
        except (KeyError,TypeError,ValueError,AttributeError):
            raise ConversionError('legacy_verification_receipt_invalid') from None
