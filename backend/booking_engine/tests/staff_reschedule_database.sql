-- Run only inside a development rollback transaction. Synthetic data; no providers.
INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','cancel-fixture'),('agency','agency-fixture');
INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES
(repeat('a',64),'client','cancel-fixture','cancel-test','https://cancel.example',clock_timestamp()+interval '1 hour'),
(repeat('b',64),'agency','agency-fixture','cancel-test','https://cancel.example',clock_timestamp()+interval '1 hour');
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE c uuid:=gen_random_uuid();r uuid:=gen_random_uuid();b uuid:=gen_random_uuid();claim uuid:=gen_random_uuid();op uuid:=gen_random_uuid();obs uuid:=gen_random_uuid();job uuid:=gen_random_uuid();lease uuid:=gen_random_uuid();start_at timestamptz:=clock_timestamp()+interval '3 days';value jsonb;event text;result text;target timestamptz;closure uuid:=gen_random_uuid();
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

 SELECT (day::date+time '10:00') AT TIME ZONE 'Asia/Kolkata' INTO target
 FROM generate_series(current_date+2,current_date+7,interval '1 day') day
 WHERE extract(isodow FROM day)<7 ORDER BY day LIMIT 1;
 INSERT INTO sarsa_booking.slot_claims(id,starts_at,ends_at,closure_reason) VALUES(closure,target,target+interval '30 minutes','Synthetic closure');
 value:=sarsa_booking.studio_appointment_reschedule(repeat('b',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request',target);
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency authorized';END IF;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request',target);
 IF value->>'code'<>'time_already_reserved' THEN RAISE EXCEPTION 'overlap allowed %',value;END IF;
 IF (SELECT starts_at FROM sarsa_booking.bookings WHERE id=b)<>start_at OR (SELECT starts_at FROM sarsa_booking.slot_claims WHERE id=claim)<>start_at THEN RAISE EXCEPTION 'failed move lost original';END IF;
 UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp() WHERE id=closure;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request',target);
 IF value->>'code'<>'rescheduled' OR value->>'revision'<>'2' THEN RAISE EXCEPTION 'move failed %',value;END IF;
 IF (SELECT starts_at FROM sarsa_booking.slot_claims WHERE id=claim)<>target OR (SELECT revision FROM sarsa_booking.bookings WHERE id=b)<>2 THEN RAISE EXCEPTION 'move not atomic';END IF;
 IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 THEN RAISE EXCEPTION 'move jobs';END IF;
 IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND payload->>'change_kind'='rescheduled')<>2 THEN RAISE EXCEPTION 'move emails';END IF;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request',target);
 IF value->>'code'<>'rescheduled' OR (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 THEN RAISE EXCEPTION 'duplicate move';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',op,claim,1,'Customer request');
 IF value->>'code'<>'request_conflict' THEN RAISE EXCEPTION 'cross-action replay';END IF;
 value:=sarsa_booking.studio_appointment_detail(repeat('a',64),'cancel-test','https://cancel.example',claim);
 IF value->>'policy_guidance'<>'staff_review' THEN RAISE EXCEPTION 'moving bypassed refund cutoff';END IF;
 IF (SELECT count(*) FROM sarsa_booking.accepted_payments WHERE booking_id=b)<>1 THEN RAISE EXCEPTION 'payment changed';END IF;
 -- Frozen, expired old creation must be claimed as obsolete, never recreated.
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload,next_attempt_at)
 VALUES(job,b,'booking_calendar','calendar',1,jsonb_build_object('id',b,'revision',1),clock_timestamp()-interval '1 day');
 value:=sarsa_booking.claim_google_delivery();
 IF value->>'id'<>job::text OR value->>'obsolete'<>'true' THEN RAISE EXCEPTION 'old creation not marked obsolete %',value;END IF;
 IF NOT sarsa_booking.finish_google_delivery(job,(value->>'lease_token')::uuid,'obsolete',NULL,NULL,NULL,15) THEN RAISE EXCEPTION 'cleanup not saved';END IF;
 IF (SELECT state FROM sarsa_booking.delivery_jobs WHERE id=job)<>'suppressed' THEN RAISE EXCEPTION 'old creation still pending';END IF;
 -- Simulate a near-term appointment to exercise the single late exception.
 UPDATE sarsa_booking.bookings SET starts_at=clock_timestamp()+interval '2 hours',ends_at=clock_timestamp()+interval '150 minutes' WHERE id=b;
 UPDATE sarsa_booking.slot_claims SET starts_at=(SELECT starts_at FROM sarsa_booking.bookings WHERE id=b),ends_at=(SELECT ends_at FROM sarsa_booking.bookings WHERE id=b) WHERE id=claim;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),claim,2,'Late customer request',target);
 IF value->>'code'<>'rescheduled' OR (SELECT reschedule_deadline_at FROM sarsa_booking.bookings WHERE id=b) IS NULL THEN RAISE EXCEPTION 'late exception failed %',value;END IF;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),claim,3,'Beyond deadline',target+interval '20 days');
 IF value->>'code'<>'time_unavailable' THEN RAISE EXCEPTION 'late deadline extended';END IF;
 UPDATE sarsa_booking.bookings SET starts_at=clock_timestamp()+interval '2 hours',ends_at=clock_timestamp()+interval '150 minutes' WHERE id=b;
 UPDATE sarsa_booking.slot_claims SET starts_at=(SELECT starts_at FROM sarsa_booking.bookings WHERE id=b),ends_at=(SELECT ends_at FROM sarsa_booking.bookings WHERE id=b) WHERE id=claim;
 value:=sarsa_booking.studio_appointment_reschedule(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),claim,3,'Repeated late request',target);
 IF value->>'code'<>'late_reschedule_used' THEN RAISE EXCEPTION 'late allowance repeated';END IF;

END $test$;
RESET ROLE;
SELECT 'Reschedule rollback fixture passed' result;
