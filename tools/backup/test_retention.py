"""Retention boundaries and failure safety, with synthetic archives only."""
from datetime import date,timedelta
import copy
import unittest
import httpx
from drive import Drive,API,OWNER
from envelope import BackupError
from retention import candidates,PROJECT


def archive(day,identity,verified=True):
    return {'id':identity,'name':f'sarsa-004-{day}.pgdump.aesgcm','mimeType':'application/octet-stream',
        'parents':['folder'],'owners':[{'emailAddress':OWNER}],'size':'123','md5Checksum':'a'*32,
        'createdTime':str(day)+'T03:02:00.000Z',
        'appProperties':{'sarsaProject':PROJECT,'backupDay':str(day),'format':'aes256gcm-v1',
                         **({'restoreVerified':'1','restoredMigrations':'31'} if verified else {})}}


class RetentionTests(unittest.TestCase):
    def test_recent_days_monthly_representatives_two_latest_and_current_survive(self):
        today=date(2026,9,30)
        records=[archive(today-timedelta(days=i),'file-'+str(i)) for i in range(430)]
        chosen=[]
        while True:
            remove=candidates(records,'folder',today,'file-0')
            if not remove:break
            self.assertLessEqual(len(remove),20)
            chosen.extend(r['id'] for r in remove)
            records=[r for r in records if r['id'] not in {x['id'] for x in remove}]
        self.assertTrue(all('file-'+str(i) not in chosen for i in range(30)))
        months={r['appProperties']['backupDay'][:7] for r in records}
        self.assertEqual(len(months),12)
        self.assertLessEqual(len(records),42)
        self.assertNotIn('file-0',chosen)

    def test_unknown_unverified_archives_are_preserved(self):
        today=date(2026,9,30)
        records=[archive(today,'new'),archive(today-timedelta(days=400),'old'),
                 archive(today-timedelta(days=401),'older'),archive(today-timedelta(days=500),'unknown',False)]
        self.assertEqual([r['id'] for r in candidates(records,'folder',today,'new')],['older'])
        records[0]['appProperties'].pop('restoreVerified')
        with self.assertRaisesRegex(BackupError,'current_not_verified'):candidates(records,'folder',today,'new')

    def test_owner_project_folder_name_duplicate_and_future_checks(self):
        today=date(2026,9,30);record=archive(today,'new')
        for alter in [lambda r:r.update(parents=['other']),lambda r:r.update(name='unrelated'),
                      lambda r:r.update(owners=[{'emailAddress':'neuraflowindia@gmail.com'}]),
                      lambda r:r['appProperties'].update(sarsaProject='003-other')]:
            value=copy.deepcopy(record);alter(value)
            with self.assertRaises(BackupError):candidates([value],'folder',today,'new')
        with self.assertRaises(BackupError):candidates([record,record],'folder',today,'new')
        with self.assertRaises(BackupError):candidates([archive(today+timedelta(days=1),'new')],'folder',today,'new')

    def client(self,record,mode):
        calls=[];gets=0
        def handler(request):
            nonlocal gets
            calls.append(request.method)
            if request.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'synthetic'})
            if request.url.path.endswith('/about'):return httpx.Response(200,json={'user':{'emailAddress':OWNER},'storageQuota':{'limit':'10000000','usage':'0'}})
            if request.method=='DELETE':
                if mode=='lost':raise httpx.ReadTimeout('synthetic',request=request)
                return httpx.Response(503 if mode=='failed' else 204)
            gets+=1
            if gets>1 and mode=='lost':return httpx.Response(404)
            if mode=='changed':
                value=copy.deepcopy(record);value['md5Checksum']='b'*32
                return httpx.Response(200,json=value)
            return httpx.Response(200,json=record)
        return Drive({'client_id':'x','client_secret':'x','refresh_token':'x'},httpx.Client(transport=httpx.MockTransport(handler))),calls

    def test_changed_archive_is_not_deleted_and_failed_delete_is_not_success(self):
        record=archive(date(2025,1,1),'old')
        for mode in ['changed','failed']:
            drive,calls=self.client(record,mode)
            try:
                with self.assertRaises(BackupError):drive.remove_verified(record,'folder')
                if mode=='changed':self.assertNotIn('DELETE',calls)
            finally:drive.close()

    def test_uncertain_delete_resolves_same_identity_without_deleting_another(self):
        record=archive(date(2025,1,1),'old');drive,calls=self.client(record,'lost')
        try:
            drive.remove_verified(record,'folder')
            self.assertEqual(calls.count('DELETE'),1)
        finally:drive.close()

    def test_pagination_is_bounded_and_repeated_token_never_starts_removal(self):
        record=archive(date(2026,9,30),'new');drive,calls=self.client(record,'ok')
        try:
            drive.request=lambda *a,**kw:{'files':[record],'nextPageToken':'same'}
            with self.assertRaisesRegex(BackupError,'inventory_ambiguous'):drive.inventory('folder')
            self.assertNotIn('DELETE',calls)
        finally:drive.close()
