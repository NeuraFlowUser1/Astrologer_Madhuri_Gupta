"""Capture real adapter requests using synthetic HTTP, including OAuth scopes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import httpx
from appointment_system.backup.drive import Drive,READ,WRITE,API,file_id,checked_name
from appointment_system.backup.protocol import BackupError
from .backup_fixtures import record,manifest,OWNER,SCOPE,FOLDER_NAME

class DriveTests(unittest.TestCase):
    def connect(self,*,reader=False,scope=None,owner=OWNER,handler=None,permission=None):
        calls=[];name=manifest()['archive_name']
        archive=record(name,'encrypted-backup')
        folder={'id':'synthetic-folder','name':FOLDER_NAME,
            'mimeType':'application/vnd.google-apps.folder','owners':[{'emailAddress':OWNER}],'trashed':False}
        def request(r):
            calls.append(r)
            if r.url.host=='oauth2.googleapis.com':
                return httpx.Response(200,json={'access_token':'synthetic-access','scope':scope if scope is not None else READ if reader else WRITE})
            if r.url.path.endswith('/about'):return httpx.Response(200,json={'user':{'emailAddress':owner},'storageQuota':{'limit':'15000000000','usage':'0'}})
            if r.url.path.endswith('/permissions'):
                return httpx.Response(200,json=permission or {'permissions':[{'type':'user','role':'owner','emailAddress':OWNER}]})
            if str(r.url).startswith(API+'files/synthetic-folder'):
                return httpx.Response(200,json=folder)
            return handler(r,archive) if handler else httpx.Response(200,json={'files':[archive]})
        grant={'client_id':'synthetic-id','client_secret':'synthetic-secret','refresh_token':'synthetic-refresh'}
        client=httpx.Client(transport=httpx.MockTransport(request),follow_redirects=False)
        return Drive(SCOPE,grant,'synthetic-folder',FOLDER_NAME,reader=reader,client=client),calls,archive
    def test_validator_requires_actual_readonly_scope_and_never_sends_writes(self):
        store,calls,_=self.connect(reader=True)
        try:
            self.assertIsNotNone(store.find('encrypted-backup','1','1'))
            before=len(calls)
            for operation in ('POST','PATCH','DELETE'):
                with self.assertRaisesRegex(BackupError,'cannot_write'):store.request(operation,'files')
            with self.assertRaises(BackupError):store.upload(Path('never-opened'),'bad','encrypted-backup','1','1')
            with self.assertRaises(BackupError):store.remove({})
            self.assertEqual(len(calls),before)
        finally:store.close()
        for scope in ('',WRITE,READ+' '+WRITE,READ+' https://www.googleapis.com/auth/drive'):
            with self.subTest(scope=scope),self.assertRaisesRegex(BackupError,'scope_invalid'):
                self.connect(reader=True,scope=scope)
    def test_wrong_owner_public_sharing_and_ambiguous_folder_fail(self):
        with self.assertRaisesRegex(BackupError,'owner_mismatch'):self.connect(owner='foreign@example.invalid')
        for permission in ({'permissions':[{'type':'anyone','role':'reader'}]},
            {'permissions':[{'type':'user','role':'owner','emailAddress':OWNER}],'nextPageToken':'more'}):
            with self.assertRaisesRegex(BackupError,'shared_storage'):self.connect(permission=permission)
    def test_labels_match_actual_purpose_filename_owner_and_run(self):
        store,_,archive=self.connect()
        try:
            self.assertEqual(store.checked(archive),archive)
            for change in ({'name':archive['name']+'.manifest.json'},{'parents':['foreign-folder']},
                {'version':True},{'owners':[{'emailAddress':'foreign@example.invalid'}]},
                {'properties':dict(archive['properties'],sourceRun='2')},{'mimeType':'text/html'}):
                with self.subTest(change=change),self.assertRaises(BackupError):store.checked(dict(archive,**change))
        finally:store.close()
        for identity in ('',None,'bad/id','x'*181):
            with self.assertRaises(BackupError):file_id(identity)
    def test_listing_rejects_duplicates_nonobjects_and_more_than_twenty_pages(self):
        for handler,code in [(lambda r,a:httpx.Response(200,json={'files':[a,a]}),'ambiguous'),
            (lambda r,a:httpx.Response(200,json={'files':None}),'listing_invalid'),
            (lambda r,a:httpx.Response(200,json={'files':[],'nextPageToken':True}),'listing_invalid'),
            (lambda r,a:httpx.Response(200,json={'files':[],'nextPageToken':'repeat'}),'listing_ambiguous')]:
            store,_,_=self.connect(handler=handler)
            try:
                with self.assertRaisesRegex(BackupError,code):store.files()
            finally:store.close()
    def test_google_json_metadata_is_allowed_only_for_signed_record_documents(self):
        store,_,archive=self.connect()
        try:
            for purpose,suffix in (('backup-manifest','.manifest.json'),('backup-restore-proof','.restore.json')):
                item=record(archive['name']+suffix,purpose)
                for mime in ('application/json','application/octet-stream'):
                    self.assertEqual(store.checked(dict(item,mimeType=mime)),dict(item,mimeType=mime))
                for mime in ('text/html','text/plain','application/vnd.google-apps.document',None,[]):
                    with self.subTest(purpose=purpose,mime=mime),self.assertRaisesRegex(BackupError,'record_mismatch'):
                        store.checked(dict(item,mimeType=mime))
                with self.assertRaises(BackupError):store.checked(dict(item,mimeType='application/json'),purpose='encrypted-backup')
            with self.assertRaisesRegex(BackupError,'record_mismatch'):
                store.checked(dict(archive,mimeType='application/json'))
        finally:store.close()
    def test_document_upload_declares_json_consistently_and_verifies_real_metadata(self):
        for purpose,suffix in (('backup-manifest','.manifest.json'),('backup-restore-proof','.restore.json')):
            name=manifest()['archive_name']+suffix;content=b'{"synthetic":"signed-envelope"}'
            saved=dict(record(name,purpose,identity='generated-document-123',body=content),mimeType='application/json')
            def handler(request,archive):
                if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':[saved['id']]})
                if request.method=='POST':
                    self.assertEqual(json.loads(request.read())['mimeType'],'application/json')
                    self.assertEqual(request.headers['X-Upload-Content-Type'],'application/json')
                    return httpx.Response(200,headers={'location':'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic'})
                if request.method=='PUT':
                    self.assertEqual(request.headers['Content-Type'],'application/json')
                    self.assertEqual(request.read(),content)
                    return httpx.Response(200)
                return httpx.Response(200,json=saved)
            store,calls,_=self.connect(handler=handler)
            try:
                with tempfile.TemporaryDirectory() as scratch:
                    path=Path(scratch)/'record.json';path.write_bytes(content)
                    self.assertEqual(store.upload(path,name,purpose,'1','1'),saved)
                self.assertEqual(sum(request.method=='PUT' for request in calls),1)
            finally:store.close()
    def test_download_checks_bytes_checksum_private_owner_and_size_limit(self):
        def handler(r,a):
            return httpx.Response(200,content=b'synthetic-ciphertext'+(b'excess' if mode=='excess' else b''))
        for mode in ('correct','excess'):
            store,_,archive=self.connect(handler=handler)
            try:
                with tempfile.TemporaryDirectory() as scratch:
                    destination=Path(scratch)/'download'
                    if mode=='correct':
                        store.download(archive,destination);self.assertEqual(destination.read_bytes(),b'synthetic-ciphertext')
                    else:
                        with self.assertRaisesRegex(BackupError,'download_unverified'):store.download(archive,destination)
                    with self.assertRaises(BackupError):store.download(dict(archive,size='0'),Path(scratch)/'wrong')
            finally:store.close()
    def test_lost_upload_response_resolves_exact_generated_id_and_never_creates_twice(self):
        name=manifest()['archive_name'];saved=record(name,'encrypted-backup',identity='generated-file-123')
        def handler(r,a):
            if r.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':[saved['id']]})
            if r.method=='POST':return httpx.Response(200,headers={'location':'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic'})
            if r.method=='PUT':raise httpx.ReadTimeout('synthetic lost response',request=r)
            return httpx.Response(200,json=saved)
        store,calls,_=self.connect(handler=handler)
        try:
            with tempfile.TemporaryDirectory() as scratch:
                path=Path(scratch)/'encrypted';path.write_bytes(b'synthetic-ciphertext')
                self.assertEqual(store.upload(path,name,'encrypted-backup','1','1')['id'],saved['id'])
            self.assertEqual(sum(r.method=='PUT' for r in calls),1)
            self.assertEqual(sum(r.method=='POST' and r.url.host=='www.googleapis.com' for r in calls),1)
        finally:store.close()
    def test_foreign_upload_location_receives_no_secret_and_no_followup(self):
        def handler(r,a):
            if r.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':['generated-file-123']})
            if r.method=='POST':return httpx.Response(200,headers={'location':'https://foreign.invalid/upload'})
            return httpx.Response(404,json={})
        store,calls,_=self.connect(handler=handler)
        try:
            with tempfile.TemporaryDirectory() as scratch:
                path=Path(scratch)/'encrypted';path.write_bytes(b'synthetic-ciphertext')
                with self.assertRaises(BackupError):store.upload(path,manifest()['archive_name'],'encrypted-backup','1','1')
            self.assertFalse(any(r.url.host=='foreign.invalid' or r.method=='PUT' for r in calls))
        finally:store.close()
    def test_google_issued_opaque_session_parameters_are_preserved_during_upload(self):
        name=manifest()['archive_name'];saved=record(name,'encrypted-backup',identity='generated-file-123')
        location='https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic&fields=id%2Cname&session_crd=synthetic-session%2Fopaque'
        def handler(request,archive):
            if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':[saved['id']]})
            if request.method=='POST':return httpx.Response(200,headers={'location':location})
            if request.method=='PUT':
                self.assertEqual(str(request.url),location)
                self.assertEqual(request.read(),b'synthetic-ciphertext')
                self.assertEqual(request.headers['content-length'],str(len(b'synthetic-ciphertext')))
                return httpx.Response(200)
            return httpx.Response(200,json=saved)
        store,calls,_=self.connect(handler=handler)
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'encrypted';path.write_bytes(b'synthetic-ciphertext')
                self.assertEqual(store.upload(path,name,'encrypted-backup','1','1'),saved)
            self.assertEqual(sum(r.method=='PUT' for r in calls),1)
        finally:store.close()

    def test_unsafe_or_ambiguous_session_addresses_never_receive_upload_data(self):
        base='https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic'
        locations=(base.replace('https:','http:'),base.replace('www.googleapis.com','foreign.invalid'),
            base.replace('www.googleapis.com','user:password@www.googleapis.com'),
            base.replace('www.googleapis.com','www.googleapis.com:443'),base.replace('/upload/drive/v3/files','/other'),
            base+'#fragment',base.replace('resumable','media'),base+'&upload_id=second',
            base.replace('upload_id=synthetic','upload_id='),base+'&opaque='+'x'*8192)
        for location in locations:
            with self.subTest(location=location[:100]):
                def handler(request,archive):
                    if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':['generated-file-123']})
                    if request.method=='POST':return httpx.Response(200,headers={'location':location})
                    return httpx.Response(404,json={})
                store,calls,_=self.connect(handler=handler)
                try:
                    with tempfile.TemporaryDirectory() as directory:
                        path=Path(directory)/'encrypted';path.write_bytes(b'synthetic-ciphertext')
                        with self.assertRaisesRegex(BackupError,'upload_pending'):
                            store.upload(path,manifest()['archive_name'],'encrypted-backup','1','1')
                    self.assertFalse(any(r.method=='PUT' for r in calls))
                finally:store.close()

    def test_retention_rechecks_exact_unchanged_version_before_delete(self):
        for mode in ('unchanged','changed'):
            def handler(r,a):
                if r.method=='DELETE':return httpx.Response(204)
                return httpx.Response(200,json=dict(a,version='2') if mode=='changed' else a)
            store,calls,archive=self.connect(handler=handler)
            try:
                if mode=='unchanged':
                    store.remove(archive);self.assertTrue(any(r.method=='DELETE' for r in calls))
                else:
                    with self.assertRaisesRegex(BackupError,'record_changed'):store.remove(archive)
                    self.assertFalse(any(r.method=='DELETE' for r in calls))
            finally:store.close()
    def test_bad_json_response_path_and_space_fail_closed(self):
        store,_,_=self.connect(handler=lambda r,a:httpx.Response(200,content=b'{"x":1,"x":2}',headers={'content-type':'application/json'}))
        try:
            with self.assertRaises(BackupError):store.request('GET','files')
            with self.assertRaises(BackupError):store.request('GET','../files')
            with tempfile.TemporaryDirectory() as scratch:
                path=Path(scratch)/'encrypted';path.write_bytes(b'synthetic-ciphertext');store.available=0
                with self.assertRaisesRegex(BackupError,'space_insufficient'):
                    store.upload(path,manifest()['archive_name'],'encrypted-backup','1','1')
        finally:store.close()

    def test_lost_delete_response_is_resolved_by_exact_missing_identity(self):
        deleted=False
        def handler(r,a):
            nonlocal deleted
            if r.method=='DELETE':
                deleted=True;raise httpx.ReadTimeout('synthetic lost delete reply',request=r)
            return httpx.Response(404,json={}) if deleted else httpx.Response(200,json=a)
        store,calls,archive=self.connect(handler=handler)
        try:
            store.remove(archive)
            self.assertEqual(sum(r.method=='DELETE' for r in calls),1)
            self.assertTrue(all(r.url.path.endswith('/'+archive['id']) for r in calls if r.method=='DELETE'))
        finally:store.close()
    def test_failed_delete_keeps_exact_archive_and_is_not_reported_successful(self):
        def handler(r,a):return httpx.Response(503,json={}) if r.method=='DELETE' else httpx.Response(200,json=a)
        store,calls,archive=self.connect(handler=handler)
        try:
            with self.assertRaisesRegex(BackupError,'delete_failed'):store.remove(archive)
            self.assertEqual(sum(r.method=='DELETE' for r in calls),1)
        finally:store.close()

if __name__=='__main__':unittest.main()
