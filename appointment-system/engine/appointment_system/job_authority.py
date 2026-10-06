"""Exact saved transport claim; a caller cannot borrow a replacement worker's lease."""
from dataclasses import dataclass
from uuid import UUID
import re
from .configuration import installation

@dataclass(frozen=True)
class JobClaim:
    kind:str
    identifier:str
    lease:str
    attempt:int
    installation_id:str
    generation:str
    release_digest:str
    writer_contract:int

    def __post_init__(self):
        if self.kind not in ('booking','contact','booking_code') or type(self.attempt) is not int or not 1<=self.attempt<=2147483647:
            raise ValueError('job_claim_invalid')
        if type(self.writer_contract) is not int or self.writer_contract!=1 or type(self.release_digest) is not str or not re.fullmatch('[a-f0-9]{64}',self.release_digest):
            raise ValueError('job_claim_invalid')
        for identifier in (self.identifier,self.lease,self.installation_id,self.generation):
            try:valid=type(identifier) is str and str(UUID(identifier))==identifier and bool(UUID(identifier).int)
            except (ValueError,TypeError,AttributeError):valid=False
            if not valid:raise ValueError('job_claim_invalid')
        if self.installation_id!=installation()['installation_id']:raise ValueError('job_claim_invalid')

    @classmethod
    def saved(cls,kind,job):
        try:return cls(kind,job['id'],job['lease_token'],job['attempts'],job['claim_installation'],job['claim_generation'],job['claim_release'],job['claim_contract'])
        except (KeyError,TypeError):raise ValueError('job_claim_invalid') from None

    def parameters(self):
        return (self.kind,self.identifier,self.lease,self.attempt,self.installation_id,self.generation,self.release_digest,self.writer_contract)
