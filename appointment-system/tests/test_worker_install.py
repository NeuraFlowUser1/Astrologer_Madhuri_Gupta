import copy
import unittest
from tools.install.worker import configuration
from tools.install.package import PackageError
from .fixtures import installation

class WorkerConfiguration(unittest.TestCase):
    def setUp(self):
        self.project=installation();self.release={'content_digest':'a'*64}
        self.previous={'name':self.project['worker']['name'],'account_id':'1'*32,'compatibility_date':'2026-09-11',
            'queues':{'consumers':[{'queue':'existing-owned-queue'}]},
            'migrations':[{'tag':'original-product-state','new_sqlite_classes':['BookingProductState']}],
            'kv_namespaces':[{'binding':'OLD_HEARTBEATS','id':'2'*32}]}
    def build(self,value=None):return configuration(self.previous if value is None else value,self.project,self.release,'../../appointment-system/worker/index.mjs')
    def test_existing_storage_migration_and_owned_queue_are_preserved_and_new_recovery_storage_is_appended(self):
        result=self.build();self.assertEqual(result['migrations'][0],self.previous['migrations'][0])
        self.assertEqual(result['migrations'][1],{'tag':'appointment-recovery-sqlite-v1','new_sqlite_classes':['BookingRecoveryState']})
        self.assertEqual(result['queues']['consumers'][0]['queue'],'existing-owned-queue')
        self.assertEqual(result['queues']['producers'][0]['queue'],'existing-owned-queue')
        self.assertNotIn('kv_namespaces',result);self.assertFalse(any('delete' in str(row) for row in result['migrations']))
        self.assertEqual(self.build(result),result)
    def test_release_and_project_facts_are_bound_to_the_contained_copy(self):
        result=self.build();self.assertEqual(result['vars']['BOOKING_INSTALLATION_ID'],self.project['installation_id'])
        self.assertEqual(result['vars']['BOOKING_RELEASE_DIGEST'],self.release['content_digest'])
        self.assertEqual(result['triggers']['crons'],['*/15 * * * *']);self.assertFalse(result['preview_urls'])
        self.assertFalse(any('SECRET' in key or 'KEY' in key for key in result['vars']))
    def test_different_worker_multiple_queues_unknown_storage_and_destructive_history_require_review(self):
        for change in ({'name':'other-project'}, {'account_id':'missing'}, {'queues':{'consumers':[]}},
            {'queues':{'consumers':[{'queue':'one'},{'queue':'two'}]}},
            {'migrations':[{'tag':'delete-old','deleted_classes':['BookingProductState']}]},
            {'migrations':[{'tag':'unknown','new_sqlite_classes':['OtherApplication']}]},
            {'migrations':[{'tag':'appointment-recovery-sqlite-v1','new_sqlite_classes':['BookingProductState']}]}):
            with self.subTest(change=change),self.assertRaises(PackageError):self.build(self.previous|change)
    def test_new_project_gets_both_storage_classes_without_any_cross_project_reference(self):
        result=self.build(self.previous|{'migrations':[]});self.assertEqual(len(result['migrations']),2)
        self.assertEqual([row['new_sqlite_classes'][0] for row in result['migrations']],['BookingProductState','BookingRecoveryState'])
