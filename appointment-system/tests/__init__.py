"""Master proof runs against the installed package, never a client import."""
from appointment_system.configuration import configure
from .fixtures import installation,business
configure(installation(),business())
