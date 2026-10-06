"""Company capability composition, independent of resource-owner Google consent."""
from dataclasses import dataclass,field
import hashlib
import os
import re
import certifi
import psycopg
from psycopg.types.json import Jsonb
from .configuration import installation,origin,label,project_id
from .keys import KeyRing
from .request_budget import BudgetCursor,remaining
from .serialization import canonical,decode,record_id
from .errors import Rejected
from .connection import StorageUnavailable

PREFIX="BOOKING"
COOKIE="__Host-booking-company"
LOGIN_COOKIE="__Host-booking-company-login"
# Bound only after the host has validated its contained installation profile.
ORIGIN=origin()
CLIENT_NAME=label()
PROJECT=project_id()


class ControlError(Exception):
    def __init__(self,code="company_tools_unavailable",status=503):
        self.code,self.status=code,status
        super().__init__(code)


def unique_json(value):
    return decode(value)


def snapshot(value):
    facts=installation()
    names={"version","installation_id","project","environment","origin","enabled","restore_generation",
           "generation_sequence","revision","activation_epoch"}
    try:
        if (type(value) is not dict or set(value)!=names or type(value["version"]) is not int
            or value["version"]!=1 or value["installation_id"]!=facts["installation_id"]
            or value["project"]!=facts["project_id"] or value["environment"]!=facts["environment"]
            or value["origin"]!=facts["origin"] or type(value["enabled"]) is not bool):
            raise ValueError()
        for name in ("revision","generation_sequence"):
            if (type(value[name]) is not str or not re.fullmatch(r"[1-9][0-9]{0,18}",value[name])
                or int(value[name])>9223372036854775807):
                raise ValueError()
        for name in ("restore_generation","activation_epoch"):
            record_id(value[name])
    except (ValueError,Rejected):
        raise ControlError("projection_response_invalid") from None
    return dict(value)


@dataclass(frozen=True,repr=False)
class ControlSettings:
    dsn:str=field(repr=False)
    target:dict=field(repr=False)
    session_keys:KeyRing=field(repr=False)
    google_client_id:str=""

    @property
    def expected_host(self):
        return self.target["host"]

    def __post_init__(self):
        from .connection import checked_config
        checked_config(self.dsn,self.expected_host,purpose="company")
        facts=installation()
        if (self.session_keys.installation_id!=facts["installation_id"]
            or self.session_keys.environment!=facts["environment"]
            or self.session_keys.purpose!="company-session"):
            raise ControlError()

    def digest(self,purpose,value):
        if type(value) is not str or not 1<=len(value)<=8192:
            raise ControlError("company_session_required",401)
        return self.session_keys.digest(purpose,value.encode("utf8"))


def settings_from_environment(expected_host=None,environment=None):
    source=os.environ if environment is None else environment
    try:
        facts=installation();target=facts["database_targets"]["company"]
        ring=KeyRing.parse(source["BOOKING_COMPANY_SESSION_KEYS"],installation_id=facts["installation_id"],
                           environment=facts["environment"],purpose="company-session")
        return ControlSettings(source["BOOKING_COMPANY_DATABASE_URL"],target,ring,
                               source.get("BOOKING_GOOGLE_CLIENT_ID",""))
    except (KeyError,ValueError,Rejected,ControlError,StorageUnavailable):
        return None


class ControlDatabase:
    def __init__(self,settings):
        self.settings=settings

    def call(self,statement,parameters=(),*,resource_authority=None):
        try:
            self.settings.__post_init__();remaining(3)
            with psycopg.connect(self.settings.dsn,connect_timeout=3,cursor_factory=BudgetCursor,
                                 prepare_threshold=None,sslmode="verify-full",sslrootcert=certifi.where()) as conn:
                conn.execute("SET LOCAL statement_timeout='5s'")
                conn.execute("SET LOCAL lock_timeout='2s'")
                facts=installation()
                identity=conn.execute("SELECT appointment_system.validate_caller(%s,%s,%s,%s)",
                       (facts["installation_id"],facts["environment"],"company",1)).fetchone()[0]
                if identity is not True:
                    raise ControlError()
                if resource_authority is not None:
                    if not isinstance(resource_authority,tuple) or len(resource_authority)!=4:
                        raise ControlError('company_request_rejected',403)
                    authorized=conn.execute('SELECT appointment_system.authorize_resource_operation(%s,%s,%s,%s)',resource_authority).fetchone()[0]
                    if authorized is not True:raise ControlError('company_session_required',401)
                result=conn.execute(statement,parameters).fetchone()[0]
                remaining(.1)
            return result
        except psycopg.Error as error:
            codes={"P0401":("company_session_required",401),"P0409":("company_state_changed",409),
                   "P0422":("invalid_company_request",422),"42501":("company_access_rejected",403)}
            raise ControlError(*codes.get(error.sqlstate,("company_tools_unavailable",503))) from None

    def command(self,token,csrf,operation,generation,revision,enabled,reason):
        body={"operation_id":str(operation),"generation":str(generation),"revision":revision,
              "enabled":enabled,"reason":reason}
        return self.call("SELECT appointment_system.control_command(%s,%s,%s,%s,%s,%s,%s,%s)",
                         (token,csrf,operation,generation,int(revision),enabled,reason,
                          hashlib.sha256(canonical(body)).hexdigest()))

    def status(self,token):
        return self.call("SELECT appointment_system.control_control_status(%s)",(token,))

    def claim_publication(self):
        return self.call("SELECT appointment_system.control_claim_publication()")

    def finish_publication(self,job,ack=None,error=None):
        return self.call("SELECT appointment_system.control_finish_publication(%s,%s,%s,%s)",
                         (job["operation_id"],job["lease_token"],Jsonb(ack) if ack is not None else None,error))

    def record_probe(self,job,observed):
        return self.call("SELECT appointment_system.control_record_probe(%s,%s)",
                         (job["operation_id"],Jsonb(observed)))

    def claim_probe(self):
        return self.call("SELECT appointment_system.control_claim_probe()")

    def probe_retry(self,job,error):
        return self.call("SELECT appointment_system.control_probe_retry(%s,%s,%s)",
                         (job["operation_id"],job["lease_token"],error))

    def incidents(self,token):
        return self.call("SELECT appointment_system.read_operation_incidents(%s)",(token,))


