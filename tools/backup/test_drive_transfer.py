"""Provider failure tests use synthetic bytes and never contact Google."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import httpx
from drive import Drive, OWNER, API
from envelope import BackupError


class TransferTests(unittest.TestCase):
    def fixture(self, mode):
        calls=[]
        content=b'encrypted-synthetic-bytes'
        record={'id':'fixed-id','owners':[{'emailAddress':OWNER}], 'parents':['folder'],
            'size':str(len(content)), 'md5Checksum':hashlib.md5(content,usedforsecurity=False).hexdigest()}
        def handler(request):
            calls.append((request.method,str(request.url)))
            if request.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'synthetic'})
            if request.url.path.endswith('/about'):return httpx.Response(200,json={'user':{'emailAddress':OWNER},'storageQuota':{'limit':'15000000000','usage':'0'}})
            if request.url.path.endswith('/generateIds'):return httpx.Response(200,json={'ids':['fixed-id']})
            if request.method=='POST':return httpx.Response(200,headers={'location': 'https://evil.invalid/upload' if mode=='redirect' else 'https://www.googleapis.com/upload/drive/v3/files?upload_id=synthetic'})
            if request.method=='PUT':raise httpx.ReadTimeout('synthetic response lost',request=request)
            if request.url.params.get('alt')=='media':return httpx.Response(200,content=content+b'extra')
            return httpx.Response(200,json=record)
        return Drive({'client_id':'x','client_secret':'x','refresh_token':'x'},httpx.Client(transport=httpx.MockTransport(handler))),calls,content,record

    def test_lost_upload_response_checks_same_file_without_duplicate(self):
        drive,calls,content,_=self.fixture('lost')
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'backup';path.write_bytes(content)
                self.assertEqual(drive.upload(path,'folder','2026-09-29')['id'],'fixed-id')
            self.assertEqual(sum(method=='POST' and '/upload/' in url for method,url in calls),1)
            self.assertEqual(sum(method=='PUT' for method,url in calls),1)
            self.assertTrue(any(method=='GET' and '/files/fixed-id' in url for method,url in calls))
        finally:drive.close()

    def test_upload_does_not_forward_authorization_to_other_host(self):
        drive,calls,content,_=self.fixture('redirect')
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'backup';path.write_bytes(content)
                with self.assertRaisesRegex(BackupError,'drive_upload_location_invalid'):drive.upload(path,'folder','2026-09-29')
            self.assertFalse(any('evil.invalid' in url for _,url in calls))
        finally:drive.close()

    def test_download_rejects_more_bytes_than_manifest(self):
        drive,_,_,record=self.fixture('download')
        try:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(BackupError,'backup_download_unverified'):drive.download(record,Path(directory)/'readback')
        finally:drive.close()

if __name__=='__main__':unittest.main()
