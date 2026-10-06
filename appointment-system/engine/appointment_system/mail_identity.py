"""Exact current and explicitly retained mail identities, without provider secrets.

Historical payloads and provider duplicate-prevention keys are read as saved.
They are never rewritten into the new format after a possible send attempt.
"""
import re
from dataclasses import dataclass
from uuid import UUID

from .configuration import installation, sender

FORMATS = frozenset(('resend-v1', 'resend-legacy-job-v1', 'resend-legacy-verification-v1',
                     'resend-legacy-flat-job-v1','resend-legacy-untagged-job-v1'))


def tags_for(job, version=1):
    if type(version) is not int or not 1 <= version <= 9999:
        raise ValueError('Message version is invalid.')
    facts = installation()
    return [
        {'name': 'project', 'value': facts['project_id']},
        {'name': 'installation', 'value': facts['installation_id']},
        {'name': 'environment', 'value': facts['environment']},
        {'name': 'job_id', 'value': str(UUID(str(job)))},
        {'name': 'message_version', 'value': str(version)},
    ]


@dataclass(frozen=True)
class MailIdentity:
    format: str
    project: str
    sender: str
    address: str
    reply_to: str
    event_account_id: str

    def __post_init__(self):
        if self.format not in FORMATS or not re.fullmatch(r'[A-Za-z0-9_-]{1,75}', self.project):
            raise ValueError('Mail identity is invalid.')
        for value in (self.sender, self.address, self.reply_to, self.event_account_id):
            if not isinstance(value, str) or not 1 <= len(value) <= 320 or any(ord(c) < 32 for c in value):
                raise ValueError('Mail identity is invalid.')
        if self.sender != self.address and not self.sender.endswith(' <'+self.address+'>'):
            raise ValueError('Mail identity is invalid.')
        from email_validator import validate_email
        validate_email(self.address, check_deliverability=False,test_environment=installation()['environment']!='production')
        validate_email(self.reply_to, check_deliverability=False,test_environment=installation()['environment']!='production')

    @classmethod
    def current(cls, account_id=None):
        declared = sender()
        return cls('resend-v1', installation()['project_id'],
                   declared['name']+' <'+declared['email']+'>', declared['email'],
                   declared['reply_to'], account_id or declared['email'])

    def binding(self, tags, *, event=False):
        """Return the UUID/version only for this exact registered payload format."""
        if self.format=='resend-legacy-untagged-job-v1':return None
        if event:
            if not isinstance(tags, dict): return None
            values = tags
        else:
            if not isinstance(tags, list): return None
            values = {}
            for item in tags:
                if not isinstance(item, dict) or set(item) != {'name', 'value'}: return None
                if item['name'] in values: return None
                values[item['name']] = item['value']
        identity_key = 'challenge_id' if self.format == 'resend-legacy-verification-v1' else 'job_id'
        required = {'project', identity_key}
        if self.format == 'resend-v1':
            required |= {'installation', 'environment', 'message_version'}
        optional = {'message_version'} if self.format != 'resend-v1' else set()
        if not required <= values.keys() or values.keys() - required - optional: return None
        if values['project'] != self.project: return None
        if self.format == 'resend-v1':
            facts = installation()
            if (values['installation'] != facts['installation_id']
                    or values['environment'] != facts['environment']): return None
        try:
            reference = UUID(values[identity_key])
            if not reference.int or str(reference) != values[identity_key]: return None
            version = values.get('message_version')
            if version is not None and (not isinstance(version, str) or not re.fullmatch(r'[1-9][0-9]{0,3}', version)):
                return None
            return str(reference), version
        except (ValueError, TypeError, KeyError, AttributeError): return None

    def owns_event(self,tags):
        """Narrow journal scope, even when an owned message format needs review.

        A shared Resend account signature alone does not establish the project.
        Exact sender is checked by the caller, and this checks its namespace.
        This grants no authority to update a job or decide delivered status.
        """
        if self.format=='resend-legacy-untagged-job-v1':return False
        if type(tags) is not dict or tags.get('project')!=self.project:return False
        if self.format=='resend-v1':
            facts=installation()
            return tags.get('installation')==facts['installation_id'] and tags.get('environment')==facts['environment']
        return True

    def accepts(self, payload, job):
        if self.format=='resend-legacy-untagged-job-v1':
            return isinstance(payload,dict) and payload.get('from')==self.sender and 'tags' not in payload
        return (isinstance(payload, dict) and payload.get('from') == self.sender
                and self.binding(payload.get('tags')) is not None
                and self.binding(payload.get('tags'))[0] == str(job))


def retained_key(value, job, identity, *, booking_id=None, kind=None, role=None):
    """Check a saved key; never derive a replacement for an imported attempt."""
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('Mail attempt identity is invalid.')
    reference = str(UUID(str(job)))
    # Each reader accepts only the historically supported namespace, exact UUID
    # and optional saved template version. It does not accept arbitrary keys.
    patterns = {
        'resend-v1': r'abs/'+re.escape(installation()['installation_id'])+'/'+re.escape(reference)+r'/v[1-9][0-9]{0,3}',
        'resend-legacy-job-v1': r'(?:appointment/|inquiry/)'+re.escape(reference)+r'(?:/v[1-9][0-9]{0,3})?',
        'resend-legacy-untagged-job-v1': r'inquiry/'+re.escape(reference)+r'/v[1-9][0-9]{0,3}',
        'resend-legacy-flat-job-v1': r'sarsa004/'+re.escape(reference),
        'resend-legacy-verification-v1': r'verification/'+re.escape(reference)+r'(?:/v[1-9][0-9]{0,3})?',
    }
    matches = bool(re.fullmatch(patterns[identity.format], value))
    if identity.format in ('resend-legacy-job-v1','resend-legacy-untagged-job-v1') and booking_id is not None:
        booking = str(UUID(str(booking_id)))
        if (isinstance(kind, str) and re.fullmatch(r'[a-z_]{1,60}', kind)
                and isinstance(role, str) and re.fullmatch(r'[a-z_]{1,30}', role)):
            matches |= bool(re.fullmatch('booking/'+re.escape(booking)+'/'+re.escape(kind)+'/'+re.escape(role)+r'/v[1-9][0-9]{0,3}', value))
    if not matches:
        raise ValueError('Mail attempt identity is invalid.')
    return value


def new_key(job, version=1):
    tags_for(job, version)
    return 'abs/'+installation()['installation_id']+'/'+str(UUID(str(job)))+'/v'+str(version)
