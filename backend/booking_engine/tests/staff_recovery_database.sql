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

 value:=sarsa_booking.studio_support_change(repeat('b',64),'cancel-test','https://cancel.example',op,r,1,'contact_correction','Verified callback','pay_fixture','corrected@example.com','+919876543211',repeat('c',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency correction';END IF;
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',op,r,1,'contact_correction','Verified callback','pay_unknown','corrected@example.com','+919876543211',repeat('c',64));
 IF value->>'code'<>'support_verification_unavailable' THEN RAISE EXCEPTION 'unknown payment verification';END IF;
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',op,r,1,'contact_correction','Verified callback','pay_fixture','corrected@example.com','+919876543211',repeat('c',64));
 IF value->>'code'<>'support_saved' OR value->>'revision'<>'2' OR value->>'active'<>'true' THEN RAISE EXCEPTION 'correction failed %',value;END IF;
 IF (SELECT email FROM sarsa_booking.bookings WHERE id=b)<>'corrected@example.com' OR (SELECT receipt_revoked_at FROM sarsa_booking.bookings WHERE id=b) IS NULL THEN RAISE EXCEPTION 'old receipt still valid';END IF;
 IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 OR (SELECT starts_at FROM sarsa_booking.slot_claims WHERE id=claim)<>start_at THEN RAISE EXCEPTION 'correction delivery or capacity';END IF;
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',op,r,1,'contact_correction','Verified callback','pay_fixture','corrected@example.com','+919876543211',repeat('c',64));
 IF value->>'code'<>'support_saved' OR (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b)<>6 THEN RAISE EXCEPTION 'correction replay';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('f',64),repeat('a',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'wrong code';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('c',64),repeat('d',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'old credential reactivated';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('c',64),repeat('a',64));
 IF value->>'code'<>'receipt_restored' OR (SELECT receipt_digest FROM sarsa_booking.checkout_admissions WHERE request_id=r)<>repeat('a',64) OR (SELECT receipt_revoked_at FROM sarsa_booking.bookings WHERE id=b) IS NOT NULL THEN RAISE EXCEPTION 'restore not atomic';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('c',64),repeat('a',64));
 IF value->>'code'<>'receipt_restored' THEN RAISE EXCEPTION 'lost response replay';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('c',64),repeat('b',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'consumed code changed secret';END IF;
 op:=gen_random_uuid();
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',op,r,2,'receipt_recovery','Verified new callback','pay_fixture',NULL,NULL,repeat('e',64));
 IF value->>'code'<>'support_saved' OR value->>'revision'<>'2' THEN RAISE EXCEPTION 'replacement issue';END IF;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('c',64),repeat('a',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'superseded code accepted';END IF;
 FOR result IN SELECT n::text FROM generate_series(1,4)n LOOP
  value:=sarsa_booking.redeem_receipt_recovery(r,repeat('f',64),repeat('b',64));
 END LOOP;
 value:=sarsa_booking.redeem_receipt_recovery(r,repeat('e',64),repeat('b',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'five-try lock missing';END IF;
 IF (SELECT receipt_digest FROM sarsa_booking.checkout_admissions WHERE request_id=r)<>repeat('a',64) THEN RAISE EXCEPTION 'failed code replaced working receipt';END IF;
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),r,2,'receipt_recovery','Verified callback again','pay_fixture',NULL,NULL,repeat('f',64));
 IF value->>'code'<>'support_saved' THEN RAISE EXCEPTION 'third issue refused';END IF;
 value:=sarsa_booking.studio_support_change(repeat('a',64),'cancel-test','https://cancel.example',gen_random_uuid(),r,2,'receipt_recovery','Too many issues','pay_fixture',NULL,NULL,repeat('b',64));
 IF value->>'code'<>'support_wait' THEN RAISE EXCEPTION 'issue cap missing';END IF;
 IF has_table_privilege(current_user,'sarsa_booking.receipt_recoveries','SELECT') THEN RAISE EXCEPTION 'recovery raw grant';END IF;
END $test$;
RESET ROLE;
UPDATE sarsa_booking.receipt_recoveries SET expires_at=clock_timestamp()-interval '1 second' WHERE superseded_at IS NULL;
SET LOCAL ROLE sarsa_booking_web;
DO $expired$ DECLARE value jsonb;reference uuid;BEGIN
 SELECT request_id INTO reference FROM sarsa_booking.bookings LIMIT 1;
 value:=sarsa_booking.redeem_receipt_recovery(reference,repeat('f',64),repeat('b',64));
 IF value->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'expired recovery accepted';END IF;
END $expired$;
RESET ROLE;
SELECT 'Assisted recovery rollback fixture passed' result;
