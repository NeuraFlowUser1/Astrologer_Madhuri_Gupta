"""Exact independent bearer keys; no alternate asynchronous consumer routes."""
import base64,binascii,hmac,re
from dataclasses import dataclass,field
from pydantic import BaseModel,ConfigDict

@dataclass(frozen=True)
class WorkerKey:
    value: str = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}=',self.value):
                raise ValueError()
            decoded=base64.b64decode(self.value,altchars=b'-_',validate=True)
            if len(decoded)!=32 or base64.urlsafe_b64encode(decoded).decode()!=self.value:
                raise ValueError()
        except (ValueError,binascii.Error):
            raise ValueError('Worker configuration is incomplete.') from None

    def accepts(self, headers):
        values=headers.getlist('authorization')
        return len(values)==1 and hmac.compare_digest(values[0].encode(),('Bearer '+self.value).encode())


class WakeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')

