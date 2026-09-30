"""Approved Sarsa catalogue and reference scheduling rules.

The database stores this versioned snapshot before it can accept a hold. Prices
are integer paise, never floating point or values supplied by the browser.
Availability is advisory; the database claim decides who actually owns a slot.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

from .security import request_fingerprint

IST = ZoneInfo('Asia/Kolkata')
NOTICE_MINUTES = 30
ADVANCE_DAYS = 10
HOLD_MINUTES = 10
RECEIPT_AFTER_HOURS = 24
WINDOWS = ((time(10), time(12)), (time(15), time(18)))


class InvalidSelection(ValueError):
    pass


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    amount_paise: int
    duration_minutes: int = 30

    def snapshot(self):
        return dict(id=self.id, name=self.name, amount_paise=self.amount_paise,
                    duration_minutes=self.duration_minutes, currency='INR',
                    meeting_platform='Google Meet')


SERVICES = MappingProxyType({service.id: service for service in (
    # Owner-authorised live payment test: restore 210000 paise after acceptance.
    Service('kundli-matching', 'Kundli Matching', 100),
    Service('kundli-prediction', 'Kundli Prediction', 250000),
    Service('vastu-consultation', 'Vastu Consultation', 450000),
    Service('numerology', 'Numerology', 210000),
)})


def policy_snapshot():
    # Fresh objects: a caller cannot mutate the next caller's quote.
    return dict(project='004-sarsa-jyotish-sansthan', timezone=IST.key,
                weekdays=[0, 1, 2, 3, 4, 5],
                windows=[['10:00', '12:00'], ['15:00', '18:00']],
                slot_step_minutes=30, notice_minutes=NOTICE_MINUTES,
                advance_days=ADVANCE_DAYS, hold_minutes=HOLD_MINUTES,
                receipt_after_hours=RECEIPT_AFTER_HOURS,
                availability_authority='website_staff_calendar',
                services=[service.snapshot() for service in SERVICES.values()])


def policy_version():
    return request_fingerprint(policy_snapshot())


def service_for(service_id):
    try:
        return SERVICES[service_id]
    except (KeyError, TypeError):
        raise InvalidSelection('Please choose one of the available consultations.') from None


def _local(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidSelection('Please choose a time with a valid time zone.')
    return value.astimezone(IST)


def validate_start(service_id, starts_at, now):
    service = service_for(service_id)
    start, current = _local(starts_at), _local(now)
    end = start + timedelta(minutes=service.duration_minutes)
    if (start.second or start.microsecond or start.minute % 30 or start.weekday() == 6
            or not current.date() <= start.date() <= current.date() + timedelta(days=ADVANCE_DAYS)
            or start < current + timedelta(minutes=NOTICE_MINUTES)
            or not any(start.time() >= opening and end.date() == start.date()
                       and end.time() <= closing for opening, closing in WINDOWS)):
        raise InvalidSelection('That time is no longer available. Please choose another time.')
    return end


def candidates(service_id, day, now):
    service_for(service_id)
    _local(now)
    if type(day) is not date:
        raise InvalidSelection('Please choose a valid appointment date.')
    result = []
    for opening, closing in WINDOWS:
        start = datetime.combine(day, opening, IST)
        stop = datetime.combine(day, closing, IST)
        while start < stop:
            try:
                validate_start(service_id, start, now)
            except InvalidSelection:
                pass
            else:
                result.append(start)
            start += timedelta(minutes=30)
    return tuple(result)


def quote(service_id):
    return dict(**service_for(service_id).snapshot(), quote_version=policy_version(),
                timezone=IST.key)
