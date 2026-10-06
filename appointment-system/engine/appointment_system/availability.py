"""One database algorithm supplies both advisory offers and admission checks."""

from datetime import date
from .connection import StorageUnavailable
from .policy import InvalidSelection


class IntakeClosed(Exception):
    pass


def available_times(store, service_id, day, questions=1):
    if type(day) is not date or type(questions) is not int:
        raise InvalidSelection("Please choose a valid appointment date.")
    offered = store.available_times(service_id, day, questions)
    if not isinstance(offered, dict):
        raise StorageUnavailable("The booking schedule could not be checked.")
    if offered.get("code") == "service_unavailable":
        raise InvalidSelection("Please choose an available consultation.")
    if offered.get("code") == "booking_disabled":
        raise IntakeClosed()
    return offered
