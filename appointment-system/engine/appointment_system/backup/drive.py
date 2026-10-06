"""Owner/folder-pinned Drive; the validator's actual OAuth scope is read-only."""
import hashlib
import json
import re
import time
from urllib.parse import urlsplit,parse_qs
import httpx
from .protocol import BackupError,Identity,MAX_BYTES,MAX_DOCUMENT,unique_json

API='https://www.googleapis.com/drive/v3/'
UPLOAD='https://www.googleapis.com/upload/drive/v3/files'
FIELDS='id,name,mimeType,parents,owners(emailAddress),trashed,properties,size,md5Checksum,version'
READ='https://www.googleapis.com/auth/drive.readonly'
WRITE='https://www.googleapis.com/auth/drive.file'
IDENTITY={'openid','https://www.googleapis.com/auth/userinfo.email','https://www.googleapis.com/auth/userinfo.profile'}

def file_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,180}',value):raise BackupError('backup_drive_identity_invalid')
    return value

def owned(record,owner):
    return (isinstance(record,dict) and record.get('trashed') is False
            and isinstance(record.get('owners'),list)
            and all(isinstance(o,dict) and isinstance(o.get('emailAddress'),str) for o in record['owners'])
            and [o.get('emailAddress','').lower() for o in record['owners']]==[owner])

