"""Real committed transactions and races, using synthetic bookings only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Barrier
from uuid import uuid4
import os
import unittest
from .fixtures import installation,business
from appointment_system.serialization import fingerprint
from appointment_system.settings import BusinessSettings
from tools.checks.sql_target import SQLTarget,literal


@unittest.skipUnless(os.environ.get("BOOKING_SQL_TEST_TARGET"),"Owned isolated SQL target required.")
class BookingFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=SQLTarget(os.environ["BOOKING_SQL_TEST_TARGET"])
        cls.db.check_owned()
        declared=installation();declared["database_targets"]["web"]["role"]="appointment_system_web"
        cls.db.value("SELECT appointment_system.configure_installation("+literal(declared)+"::jsonb,"+
                     literal(BusinessSettings.parse(business()).document)+"::jsonb,true);")
        cls.db.scalar("SELECT appointment_system.provision_login('appointment_system_web','web');")
        cls.db.scalar("SELECT appointment_system.configure_worker_release('"+'a'*64+"');")

    def setUp(self):
        self.db.scalar("SELECT appointment_system.configure_worker_release('"+'a'*64+"');")
        self.db.sql("TRUNCATE appointment_system.checkout_contexts CASCADE;"
                    "UPDATE appointment_system.control_product_state SET enabled=true,requested_enabled=true;"
                    "TRUNCATE appointment_system.provider_inbox;")
        self.spec=BusinessSettings.parse(business()).document
        self.set_policy(self.spec)
        self.account={"merchant_id":"SyntheticMerchant","mode":"live","credential_version":"fixture"}
        self.db.scalar("SELECT appointment_system.configure_payment_account('SyntheticMerchant','live','fixture');")
        self.starts=self.db.value("SELECT to_jsonb(ARRAY(SELECT s.starts_at::text FROM generate_series(1,9) n"
                     " CROSS JOIN LATERAL appointment_system.schedule_starts(appointment_system.current_business(),30,"
                     "(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date+n,clock_timestamp()) s"
                     " ORDER BY s.starts_at LIMIT 8));")
        self.assertGreaterEqual(len(self.starts),3)
        self.starts=[datetime.fromisoformat(value).isoformat() for value in self.starts]

    def set_policy(self,spec):
        self.version=fingerprint(spec)
        self.db.sql("INSERT INTO appointment_system.booking_policies(version,specification) VALUES ("+
                    literal(self.version)+","+literal(spec)+"::jsonb) ON CONFLICT DO NOTHING;"
                    "UPDATE appointment_system.intake_settings SET policy_version="+literal(self.version)+" WHERE singleton;")

    def draft(self,*,start=None,context=None,**changes):
        request=str(uuid4());context=context or str(uuid4())
        if self.db.scalar("SELECT EXISTS(SELECT 1 FROM appointment_system.checkout_contexts WHERE id="+literal(context)+"::uuid);")=="f":
            self.db.sql("SELECT appointment_system.api_create_context("+literal(context)+",'"+uuid4().hex*2+"');",
                        role="appointment_system_web")
        payload={"request_id":request,"full_name":"Synthetic Customer","email":"customer@example.test",
                 "phone":"+919876543210","service_id":"consultation","quote_version":self.version,
                 "starts_at":start or self.starts[0],"questions":1,"birth_date":None,
                 "birth_time":"","birth_place":"","notes":""}
        payload.update(changes)
        return {"context":context,"request":request,"receipt":uuid4().hex*2,"payload":payload,"hash":fingerprint(payload)}

    def admit(self,draft):
        return self.db.scalar("SELECT appointment_system.admit_checkout("+",".join(literal(draft[k])
                              for k in ("context","request","receipt","hash"))+");",role="appointment_system_web")

    def reserve(self,draft,*,account=True):
        if self.admit(draft) not in ("pending","committed"):
            return {"code":"admission_rejected"}
        parameters=",".join(literal(draft[k]) for k in ("context","request","receipt","hash"))
        return self.db.value("SELECT appointment_system.reserve_configured_checkout("+parameters+","+
                             literal(draft["payload"])+"::jsonb,"+(literal(self.account)+"::jsonb" if account else "NULL")+");",
                             role="appointment_system_web")

    def booking(self,**changes):
        draft=self.draft(**changes);result=self.reserve(draft)
        self.assertEqual(result["code"],"reserved")
        draft["booking"]=result["booking_id"]
        return draft

    def start_order(self,draft):
        return self.db.scalar("SELECT appointment_system.start_order_creation("+literal(draft["context"])+","+
                              literal(draft["booking"])+");",role="appointment_system_web")

    def record_order(self,draft,order="order_synthetic"):
        encoded="NULL" if order is None else literal(order)
        return self.db.scalar("SELECT appointment_system.record_order_creation("+literal(draft["context"])+","+
                              literal(draft["booking"])+",'SyntheticMerchant','live','fixture',"+encoded+");",
                              role="appointment_system_web")

    def capture(self,draft,*,payment="pay_synthetic",amount=210000,evidence="a"*64):
        return self.db.scalar("SELECT appointment_system.observe_payment("+literal(draft["context"])+","+
                              literal(draft["booking"])+",'SyntheticMerchant','live','fixture',"+
                              literal(payment)+",'order_synthetic',"+literal(evidence)+",'captured',"+
                              str(amount)+",'INR',0,true);",role="appointment_system_web")

class BookingSQL(BookingFixture):
    def test_matching_retry_returns_same_booking_and_changed_body_is_refused(self):
        saved=self.booking()
        self.assertEqual(self.reserve(saved),{"code":"existing","booking_id":saved["booking"]})
        saved["payload"]["full_name"]="Changed Customer"
        result=self.reserve(saved)
        self.assertEqual(result["code"],"request_conflict")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.bookings;"),"1")

    def test_one_context_cannot_create_two_unresolved_orders_but_another_context_is_independent(self):
        first=self.booking()
        blocked=self.reserve(self.draft(context=first["context"],start=self.starts[1]))
        self.assertEqual(blocked["code"],"checkout_in_progress")
        second=self.booking(start=self.starts[1])
        self.assertNotEqual(first["booking"],second["booking"])
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.bookings;"),"2")

    def test_concurrent_same_slot_has_one_winner_and_no_deadlock(self):
        drafts=[self.draft() for _ in range(40)]
        start=Barrier(len(drafts),timeout=30)
        def compete(draft):
            start.wait()
            return self.reserve(draft)
        with ThreadPoolExecutor(max_workers=len(drafts)) as executor:
            results=list(executor.map(compete,drafts))
        self.assertEqual(sum(result["code"]=="reserved" for result in results),1)
        self.assertEqual(sum(result["code"]=="time_unavailable" for result in results),39)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.bookings;"),"1")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;"),"1")
        # Admission reserves an intention, not an external payable order.
        # The competitors cannot leave additional provider attempts behind.
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_orders;"),"1")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_orders WHERE attempted_at IS NOT NULL OR provider_order_id IS NOT NULL;"),"0")

    def test_buffer_occupancy_rejects_an_adjacent_start_and_does_not_change_the_appointment(self):
        self.spec["buffer_after_minutes"]=15;self.set_policy(self.spec)
        first=self.booking()
        other=self.reserve(self.draft(start=self.starts[1]))
        self.assertEqual(other["code"],"time_unavailable")
        observed=self.db.value("SELECT jsonb_build_object('appointment',b.ends_at-b.starts_at,'occupied',c.ends_at-c.starts_at)"
                               " FROM appointment_system.bookings b JOIN appointment_system.slot_claims c ON c.booking_id=b.id;")
        self.assertEqual(observed,{"appointment":"00:30:00","occupied":"00:45:00"})
        self.assertEqual(self.start_order(first),"t")

    def test_expiry_releases_capacity_without_clearing_another_context(self):
        first=self.booking()
        self.db.sql("UPDATE appointment_system.bookings SET created_at=clock_timestamp()-interval '15 minutes',hold_expires_at=clock_timestamp()-interval '1 second'"
                    " WHERE id="+literal(first["booking"])+";")
        self.booking()
        self.assertEqual(self.db.scalar("SELECT active_checkout_id::text FROM appointment_system.checkout_contexts"
                                       " WHERE id="+literal(first["context"])+";"),first["booking"])
        self.assertEqual(self.db.scalar("SELECT resolution FROM appointment_system.payment_orders"
                                       " WHERE booking_id="+literal(first["booking"])+";"),"never_attempted_abandoned")

    def test_missing_payment_setup_and_stale_quote_do_not_create_a_hold(self):
        self.assertEqual(self.reserve(self.draft(),account=False)["code"],"payment_not_configured")
        self.assertEqual(self.reserve(self.draft(quote_version="f"*64))["code"],"quote_changed")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.bookings;"),"0")

    def test_quantity_and_optional_phone_are_decided_from_the_same_policy(self):
        self.spec=BusinessSettings.parse(business(per_question=True)).document
        self.spec["required_contacts"]=["email"];self.set_policy(self.spec)
        saved=self.booking(questions=3,phone="")
        self.assertEqual(self.db.scalar("SELECT amount_paise FROM appointment_system.bookings WHERE id="+
                                       literal(saved["booking"])+";"),"630000")
        self.assertEqual(self.reserve(self.draft(start=self.starts[1],questions=4))["code"],"service_unavailable")

    def test_booking_otp_is_required_when_configured_and_cannot_be_reused(self):
        self.spec["booking_verification"]["email"]=True;self.set_policy(self.spec)
        self.assertEqual(self.reserve(self.draft())["code"],"verification_required")
        allowed=self.draft();grant="d"*64
        self.db.sql("INSERT INTO appointment_system.booking_verification_grants"
                    "(digest,context_id,email,purpose,policy_digest,expires_at) VALUES ("+
                    literal(grant)+","+literal(allowed["context"])+",'customer@example.test','booking',"
                    "appointment_system.verification_policy(appointment_system.current_business()),clock_timestamp()+interval '5 minutes');")
        allowed["payload"]["verification_grant"]=grant;allowed["hash"]=fingerprint(allowed["payload"])
        result=self.reserve(allowed);self.assertEqual(result["code"],"reserved")
        used=self.db.scalar("SELECT consumed_request::text FROM appointment_system.booking_verification_grants WHERE digest="+literal(grant)+";")
        self.assertEqual(used,allowed["request"])

    def test_lost_order_reply_stays_unknown_and_cannot_issue_a_second_create(self):
        saved=self.booking();self.assertEqual(self.start_order(saved),"t")
        self.assertEqual(self.record_order(saved,None),"creation_unknown")
        self.assertEqual(self.start_order(saved),"f")
        self.assertEqual(self.record_order(saved),"ready")
        self.assertEqual(self.start_order(saved),"f")

    def test_captured_payment_confirms_once_and_queues_single_obligations(self):
        saved=self.booking();self.start_order(saved);self.record_order(saved)
        self.assertEqual(self.capture(saved),"confirmed")
        self.assertEqual(self.capture(saved),"confirmed")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.accepted_payments;"),"1")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs;"),"5")

    def test_capture_after_off_keeps_evidence_and_routes_to_private_review(self):
        saved=self.booking();self.start_order(saved);self.record_order(saved)
        self.db.sql("UPDATE appointment_system.control_product_state SET enabled=false;")
        self.assertEqual(self.capture(saved),"payment_needs_review")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.payment_observations;"),"1")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.accepted_payments;"),"0")
        self.assertEqual(self.db.scalar("SELECT reason FROM appointment_system.payment_cases;"),"booking_disabled")
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.slot_claims WHERE released_at IS NULL;"),"0")

    def test_late_capture_does_not_steal_the_reallocated_slot(self):
        late=self.booking();self.start_order(late);self.record_order(late)
        self.db.sql("UPDATE appointment_system.bookings SET created_at=clock_timestamp()-interval '15 minutes',hold_expires_at=clock_timestamp()-interval '1 second'"
                    " WHERE id="+literal(late["booking"])+";")
        current=self.booking()
        self.assertEqual(self.capture(late),"payment_needs_review")
        self.assertEqual(self.db.scalar("SELECT booking_id::text FROM appointment_system.slot_claims WHERE released_at IS NULL;"),
                         current["booking"])
