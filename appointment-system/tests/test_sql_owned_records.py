"""Committed full booking records and deterministic Calendar completion."""
from uuid import UUID,uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
from . import test_sql_google_resources as resource_tests
from appointment_system.google_records import sheet_values
from appointment_system.google_workspace import event_id,HISTORY_HEADERS,PROJECT
from appointment_system.serialization import fingerprint
from tools.checks.sql_target import literal

class OwnedRecordsSQL(resource_tests.ResourceSQL):
    def confirmed_record(self):
        b=self.booking(birth_date='1990-01-02',birth_time='10:12',birth_place='Delhi',notes='Private consultation notes')
        self.assertEqual(self.start_order(b),'t');self.assertEqual(self.record_order(b),'ready');self.assertEqual(self.capture(b),'confirmed')
        return b

    def test_full_record_and_meeting_link_are_saved_as_distinct_immutable_history(self):
        b=self.confirmed_record()
        for resource in ('client_sheet','agency_sheet'):self.assertTrue(self.install(resource)[1])
        for role in ('client','agency'):
            saved=self.worker.claim_google_workbook(role,'123456789-syntheticclient.apps.googleusercontent.com')
            self.assertEqual(saved['layout_version'],4)
            self.assertTrue(self.worker.begin_google_workbook_create(role,UUID(saved['lease']),UUID(saved['intent'])))
            self.assertTrue(self.worker.finish_google_workbook(role,UUID(saved['lease']),'owned-'+role))
        initial=self.worker.claim_google_delivery('client_sheet');values=sheet_values(initial,4)
        self.assertEqual(len(values),len(HISTORY_HEADERS));self.assertEqual(values[0],PROJECT)
        local=datetime.fromisoformat(initial['payload']['starts_at']).astimezone(ZoneInfo(initial['payload']['practice_timezone']))
        self.assertEqual(values[33:35],[local.date().isoformat(),local.strftime('%H:%M')])
        self.assertEqual(values[35],fingerprint(values[:35]))
        self.assertEqual(values[13:18],['1','1990-01-02','10:12','Delhi','Private consultation notes'])
        row=self.worker.assign_sheet_row('client',initial,values)
        self.assertEqual(row['values'],values)
        changed=values.copy();changed[17]='A changed frozen note';changed[35]=fingerprint(changed[:35])
        self.assertIsNone(self.worker.assign_sheet_row('client',initial,changed))
        self.assertTrue(self.worker.finish_google_delivery(initial,'done','owned-client',None,None,30))
        calendar=self.worker.claim_google_delivery('calendar')
        self.assertEqual(calendar['payload']['practice_timezone'],'Asia/Kolkata')
        self.assertEqual(calendar['payload']['payment_identity']['merchant_id'],'SyntheticMerchant')
        self.assertTrue(self.worker.finish_google_delivery(calendar,'done',event_id(b['booking'],1),'https://meet.google.com/abc-defg-hij',None,30))
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE event_key='meeting-ready';"),'2')
        linked=self.worker.claim_google_delivery('client_sheet');linked_values=sheet_values(linked,4)
        self.assertEqual(linked_values[24],'https://meet.google.com/abc-defg-hij')
        second=self.worker.assign_sheet_row('client',linked,linked_values)
        self.assertNotEqual(second['row'],row['row'])
        mapped=self.worker.mapped_google_row('client',UUID(initial['id']),'booking')
        self.assertEqual(mapped['values'],values);self.assertEqual(mapped['values'][24],'')
        self.assertIsNotNone(mapped['grant_id'])

    def test_legacy_event_protocols_match_python_and_reject_changed_event_identity(self):
        b=self.confirmed_record()
        for protocol in ('v1','legacy-sarsa004','legacy-astro003','legacy-astro003-unversioned'):
            expected=self.db.scalar('SELECT appointment_system.calendar_event_identity('+literal(b['booking'])+',2,'+literal(protocol)+');')
            self.assertEqual(expected,event_id(b['booking'],2,protocol))
        calendar=self.worker.claim_google_delivery('calendar')
        self.assertFalse(self.worker.finish_google_delivery(calendar,'done',event_id(b['booking'],2),'https://meet.google.com/abc-defg-hij',None,30))
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.meeting_events;'),'0')
        self.assertTrue(self.worker.finish_google_delivery(calendar,'done',event_id(b['booking'],1),'https://meet.google.com/abc-defg-hij',None,30))