def properties(identity,purpose,run,attempt):
    if (purpose not in ('encrypted-backup','backup-manifest','backup-restore-proof')
        or not isinstance(run,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',run)
        or not isinstance(attempt,str) or not re.fullmatch(r'[1-9][0-9]{0,3}',attempt)):raise BackupError('backup_drive_label_invalid')
    return {'bookingInstallation':identity.installation_id,'bookingProject':identity.project,'environment':identity.environment,'purpose':purpose,'protocolVersion':'1','sourceRun':run,'sourceAttempt':attempt}

def checked_name(identity,name,purpose,run,attempt):
    suffix={'encrypted-backup':'','backup-manifest':'.manifest.json','backup-restore-proof':'.restore.json'}.get(purpose)
    if suffix is None or not isinstance(name,str) or (suffix and not name.endswith(suffix)):raise BackupError('backup_drive_record_mismatch')
    archive=name[:-len(suffix)] if suffix else name
    if archive!='appointment-'+identity.installation_id+'-'+run+'-'+attempt+'.dump.age':raise BackupError('backup_drive_record_mismatch')
    return archive

class Drive:
    def __init__(self,identity,grant,folder,folder_name,*,reader=False,client=None):
        if not isinstance(identity,Identity):raise BackupError('backup_identity_invalid')
        identity.__post_init__()
        if type(folder_name) is not str or not 1<=len(folder_name)<=180:raise BackupError('backup_drive_folder_invalid')
        self.identity=identity
        self.reader=reader;self.folder=file_id(folder)
        self.client=client or httpx.Client(timeout=httpx.Timeout(20,connect=5),follow_redirects=False,trust_env=False)
        try:
            if type(reader) is not bool or not isinstance(grant,dict) or any(not isinstance(grant.get(k),str) or not 1<=len(grant[k])<=8192 for k in ('client_id','client_secret','refresh_token')):raise BackupError('backup_drive_grant_invalid')
            token=self.json('POST','https://oauth2.googleapis.com/token',data={**{k:grant[k] for k in ('client_id','client_secret','refresh_token')},'grant_type':'refresh_token'},authenticated=False,limit=8192)
            scopes=set(token.get('scope','').split());expected=READ if reader else WRITE
            if expected not in scopes or scopes-{expected}-IDENTITY:raise BackupError('backup_drive_scope_invalid')
            if not isinstance(token.get('access_token'),str) or not 1<=len(token['access_token'])<=8192:raise BackupError('backup_drive_token_invalid')
            self.headers={'Authorization':'Bearer '+token['access_token']}
            about=self.request('GET','about',params={'fields':'user(emailAddress),storageQuota'})
            if about.get('user',{}).get('emailAddress','').lower()!=self.identity.owner_email:raise BackupError('backup_drive_owner_mismatch')
            quota=about.get('storageQuota',{});self.available=int(quota['limit'])-int(quota['usage'])
            folder_record=self.request('GET','files/'+self.folder,params={'fields':FIELDS})
            if not owned(folder_record,self.identity.owner_email) or folder_record.get('mimeType')!='application/vnd.google-apps.folder' or folder_record.get('name')!=folder_name:raise BackupError('backup_drive_folder_mismatch')
            self.private(self.folder)
        except BackupError:self.client.close();raise
        except Exception:self.client.close();raise BackupError('backup_drive_unavailable') from None
    def close(self):self.client.close()
    def json(self,method,url,*,authenticated=True,limit=262144,**kwargs):
        try:
            started=time.monotonic()
            with self.client.stream(method,url,headers=self.headers if authenticated else {},**kwargs) as response:
                response.raise_for_status()
                if response.headers.get('content-type','').split(';')[0]!='application/json':raise ValueError()
                body=bytearray()
                for block in response.iter_bytes():
                    body.extend(block)
                    if len(body)>limit or time.monotonic()-started>30:raise ValueError()
                # Manifest parsing has the stricter independent64 KiB ceiling.
                if len(body)<=MAX_DOCUMENT:value=unique_json(bytes(body))
                else:
                    def pairs(items):
                        result={}
                        for k,v in items:
                            if k in result:raise ValueError()
                            result[k]=v
                        return result
                    value=json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                if not isinstance(value,dict):raise ValueError()
                return value
        except BackupError:raise
        except Exception:raise BackupError('backup_drive_request_failed') from None
    def request(self,method,path,**kwargs):
        if (type(path) is not str or len(path)>256 or not re.fullmatch(r'(?:about|files(?:/[A-Za-z0-9_-]{1,180}(?:/permissions)?)?)',path)):
            raise BackupError('backup_drive_path_invalid')
        if self.reader and method!='GET':raise BackupError('backup_validator_cannot_write')
        return self.json(method,API+path,**kwargs)
    def private(self,identity):
        value=self.request('GET','files/'+file_id(identity)+'/permissions',params={'fields':'permissions(type,role,emailAddress,deleted),nextPageToken','pageSize':100})
        permissions=value.get('permissions')
        if value.get('nextPageToken') or not isinstance(permissions,list) or len(permissions)!=1 or any(not isinstance(p,dict) or p.get('type')!='user' or p.get('role')!='owner' or not isinstance(p.get('emailAddress'),str) or p['emailAddress'].lower()!=self.identity.owner_email or p.get('deleted') is True for p in permissions):raise BackupError('backup_drive_shared_storage_rejected')
    def checked(self,record,*,purpose=None):
        if not owned(record,self.identity.owner_email) or record.get('parents')!=[self.folder] or record.get('mimeType')!='application/octet-stream' or not isinstance(record.get('properties'),dict):raise BackupError('backup_drive_record_mismatch')
        props=record['properties'];expected=properties(self.identity,purpose or props.get('purpose',''),props.get('sourceRun',''),props.get('sourceAttempt',''))
        if props!=expected:raise BackupError('backup_drive_record_mismatch')
        checked_name(self.identity,record.get('name'),expected['purpose'],expected['sourceRun'],expected['sourceAttempt'])
        if not isinstance(record.get('version'),str) or not re.fullmatch(r'[1-9][0-9]{0,19}',record['version']):raise BackupError('backup_drive_record_mismatch')
        file_id(record.get('id'));return record
    def files(self):
        records=[];page=None;seen=set();pages=set()
        for _ in range(20):
            params={'q':"trashed=false and '"+self.folder+"' in parents",'fields':'files('+FIELDS+'),nextPageToken','pageSize':100}
            if page:params['pageToken']=page
            value=self.request('GET','files',params=params)
            rows=value.get('files');page=value.get('nextPageToken')
            if not isinstance(rows,list) or len(rows)>100:raise BackupError('backup_drive_listing_invalid')
            for row in rows:
                if not isinstance(row,dict):raise BackupError('backup_drive_listing_invalid')
                identity=file_id(row.get('id'))
                if identity in seen:raise BackupError('backup_drive_listing_ambiguous')
                seen.add(identity);records.append(row)
            if not page:return records
            if not isinstance(page,str) or not 1<=len(page)<=2048:raise BackupError('backup_drive_listing_invalid')
            if page in pages:raise BackupError('backup_drive_listing_ambiguous')
            pages.add(page)
        raise BackupError('backup_drive_listing_limit')
    def find(self,purpose,run,attempt):
        labels=properties(self.identity,purpose,run,attempt)
        result=[r for r in self.files() if isinstance(r.get('properties'),dict) and all(r['properties'].get(k)==v for k,v in labels.items())]
        if len(result)>1:raise BackupError('backup_drive_run_ambiguous')
        return self.checked(result[0],purpose=purpose) if result else None
    def download(self,record,path,*,limit=MAX_BYTES):
        record=self.checked(record);self.private(record['id'])
        try:
            expected=int(record['size'])
            if not 0<expected<=limit:raise ValueError()
            total=0;digest=hashlib.md5(usedforsecurity=False);started=time.monotonic()
            with self.client.stream('GET',API+'files/'+record['id'],params={'alt':'media'},headers=self.headers) as response:
                response.raise_for_status()
                with path.open('xb') as output:
                    for block in response.iter_bytes(65536):
                        total+=len(block)
                        if total>expected or time.monotonic()-started>120:raise ValueError()
                        digest.update(block);output.write(block)
            if total!=expected or digest.hexdigest()!=record.get('md5Checksum'):raise ValueError()
        except Exception:raise BackupError('backup_drive_download_unverified') from None
    def upload(self,path,name,purpose,run,attempt):
        if self.reader:raise BackupError('backup_validator_cannot_write')
        checked_name(self.identity,name,purpose,run,attempt)
        labels=properties(self.identity,purpose,run,attempt);size=path.stat().st_size
        if not 0<size<=MAX_BYTES or self.available<size+10*1024*1024:raise BackupError('backup_drive_space_insufficient')
        generated=self.request('GET','files/generateIds',params={'count':1,'space':'drive'})
        if not isinstance(generated.get('ids'),list) or len(generated['ids'])!=1:raise BackupError('backup_drive_identity_invalid')
        identity=file_id(generated['ids'][0]);metadata={'id':identity,'name':name,'mimeType':'application/octet-stream','parents':[self.folder],'properties':labels}
        try:
            with self.client.stream('POST',UPLOAD,params={'uploadType':'resumable','fields':FIELDS},headers=self.headers|{'X-Upload-Content-Type':'application/octet-stream','X-Upload-Content-Length':str(size)},json=metadata) as response:
                response.raise_for_status();location=response.headers.get('location','')
            # Google owns the opaque session query (including fields/session_crd).
            # Restrict the HTTPS destination; preserve its issued query unchanged.
            url=urlsplit(location);query=parse_qs(url.query,keep_blank_values=True)
            if url.scheme!='https' or url.netloc!='www.googleapis.com' or url.path!='/upload/drive/v3/files' or url.fragment or query.get('uploadType')!=['resumable'] or len(query.get('upload_id',[]))!=1 or not query['upload_id'][0] or not 1<=len(location)<=8192:raise ValueError()
            with path.open('rb') as source:
                with self.client.stream('PUT',location,headers=self.headers|{'Content-Type':'application/octet-stream','Content-Length':str(size)},content=iter(lambda:source.read(65536),b''),timeout=120) as response:
                    response.raise_for_status()
        except Exception:
            # Exact generated identity is checked; no blind second create.
            try:record=self.request('GET','files/'+identity,params={'fields':FIELDS})
            except BackupError:raise BackupError('backup_drive_upload_pending') from None
        else:record=self.request('GET','files/'+identity,params={'fields':FIELDS})
        self.checked(record,purpose=purpose)
        digest=hashlib.md5(usedforsecurity=False)
        with path.open('rb') as source:
            for block in iter(lambda:source.read(65536),b''):digest.update(block)
        if record['id']!=identity or record['name']!=name or int(record.get('size','0'))!=size or record.get('md5Checksum')!=digest.hexdigest():raise BackupError('backup_drive_upload_unverified')
        self.private(identity);self.available-=size
        return record
    def remove(self,record):
        if self.reader:raise BackupError('backup_validator_cannot_write')
        record=self.checked(record);fresh=self.request('GET','files/'+record['id'],params={'fields':FIELDS})
        if self.checked(fresh).get('name')!=record['name'] or any(fresh.get(k)!=record.get(k) for k in ('properties','version','size','md5Checksum')):raise BackupError('backup_retention_record_changed')
        self.private(record['id'])
        try:
            with self.client.stream('DELETE',API+'files/'+record['id'],headers=self.headers) as response:
                if response.status_code==204:return
        except httpx.HTTPError:pass
        # An interrupted response is resolved against this exact identity.
        # A missing file is success; no other object is selected or deleted.
        try:
            with self.client.stream('GET',API+'files/'+record['id'],headers=self.headers,
                                    params={'fields':'id'}) as response:
                if response.status_code==404:return
        except httpx.HTTPError:pass
        raise BackupError('backup_retention_delete_failed')
