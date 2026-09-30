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

 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,state,last_error_code)
 VALUES(job,b,'sheet_booking','client_sheet',1,'attention','google_record_assignment_unavailable');
 value:=sarsa_booking.studio_booking_lookup(repeat('b',64),'cancel-test','https://cancel.example',r);
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency lookup allowed';END IF;
 value:=sarsa_booking.studio_booking_lookup(repeat('a',64),'cancel-test','https://cancel.example',r);
 IF value->>'code'<>'ok' OR value->>'claim_id'<>claim::text OR jsonb_array_length(value->'payments')<>1 OR value::text LIKE '%receipt_digest%' THEN RAISE EXCEPTION 'lookup contract %',value;END IF;
 value:=sarsa_booking.studio_inbox_retry(repeat('b',64),'cancel-test','https://cancel.example',op,'delivery:'||job,0,'Fixed connection');
 IF value->>'code'<>'item_unavailable' THEN RAISE EXCEPTION 'agency retries client work';END IF;
 value:=sarsa_booking.studio_inbox_retry(repeat('a',64),'cancel-test','https://cancel.example',op,'delivery:'||job,0,'Fixed connection');
 IF value->>'code'<>'retry_queued' OR (SELECT state FROM sarsa_booking.delivery_jobs WHERE id=job)<>'pending' THEN RAISE EXCEPTION 'retry not queued %',value;END IF;
 value:=sarsa_booking.studio_inbox_retry(repeat('a',64),'cancel-test','https://cancel.example',op,'delivery:'||job,0,'Fixed connection');
 IF value->>'code'<>'retry_queued' THEN RAISE EXCEPTION 'retry lost after issue disappears';END IF;
 value:=sarsa_booking.studio_inbox_review(repeat('a',64),'cancel-test','https://cancel.example',op,'delivery:'||job,0,'Fixed connection');
 IF value->>'code'<>'request_conflict' THEN RAISE EXCEPTION 'retry became a note';END IF;
 -- A currently leased provider operation must not be interrupted.
 UPDATE sarsa_booking.delivery_jobs SET state='attention',lease_token=lease,lease_expires_at=clock_timestamp()+interval '2 minutes' WHERE id=job;
 value:=sarsa_booking.studio_inbox_retry(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'delivery:'||job,1,'Try again');
 IF value->>'code'<>'retry_wait' THEN RAISE EXCEPTION 'retry cooldown missing';END IF;
 job:=gen_random_uuid();
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,state,first_attempt_at,send_deadline_at,destination)
 VALUES(job,b,'booking_ack','customer',1,'attention',clock_timestamp()-interval '24 hours',start_at,'no-send@example.com');
 value:=sarsa_booking.studio_inbox_retry(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'delivery:'||job,0,'Try old email');
 IF value->>'code'<>'retry_unavailable' THEN RAISE EXCEPTION 'expired email retry allowed';END IF;
 IF (SELECT first_attempt_at FROM sarsa_booking.delivery_jobs WHERE id=job)>clock_timestamp()-interval '23 hours' THEN RAISE EXCEPTION 'attempt reset';END IF;
 INSERT INTO sarsa_booking.payment_cases(id,booking_id,event_key,reason) VALUES(gen_random_uuid(),b,'pay_fixture:refund_observed','refund_observed') RETURNING id INTO job;
 value:=sarsa_booking.studio_inbox_retry(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'payment:'||job,0,'Check provider evidence');
 IF value->>'code'<>'retry_queued' OR NOT(SELECT recovery_followup FROM sarsa_booking.payment_orders WHERE booking_id=b) THEN RAISE EXCEPTION 'payment recheck absent';END IF;
 IF (SELECT resolved_at FROM sarsa_booking.payment_cases WHERE id=job) IS NOT NULL OR (SELECT count(*) FROM sarsa_booking.accepted_payments WHERE booking_id=b)<>1 THEN RAISE EXCEPTION 'staff invented financial resolution';END IF;

 value:=sarsa_booking.studio_inbox_refund_verified(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'payment:'||job,1,'Checked refund');
 IF value->>'code'<>'refund_not_verified' THEN RAISE EXCEPTION 'note invented refund';END IF;
 INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,amount_paise,currency,refunded_paise,captured)
 VALUES(gen_random_uuid(),b,'SyntheticMerchant','live','pay_fixture','order_fixture',repeat('c',64),'captured',100,'INR',50,true);
 value:=sarsa_booking.studio_inbox_refund_verified(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'payment:'||job,1,'Checked partial refund');
 IF value->>'code'<>'refund_not_verified' THEN RAISE EXCEPTION 'partial refund closed full case';END IF;
 INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,amount_paise,currency,refunded_paise,captured)
 VALUES(gen_random_uuid(),b,'SyntheticMerchant','live','pay_fixture','order_fixture',repeat('d',64),'refunded',100,'INR',100,true);
 value:=sarsa_booking.studio_inbox_refund_verified(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),'payment:'||job,1,'Checked refund');
 IF value->>'code'<>'refund_not_verified' THEN RAISE EXCEPTION 'unpaid confirmed appointment hidden';END IF;
 value:=sarsa_booking.studio_appointment_cancel(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),claim,1,'Customer cancelled after refund');
 IF value->>'code'<>'cancelled' THEN RAISE EXCEPTION 'cancel prerequisite failed';END IF;
 op:=gen_random_uuid();
 value:=sarsa_booking.studio_inbox_refund_verified(repeat('a',64),'cancel-test','https://cancel.example',op,'payment:'||job,1,'Checked full refund');
 IF value->>'code'<>'refund_verified' OR (SELECT resolved_at FROM sarsa_booking.payment_cases WHERE id=job) IS NULL THEN RAISE EXCEPTION 'verified refund not saved %',value;END IF;
 value:=sarsa_booking.studio_inbox_refund_verified(repeat('a',64),'cancel-test','https://cancel.example',op,'payment:'||job,1,'Checked full refund');
 IF value->>'code'<>'refund_verified' THEN RAISE EXCEPTION 'refund replay failed';END IF;
 value:=sarsa_booking.studio_inbox_refund_verified(repeat('b',64),'cancel-test','https://cancel.example',op,'payment:'||job,1,'Checked full refund');
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency finance access';END IF;
END $test$;
RESET ROLE;
SELECT 'Staff support rollback fixture passed' result;
