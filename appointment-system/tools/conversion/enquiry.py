"""Reprotect an existing enquiry code without changing its value or lifetime."""
from copy import deepcopy
from dataclasses import dataclass,field
import hmac
from appointment_system.contact import ContactSecrets
from appointment_system.errors import Rejected
from .source import ConversionError
from .records import stamp


@dataclass(frozen=True,repr=False)
class EnquiryTransfer:
    protection:ContactSecrets=field(repr=False)
    cipher_format:str
    digest_format:str

    def __post_init__(self):
        if (not isinstance(self.protection,ContactSecrets)
                or self.cipher_format not in self.protection.cipher.readers
                or self.digest_format not in {value[0] for value in self.protection.legacy_digests}):
            raise ConversionError('legacy_enquiry_reader_invalid')

    def __call__(self,original,now):
        row=deepcopy(original);keys=self.protection
        try:
            reference=row['request_id'];email=row['payload']['email'];generation=row['generation']
            if row['verified_at'] is not None or stamp(row['code_expires_at'])<=now:
                raise ValueError()
            code=keys.open_code(row['code_ciphertext'],reference,email,generation,stamp(row['code_expires_at']),
                                now=now,format=self.cipher_format)
            expected=keys.digest('code',reference,generation,email,code,format=self.digest_format)
            if not hmac.compare_digest(expected,row['code_digest']):raise ValueError()
            body=dict(purpose='appointment:v1:enquiry-code',request_id=reference,email=email,
                      generation=generation,code=code,digest_key_id=keys.digest_key.active)
            row.update(code_ciphertext=keys.cipher.seal(keys.record('code',reference,email,generation),body),
                       code_digest=keys.digest('code',reference,generation,email,code),
                       code_format='v1',code_digest_format='v1',code_digest_key_id=keys.digest_key.active)
            return row
        except (Rejected,KeyError,ValueError,TypeError,AttributeError):
            raise ConversionError('legacy_enquiry_code_invalid') from None
