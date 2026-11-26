"""Password-protected company controls; Google consent is a separate resource flow."""
import hashlib
import hmac
import html
import re
from ipaddress import ip_address,ip_network
from pathlib import Path
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,JSONResponse,Response
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from psycopg.types.json import Jsonb
from .company_auth import Credentials,COOKIE
from .configuration import origin as public_origin,label,project_id,installation
from .serialization import canonical
from .errors import Rejected
from .service_control import ControlDatabase,ControlError
from .request_budget import BudgetExpired

ASSETS=Path(__file__).parent/"company_assets"
PENDING=frozenset(("accepted","publishing","published"))
PRIVATE_HEADERS={"Cache-Control":"private, no-store","Pragma":"no-cache",
 "Referrer-Policy":"no-referrer","X-Content-Type-Options":"nosniff",
 "X-Robots-Tag":"noindex, nofollow","Content-Security-Policy":
 "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
 "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}


class Login(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    username:str=Field(min_length=3,max_length=64)
    password:str=Field(min_length=15,max_length=128,repr=False)


class Command(BaseModel):
    model_config=ConfigDict(extra="forbid")
    operation_id:UUID
    generation:UUID
    revision:str=Field(pattern=r"^[1-9][0-9]{0,18}$")
    enabled:StrictBool
    reason:str=Field(min_length=5,max_length=300)


class EmptyRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)

class PasswordConfirmation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    password:str=Field(min_length=15,max_length=128,repr=False)

class PasswordChange(PasswordConfirmation):
    new_password:str=Field(min_length=15,max_length=128,repr=False)

class BusinessChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    revision:str=Field(pattern=r'^[1-9][0-9]{0,18}$')
    settings:dict
    reason:str=Field(min_length=5,max_length=300)

class SheetReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    record_id:UUID
    role:Literal['client','agency']
    record_kind:Literal['booking','enquiry']
    sequence:str=Field(pattern=r'^[1-9][0-9]{0,18}$')
    reason:str=Field(min_length=5,max_length=300)


def re_full_csrf(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}",value) is not None


def router(settings,*,database=None,publisher=None,worker_key=None,address=None,wake=None):
    routes=APIRouter()
    database=database or (ControlDatabase(settings) if settings is not None else None)
    credentials=Credentials(database,settings) if settings is not None else None

    def configured():
        if credentials is None or database is None:
            raise ControlError("company_tools_unavailable")

    def browser(request):
        if (request.headers.getlist("origin")!=[public_origin()]
            or request.headers.get("content-type","").split(";")[0]!="application/json"
            or request.headers.get("content-encoding","identity")!="identity"):
            raise ControlError("company_request_rejected",403)

    def session(request):
        configured()
        try:return credentials.session(request.cookies.get(COOKIE))
        except Rejected as error:raise ControlError(error.code,error.status) from None

    def write(request):
        browser(request);token=session(request)
        csrf=request.headers.get("x-company-csrf","")
        expected=settings.digest("csrf",request.cookies[COOKIE])
        if not re_full_csrf(csrf) or not hmac.compare_digest(csrf,expected):
            raise ControlError("company_request_rejected",403)
        return token,hashlib.sha256(csrf.encode()).hexdigest()

    def risk_source(request):
        try:
            parsed=ip_address(address(request) if address is not None else None)
            if parsed.version==6 and parsed.ipv4_mapped:parsed=parsed.ipv4_mapped
            return str(ip_network(f'{parsed}/64',strict=False)) if parsed.version==6 else str(parsed)
        except (ValueError,TypeError):return 'unverified-shared-source'

    def issued_response(token,value):
        response=JSONResponse(value,headers=PRIVATE_HEADERS)
        response.set_cookie(COOKIE,token,max_age=28800,secure=True,httponly=True,samesite='strict',path='/')
        return response

    @routes.get("/company/booking-control")
    def page():
        source=(ASSETS/"control.html").read_text()
        source=source.replace("CLIENT_NAME",html.escape(label())).replace("PROJECT_NUMBER",html.escape(project_id()))
        return HTMLResponse(source,headers=PRIVATE_HEADERS)

    @routes.get("/api/company/assets/{name}")
    def asset(name:str):
        types={"control.js":"text/javascript","control.css":"text/css","command-journal.js":"text/javascript"}
        if name not in types:raise ControlError("company_page_unavailable",404)
        source=(ASSETS/name).read_bytes()
        if name=='command-journal.js':
            facts=installation()
            source=source.replace(b'/*COMPANY_BROWSER_CONFIGURATION*/null',canonical({
                'installation_id':facts['installation_id'],'environment':facts['environment']}))
        return Response(source,media_type=types[name],headers=PRIVATE_HEADERS)

    @routes.post('/api/company/login')
    @routes.post("/api/company/sign-in/start")
    def login(body:Login,request:Request):
        configured();browser(request)
        try:token,_=credentials.login(body.username,body.password,risk_source(request))
        except Rejected as error:raise ControlError(error.code,error.status) from None
        return issued_response(token,{'signed_in':True})

    @routes.post('/api/company/reauthenticate')
    def reauthenticate(body:PasswordConfirmation,request:Request):
        token,csrf=write(request)
        try:fresh,_=credentials.credential_action(token,csrf,body.password,risk_source(request))
        except Rejected as error:raise ControlError(error.code,error.status) from None
        return issued_response(fresh,{'confirmed':True})

    @routes.post('/api/company/password')
    def change_password(body:PasswordChange,request:Request):
        token,csrf=write(request)
        try:fresh,_=credentials.credential_action(token,csrf,body.password,risk_source(request),body.new_password)
        except Rejected as error:raise ControlError(error.code,error.status) from None
        return issued_response(fresh,{'changed':True})

    def ring():
        # Best effort: a lost ring never changes a company reply; the worker's own checks remain the safety net.
        if wake is None:return
        try:wake.publish()
        except Exception:pass

    @routes.get("/api/company/control/status")
    def status(request:Request):
        token=session(request);result=database.status(token)
        # The page's own 20-second re-checks send this header; they ring only when the change has just taken effect.
        automatic=request.headers.get("x-company-recheck")=="1"
        before=result.get("progress");unconfirmed=False
        # A switch change still on its way to the website is published again (the same fenced job as the change
        # route), so a lost publication cannot leave booking hidden while the page is open.
        if publisher is not None and before in PENDING:
            try:
                outcome=publisher()
                # The publisher reports an unanswered worker as a retry rather than an error.
                unconfirmed=isinstance(outcome,dict) and outcome.get("retry") is True
                result=database.status(token)
            except (ControlError,BudgetExpired):unconfirmed=True
        # Opening or refreshing this page nudges background work, also while booking is off and the timer sleeps.
        # While a republication is unconfirmed the same worker is unlikely to answer a ring, so the page is not held up.
        if not unconfirmed and (not automatic or (before in PENDING and result.get("progress")=="effective")):ring()
        result["csrf_token"]=settings.digest("csrf",request.cookies[COOKIE])
        return JSONResponse(result,headers=PRIVATE_HEADERS)

    @routes.get("/api/company/operations/incidents")
    def incidents(request:Request):
        return JSONResponse(database.incidents(session(request)),headers=PRIVATE_HEADERS)

    @routes.get('/api/company/records/status')
    def record_status(request:Request):
        return JSONResponse(database.call('SELECT appointment_system.company_sheet_status(%s)',
            (session(request),)),headers=PRIVATE_HEADERS)

    @routes.post('/api/company/records/recheck')
    def recheck_record(body:SheetReview,request:Request):
        token,csrf=write(request)
        if body.operation_id.int==0 or body.record_id.int==0 or int(body.sequence)>=9223372036854775807:
            raise ControlError('invalid_company_request',422)
        result=database.call('SELECT appointment_system.company_sheet_recheck(%s,%s,%s,%s,%s,%s,%s,%s)',
            (token,csrf,body.operation_id,body.role,body.record_kind,body.record_id,int(body.sequence),body.reason.strip()))
        ring()
        return JSONResponse(result,headers=PRIVATE_HEADERS)

    @routes.get('/api/company/settings')
    def business_settings(request:Request):
        return JSONResponse(database.call('SELECT appointment_system.company_business_settings(%s)',
            (session(request),)),headers=PRIVATE_HEADERS)

    @routes.post('/api/company/settings')
    def change_business(body:BusinessChange,request:Request):
        token,csrf=write(request)
        if body.operation_id.int==0 or int(body.revision)>=9223372036854775807:
            raise ControlError('invalid_company_request',422)
        from .settings import BusinessSettings,canonical_business_contacts
        try:spec=BusinessSettings.parse(canonical_business_contacts(body.settings)).document
        except Rejected as error:raise ControlError('invalid_company_request',422) from None
        result=database.call('SELECT appointment_system.company_save_business_settings(%s,%s,%s,%s,%s,%s)',
            (token,csrf,body.operation_id,int(body.revision),Jsonb(spec),body.reason.strip()))
        return JSONResponse(result,headers=PRIVATE_HEADERS)

    @routes.post("/api/company/control/change")
    def change(body:Command,request:Request):
        token,csrf=write(request)
        if int(body.revision)>9223372036854775807 or body.operation_id.int==0 or body.generation.int==0:
            raise ControlError("invalid_company_request",422)
        result=database.command(token,csrf,body.operation_id,body.generation,body.revision,body.enabled,body.reason.strip())
        expired=None
        if publisher is not None:
            try:publisher()
            except ControlError:pass
            except BudgetExpired as error:expired=error
            if expired is None:
                try:result=database.call("SELECT appointment_system.control_command_result(%s,%s)",(token,body.operation_id))
                except BudgetExpired as error:expired=error
        # Every accepted change rings: OFF starts its drain at once and ON resumes at once. A spent request budget
        # still answers as before (the saved change is checked again by the page), after the ring is tried.
        ring()
        if expired is not None:raise expired
        return JSONResponse(result,status_code=200 if result["progress"]=="effective" else 202,headers=PRIVATE_HEADERS)

    @routes.post('/api/company/logout')
    @routes.post("/api/company/sign-out")
    def logout(body:EmptyRequest,request:Request):
        token,_=write(request)
        database.call("SELECT appointment_system.control_session_end(%s)",(token,))
        response=JSONResponse({"signed_out":True},headers=PRIVATE_HEADERS)
        response.delete_cookie(COOKIE,secure=True,httponly=True,samesite="strict",path="/")
        return response

    @routes.post("/api/internal/service-control/publish")
    def publish(body:EmptyRequest,request:Request):
        valid=worker_key.accepts(request.headers) if hasattr(worker_key,"accepts") else False
        if valid is not True:raise ControlError("company_worker_unauthorized",401)
        configured()
        if publisher is None:raise ControlError("publication_configuration")
        return dict(application=project_id(),**publisher())

    return routes
