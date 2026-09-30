"""Explicit Sarsa merchant configuration with retained credential versions.

Import and parsing perform no provider requests. The database's immutable order
identity remains authoritative; this configuration cannot rewrite an old order.
"""

import json

from .razorpay import Credentials, Razorpay, merchant_identity
from .recovery import Accounts
from .webhook import WebhookAccount


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Repeated payment configuration field.')
        result[name] = value
    return result


def payment_accounts(value):
    if not isinstance(value, str) or not 0 < len(value) <= 32768:
        raise ValueError('Payment configuration is missing.')
    config = json.loads(value, object_pairs_hook=unique_object)
    if (not isinstance(config, dict)
            or set(config) != {'merchant_id', 'mode', 'current_version', 'versions'}
            or merchant_identity(config['merchant_id']) is None or config['mode'] != 'live'
            or not isinstance(config['current_version'], str)
            or not isinstance(config['versions'], list) or not 1 <= len(config['versions']) <= 8):
        raise ValueError('Payment configuration is invalid.')
    adapters = []
    for version in config['versions']:
        if not isinstance(version, dict) or set(version) != {'version', 'key_id', 'key_secret'}:
            raise ValueError('Payment credential version is invalid.')
        adapters.append(Razorpay(Credentials(config['merchant_id'], config['mode'],
            version['version'], version['key_id'], version['key_secret'])))
    accounts = Accounts(adapters, current_versions={
        (merchant_identity(config['merchant_id']), config['mode']): config['current_version']})
    accounts.current(config['merchant_id'], config['mode'])
    return accounts


def payment_webhook(value, accounts):
    if not isinstance(value, str) or not 0 < len(value) <= 8192 or accounts is None:
        raise ValueError('Payment webhook configuration is missing.')
    config = json.loads(value, object_pairs_hook=unique_object)
    if (not isinstance(config, dict) or set(config) != {'merchant_id', 'mode', 'signing_secrets'}
            or config['mode'] != 'live' or not isinstance(config['signing_secrets'], list)):
        raise ValueError('Payment webhook configuration is invalid.')
    # An authenticated event must belong to the same configured Sarsa account.
    accounts.current(config['merchant_id'], config['mode'])
    return WebhookAccount(config['merchant_id'], config['mode'], tuple(config['signing_secrets']))
