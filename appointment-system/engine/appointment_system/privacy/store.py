"""Inspected foundation SHA256: 92b73a251a59b7811bb4742f1b5788749c4a15c28f4ca07b4f406e999fd6f1bb."""
"""Private Drive ledger storage with a separate harmless conditional-write probe.

CAS support is measured on the probe before any head write. An unsupported
provider never authorizes content erasure. No backup archive is changed here.
"""
import hashlib,re,secrets,time
import httpx
from .ledger import PrivacyError,PROJECT,MAXIMUM,canonical,checked_id,checked_hash

API='https://www.googleapis.com/drive/v3/'
V2='https://www.googleapis.com/drive/v2/'
UPLOAD='https://www.googleapis.com/upload/drive/'
from ..configuration import installation
FACTS=installation();INSTALLATION=FACTS['installation_id']
FIELDS='id,name,mimeType,parents,owners(emailAddress),trashed,properties,size,md5Checksum,version'

def etag(value):
 if not isinstance(value,str) or not re.fullmatch(r'"[!#-~]{1,176}"',value):raise PrivacyError('privacy_conditional_version_invalid')
 return value

def properties(purpose):return {'bookingInstallation':INSTALLATION,'bookingProject':PROJECT,'environment':FACTS['environment'],'purpose':purpose,'ledgerVersion':'1'}

