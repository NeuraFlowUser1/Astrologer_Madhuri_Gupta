"""A lane's SQL calls keep the exact admitted run, release and restore authority."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID
import re

_turn=ContextVar('appointment_worker_turn',default=None)

@dataclass(frozen=True)
class Turn:
    run_id:str
    lane:str
    generation:str
    release_digest:str
    lease_token:str

    def __post_init__(self):
        from .recovery_contract import LANES
        if self.lane not in LANES or not re.fullmatch('[a-f0-9]{64}',self.release_digest):raise ValueError('worker_identity_invalid')
        for value in (self.run_id,self.generation,self.lease_token):
            if type(value) is not str or str(UUID(value))!=value or not UUID(value).int:raise ValueError('worker_identity_invalid')

    def parameters(self):return (self.run_id,self.lane,self.generation,self.release_digest,self.lease_token)

def current():return _turn.get()

@contextmanager
def admitted(turn):
    if not isinstance(turn,Turn) or current() is not None:raise ValueError('worker_identity_invalid')
    token=_turn.set(turn)
    try:yield
    finally:_turn.reset(token)
