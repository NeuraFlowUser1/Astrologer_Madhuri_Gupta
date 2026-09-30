-- Run only inside a development rollback transaction. Synthetic data; no providers.
INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','cancel-fixture'),('agency','agency-fixture');
INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES
(repeat('a',64),'client','cancel-fixture','cancel-test','https://cancel.example',clock_timestamp()+interval '1 hour'),
(repeat('b',64),'agency','agency-fixture','cancel-test','https://cancel.example',clock_timestamp()+interval '1 hour');
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE c uuid:=gen_random_uuid();r uuid:=gen_random_uuid();b uuid:=gen_random_uuid();claim uuid:=gen_random_uuid();op uuid:=gen_random_uuid();obs uuid:=gen_random_uuid();job uuid:=gen_random_uuid();lease uuid:=gen_random_uuid();start_at timestamptz:=clock_timestamp()+interval '3 days';value jsonb;event text;result text;
BEGIN
 INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at) VALUES(c,repeat('c',64),clock_timestamp()+interval '1 day');
 INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint) VALUES(r,c,repeat('d',64),repeat('e',64));
 INSERT INTO sarsa_booking.bookings(id,request_id,context_id,state,service_id,policy_version,service_snapshot,amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,hold_expires_at,receipt_expires_at)
 VALUES(b,r,c,'confirmed','synthetic',repeat('f',64),'{"name":"Synthetic consultation"}',100,'INR',start_at,start_at+interval '30 minutes','Asia/Kolkata','Synthetic Client','no-send@example.com','+919876543210',clock_timestamp()+interval '10 minutes',start_at+interval '1 day');
 INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at) VALUES(claim,b,start_at,start_at+interval '30 minutes');
 INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version,provider_order_id,state,attempted_at,resolution,resolved_at)
 VALUES(b,'SyntheticMerchant','live','fixture','order_fixture','ready',clock_timestamp(),'confirmed',clock_timestamp());
 INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,amount_paise,currency,captured)
 VALUES(obs,b,'SyntheticMerchant','live','pay_fixture','order_fixture',repeat('a',64),'captured',100,'INR',true);
 INSERT INTO sarsa_booking.accepted_payments(booking_id,observation_id,merchant_id,mode,payment_id) VALUES(b,obs,'SyntheticMerchant','live','pay_fixture');
 -- Model an in-flight Google event creation which returns after cancellation.
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,state,lease_token,lease_expires_at,first_attempt_at,payload)
 VALUES(job,b,'booking_calendar','calendar',1,'processing',lease,clock_timestamp()+interval '2 minutes',clock_timestamp(),jsonb_build_object('id',b,'revision',1));
 value:=sarsa_booking.studio_appointment_cancel(repeat('b',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request');
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency authorized';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'wrong','https://cancel.example',op,claim,1,'Customer request');
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'wrong audience';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',op,claim,2,'Customer request');
 IF value->>'code'<>'revision_changed' THEN RAISE EXCEPTION 'stale revision';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request');
 IF value->>'code'<>'cancelled' OR value->>'revision'<>'2' OR value->>'policy_guidance'<>'full_refund_review' THEN RAISE EXCEPTION 'cancel failed %',value;END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE id=claim AND released_at IS NULL) OR (SELECT state FROM sarsa_booking.bookings WHERE id=b)<>'cancelled' THEN RAISE EXCEPTION 'capacity state';END IF;
 IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 THEN RAISE EXCEPTION 'jobs missing';END IF;
 IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='sheet_booking' AND booking_revision=2 AND payload->>'state'='cancelled')<>2 THEN RAISE EXCEPTION 'cancelled records';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request');
 IF value->>'code'<>'cancelled' OR (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 THEN RAISE EXCEPTION 'duplicate replay';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Changed reason');
 IF value->>'code'<>'request_conflict' THEN RAISE EXCEPTION 'changed replay';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),claim,2,'Cancel twice');
 IF value->>'code'<>'appointment_unavailable' THEN RAISE EXCEPTION 'cancelled twice';END IF;
 IF (SELECT count(*) FROM sarsa_booking.accepted_payments WHERE booking_id=b)<>1 OR EXISTS(SELECT 1 FROM sarsa_booking.payment_observations WHERE booking_id=b AND refunded_paise<>0) THEN RAISE EXCEPTION 'financial evidence changed';END IF;
 event:='sarsa'||encode(sha256(convert_to('004-sarsa-jyotish-sansthan:'||b::text||':1','UTF8')),'hex');
 IF NOT sarsa_booking.finish_google_delivery(job,lease,'done',event,'https://meet.google.com/abc-defg-hij',NULL,15) THEN RAISE EXCEPTION 'late meeting completion lost';END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='booking_cancelled' AND recipient_role='calendar' AND booking_revision=1 AND state='pending') THEN RAISE EXCEPTION 'late meeting cleanup missing';END IF;
 result:=sarsa_booking.observe_payment(c,b,'SyntheticMerchant','live','fixture','pay_fixture','order_fixture',repeat('b',64),'captured',100,'INR',0,true);
 IF result<>'observed' OR EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=b) OR (SELECT state FROM sarsa_booking.bookings WHERE id=b)<>'cancelled' THEN RAISE EXCEPTION 'repeat payment revived cancelled booking or false alarm';END IF;
 result:=sarsa_booking.observe_payment(c,b,'SyntheticMerchant','live','fixture','pay_other','order_fixture',repeat('c',64),'captured',100,'INR',0,true);
 IF result<>'payment_needs_review' OR NOT EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=b AND reason='additional_payment') THEN RAISE EXCEPTION 'real additional payment ignored';END IF;
 IF has_table_privilege(current_user,'sarsa_booking.staff_appointment_actions','INSERT') THEN RAISE EXCEPTION 'raw audit write granted';END IF;
END $test$;
RESET ROLE;
SELECT 'Cancellation rollback fixture passed' result;
