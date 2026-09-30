"""Best-effort post-commit wake-up. Failure never replaces saved work or its result."""
import logging
from dataclasses import dataclass,field
import httpx
from .google_worker import WorkerKey

log=logging.getLogger(__name__)
WAKE_URL='https://sarsa-booking-recovery.neuraflowindia.workers.dev/wake'


@dataclass(frozen=True)
class WakePublisher:
    url:str
    key:str=field(repr=False)
    transport:object=field(default=None,repr=False,compare=False)

    def __post_init__(self):
        WorkerKey(self.key)
        if self.url!=WAKE_URL:
            raise ValueError('Dedicated Sarsa wake address required.')

    def publish(self):
        try:
            with httpx.Client(timeout=httpx.Timeout(3),follow_redirects=False,trust_env=False,
                              transport=self.transport) as client:
                with client.stream('POST',self.url,headers={'Authorization':'Bearer '+self.key},json={}) as response:
                    if response.status_code!=202 or not response.headers.get('content-type','').lower().startswith('application/json'):
                        raise ValueError()
                    data=bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data)>1024:raise ValueError()
                    import json
                    body=json.loads(data)
                    if body!={'application':'004-sarsa-jyotish-sansthan','queued':True}:raise ValueError()
            return True
        except (httpx.HTTPError,ValueError,UnicodeError):
            log.warning('sarsa_wake_pending_rescue')
            return False
