from appointment_system.configuration import configure
from .fixtures import installation,business
configure(installation(),business())
"""Captured Drive media/ETag traffic, no genuine OAuth grant or live traffic."""
import hashlib,json,unittest
import httpx
from appointment_system.privacy.ledger import PrivacyError,MAXIMUM
from appointment_system.privacy.store import DriveStore,properties,API

from types import SimpleNamespace
OWNER='practice@example.test';FOLDER_NAME='Example Practice privacy ledger'
FOLDER='synthetic-private-folder';HEAD='synthetic-private-head';PROBE='synthetic-private-probe';ENTRY='synthetic-private-entry'
class CapturedDrive:
 def __init__(self):
  self.identity=SimpleNamespace(owner_email=OWNER,installation_id=installation()['installation_id'],project=installation()['project_id'],environment=installation()['environment'])
  self.headers={'Authorization':'Bearer synthetic-token'};self.available=15000000000;self.reader=False;self.calls=[];self.ignore_match=False;self.lost_write=False;self.lost_create=False;self.transform=None;self.media_transform=None
  self.records={FOLDER:{'id':FOLDER,'name':FOLDER_NAME,'mimeType':'application/vnd.google-apps.folder','owners':[{'emailAddress':OWNER}],'trashed':False,'properties':properties('privacy-ledger-folder')}}
  self.data={};self.add(HEAD,'privacy-head','privacy-head-v1.enc',b'encrypted-head');self.add(PROBE,'privacy-cas-probe','privacy-cas-probe-v1.bin',b'harmless-probe')
  self.client=httpx.Client(transport=httpx.MockTransport(self.handler),follow_redirects=False,trust_env=False)
 def add(self,identity,purpose,name,data):
  self.data[identity]=data;self.records[identity]={'id':identity,'name':name,'mimeType':'application/octet-stream','parents':[FOLDER],'owners':[{'emailAddress':OWNER}],'trashed':False,'properties':properties(purpose),'version':'1','size':str(len(data)),'md5Checksum':hashlib.md5(data,usedforsecurity=False).hexdigest()}
 def update(self,identity,data):
  self.data[identity]=data;r=self.records[identity];r.update(version=str(int(r['version'])+1),size=str(len(data)),md5Checksum=hashlib.md5(data,usedforsecurity=False).hexdigest())
 def json(self,method,url,**kwargs):
  response=self.client.request(method,url,headers=self.headers,**kwargs);response.raise_for_status();return response.json()
 def private(self,identity):
  permissions=self.json('GET',API+'files/'+identity+'/permissions')
  if permissions!={'permissions':[{'type':'user','role':'owner','emailAddress':OWNER}]}:raise ValueError('Synthetic shared storage')
 def handler(self,request):
  self.calls.append(request);identity=request.url.path.split('/')[-1]
  if self.transform:
   result=self.transform(request)
   if result is not None:return result
  if request.url.path.endswith('/permissions'):return httpx.Response(200,json={'permissions':[{'type':'user','role':'owner','emailAddress':OWNER}]})
  if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':[ENTRY]})
  if request.method=='PUT':
   identity=request.url.path.split('/')[-1]
   token='"version-'+self.records[identity]['version']+'"'
   if not self.ignore_match and request.headers.get('If-Match')!=token:return httpx.Response(412)
   self.update(identity,request.read())
   if self.lost_write and identity==HEAD:raise httpx.ReadTimeout('Synthetic lost response',request=request)
   return httpx.Response(200,json={'id':identity})
  if request.method=='POST':
   content=request.read();metadata=json.loads(content.split(b'\r\n\r\n')[1].split(b'\r\n--')[0]);data=content.split(b'\r\n\r\n')[2].split(b'\r\n--')[0]
   self.add(metadata['id'],metadata['properties']['purpose'],metadata['name'],data)
   if self.lost_create:raise httpx.ReadTimeout('Synthetic lost upload response',request=request)
   return httpx.Response(200,json=self.records[metadata['id']])
  if identity not in self.records:return httpx.Response(404)
  if request.url.path.startswith('/drive/v2/'):
   return httpx.Response(200,json={'id':identity,'version':self.records[identity]['version'],'etag':'"version-'+self.records[identity]['version']+'"'})
  if request.url.params.get('alt')=='media':
   return self.media_transform(request) if self.media_transform else httpx.Response(200,content=self.data[identity])
  return httpx.Response(200,json=self.records[identity])

