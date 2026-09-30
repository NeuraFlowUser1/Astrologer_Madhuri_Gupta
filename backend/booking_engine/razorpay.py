"""Sarsa-specific adaptation of project003 Razorpay transport; durable callers own intents and reconciliation.

Never retry order creation here: a timeout can hide a successful remote write.
This module does not confirm bookings, move money or expose public routes.
"""
from dataclasses import dataclass, field

import hashlib
import hmac
import json
import re
from uuid import UUID

import httpx

API = 'https://api.razorpay.com/v1/'
MAX_RESPONSE = 262144


class RazorpayFailure(Exception):
    def __init__(self, code, *, uncertain=False):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


def identifier(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r'_[A-Za-z0-9]{1,64}', value):
        raise ValueError('Invalid provider identifier.')
    return value


def merchant_identity(value):
    """Normalize Razorpay's MID and its account-prefixed webhook form."""
    if not isinstance(value, str):
        return None
    value = value.removeprefix('acc_')
    return value if re.fullmatch(r'[A-Za-z0-9]{1,64}', value) else None


def order_receipt(intent_id, mode):
    if mode not in ('test', 'live'):
        raise ValueError('Invalid payment mode.')
    return ('s4t_' if mode == 'test' else 's4l_') + UUID(str(intent_id)).hex


def verify_signature(body, signature, secret):
    if (not isinstance(body, bytes) or not isinstance(secret, str) or not secret or
            not isinstance(signature, str) or not re.fullmatch(r'[0-9a-f]{64}', signature)):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_checkout(stored_order_id, payment_id, signature, secret):
    identifier(stored_order_id, 'order')
    identifier(payment_id, 'pay')
    return verify_signature((stored_order_id + '|' + payment_id).encode(), signature, secret)


def payment_matches(payment, *, payment_id, order_id, amount):
    """Capture alone is not enough: bind to the saved order, amount and currency.

    Caller must fetch this through the saved merchant/mode credentials, then
    check current slot ownership inside its scheduling transaction.
    """
    return (isinstance(payment, dict) and type(amount) is int and amount > 0 and
            payment.get('entity') == 'payment' and payment.get('id') == payment_id and
            payment.get('order_id') == order_id and type(payment.get('amount')) is int and
            payment['amount'] == amount and payment.get('currency') == 'INR' and
            payment.get('status') == 'captured' and payment.get('captured') is True and
            type(payment.get('amount_refunded')) is int and payment['amount_refunded'] == 0)


@dataclass(frozen=True)
class Credentials:
    merchant_id: str
    mode: str
    version: str
    key_id: str = field(repr=False)
    key_secret: str = field(repr=False)

    def __post_init__(self):
        if (merchant_identity(self.merchant_id) is None or self.mode not in ('test','live')
                or not isinstance(self.version,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.version)
                or not isinstance(self.key_id,str)
                or not re.fullmatch('rzp_'+self.mode+r'_[A-Za-z0-9]+',self.key_id)
                or not isinstance(self.key_secret,str) or not self.key_secret.strip()):
            raise RazorpayFailure('payment_configuration_missing')

    def matches_intent(self, merchant_id, mode, version):
        return (merchant_identity(merchant_id)==merchant_identity(self.merchant_id)
                and mode==self.mode and version==self.version)


class Razorpay:
    def __init__(self, credentials, *, transport=None):
        if not isinstance(credentials,Credentials):
            raise RazorpayFailure('payment_configuration_missing')
        self.credentials = credentials
        self.key_id, self._secret = credentials.key_id, credentials.key_secret
        self.mode, self.transport = credentials.mode, transport

    def _request(self, method, path, *, payload=None, params=None):
        writing = method == 'POST'
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False, transport=self.transport,
                              auth=(self.key_id, self._secret)) as client:
                with client.stream(method, API + path, json=payload, params=params,
                                   headers={'Accept': 'application/json'}) as response:
                    if response.status_code in (401, 403):
                        raise RazorpayFailure('payment_credentials_rejected', uncertain=writing)
                    if response.status_code == 404:
                        raise RazorpayFailure('payment_resource_missing', uncertain=writing)
                    if response.status_code not in (200, 201):
                        raise RazorpayFailure('payment_provider_unavailable', uncertain=writing)
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE:
                            raise RazorpayFailure('payment_response_invalid', uncertain=writing)
                    if not response.headers.get('content-type', '').lower().startswith('application/json'):
                        raise RazorpayFailure('payment_response_invalid', uncertain=writing)
                    try:
                        data = json.loads(body)
                    except (ValueError, UnicodeError):
                        raise RazorpayFailure('payment_response_invalid', uncertain=writing) from None
                    if not isinstance(data, dict):
                        raise RazorpayFailure('payment_response_invalid', uncertain=writing)
                    return data
        except (httpx.HTTPError, UnicodeError):
            raise RazorpayFailure('payment_provider_unavailable', uncertain=writing) from None

    def create_order(self, intent_id, amount):
        if type(amount) is not int or amount <= 0:
            raise ValueError('Amount must be positive integer paise.')
        receipt = order_receipt(intent_id, self.mode)
        result = self._request('POST', 'orders', payload={
            'amount': amount, 'currency': 'INR', 'receipt': receipt, 'partial_payment': False})
        try:
            identifier(result.get('id'), 'order')
        except ValueError:
            raise RazorpayFailure('payment_order_mismatch', uncertain=True) from None
        if (result.get('entity') != 'order' or result.get('receipt') != receipt or
                type(result.get('amount')) is not int or result['amount'] != amount or
                result.get('currency') != 'INR' or result.get('partial_payment', False) is not False):
            raise RazorpayFailure('payment_order_mismatch', uncertain=True)
        return result

    def order(self, order_id):
        return self._request('GET', 'orders/' + identifier(order_id, 'order'))

    def payment(self, payment_id):
        return self._request('GET', 'payments/' + identifier(payment_id, 'pay'))

    def order_payments(self, order_id):
        return self._request('GET', 'orders/' + identifier(order_id, 'order') + '/payments')

    def orders_page(self, intent_id, *, skip=0):
        # A page, not a uniqueness assertion. Durable reconciliation must paginate
        # and verify each candidate. An empty result never authorizes re-creation.
        if type(skip) is not int or skip < 0:
            raise ValueError('Invalid page offset.')
        return self._request('GET', 'orders', params={
            'receipt': order_receipt(intent_id, self.mode), 'count': 100, 'skip': skip})
