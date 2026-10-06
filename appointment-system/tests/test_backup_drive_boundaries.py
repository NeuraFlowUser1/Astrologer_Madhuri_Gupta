"""Real Drive adapter with bounded synthetic HTTP; never an external account."""
import json
from pathlib import Path
import tempfile
import unittest
import httpx
from appointment_system.backup.drive import Drive,WRITE,properties,checked_name
from appointment_system.backup.protocol import BackupError
from . import test_backup_drive as drive_tests
from .backup_fixtures import SCOPE,OWNER,FOLDER_NAME,record,manifest


class DriveBoundaries(unittest.TestCase):
    connect=drive_tests.DriveTests.connect

    def test_setup_refuses_wrong_identity_missing_grant_token_owner_quota_and_folder(self):
        grant={'client_id':'fixture','client_secret':'fixture','refresh_token':'fixture'}
        def create(*,identity=SCOPE,secret=grant,reader=False,token=None,about=None,folder=None):
            def handler(request):
                if request.url.host=='oauth2.googleapis.com':return httpx.Response(200,json=token if token is not None else {'access_token':'synthetic','scope':WRITE})
                if request.url.path.endswith('/about'):return httpx.Response(200,json=about if about is not None else {'user':{'emailAddress':OWNER},'storageQuota':{'limit':'999999','usage':'0'}})
                return httpx.Response(200,json=folder if folder is not None else {})
            client=httpx.Client(transport=httpx.MockTransport(handler))
            try:
                with self.assertRaises(BackupError):Drive(identity,secret,'synthetic-folder',FOLDER_NAME,reader=reader,client=client)
            finally:client.close()
        for arguments in ({'identity':None},{'secret':{}},{'reader':1},{'token':{'scope':WRITE}},
            {'token':{'scope':WRITE,'access_token':''}},{'about':{'user':{'emailAddress':OWNER},'storageQuota':{}}},
            {'folder':{'id':'synthetic-folder','name':'wrong','mimeType':'application/vnd.google-apps.folder','owners':[{'emailAddress':OWNER}],'trashed':False}}):
            with self.subTest(arguments=arguments):create(**arguments)
        for purpose,run,attempt in [('unknown','1','1'),('encrypted-backup',1,'1'),('encrypted-backup','1','0')]:
            with self.assertRaises(BackupError):properties(SCOPE,purpose,run,attempt)
        with self.assertRaises(BackupError):checked_name(SCOPE,'wrong','backup-manifest','1','1')

    def test_large_provider_json_remains_bounded_unique_and_object_shaped(self):
        large={'padding':'x'*66000,'files':[]}
        for body,content_type,valid in [(json.dumps(large),'application/json',True),
            ('{"padding":"'+'x'*66000+'","a":1,"a":2}','application/json',False),
            ('{"padding":"'+'x'*66000+'","a":NaN}','application/json',False),
            ('[]','application/json',False),('x'*262145,'application/json',False),('{}','text/html',False)]:
            store,_,_=self.connect(handler=lambda r,a:httpx.Response(200,content=body,headers={'content-type':content_type}))
            try:
                if valid:self.assertEqual(store.request('GET','files'),large)
                else:
                    with self.assertRaises(BackupError):store.request('GET','files')
            finally:store.close()

    def test_listing_paginates_once_and_refuses_invalid_rows_oversized_and_endless_pages(self):
        count=0
        def paging(request,archive):
            nonlocal count
            count+=1
            return httpx.Response(200,json={'files':[dict(archive,id='synthetic-file-'+str(count))],**({'nextPageToken':'page-'+str(count)} if count<2 else {})})
        store,calls,_=self.connect(handler=paging)
        try:
            self.assertEqual(len(store.files()),2);self.assertEqual(calls[-1].url.params['pageToken'],'page-1')
        finally:store.close()
        for value in ({'files':[None]},{'files':[{}]*101},{'files':[],'nextPageToken':'x'*2049}):
            store,_,_=self.connect(handler=lambda r,a:httpx.Response(200,json=value))
            try:
                with self.assertRaises(BackupError):store.files()
            finally:store.close()
        count=0
        def endless(request,archive):
            nonlocal count
            count+=1;return httpx.Response(200,json={'files':[],'nextPageToken':'page-'+str(count)})
        store,_,_=self.connect(handler=endless)
        try:
            with self.assertRaisesRegex(BackupError,'listing_limit'):store.files()
            self.assertEqual(count,20)
        finally:store.close()
        for mode in ('absent','duplicate'):
            store,_,_=self.connect(handler=lambda r,a:httpx.Response(200,json={'files':[] if mode=='absent' else [a,dict(a,id='other-file')]}))
            try:
                if mode=='absent':self.assertIsNone(store.find('encrypted-backup','1','1'))
                else:
                    with self.assertRaisesRegex(BackupError,'run_ambiguous'):store.find('encrypted-backup','1','1')
            finally:store.close()

    def test_successful_upload_reads_back_exact_checksum_and_malformed_ids_never_start_upload(self):
        name=manifest()['archive_name'];saved=record(name,'encrypted-backup',identity='generated-file-123')
        for mode in ('success','ids','checksum'):
            def handler(request,archive):
                if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':[] if mode=='ids' else [saved['id']]})
                if request.method=='POST':return httpx.Response(200,headers={'location':'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=synthetic'})
                if request.method=='PUT':return httpx.Response(200)
                return httpx.Response(200,json=dict(saved,md5Checksum='bad') if mode=='checksum' else saved)
            store,calls,_=self.connect(handler=handler)
            try:
                before=store.available
                with tempfile.TemporaryDirectory() as directory:
                    path=Path(directory)/'encrypted';path.write_bytes(b'synthetic-ciphertext')
                    if mode=='success':self.assertEqual(store.upload(path,name,'encrypted-backup','1','1'),saved);self.assertEqual(store.available,before-path.stat().st_size)
                    else:
                        with self.assertRaises(BackupError):store.upload(path,name,'encrypted-backup','1','1')
                        self.assertEqual(store.available,before)
                    if mode=='ids':self.assertFalse(any(r.method in ('PUT','POST') and r.url.host=='www.googleapis.com' for r in calls))
            finally:store.close()

    def test_failed_delete_readback_is_not_reported_as_deleted(self):
        deleting=False
        def handler(request,archive):
            nonlocal deleting
            if request.method=='DELETE':deleting=True;return httpx.Response(503)
            if deleting:raise httpx.ReadTimeout('synthetic readback failure',request=request)
            return httpx.Response(200,json=archive)
        store,calls,archive=self.connect(handler=handler)
        try:
            with self.assertRaisesRegex(BackupError,'delete_failed'):store.remove(archive)
            self.assertEqual(sum(r.method=='DELETE' for r in calls),1)
        finally:store.close()