class StoreTests(unittest.TestCase):
 def setUp(self):self.drive=CapturedDrive();self.store=DriveStore(self.drive,FOLDER,HEAD,PROBE,folder_name=FOLDER_NAME)
 def tearDown(self):self.drive.client.close()
 def test_exact_owner_private_folder_head_and_entry_identity_checked(self):
  self.assertEqual(self.store.read_head()[0],b'encrypted-head');self.assertEqual(self.store.create_entry(b'encrypted-entry',1,'a'*64),ENTRY)
  self.assertEqual(self.store.read_entry(ENTRY),b'encrypted-entry')
  self.assertTrue(all(r.url.host=='www.googleapis.com' for r in self.drive.calls))
 def test_wrong_owner_folder_marker_name_or_identity_rejected_before_write(self):
  original=self.drive.records[FOLDER].copy()
  for change in ({'owners':[{'emailAddress':'foreign@example.com'}]},{'trashed':True},{'name':'Other folder'},{'id':'other-private-folder'},{'properties':properties('backup')},{'mimeType':'text/plain'}):
   self.drive.records[FOLDER]=original|change
   with self.assertRaises(PrivacyError):DriveStore(self.drive,FOLDER,HEAD,PROBE,folder_name=FOLDER_NAME)
  self.drive.records[FOLDER]=original
  for ids in ((FOLDER,HEAD,HEAD),('bad',HEAD,PROBE)):
   with self.assertRaises(PrivacyError):DriveStore(self.drive,*ids,folder_name=FOLDER_NAME)
 def test_shared_folder_and_changed_file_permissions_rejected(self):
  self.drive.transform=lambda r:httpx.Response(200,json={'permissions':[{'type':'anyone','role':'reader'}]}) if r.url.path.endswith('/permissions') else None
  with self.assertRaisesRegex(PrivacyError,'shared_storage'):self.store.read_head()
  with self.assertRaisesRegex(PrivacyError,'shared_storage'):DriveStore(self.drive,FOLDER,HEAD,PROBE,folder_name=FOLDER_NAME)
 def test_reader_cannot_create_probe_head_or_change_an_entry(self):
  self.drive.reader=True;reader=DriveStore(self.drive,FOLDER,HEAD,PROBE,reader=True,folder_name=FOLDER_NAME);before=len(self.drive.calls)
  for action in (lambda:reader.create_entry(b'x',1,'a'*64),lambda:reader.preflight(),lambda:reader.compare_and_swap_head('"version-1"',b'x'),lambda:reader.conditional_write(HEAD,'"version-1"',b'x')):
   with self.assertRaisesRegex(PrivacyError,'reader_cannot_write'):action()
  self.assertEqual(len(self.drive.calls),before)
  self.drive.reader=True
  with self.assertRaisesRegex(PrivacyError,'storage_authority'):DriveStore(self.drive,FOLDER,HEAD,PROBE,folder_name=FOLDER_NAME)
 def test_metadata_checksum_size_mime_labels_and_weak_version_are_strict(self):
  original=self.drive.records[HEAD].copy()
  for change in ({'parents':['different-folder']},{'mimeType':'text/plain'},{'properties':properties('other')},{'version':'0'},{'version':1},{'name':'other.enc'},{'id':PROBE},{'size':'0'},{'size':str(MAXIMUM+1)},{'md5Checksum':'a'*32}):
   self.drive.records[HEAD]=original|change
   with self.subTest(change=change),self.assertRaises(PrivacyError):self.store.read_head()
  self.drive.records[HEAD]=original
  for value in ({'id':HEAD,'version':'2','etag':'"v2"'},{'id':PROBE,'version':'1','etag':'"v1"'},{'id':HEAD,'version':'1','etag':'W/"weak"'},{'id':HEAD,'version':'1','etag':'unquoted'},{'id':HEAD,'version':'1','etag':'"valid"','extra':1}):
   self.drive.transform=lambda r:httpx.Response(200,json=value) if r.url.path.startswith('/drive/v2/') else None
   with self.assertRaises(PrivacyError):self.store.read_head()
 def test_media_bound_redirect_failure_and_postread_version_change_are_unconfirmed(self):
  for response in (httpx.Response(503),httpx.Response(302,headers={'location':'https://evil.example'}),httpx.Response(200,content=b'x'*(MAXIMUM+1)),httpx.Response(200,content=b'too short')):
   self.drive.media_transform=lambda r:response
   with self.assertRaisesRegex(PrivacyError,'readback_unconfirmed'):self.store.read_head()
  def change(r):
   original=self.drive.data[HEAD];self.drive.update(HEAD,b'changed-after-read');return httpx.Response(200,content=original)
  self.drive.media_transform=change
  with self.assertRaisesRegex(PrivacyError,'readback_unconfirmed'):self.store.read_head()
 def test_real_conditional_probe_proves_rejection_and_success_before_head_change(self):
  self.store.compare_and_swap_head('"version-1"',b'new-encrypted-head')
  writes=[r for r in self.drive.calls if r.method=='PUT'];self.assertEqual([r.url.path.split('/')[-1] for r in writes],[PROBE,PROBE,PROBE,HEAD])
  self.assertEqual(self.drive.data[HEAD],b'new-encrypted-head');self.assertTrue(self.store.checked_concurrency)
  with self.assertRaisesRegex(PrivacyError,'head_changed'):self.store.compare_and_swap_head('"version-1"',b'old-writer')
  self.assertEqual(self.drive.data[HEAD],b'new-encrypted-head')
 def test_provider_ignoring_conditions_fails_probe_without_touching_head(self):
  self.drive.ignore_match=True
  with self.assertRaisesRegex(PrivacyError,'compare_and_swap_unproved'):self.store.compare_and_swap_head('"version-1"',b'unsafe-head')
  self.assertEqual(self.drive.data[HEAD],b'encrypted-head');self.assertFalse(self.store.checked_concurrency)
  self.assertFalse(any(r.method=='PUT' and r.url.path.endswith(HEAD) for r in self.drive.calls))
 def test_busy_or_failed_probe_has_bounded_attempts(self):
  for status in (412,503):
   self.drive.transform=lambda r:httpx.Response(412 if r.headers.get('If-Match','').startswith('"'+('version-')) is False else status) if r.method=='PUT' else None
   with self.assertRaises(PrivacyError):self.store.preflight()
  self.assertFalse(self.store.checked_concurrency)
 def test_lost_head_reply_is_recovered_by_exact_saved_bytes(self):
  self.store.preflight();self.drive.lost_write=True;self.store.compare_and_swap_head('"version-1"',b'new-head');self.assertEqual(self.store.read_head()[0],b'new-head')
  self.drive.transform=lambda r:httpx.Response(503) if r.method=='PUT' else None
  with self.assertRaisesRegex(PrivacyError,'storage_unavailable'):self.store.compare_and_swap_head('"version-2"',b'different-head')
 def test_lost_entry_creation_readback_uses_preallocated_id_and_cannot_rewrite_entry(self):
  self.drive.lost_create=True;self.assertEqual(self.store.create_entry(b'ciphertext',1,'a'*64),ENTRY)
  self.assertEqual(sum(r.method=='POST' for r in self.drive.calls),1)
  with self.assertRaisesRegex(PrivacyError,'entry_is_immutable'):self.store.conditional_write(ENTRY,'"version-1"',b'rewritten')
  self.assertEqual(self.store.read_entry(ENTRY),b'ciphertext')
 def test_low_quota_bad_sequence_hash_and_malformed_generated_identity_never_authorize_entry(self):
  self.drive.available=1
  with self.assertRaisesRegex(PrivacyError,'capacity'):self.store.create_entry(b'encrypted',1,'a'*64)
  self.drive.available=15000000000
  for data,sequence,entry_hash in ((b'',1,'a'*64),(b'x',True,'a'*64),(b'x',0,'a'*64),(b'x',1,'invalid')):
   with self.assertRaises(PrivacyError):self.store.create_entry(data,sequence,entry_hash)
  for value in ({'ids':[]},{'ids':[HEAD,PROBE]},{'ids':['../elsewhere']}):
   self.drive.transform=lambda r:httpx.Response(200,json=value) if r.url.path.endswith('/generateIds') else None
   with self.assertRaises(PrivacyError):self.store.create_entry(b'encrypted',1,'a'*64)
 def test_create_failure_does_not_guess_or_make_another_file(self):
  self.drive.transform=lambda r:httpx.Response(503) if r.method=='POST' else None
  with self.assertRaises(PrivacyError):self.store.create_entry(b'encrypted',1,'a'*64)
  self.assertEqual(sum(r.method=='POST' for r in self.drive.calls),1);self.assertNotIn(ENTRY,self.drive.records)

if __name__=='__main__':unittest.main()
