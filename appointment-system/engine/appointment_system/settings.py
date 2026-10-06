"""Strict public installation facts and basic, immutable business settings."""

from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import invalid
from .serialization import canonical, decode, integer, object_fields, record_id, text

IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
DNS = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")
EMAIL = re.compile(r"[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+\Z")
CONTACT_FIELDS = {"email", "phone"}
PREPARATION_FIELDS = {"birth_date", "birth_time", "birth_place", "notes"}
PROJECT_FIELDS = {"version", "installation_id", "project_id", "label", "environment",
                  "origin", "aliases", "database_targets", "owners", "sender",
                  "providers", "worker", "surfaces"}
BUSINESS_FIELDS = {"version", "timezone", "services", "weekly_windows",
                   "slot_step_minutes", "notice_minutes", "horizon_days",
                   "buffer_before_minutes", "buffer_after_minutes",
                   "booking_verification", "required_contacts", "meeting",
                   "email_budget"}


def identifier(value, field="id"):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):
        raise invalid(field)
    return value


def email(value, field="email"):
    text(value, 3, 254, field=field)
    if not EMAIL.fullmatch(value):
        raise invalid(field)
    return value.lower()


def boolean(value, field="settings"):
    if type(value) is not bool:
        raise invalid(field)
    return value


def origin(value, environment):
    text(value, 8, 512, field="origin")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise invalid("origin") from None
    host = parsed.hostname
    if (not host or not DNS.fullmatch(host) or host != host.lower()
            or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment or parsed.netloc != parsed.netloc.lower()):
        raise invalid("origin")
    if environment == "production":
        if parsed.scheme != "https" or port is not None or host == "localhost":
            raise invalid("origin")
    elif (parsed.scheme != "https" and not (
            parsed.scheme == "http" and host in ("localhost", "127.0.0.1"))):
        raise invalid("origin")
    return value


def _unique_list(value, maximum, allowed=None, field="settings"):
    if (type(value) is not list or len(value) > maximum
            or any(type(item) is not str for item in value)
            or len(set(value)) != len(value)
            or allowed is not None and set(value) - allowed):
        raise invalid(field)
    return value


def _minute(value, *, end=False):
    if type(value) is not str or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise invalid("weekly_windows")
    hour, minute = map(int, value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59 or end and hour == 24 and minute == 0):
        raise invalid("weekly_windows")
    return hour * 60 + minute


@dataclass(frozen=True)
class Installation:
    """Private connections cannot override these independently declared targets."""

    encoded: bytes

    @classmethod
    def parse(cls, document):
        value = decode(canonical(document))
        object_fields(value, PROJECT_FIELDS)
        integer(value["version"], 1, 1)
        record_id(value["installation_id"], field="installation_id")
        identifier(value["project_id"], "project_id")
        if len(value["project_id"])>75:
            raise invalid("project_id")
        text(value["label"], 1, 150)
        if value["environment"] not in ("development", "test", "production"):
            raise invalid("environment")
        origin(value["origin"], value["environment"])
        _unique_list(value["aliases"], 20, field="aliases")
        for alias in value["aliases"]:
            origin(alias, value["environment"])
            if alias == value["origin"]:
                raise invalid("aliases")
        targets = value["database_targets"]
        purposes = {"web", "staff", "company", "worker", "maintenance", "backup", "migration", "journal"}
        object_fields(targets, (), purposes)
        if "web" not in targets:
            raise invalid("database_targets")
        for target in targets.values():
            object_fields(target, {"host", "database", "role", "port", "pooling"})
            if type(target["host"]) is not str or not DNS.fullmatch(target["host"]):
                raise invalid("database_targets")
            for field in ("database", "role"):
                if type(target[field]) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", target[field]):
                    raise invalid("database_targets")
            integer(target["port"], 1, 65535)
            boolean(target["pooling"])
        owners = object_fields(value["owners"], {"client_email", "agency_email"})
        for name in owners:
            owners[name] = email(owners[name], "owners")
        if len(set(owners.values())) != 2:
            raise invalid("owners")
        sender = object_fields(value["sender"], {"name", "email", "reply_to"})
        text(sender["name"], 1, 150)
        sender["email"] = email(sender["email"])
        sender["reply_to"] = email(sender["reply_to"])
        providers = object_fields(value["providers"], {"payment", "calendar", "email", "sms"})
        if (providers["payment"] != "razorpay" or providers["email"] != "resend"
                or providers["calendar"] not in ("internal", "google") or providers["sms"] is not None):
            raise invalid("providers")
        worker = object_fields(value["worker"], {"name", "origin"})
        identifier(worker["name"], "worker")
        origin(worker["origin"], value["environment"])
        surfaces = value["surfaces"]
        if type(surfaces) is not list or not 1 <= len(surfaces) <= 1000:
            raise invalid("surfaces")
        paths = set()
        for surface in surfaces:
            object_fields(surface, {"path", "class"})
            path = text(surface["path"], 1, 512, field="surfaces")
            if (not path.startswith("/") or path.startswith("//") or "\\" in path
                    or "%" in path or "?" in path or "#" in path
                    or any(part in (".", "..") for part in path.split("/")) or path in paths):
                raise invalid("surfaces")
            if surface["class"] not in ("general", "enquiry", "booking", "company", "provider", "worker"):
                raise invalid("surfaces")
            paths.add(path)
        return cls(canonical(value))

    @property
    def document(self):
        return decode(self.encoded)

    @property
    def installation_id(self):
        return self.document["installation_id"]

    @property
    def project_id(self):
        return self.document["project_id"]

    @property
    def environment(self):
        return self.document["environment"]


