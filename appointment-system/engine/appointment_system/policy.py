"""Validated bootstrap policy. SQL alone computes quotes and scheduling offers."""

from zoneinfo import ZoneInfo
from .configuration import business
from .serialization import fingerprint


class InvalidSelection(ValueError):
    pass


def timezone():
    return ZoneInfo(business()["timezone"])


def policy_snapshot():
    return business()


def policy_version():
    return fingerprint(policy_snapshot())
