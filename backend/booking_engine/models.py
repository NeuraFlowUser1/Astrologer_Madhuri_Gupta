"""Strict booking inputs, deliberately independent of enquiry verification."""

from datetime import date, datetime, timezone
from uuid import UUID
from typing import Literal

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class BookingInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr = Field(max_length=254)
    phone: str = Field(min_length=7, max_length=32)
    service_id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    quote_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    starts_at: datetime
    birth_date: date | None = None
    birth_time: str = Field(default='', pattern=r'^(?:|(?:[01][0-9]|2[0-3]):[0-5][0-9])$')
    birth_place: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=4000)

    @field_validator('full_name', 'birth_place', 'notes')
    @classmethod
    def no_controls(cls, value):
        if any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('Please remove unsupported control characters.')
        return value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return value.lower()

    @field_validator('phone')
    @classmethod
    def international_mobile(cls, value):
        if not value.startswith('+'):
            raise ValueError('Include your country code, for example +91.')
        try:
            number = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException:
            raise ValueError('Please enter a valid mobile number.') from None
        if (number.extension or not phonenumbers.is_valid_number(number) or
                phonenumbers.number_type(number) not in (
                    phonenumbers.PhoneNumberType.MOBILE,
                    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE)):
            raise ValueError('Please enter a valid mobile number without an extension.')
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)

    @field_validator('starts_at')
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None or value.second or value.microsecond:
            raise ValueError('Please choose a valid appointment time.')
        return value.astimezone(timezone.utc)


class BookingRequest(BookingInput):
    """V2 preserves mailbox spelling; explicit V1 retains old retry bindings."""
    normalization_version: Literal[1, 2] = 2

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        # EmailStr already normalizes the domain; the local part can be case
        # sensitive and is not silently rewritten for new requests.
        return value

    @model_validator(mode='after')
    def legacy_normalization(self):
        if self.normalization_version == 1:
            self.email = self.email.lower()
        return self
