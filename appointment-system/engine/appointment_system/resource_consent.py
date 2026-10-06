"""Google callback stages permission; the initiating session alone installs it."""
import hashlib,hmac,secrets,re,html
from uuid import UUID,uuid4
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse,Response
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from psycopg.types.json import Jsonb
from .company_control import PRIVATE_HEADERS,re_full_csrf
from .company_auth import Credentials,COOKIE
from .service_control import ControlError
from .configuration import origin,label
from .google_oauth import Attempt,GoogleFailure,RESOURCE_ROLES
from .receipt_view import timestamp
from .studio import SESSION_COOKIE
from .serialization import fingerprint
from .company_control import ASSETS

CORRELATION='__Host-appointment-resource-consent'
class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    resource:Literal['calendar','client_sheet','agency_sheet']
class Finish(BaseModel):
    model_config=ConfigDict(extra='forbid')
    attempt_id:UUID
class OwnerLink(Start):
    operation_id:UUID
    reference:UUID
    reason:str=Field(min_length=5,max_length=300)
class OwnerAccess(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation_id:UUID
    secret:str=Field(pattern=r'^[a-f0-9]{64}$',repr=False)

def router(studio,company_settings,company_database,staff_store,limit):
    routes=APIRouter();resources=getattr(studio,'resources',None)
    def configured():
        if resources is None:raise ControlError('google_resource_setup_required',503)

    @routes.get('/company/google-repair')
    def owner_page():
        return HTMLResponse((ASSETS/'google-repair.html').read_text().replace('CLIENT_NAME',html.escape(label())),headers=PRIVATE_HEADERS)
    @routes.get('/api/company/google-repair.js')
    def owner_script():
        return Response((ASSETS/'google-repair.js').read_bytes(),media_type='text/javascript',headers=PRIVATE_HEADERS)
    def authority(request):return 'company' if request.url.path.startswith('/api/company/') else 'staff'
    def store(auth):
        selected=company_database if auth=='company' else staff_store
        if selected is None:raise ControlError('google_resource_setup_required',503)
        return selected
    def call(auth,sql,values=()):
        selected=store(auth)
        return selected.call(sql,values) if auth=='company' else selected._call(sql,values)
    def digest(purpose,value):
        if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}',value):raise ControlError('google_consent_unavailable',401)
        return resources.cipher.ring.digest('google-consent:'+purpose,value.encode())
    def parent(request):
        configured();auth=authority(request)
        if (request.headers.getlist('origin')!=[origin()] or request.headers.get('content-type','').split(';')[0]!='application/json'
            or request.headers.get('content-encoding','identity')!='identity'):raise ControlError('company_request_rejected',403)
        if auth=='company':
            if company_settings is None or company_database is None:raise ControlError('google_resource_setup_required',503)
            token=request.cookies.get(COOKIE);Credentials(company_database,company_settings).session(token)
            csrf=company_settings.digest('csrf',token)
            if not re_full_csrf(request.headers.get('x-company-csrf')) or not hmac.compare_digest(csrf,request.headers['x-company-csrf']):
                raise ControlError('company_request_rejected',403)
            return auth,company_settings.digest('session',token),hashlib.sha256(csrf.encode()).hexdigest()
        token=studio.digest('session',request.cookies.get(SESSION_COOKIE))
        # Staff consent has the same origin and opaque session checks as staff actions.
        return auth,token,None

    @routes.get('/api/company/resources/status')
    @routes.get('/api/studio/resources/status')
    def status(request:Request):
        configured();auth=authority(request)
        if auth=='company':
            if company_settings is None or company_database is None:raise ControlError('google_resource_setup_required',503)
            token=request.cookies.get(COOKIE);Credentials(company_database,company_settings).session(token)
            token=company_settings.digest('session',token)
        else:token=studio.digest('session',request.cookies.get(SESSION_COOKIE))
        result=call(auth,'SELECT appointment_system.resource_connection_status(%s,%s,%s)',(auth,token,studio.google.settings.client_id))
        pending=call(auth,'SELECT appointment_system.pending_resource_consents(%s)',(token,)) if auth=='company' else []
        return JSONResponse({'resources':result,'pending':pending},headers=PRIVATE_HEADERS)

    @routes.post('/api/company/resources/owner-link')
    def issue_owner_link(body:OwnerLink,request:Request):
        auth,token,csrf=parent(request)
        if body.operation_id.int==0 or body.reference.int==0:raise ControlError('google_consent_unavailable',422)
        secret=resources.cipher.ring.digest('google-consent:owner-link',str(body.operation_id).encode())
        access=resources.cipher.ring.digest('google-consent:owner-access',secret.encode())
        data=body.model_dump(mode='json');data['reason']=data['reason'].strip()
        result=call(auth,'SELECT appointment_system.issue_resource_owner_link(%s,%s,%s,%s,%s,%s,%s,%s)',
            (token,csrf,body.operation_id,body.resource,body.reference,data['reason'],access,fingerprint(data)))
        if result is None:raise ControlError('existing_obligation_required',409)
        return JSONResponse(result|{'owner_link':origin()+'/company/google-repair#link='+str(body.operation_id)+'.'+secret},headers=PRIVATE_HEADERS)

    @routes.post('/api/company/resources/owner-start')
    def owner_start(body:OwnerAccess,request:Request):
        configured()
        if request.headers.getlist('origin')!=[origin()] or request.headers.get('content-type','').split(';')[0]!='application/json':
            raise ControlError('company_request_rejected',403)
        limit(request,'studio')
        access=resources.cipher.ring.digest('google-consent:owner-access',body.secret.encode())
        context=call('company','SELECT appointment_system.owner_resource_link_context(%s,%s)',(body.operation_id,access))
        if context is None:raise ControlError('google_consent_unavailable',401)
        provider=resources.provider(context['resource'],client_id=context['client_id'])
        attempt=Attempt.new(RESOURCE_ROLES[context['resource']]);identifier=uuid4();browser=secrets.token_urlsafe(32)
        encrypted=resources.cipher.seal_attempt(identifier,context['resource'],context['client_id'],attempt)
        saved=call('company','SELECT appointment_system.start_owner_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',
          (body.operation_id,access,identifier,digest('state',attempt.state),digest('browser',browser),encrypted,uuid4(),context['client_id']))
        if saved is None:raise ControlError('google_consent_unavailable',401)
        response=JSONResponse({'authorization_url':provider.authorization_url(attempt)},headers=PRIVATE_HEADERS)
        response.set_cookie(CORRELATION,browser,max_age=600,secure=True,httponly=True,samesite='lax',path='/')
        return response

    @routes.post('/api/company/resources/workbook')
    def prepare(body:Start,request:Request):
        auth,token,csrf=parent(request)
        if body.resource not in ('client_sheet','agency_sheet'):raise ControlError('google_consent_unavailable',422)
        from .google_records import prepare_owner_workbook
        from .google_workspace import resource_id
        role=RESOURCE_ROLES[body.resource]
        from .storage import Store
        # The company database adapter exposes the same fixed Store operations.
        class CompanyStore:
            def _call(self,statement,parameters=(),**kwargs):
                return company_database.call(statement,parameters,resource_authority=(token,csrf,studio.google.settings.client_id,body.resource))
            claim_google_resource_refresh=Store.claim_google_resource_refresh
            finish_google_resource_refresh=Store.finish_google_resource_refresh
            claim_google_workbook=Store.claim_google_workbook
            begin_google_workbook_create=Store.begin_google_workbook_create
            finish_google_workbook=Store.finish_google_workbook
        _,saved=prepare_owner_workbook(CompanyStore(),studio,role)
        return JSONResponse({'workbook_url':'https://docs.google.com/spreadsheets/d/'+resource_id(saved['spreadsheet_id'])},headers=PRIVATE_HEADERS)

    @routes.post('/api/company/resources/start')
    @routes.post('/api/studio/resources/start')
    def start(body:Start,request:Request):
        auth,token,csrf=parent(request);limit(request,'studio');identifier=uuid4();grant_id=uuid4()
        provider=resources.provider(body.resource,callback='/api/'+('company' if auth=='company' else 'studio')+'/resources/callback')
        attempt=Attempt.new(RESOURCE_ROLES[body.resource]);browser=secrets.token_urlsafe(32)
        encrypted=resources.cipher.seal_attempt(identifier,body.resource,provider.settings.client_id,attempt)
        saved=call(auth,'SELECT appointment_system.start_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (auth,token,csrf,studio.google.settings.client_id,identifier,body.resource,digest('state',attempt.state),
             digest('browser',browser),encrypted,grant_id,provider.settings.client_id))
        if saved is None:raise ControlError('google_consent_unavailable',409)
        response=JSONResponse({'authorization_url':provider.authorization_url(attempt)},headers=PRIVATE_HEADERS)
        response.set_cookie(CORRELATION,browser,max_age=600,secure=True,httponly=True,samesite='lax',path='/')
        return response

    @routes.get('/api/company/resources/callback')
    @routes.get('/api/studio/resources/callback')
    def callback(request:Request):
        configured();auth=authority(request);q=request.query_params
        if (len(request.scope.get('query_string',b''))>8192 or set(q)-{'state','code','error','error_description','error_uri','scope','authuser','prompt','iss'}
            or any(len(q.getlist(k))>1 for k in q) or 'code' in q and 'error' in q or len(q.get('code',''))>4096):
            raise ControlError('google_consent_unavailable',401)
        state=q.get('state');state_digest=digest('state',state)
        saved=call(auth,'SELECT appointment_system.consume_resource_consent(%s,%s,%s)',
            (auth,state_digest,digest('browser',request.cookies.get(CORRELATION))))
        if saved is None:raise ControlError('google_consent_unavailable',401)
        outcome='failed'
        if q.get('code') and not q.get('error'):
            try:
                attempt=resources.cipher.open_attempt(saved,state)
                provider=resources.provider(saved['resource'],client_id=saved['client_id'],callback=request.url.path)
                access=provider.exchange(attempt,q['code'],now=timestamp(saved['server_now']),previous_subject=saved['previous_subject'])
                grant=access.grant
                encrypted=resources.cipher.seal(saved['grant_id'],saved['client_id'],grant)
                staged=call(auth,'SELECT appointment_system.stage_resource_consent(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (auth,saved['id'],state_digest,grant.subject,grant.email,encrypted,Jsonb(sorted(grant.scopes)),grant.refresh_expires_at))
                if staged is True:outcome='pending'
            except GoogleFailure:pass
        # No company or staff session is issued here, and no grant is installed.
        destination='/company/booking-control' if auth=='company' else '/studio'
        fragment='#google-consent='+saved['id']+'.'+outcome
        if saved.get('delegated') is True:destination='/company/google-repair';fragment='#approved='+outcome
        response=RedirectResponse(destination+fragment,303,headers=PRIVATE_HEADERS)
        response.delete_cookie(CORRELATION,secure=True,httponly=True,samesite='lax',path='/')
        return response

    @routes.post('/api/company/resources/finish')
    @routes.post('/api/studio/resources/finish')
    def finish(body:Finish,request:Request):
        auth,token,csrf=parent(request)
        if body.attempt_id.int==0:raise ControlError('google_consent_unavailable',422)
        result=call(auth,'SELECT appointment_system.finish_resource_consent(%s,%s,%s,%s)',(auth,token,csrf,body.attempt_id))
        return JSONResponse(result,headers=PRIVATE_HEADERS)
    return routes
