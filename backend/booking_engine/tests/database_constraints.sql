-- Development branch only. All synthetic rows are rolled back by the enclosing
-- exception block; failed assertions escape instead of being reported as passes.
DO $test$
DECLARE
    c uuid := gen_random_uuid(); c2 uuid := gen_random_uuid();
    r uuid := gen_random_uuid(); r2 uuid := gen_random_uuid();
    b uuid := gen_random_uuid(); b2 uuid := gen_random_uuid();
    start_time timestamptz := date_trunc('day', now()) + interval '30 days';
BEGIN
  BEGIN
    INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at)
      VALUES (c,repeat('a',64),now()+interval '1 day'),(c2,repeat('b',64),now()+interval '1 day');
    INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint)
      VALUES (r,c,repeat('c',64),repeat('d',64)),(r2,c2,repeat('e',64),repeat('f',64));
    INSERT INTO sarsa_booking.bookings(id,request_id,context_id,state,service_id,policy_version,
      service_snapshot,amount_paise,currency,starts_at,ends_at,practice_timezone,
      full_name,email,phone,hold_expires_at,receipt_expires_at)
      VALUES (b,r,c,'held','synthetic-test',repeat('a',64),'{}',100,'INR',start_time,
      start_time+interval '45 minutes','Asia/Kolkata','Synthetic Test','test@example.com',
      '+919876543210',now()+interval '10 minutes',start_time+interval '2 days'),
      (b2,r2,c2,'held','synthetic-test',repeat('a',64),'{}',100,'INR',start_time+interval '15 minutes',
      start_time+interval '1 hour','Asia/Kolkata','Synthetic Test','test@example.com',
      '+919876543210',now()+interval '10 minutes',start_time+interval '2 days');
    UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=b WHERE id=c;
    BEGIN
      UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=b2 WHERE id=c;
      RAISE EXCEPTION 'FAIL: cross-context checkout accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL; END;

    INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at)
      VALUES(gen_random_uuid(),b,start_time,start_time+interval '45 minutes');
    BEGIN
      INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at)
        VALUES(gen_random_uuid(),b2,start_time+interval '15 minutes',start_time+interval '1 hour');
      RAISE EXCEPTION 'FAIL: overlapping appointment accepted';
    EXCEPTION WHEN exclusion_violation THEN NULL; END;
    BEGIN
      INSERT INTO sarsa_booking.slot_claims(id,closure_reason,starts_at,ends_at)
        VALUES(gen_random_uuid(),'synthetic closure',start_time+interval '20 minutes',start_time+interval '1 hour');
      RAISE EXCEPTION 'FAIL: overlapping manual closure accepted';
    EXCEPTION WHEN exclusion_violation THEN NULL; END;
    INSERT INTO sarsa_booking.slot_claims(id,closure_reason,starts_at,ends_at)
      VALUES(gen_random_uuid(),'adjacent closure',start_time+interval '45 minutes',start_time+interval '1 hour');

    INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version,state,attempted_at,provider_order_id)
      VALUES(b,'syntheticMerchant','test','test-version','not_attempted',NULL,NULL);
    IF NOT sarsa_booking.start_order_creation(c,b) THEN
      RAISE EXCEPTION 'FAIL: first order intent not claimed';
    END IF;
    IF sarsa_booking.start_order_creation(c,b) THEN
      RAISE EXCEPTION 'FAIL: repeated creation allowed';
    END IF;
    IF sarsa_booking.abandon_unattempted(c,b) THEN
      RAISE EXCEPTION 'FAIL: attempted order released';
    END IF;
    UPDATE sarsa_booking.payment_orders SET state='ready',provider_order_id='order_synthetic' WHERE booking_id=b;
    UPDATE sarsa_booking.bookings SET created_at=now()-interval '20 minutes',
      hold_expires_at=now()-interval '1 minute' WHERE id=b;
    PERFORM sarsa_booking.expire_holds();
    IF (SELECT state FROM sarsa_booking.bookings WHERE id=b) <> 'expired' THEN
      RAISE EXCEPTION 'FAIL: hold not expired';
    END IF;
    IF sarsa_booking.start_order_creation(c,b) THEN
      RAISE EXCEPTION 'FAIL: expired order creation allowed';
    END IF;
    UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=b2 WHERE id=c2;
    INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version)
      VALUES(b2,'syntheticMerchant','test','test-version');
    IF NOT sarsa_booking.abandon_unattempted(c2,b2) OR NOT sarsa_booking.abandon_unattempted(c2,b2) THEN
      RAISE EXCEPTION 'FAIL: unattempted abandonment not idempotent';
    END IF;
    IF (SELECT active_checkout_id FROM sarsa_booking.checkout_contexts WHERE id=c2) IS NOT NULL THEN
      RAISE EXCEPTION 'FAIL: unattempted checkout still owns context';
    END IF;
    IF (SELECT active_checkout_id FROM sarsa_booking.checkout_contexts WHERE id=c) IS DISTINCT FROM b THEN
      RAISE EXCEPTION 'FAIL: expiry cleared unresolved ownership';
    END IF;
    BEGIN
      UPDATE sarsa_booking.payment_orders SET resolution='never_attempted_abandoned',resolved_at=now() WHERE booking_id=b;
      RAISE EXCEPTION 'FAIL: attempted order abandoned as unattempted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
      UPDATE sarsa_booking.payment_orders SET resolution='studio_reviewed',resolved_at=now() WHERE booking_id=b;
      RAISE EXCEPTION 'FAIL: unaudited studio resolution accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
      VALUES(gen_random_uuid(),b,'payment_review','client',1,'pay_first'),
            (gen_random_uuid(),b,'payment_review','client',1,'pay_second');
    IF (SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE booking_id=b) <> 2 THEN
      RAISE EXCEPTION 'FAIL: distinct financial exceptions collided';
    END IF;
    BEGIN
      INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
        VALUES(gen_random_uuid(),b,'payment_review','client',1,'pay_first');
      RAISE EXCEPTION 'FAIL: repeated event accepted twice';
    EXCEPTION WHEN unique_violation THEN NULL; END;
    BEGIN
      INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
        VALUES(gen_random_uuid(),b,'booking_calendar','customer',1);
      RAISE EXCEPTION 'FAIL: invalid kind/recipient accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
      VALUES(gen_random_uuid(),b,'booking_ack','customer',1),
            (gen_random_uuid(),b,'booking_ack','client',1),
            (gen_random_uuid(),b,'booking_calendar','calendar',1),
            (gen_random_uuid(),b,'booking_details','customer',1),
            (gen_random_uuid(),b,'sheet_booking','client_sheet',1),
            (gen_random_uuid(),b,'sheet_booking','agency_sheet',1);
    BEGIN
      UPDATE sarsa_booking.bookings SET phone='' WHERE id=b;
      RAISE EXCEPTION 'FAIL: empty mandatory phone accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
      UPDATE sarsa_booking.bookings SET email='' WHERE id=b;
      RAISE EXCEPTION 'FAIL: empty mandatory email accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    RAISE EXCEPTION USING ERRCODE='ZT001', MESSAGE='synthetic checks completed; rollback fixtures';
  EXCEPTION WHEN SQLSTATE 'ZT001' THEN NULL;
  END;
  IF EXISTS(SELECT 1 FROM sarsa_booking.bookings WHERE id IN (b,b2)) THEN
    RAISE EXCEPTION 'FAIL: synthetic rows persisted';
  END IF;
END
$test$;
