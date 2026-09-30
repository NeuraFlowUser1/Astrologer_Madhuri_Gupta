"""Available times are a database-backed offer, not a reservation guarantee."""

from datetime import date, datetime, time, timedelta

from .connection import StorageUnavailable
from .policy import IST, InvalidSelection, candidates, policy_snapshot, policy_version, quote, service_for
from .receipt_view import timestamp


class IntakeClosed(Exception):
    pass


def available_times(store, service_id, day):
    service = service_for(service_id)
    if type(day) is not date:
        raise ValueError('Please choose a valid appointment date.')
    start = datetime.combine(day, time(), IST)
    try:
        end = start+timedelta(days=1)
    except OverflowError:
        raise InvalidSelection('Please choose a valid appointment date.') from None
    snapshot = store.scheduling_snapshot(start,end)
    if (not snapshot or snapshot.get('policy_version') != policy_version()
            or snapshot.get('specification') != policy_snapshot()):
        raise StorageUnavailable('The booking schedule is being updated.')
    if snapshot.get('schedule_browsing_open') is not True:
        raise IntakeClosed()
    now = timestamp(snapshot['server_now'])
    occupied = [(timestamp(row['starts_at']),timestamp(row['ends_at'])) for row in snapshot['claims']]
    if any(end <= begin for begin,end in occupied):
        raise StorageUnavailable('The booking schedule could not be checked.')
    slots=[]
    for value in candidates(service_id,day,now):
        end = value+timedelta(minutes=service.duration_minutes)
        if not any(value < occupied_end and end > occupied_start for occupied_start,occupied_end in occupied):
            slots.append(dict(starts_at=value.isoformat(),ends_at=end.isoformat()))
    return dict(service=quote(service_id),date=day.isoformat(),server_now=now.isoformat(),slots=slots)