@dataclass(frozen=True)
class BusinessSettings:
    """Immutable data; neither a caller nor one client supplies executable rules."""

    encoded: bytes

    @classmethod
    def parse(cls, document):
        value = decode(canonical(document))
        object_fields(value, BUSINESS_FIELDS)
        integer(value["version"], 1, 1)
        text(value["timezone"], 1, 100)
        try:
            ZoneInfo(value["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise invalid("timezone") from None
        for name, lo, hi in (("slot_step_minutes", 5, 120), ("notice_minutes", 0, 10080),
                             ("horizon_days", 1, 365), ("buffer_before_minutes", 0, 120),
                             ("buffer_after_minutes", 0, 120)):
            integer(value[name], lo, hi, field=name)
        if value["slot_step_minutes"] % 5:
            raise invalid("slot_step_minutes")
        verification = object_fields(value["booking_verification"], {"email", "sms"})
        for item in verification.values():
            boolean(item, "booking_verification")
        if verification["sms"]:
            raise invalid("booking_verification")
        _unique_list(value["required_contacts"], 2, CONTACT_FIELDS, "required_contacts")
        if "email" not in value["required_contacts"]:
            raise invalid("required_contacts")
        if value["meeting"] not in ("internal", "google_meet"):
            raise invalid("meeting")
        services = value["services"]
        if type(services) is not list or not 1 <= len(services) <= 100:
            raise invalid("services")
        ids = set()
        for service in services:
            object_fields(service, {"id", "name", "enabled", "duration_minutes", "pricing", "required_preparation"})
            identifier(service["id"], "service_id")
            if service["id"] in ids:
                raise invalid("services")
            ids.add(service["id"])
            text(service["name"], 1, 150)
            boolean(service["enabled"])
            integer(service["duration_minutes"], 5, 480, field="duration_minutes")
            if service["duration_minutes"] % 5:
                raise invalid("duration_minutes")
            _unique_list(service["required_preparation"], 4, PREPARATION_FIELDS, "required_preparation")
            pricing = object_fields(service["pricing"], {"kind", "amount_paise", "maximum_questions"})
            integer(pricing["amount_paise"], 1, 2147483647, field="amount_paise")
            integer(pricing["maximum_questions"], 1, 10, field="maximum_questions")
            if pricing["kind"] not in ("fixed", "per_question") or (
                    pricing["kind"] == "fixed" and pricing["maximum_questions"] != 1):
                raise invalid("pricing")
            if pricing["amount_paise"] * pricing["maximum_questions"] > 2147483647:
                raise invalid("pricing")
        windows = value["weekly_windows"]
        if type(windows) is not list or not 1 <= len(windows) <= 28:
            raise invalid("weekly_windows")
        prior = {}
        for window in windows:
            object_fields(window, {"weekday", "start", "end"})
            day = integer(window["weekday"], 0, 6, field="weekly_windows")
            start, end = _minute(window["start"]), _minute(window["end"], end=True)
            if start >= end or any(start < old_end and end > old_start for old_start, old_end in prior.get(day, [])):
                raise invalid("weekly_windows")
            prior.setdefault(day, []).append((start, end))
        windows.sort(key=lambda w: (w["weekday"], w["start"]))
        budget = object_fields(value["email_budget"], {"daily", "rolling", "verification_daily", "verification_rolling"})
        for name in budget:
            integer(budget[name], 0, 100000, field="email_budget")
        if (budget["verification_daily"] > budget["daily"] or
                budget["verification_rolling"] > budget["rolling"] or budget["rolling"] < budget["daily"] or
                budget["verification_daily"] > budget["verification_rolling"]):
            raise invalid("email_budget")
        return cls(canonical(value))

    @property
    def document(self):
        return decode(self.encoded)

    def public_services(self):
        # No slot, verification, provider or portal details in the general catalogue.
        return [{"id": item["id"], "name": item["name"]} for item in self.document["services"]]
