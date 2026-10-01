"""Storage identity, ambiguity and retention failure cases use captured HTTP."""
from datetime import date
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import httpx
from drive import Drive,OWNER,file_id
from envelope import BackupError
from test_retention import archive

class DriveBoundaryTests(unittest.TestCase):
    def connect(self,handler=None,token='synthetic'):
        calls=[]
        def request(r):
            calls.append(r)
            if r.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':token})
            if r.url.path.endswith('/about'):return httpx.Response(200,json={'user':{'emailAddress':OWNER},'storageQuota':{'limit':'15000000000','usage':'0'}})
            return handler(r) if handler else httpx.Response(200,json={})
        return Drive({'client_id':'synthetic','client_secret':'synthetic','refresh_token':'synthetic'},httpx.Client(transport=httpx.MockTransport(request))),calls

    def test_invalid_token_and_non_object_provider_response_are_not_trusted(self):
        for token in ('',None,7):
            with self.assertRaisesRegex(BackupError,'connection_unavailable'):self.connect(token=token)
        drive,_=self.connect(lambda r:httpx.Response(200,json=[]))
        try:
            with self.assertRaisesRegex(BackupError,'request_failed'):drive.request('GET','files')
        finally:drive.close()
        for identity in ('',"folder' or true",None):
            with self.assertRaisesRegex(BackupError,'identity_invalid'):file_id(identity)

    def test_folder_creation_and_existing_folder_both_verify_owner(self):
        for found in (True,False):
            folder={'id':'folder','owners':[{'emailAddress':OWNER}]}
            drive,calls=self.connect(lambda r:httpx.Response(200,json={'files':[folder]} if r.method=='GET' else folder))
            if not found:
                original=drive.request
                drive.request=lambda method,path,**kwargs:{'files':[]} if method=='GET' else original(method,path,**kwargs)
            try:self.assertEqual(drive.folder(),'folder');self.assertEqual(sum(r.method=='POST' for r in calls),1 if found else 2)
            finally:drive.close()
        for response,code in [({'files':[],'nextPageToken':'more'},'folder_ambiguous'),({'files':[folder,folder]},'folder_ambiguous'),({'files':[{'id':'folder','owners':[]}]},'folder_owner_mismatch')]:
            drive,_=self.connect(lambda r:httpx.Response(200,json=response))
            try:
                with self.assertRaisesRegex(BackupError,code):drive.folder()
            finally:drive.close()

    def test_existing_archive_filters_kind_revision_and_rejects_ambiguity(self):
        current=archive(date(2026,10,1),'archive')
        drive,_=self.connect()
        try:
            drive.request=Mock(return_value={'files':[current]});self.assertEqual(drive.existing('folder','2026-10-01')['id'],'archive')
            self.assertIsNone(drive.existing('folder','2026-10-01','checkpoint','a'*40))
            for response,code in [({'files':[current,current]},'ambiguous'),({'files':[current],'nextPageToken':'more'},'ambiguous'),({'files':[{**current,'parents':['other']}]},'owner_mismatch')]:
                drive.request.return_value=response
                with self.assertRaisesRegex(BackupError,code):drive.existing('folder','2026-10-01')
            with self.assertRaisesRegex(BackupError,'day_invalid'):drive.existing('folder',"2026-10-01' or true")
        finally:drive.close()

    def test_inventory_handles_multiple_pages_and_rejects_invalid_unbounded_results(self):
        drive,_=self.connect()
        try:
            drive.request=Mock(side_effect=[{'files':[],'nextPageToken':'second'},{'files':[]}]);self.assertEqual(drive.inventory('folder'),[]);self.assertEqual(drive.request.call_args.kwargs['params']['pageToken'],'second')
            for data,code in [({'files':None},'inventory_invalid'),({'files':[],'nextPageToken':5},'inventory_ambiguous')]:
                drive.request=Mock(return_value=data)
                with self.assertRaisesRegex(BackupError,code):drive.inventory('folder')
            drive.request=Mock(side_effect=[{'files':[],'nextPageToken':str(i)} for i in range(20)])
            with self.assertRaisesRegex(BackupError,'inventory_limit'):drive.inventory('folder')
        finally:drive.close()

    def test_verification_marks_only_matching_proof_and_unchanged_encrypted_file(self):
        record=archive(date(2026,10,1),'archive',False);drive,_=self.connect()
        try:
            confirmed=copy.deepcopy(record);confirmed['appProperties'].update(restoreVerified='1',restoredMigrations='31');drive.request=Mock(return_value=confirmed)
            self.assertEqual(drive.mark_verified(record,'folder',{'restored_migrations':31}),confirmed)
            for proof in ({},{'restored_migrations':True},{'restored_migrations':0}):
                with self.assertRaisesRegex(BackupError,'proof_invalid'):drive.mark_verified(record,'folder',proof)
            for changes in ({'id':'other'},{'size':'7'},{'md5Checksum':'b'*32},{'appProperties':record['appProperties']}):
                drive.request.return_value={**confirmed,**changes}
                with self.assertRaises(BackupError):drive.mark_verified(record,'folder',{'restored_migrations':31})
        finally:drive.close()

    def test_upload_failure_size_limit_and_download_checksum_do_not_count_as_success(self):
        drive,_=self.connect(lambda r:httpx.Response(503))
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'archive';path.write_bytes(b'synthetic encrypted data')
                for kind,revision in [('other',''),('checkpoint','broken')]:
                    with self.assertRaisesRegex(BackupError,'kind_invalid'):drive.upload(path,'folder','2026-10-01',kind,revision)
                drive.available=0
                with self.assertRaisesRegex(BackupError,'space_insufficient'):drive.upload(path,'folder','2026-10-01')
                drive.available=15000000000
                with self.assertRaisesRegex(BackupError,'request_failed'):drive.upload(path,'folder','2026-10-01')
                for size in ('0',str(514*1024*1024),'invalid'):
                    with self.assertRaisesRegex(BackupError,'download_unverified'):drive.download({'id':'archive','size':size},Path(directory)/'output')
        finally:drive.close()

    def test_retention_deletes_only_selected_verified_files(self):
        today=date(2026,10,1);new=archive(today,'new');old=archive(date(2020,1,1),'old');older=archive(date(2019,1,1),'older');drive,_=self.connect()
        try:
            drive.inventory=Mock(return_value=[new,old,older]);drive.remove_verified=Mock();self.assertEqual(drive.retain('folder',today,new),1);drive.remove_verified.assert_called_once_with(older,'folder')
        finally:drive.close()

if __name__=='__main__':unittest.main()
