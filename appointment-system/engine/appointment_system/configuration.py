"""One explicitly bound installation per process; no account discovery or fallback."""

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .errors import unavailable
from .serialization import decode
from .settings import BusinessSettings, Installation, canonical_business_contacts


@dataclass(frozen=True)
class Profile:
    installation: Installation
    initial_business: BusinessSettings

    def facts(self):
        return self.installation.document


_profile = None
_lock = Lock()


def configure(installation, initial_business):
    """Called by the contained host wrapper before importing provider composition.

    A process never switches installations. Business changes are read from the
    database, not by modifying this bootstrap snapshot or hot-reloading files.
    """
    incoming = Profile(Installation.parse(installation), BusinessSettings.parse(canonical_business_contacts(initial_business)))
    global _profile
    with _lock:
        if _profile is not None and _profile != incoming:
            raise ValueError("An installation change requires a fresh process.")
        _profile = incoming
    return incoming


def load(project_file):
    path = Path(project_file)
    business = path.with_name("business-settings.json")
    if (path.is_symlink() or business.is_symlink() or not path.is_file()
            or not business.is_file() or path.stat().st_size > 131072
            or business.stat().st_size > 131072):
        raise ValueError("Explicit project settings are required.")
    return configure(decode(path.read_bytes()), decode(business.read_bytes()))


def profile():
    if _profile is None:
        raise unavailable()
    return _profile


def installation():
    return profile().facts()


def business():
    """Bootstrap/migration facts only. Scheduling always reads current SQL policy."""
    return profile().initial_business.document


def origin():
    return installation()["origin"]


def label():
    return installation()["label"]


def project_id():
    return installation()["project_id"]


def owners():
    declared = installation()["owners"]
    return {"client": declared["client_email"], "agency": declared["agency_email"]}


def sender():
    return installation()["sender"]


def worker_origin():
    return installation()["worker"]["origin"]