class DriveStore:
 def __init__(self,drive,folder,head,probe,*,folder_name,reader=False):
  self.owner=drive.identity.owner_email
  if drive.identity.installation_id!=INSTALLATION or drive.identity.project!=PROJECT or drive.identity.environment!=FACTS['environment'] or drive.reader is not reader:raise PrivacyError('privacy_storage_authority_invalid')
  if type(folder_name) is not str or not 1<=len(folder_name)<=180:raise PrivacyError('privacy_folder_invalid')
  self.drive=drive;self.folder=checked_id(folder);self.head=checked_id(head);self.probe=checked_id(probe)
  self.reader=reader;self.checked_concurrency=False
  if type(reader) is not bool or len({folder,head,probe})!=3:raise PrivacyError('privacy_storage_identity_invalid')
  if not reader and getattr(drive,'reader',False):raise PrivacyError('privacy_reader_cannot_write')
  record=self.json('GET',API+'files/'+self.folder,params={'fields':FIELDS})
  self.owned(record)
  if record.get('id')!=self.folder or record.get('name')!=folder_name or record.get('mimeType')!='application/vnd.google-apps.folder' or record.get('properties')!=properties('privacy-ledger-folder'):raise PrivacyError('privacy_folder_invalid')
  self.private(self.folder)
 def json(self,method,url,**kwargs):
  try:return self.drive.json(method,url,**kwargs)
  except Exception:raise PrivacyError('privacy_storage_unavailable') from None
 def private(self,identity):
  try:self.drive.private(checked_id(identity))
  except Exception:raise PrivacyError('privacy_shared_storage_rejected') from None
 def owned(self,record):
  if (not isinstance(record,dict) or record.get('trashed') is not False or not isinstance(record.get('owners'),list)
      or any(not isinstance(o,dict) for o in record['owners'])
      or [o.get('emailAddress','').lower() for o in record['owners']]!=[self.owner]):raise PrivacyError('privacy_owner_invalid')
 def metadata(self,identity,purpose):
  identity=checked_id(identity);record=self.json('GET',API+'files/'+identity,params={'fields':FIELDS});self.owned(record);self.private(identity)
  if (record.get('id')!=identity or record.get('parents')!=[self.folder] or record.get('properties')!=properties(purpose)
      or record.get('mimeType')!='application/octet-stream' or not isinstance(record.get('version'),str)
      or not re.fullmatch(r'[1-9][0-9]{0,19}',record['version'])):raise PrivacyError('privacy_storage_identity_invalid')
  names={'privacy-head':'privacy-head-v1.enc','privacy-cas-probe':'privacy-cas-probe-v1.bin'}
  if purpose in names and record.get('name')!=names[purpose]:raise PrivacyError('privacy_storage_identity_invalid')
  if purpose=='privacy-entry' and (not isinstance(record.get('name'),str) or not re.fullmatch(r'privacy-entry-[1-9][0-9]{0,18}-[a-f0-9]{64}\.enc',record['name'])):raise PrivacyError('privacy_storage_identity_invalid')
  return record
 def read(self,identity,purpose):
  record=self.metadata(identity,purpose)
  version=self.json('GET',V2+'files/'+checked_id(identity),params={'fields':'id,etag,version'})
  if set(version)!={'id','etag','version'} or version['id']!=identity or version['version']!=record['version']:raise PrivacyError('privacy_storage_changed')
  token=etag(version['etag'])
  try:
   size=int(record.get('size','0'))
   if not 0<size<=MAXIMUM:raise ValueError()
   body=bytearray();started=time.monotonic()
   with self.drive.client.stream('GET',API+'files/'+identity,params={'alt':'media'},headers=self.drive.headers,timeout=8,follow_redirects=False) as response:
    response.raise_for_status()
    for block in response.iter_bytes():
     body.extend(block)
     if len(body)>size or time.monotonic()-started>10:raise ValueError()
   if len(body)!=size or hashlib.md5(body,usedforsecurity=False).hexdigest()!=record.get('md5Checksum'):raise ValueError()
   if self.metadata(identity,purpose)!=record:raise ValueError()
   return bytes(body),token
  except Exception:raise PrivacyError('privacy_readback_unconfirmed') from None
 def read_head(self):return self.read(self.head,'privacy-head')
 def read_entry(self,identity):return self.read(checked_id(identity),'privacy-entry')[0]
 def conditional_write(self,identity,token,data):
  if self.reader:raise PrivacyError('privacy_reader_cannot_write')
  checked_id(identity);etag(token)
  if identity not in (self.head,self.probe):raise PrivacyError('privacy_entry_is_immutable')
  if not isinstance(data,bytes) or not 0<len(data)<=MAXIMUM:raise PrivacyError('privacy_document_limit')
  try:
   with self.drive.client.stream('PUT',UPLOAD+'v2/files/'+identity,params={'uploadType':'media'},headers=self.drive.headers|{'Content-Type':'application/octet-stream','If-Match':token},content=data,timeout=8,follow_redirects=False) as response:return response.status_code
  except httpx.HTTPError:raise PrivacyError('privacy_write_uncertain') from None
 def preflight(self):
  if self.reader:raise PrivacyError('privacy_reader_cannot_write')
  for _ in range(3):
   _,original=self.read(self.probe,'privacy-cas-probe')
   candidate=canonical({'installation_id':INSTALLATION,'project':PROJECT,'purpose':'privacy-cas-probe','nonce':secrets.token_hex(16)})
   wrong='"'+secrets.token_hex(32)+'"'
   if self.conditional_write(self.probe,wrong,candidate)!=412:raise PrivacyError('privacy_compare_and_swap_unproved')
   status=self.conditional_write(self.probe,original,candidate)
   if status==412:continue
   if status!=200:raise PrivacyError('privacy_compare_and_swap_unproved')
   confirmed,current=self.read(self.probe,'privacy-cas-probe')
   if confirmed!=candidate or current==original:raise PrivacyError('privacy_compare_and_swap_unproved')
   if self.conditional_write(self.probe,original,candidate)!=412:raise PrivacyError('privacy_compare_and_swap_unproved')
   self.checked_concurrency=True;return
  raise PrivacyError('privacy_head_busy')
 def compare_and_swap_head(self,version,data):
  if self.reader:raise PrivacyError('privacy_reader_cannot_write')
  if not self.checked_concurrency:self.preflight()
  self.metadata(self.head,'privacy-head')
  try:status=self.conditional_write(self.head,version,data)
  except PrivacyError as error:
   if str(error)!='privacy_write_uncertain':raise
   status=None
  if status==412:raise PrivacyError('privacy_head_changed')
  if status not in (None,200):raise PrivacyError('privacy_storage_unavailable')
  # Resolve a lost acknowledgement by this exact head; caller checks linked
  # history if another legitimate writer has moved it forward meanwhile.
  confirmed,_=self.read_head()
  if confirmed!=data:raise PrivacyError('privacy_head_changed')
 def create_entry(self,data,sequence,entry_hash):
  if self.reader:raise PrivacyError('privacy_reader_cannot_write')
  if not isinstance(data,bytes) or not 0<len(data)<=MAXIMUM or type(sequence) is not int or not 1<=sequence<=9223372036854775807:raise PrivacyError('privacy_document_limit')
  checked_hash(entry_hash)
  if self.drive.available<len(data)+1024*1024:raise PrivacyError('privacy_storage_capacity')
  generated=self.json('GET',API+'files/generateIds',params={'count':1,'space':'drive'})
  if not isinstance(generated.get('ids'),list) or len(generated['ids'])!=1:raise PrivacyError('privacy_storage_identity_invalid')
  identity=checked_id(generated['ids'][0]);name=f'privacy-entry-{sequence}-{entry_hash}.enc'
  metadata={'id':identity,'name':name,'mimeType':'application/octet-stream','parents':[self.folder],'properties':properties('privacy-entry')}
  boundary='privacy-'+secrets.token_hex(16)
  content=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+canonical(metadata)+f'\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
  try:
   with self.drive.client.stream('POST',UPLOAD+'v3/files',params={'uploadType':'multipart','fields':FIELDS},headers=self.drive.headers|{'Content-Type':'multipart/related; boundary='+boundary},content=content,timeout=8,follow_redirects=False) as response:
    response.raise_for_status()
  except httpx.HTTPError:pass
  # A failed/lost creation has only its preallocated identity. No blind retry.
  record=self.metadata(identity,'privacy-entry')
  if record['name']!=name or self.read_entry(identity)!=data:raise PrivacyError('privacy_entry_unconfirmed')
  self.drive.available-=len(data);return identity
