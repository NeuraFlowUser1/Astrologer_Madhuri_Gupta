"""Best-effort post-commit wake-up. Failure never replaces saved work or its result."""

from .configuration import owners,sender,project_id,label,worker_origin,origin
from .request_budget import BudgetExpired,provider_timeout,chunks,remaining
import logging
from dataclasses import dataclass,field
import httpx
from .worker_access import WorkerKey
from .serialization import decode

log=logging.getLogger(__name__)
WAKE_URL=worker_origin()+'/wake'


@dataclass(frozen=True)
class WakePublisher:
    url:str
    key:str=field(repr=False)
    transport:object=field(default=None,repr=False,compare=False)

    def __post_init__(self):
        WorkerKey(self.key)
        if self.url!=WAKE_URL:
            raise ValueError('Dedicated Practice wake address required.')

    def publish(self):
        try:
            with httpx.Client(timeout=provider_timeout(3),follow_redirects=False,trust_env=False,
                              transport=self.transport) as client:
                with client.stream('POST',self.url,headers={'Authorization':'Bearer '+self.key},json={}) as response:
                    if response.status_code!=202 or response.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':
                        raise ValueError()
                    data=bytearray()
                    for chunk in chunks(response):
                        data.extend(chunk)
                        if len(data)>1024:raise ValueError()
                    body=decode(bytes(data),maximum=1024)
                    if (type(body) is not dict or set(body)!={'application','queued'}
                        or body['application']!=project_id() or body['queued'] is not True):raise ValueError()
            return True
        except (BudgetExpired,httpx.HTTPError,ValueError,UnicodeError):
            log.warning('appointment_wake_pending_rescue')
            return False
