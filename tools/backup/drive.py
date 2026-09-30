"""Project 004 backup storage owned by the approved Sarsa account. No sharing or deletion operations."""
import hashlib
import json
import re
from urllib.parse import urlsplit
import httpx
from envelope import BackupError

OWNER='sarsajyotish@gmail.com'
PROJECT='004-sarsa-jyotish-sansthan'
API='https://www.googleapis.com/drive/v3/'
FIELDS='id,name,mimeType,parents,owners(emailAddress),trashed,appProperties,size,md5Checksum'


def file_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,180}',value):
        raise BackupError('drive_identity_invalid')
    return value


def owned(record):
    return (record.get('trashed') is not True and
            [o.get('emailAddress','').lower() for o in record.get('owners',[])]==[OWNER])


class Drive:
    def __init__(self,grant,client=None):
        self.client=client or httpx.Client(timeout=60,follow_redirects=False)
        try:
            response=self.client.post('https://oauth2.googleapis.com/token',data={
                'grant_type':'refresh_token','client_id':grant['client_id'],
                'client_secret':grant['client_secret'],'refresh_token':grant['refresh_token']})
            response.raise_for_status()
            token=response.json()['access_token']
            if not isinstance(token,str) or not token:raise ValueError()
            self.headers={'Authorization':'Bearer '+token}
            about=self.request('GET','about',params={'fields':'user(emailAddress),storageQuota'})
            if about.get('user',{}).get('emailAddress','').lower()!=OWNER:
                raise BackupError('drive_owner_mismatch')
            quota=about.get('storageQuota',{})
            self.available=int(quota['limit'])-int(quota['usage'])
        except BackupError:
            self.client.close()
            raise
        except Exception:
            self.client.close()
            raise BackupError('drive_connection_unavailable') from None

    def close(self):self.client.close()

    def request(self,method,path,**kwargs):
        try:
            response=self.client.request(method,API+path,headers=self.headers,**kwargs)
            response.raise_for_status()
            value=response.json()
            if not isinstance(value,dict):raise ValueError()
            return value
        except Exception:raise BackupError('drive_request_failed') from None

    def folder(self):
        q="trashed=false and mimeType='application/vnd.google-apps.folder' and appProperties has { key='sarsaProject' and value='"+PROJECT+"' } and appProperties has { key='purpose' and value='encrypted-backups' }"
        result=self.request('GET','files',params={'q':q,'fields':'files('+FIELDS+'),nextPageToken','pageSize':100})
        files=result.get('files',[])
        if result.get('nextPageToken') or len(files)>1:raise BackupError('backup_folder_ambiguous')
        if files:
            folder=files[0]
        else:
            folder=self.request('POST','files',params={'fields':FIELDS},json={
                'name':'Sarsa Project 004 – Encrypted Backups','mimeType':'application/vnd.google-apps.folder',
                'appProperties':{'sarsaProject':PROJECT,'purpose':'encrypted-backups'}})
        if not owned(folder):raise BackupError('backup_folder_owner_mismatch')
        return file_id(folder.get('id'))

    def existing(self,folder,day):
        # Date is produced by the caller's UTC clock, never arbitrary query input.
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise BackupError('backup_day_invalid')
        q="trashed=false and '"+file_id(folder)+"' in parents and appProperties has { key='sarsaProject' and value='"+PROJECT+"' } and appProperties has { key='backupDay' and value='"+day+"' }"
        result=self.request('GET','files',params={'q':q,'fields':'files('+FIELDS+'),nextPageToken','pageSize':100})
        files=result.get('files',[])
        if result.get('nextPageToken') or len(files)>1:raise BackupError('daily_backup_ambiguous')
        if not files:return None
        record=files[0]
        if not owned(record) or folder not in record.get('parents',[]):raise BackupError('backup_owner_mismatch')
        file_id(record.get('id'))
        return record

    def download(self,record,destination):
        try:
            expected=int(record['size'])
            if not 0<expected<514*1024*1024:raise ValueError()
            total=0;digest=hashlib.md5(usedforsecurity=False)
            with self.client.stream('GET',API+'files/'+file_id(record['id']),params={'alt':'media'},headers=self.headers) as response:
                response.raise_for_status()
                with destination.open('xb') as output:
                    for block in response.iter_bytes(1024*1024):
                        total+=len(block)
                        if total>expected:raise ValueError()
                        output.write(block);digest.update(block)
            if total!=expected or digest.hexdigest()!=record['md5Checksum']:raise ValueError()
        except Exception:raise BackupError('backup_download_unverified') from None

    def upload(self,path,folder,day):
        size=path.stat().st_size
        if self.available<size+10*1024*1024:raise BackupError('drive_space_insufficient')
        identity=self.request('GET','files/generateIds',params={'count':1,'space':'drive'})
        identity=file_id(identity['ids'][0])
        digest=hashlib.md5(usedforsecurity=False)
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        metadata={'id':identity,'name':f'sarsa-004-{day}.pgdump.aesgcm','mimeType':'application/octet-stream',
            'parents':[file_id(folder)],'appProperties':{'sarsaProject':PROJECT,'backupDay':day,'format':'aes256gcm-v1'}}
        try:
            response=self.client.post('https://www.googleapis.com/upload/drive/v3/files',
                params={'uploadType':'resumable','fields':FIELDS},headers={**self.headers,
                    'X-Upload-Content-Type':'application/octet-stream','X-Upload-Content-Length':str(size)},json=metadata)
            response.raise_for_status()
            location=response.headers['location'];url=urlsplit(location)
            if url.scheme!='https' or url.netloc!='www.googleapis.com' or not url.path.startswith('/upload/drive/v3/files'):
                raise BackupError('drive_upload_location_invalid')
            with path.open('rb') as stream:
                try:
                    sent=self.client.put(location,headers={**self.headers,'Content-Length':str(size),'Content-Type':'application/octet-stream'},content=stream,timeout=180)
                    sent.raise_for_status()
                except httpx.HTTPError:
                    # An uncertain upload is resolved by its preallocated ID;
                    # never create another file to handle a lost response.
                    pass
            record=self.request('GET','files/'+identity,params={'fields':FIELDS})
            if (not owned(record) or str(record.get('size'))!=str(size)
                    or record.get('md5Checksum')!=digest.hexdigest() or folder not in record.get('parents',[])):
                raise BackupError('drive_upload_unverified')
            return record
        except BackupError:raise
        except Exception:raise BackupError('drive_upload_failed') from None
