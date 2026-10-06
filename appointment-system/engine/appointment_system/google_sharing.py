"""Compare Google file access with the named, immutable volume approvals.

No permissions are created or removed here. Unexpected sharing stops delivery
for private review instead of sending more personal information to that file.
"""
import re


def identity(value):
    if (type(value) is not str or len(value) > 254
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value)):
        raise ValueError('google_sharing_identity_invalid')
    return value.lower()


def approvals(values, owner):
    owner = identity(owner)
    if type(values) is not list or len(values) > 16:
        raise ValueError('google_sharing_approval_invalid')
    result = {}
    for value in values:
        if (type(value) is not dict or set(value) != {'type', 'role', 'emailAddress'}
                or value['type'] not in ('user', 'group')
                or value['role'] not in ('reader', 'commenter', 'writer')):
            raise ValueError('google_sharing_approval_invalid')
        email = identity(value['emailAddress'])
        if email == owner or email in result:
            raise ValueError('google_sharing_approval_invalid')
        result[email] = (value['type'], value['role'])
    return result


def check_permissions(values, owner, approved):
    owner = identity(owner)
    allowed = approvals(approved, owner) | {owner: ('user', 'owner')}
    if type(values) is not list or not 1 <= len(values) <= 17:
        raise ValueError('google_workbook_sharing_mismatch')
    seen = set()
    for value in values:
        if (type(value) is not dict or value.get('type') not in ('user', 'group')
                or value.get('pendingOwner', False) is not False
                or value.get('deleted', False) is not False):
            raise ValueError('google_workbook_sharing_mismatch')
        email = identity(value.get('emailAddress'))
        if email in seen or allowed.get(email) != (value['type'], value.get('role')):
            raise ValueError('google_workbook_sharing_mismatch')
        seen.add(email)
    # An approval allows named access; a recipient removing its access is safe.
    if owner not in seen:
        raise ValueError('google_workbook_sharing_mismatch')
