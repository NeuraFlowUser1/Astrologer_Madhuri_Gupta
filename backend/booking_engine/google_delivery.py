"""One durable Google delivery per invocation; scheduling is a separate concern."""

from .google_access import refresh_connection
from .google_oauth import GoogleFailure
from .google_records import copy_booking_record
from .google_workspace import Workspace, WorkspaceFailure
from .recovery import delay_for

ATTENTION = frozenset({'google_appointment_ended','google_event_mismatch','google_meeting_invalid','google_meeting_unavailable',
    'google_workbook_owner_mismatch','google_workbook_ambiguous','google_workbook_layout_changed',
    'google_row_conflict','google_row_invalid','google_record_assignment_unavailable'})


def run_google_delivery_once(store, services, *, transport=None):
    job = store.claim_google_delivery()
    if job is None:
        return {'processed':0}
    state, provider, meet, error = 'done', None, None, None
    delay = delay_for(job['attempts'])
    try:
        if job['kind']=='sheet_booking':
            provider = copy_booking_record(store, services, job, transport=transport)
        elif job['kind']=='booking_calendar':
            access = refresh_connection(store, services, 'client')
            workspace = Workspace(access, transport=transport)
            if job.get('obsolete') is True:
                workspace.cancel_meeting(job['payload'])
                state = 'obsolete'
            else:
                result = workspace.ensure_meeting(job['payload'])
                provider, meet = result['event_id'], result['meet_url']
                if result['state']=='waiting':
                    state, delay = 'waiting', 15
        elif job['kind']=='booking_cancelled' and job['recipient_role']=='calendar':
            access = refresh_connection(store, services, 'client')
            Workspace(access, transport=transport).cancel_meeting(job['payload'])
        else:
            raise WorkspaceFailure('google_record_job_invalid')
    except (GoogleFailure, WorkspaceFailure) as failure:
        error = str(failure)
        state = 'attention' if error in ATTENTION else 'failed'
    # Storage errors, including unknown commits, propagate: the saved lease
    # expires and a later worker reconciles the deterministic remote identity.
    if store.finish_google_delivery(job,state,provider,meet,error,delay) is not True:
        return {'processed':0,'retry':True}
    return {'processed':1,'state':state}
