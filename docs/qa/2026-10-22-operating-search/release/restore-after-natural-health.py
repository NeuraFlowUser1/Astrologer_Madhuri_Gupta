"""One-shot release operator: observe natural cron, then restore the saved intent.

This never schedules/forces a Worker turn or customer dispatch. It expires at
17:46:30 UTC on 22 October 2026 and must not be reused for a later programme.
"""
import datetime
import importlib.util
import json
from pathlib import Path
import time
import httpx

here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('release_operator',here/'operator-004.py')
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
start=datetime.datetime(2026,10,22,17,44,50,tzinfo=datetime.timezone.utc).timestamp()
deadline=datetime.datetime(2026,10,22,17,46,30,tzinfo=datetime.timezone.utc).timestamp()
observations=[]
try:
    if time.time()>deadline:raise op.Stop('this_release_health_window_has_expired')
    while time.time()<start:time.sleep(min(2,start-time.time()))
    helper=op.module('existing_encrypted_access',op.SHARED/'001-implementation-evidence/2026-10-04-complete-local-checks/validate-sarsa-access-settings.py')
    bundle=helper.private_bundle()
    try:
        with httpx.Client(timeout=5,trust_env=False,follow_redirects=False) as client:
            while time.time()<=deadline:
                response=client.get('https://sarsa-booking-recovery.neuraflowindia.workers.dev/health',headers={'Authorization':'Bearer '+bundle['settings']['BOOKING_MONITOR_KEY']})
                observations.append({'observed_at':op.now(),'status':response.status_code,'health':response.json()})
                op.save('natural-health-observations.json',observations)
                if response.status_code==200 and response.json()=={'status':'healthy'}:break
                time.sleep(2)
            else:raise op.Stop('natural_scheduled_health_not_accepted')
    finally:bundle.clear()
    checked=op.protected()
    if checked['release_digest']!=op.NEW or not all(checked['configured'].values()) or checked['worker_health_status']!=200:
        raise op.Stop('matching_live_release_not_accepted')
    op.save('operator-protected.json',checked)
    # company('on') verifies the saved OFF operation/generation/revision again;
    # a newer company command wins and prevents this restoration.
    result=op.company('on')
    op.save('operator-on.json',result)
    print(json.dumps({'natural_health':observations[-1],'restored':result}))
except Exception as error:
    value={'successful':False,'observed_at':op.now(),'safe_error':str(error) if isinstance(error,op.Stop) else type(error).__name__,'private_values_printed':False}
    op.save('natural-health-restoration-blocked.json',value);print(json.dumps(value));raise SystemExit(1) from None
