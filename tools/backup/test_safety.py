import json
import unittest
import httpx
from drive import Drive, owned
from envelope import BackupError
from postgres import database_environment, HOST

class BackupSafetyTests(unittest.TestCase):
    def test_database_is_fixed_to_direct_sarsa_host_and_read_role(self):
        value=f'postgresql://sarsa_booking_backup:synthetic@{HOST}/neondb?sslmode=require'
        env=database_environment(value)
        self.assertEqual(env['PGSSLMODE'],'verify-full')
        self.assertEqual(env['PGUSER'],'sarsa_booking_backup')
        for bad in [value.replace(HOST,'example.com'),value.replace('sarsa_booking_backup','neondb_owner'),value.replace('/neondb','/other'),value+'&service=other']:
            with self.assertRaises(BackupError):database_environment(bad)

    def connect(self,owner,quota=True):
        def handler(request):
            if request.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'synthetic'})
            response={'user':{'emailAddress':owner}}
            if quota:response['storageQuota']={'limit':'15000000000','usage':'1000'}
            return httpx.Response(200,json=response)
        return Drive({'client_id':'synthetic','client_secret':'synthetic','refresh_token':'synthetic'},httpx.Client(transport=httpx.MockTransport(handler)))

    def test_google_owner_is_approved_client_not_agency(self):
        with self.assertRaisesRegex(BackupError,'drive_owner_mismatch'):self.connect('neuraflowindia@gmail.com')
        drive=self.connect('sarsajyotish@gmail.com');self.assertGreater(drive.available,0);drive.close()
        with self.assertRaises(BackupError):self.connect('sarsajyotish@gmail.com',False)

    def test_shared_or_trashed_records_are_not_accepted_as_owned_backup(self):
        self.assertTrue(owned({'owners':[{'emailAddress':'sarsajyotish@gmail.com'}]}))
        self.assertFalse(owned({'owners':[{'emailAddress':'neuraflowindia@gmail.com'}]}))
        self.assertFalse(owned({'owners':[{'emailAddress':'sarsajyotish@gmail.com'}],'trashed':True}))

if __name__=='__main__':unittest.main()
