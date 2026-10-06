"""Explicit installation/account binding for mail credentials and retained readers."""
import re
from dataclasses import dataclass, field
from types import MappingProxyType

from .configuration import installation
from .mail_identity import MailIdentity
from .serialization import decode, object_fields

ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')


@dataclass(frozen=True)
class EmailConnection:
    account_id: str
    active_key_id: str
    keys: object = field(repr=False)
    identities: tuple

    def pinned(self, version):
        try: return self.keys[version]
        except (KeyError, TypeError): raise ValueError('Saved sending credential is unavailable.') from None

    def identity(self, format):
        found = [item for item in self.identities if item.format == format]
        if len(found) != 1: raise ValueError('Saved sending identity is unavailable.')
        return found[0]


def scoped(raw, fields, purpose):
    value = object_fields(decode(raw, maximum=65536), fields)
    facts = installation()
    if (type(value['version']) is not int or value['version'] != 1
            or value['installation_id'] != facts['installation_id']
            or value['environment'] != facts['environment'] or value['provider'] != 'resend'
            or value['purpose'] != purpose):
        raise ValueError('Sending settings belong to another installation or purpose.')
    return value


def connection(raw):
    value = scoped(raw, {'version','installation_id','environment','provider','purpose',
                         'account_id','active_key_id','keys','legacy_identities'}, 'email-send')
    if (not isinstance(value['account_id'], str) or not ID.fullmatch(value['account_id'])
            or not isinstance(value['keys'], list) or not 1 <= len(value['keys']) <= 8
            or not isinstance(value['legacy_identities'], list) or len(value['legacy_identities']) > 2):
        raise ValueError('Sending settings are invalid.')
    keys = {}; secrets = set()
    for record in value['keys']:
        object_fields(record, {'key_id','secret'})
        if (not isinstance(record['key_id'], str) or not ID.fullmatch(record['key_id'])
                or record['key_id'] in keys or not isinstance(record['secret'], str)
                or not re.fullmatch(r're_[A-Za-z0-9_-]{16,256}', record['secret'])
                or record['secret'] in secrets):
            raise ValueError('Sending credentials must have distinct exact identities.')
        keys[record['key_id']] = record['secret']; secrets.add(record['secret'])
    if value['active_key_id'] not in keys: raise ValueError('An active sending credential is required.')
    identities = [MailIdentity.current(value['account_id'])]
    for record in value['legacy_identities']:
        object_fields(record, {'format','project','sender','address','reply_to','event_account_id'})
        identity = MailIdentity(**record)
        if identity.format == 'resend-v1' or any(item.format == identity.format for item in identities):
            raise ValueError('Retained mail readers must be explicit and distinct.')
        identities.append(identity)
    return EmailConnection(value['account_id'], value['active_key_id'], MappingProxyType(keys), tuple(identities))


def webhook(raw, declared):
    from .email_events import EmailWebhook
    value = scoped(raw, {'version','installation_id','environment','provider','purpose','key_map'}, 'email-webhook')
    if declared is None or not isinstance(value['key_map'], dict) or set(value['key_map']) != {declared.account_id}:
        raise ValueError('Notification account must match the declared sending account.')
    record = object_fields(value['key_map'][declared.account_id], {'keys'})
    if not isinstance(record['keys'], list) or not 1 <= len(record['keys']) <= 2:
        raise ValueError('Notification settings are invalid.')
    keys = []; identifiers = set()
    for item in record['keys']:
        object_fields(item, {'key_id','secret'})
        if (not isinstance(item['key_id'], str) or not ID.fullmatch(item['key_id'])
                or item['key_id'] in identifiers or item['secret'] in keys):
            raise ValueError('Notification credentials must be distinct.')
        identifiers.add(item['key_id']); keys.append(item['secret'])
    return EmailWebhook(tuple(keys), identities=declared.identities)
