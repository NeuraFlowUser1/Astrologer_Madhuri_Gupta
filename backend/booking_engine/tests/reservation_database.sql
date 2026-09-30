DO $test$
DECLARE c1 uuid := gen_random_uuid(); c2 uuid := gen_random_uuid();
        r1 uuid := gen_random_uuid(); r2 uuid := gen_random_uuid();
        r3 uuid := gen_random_uuid(); r4 uuid := gen_random_uuid();
        extra uuid; i integer; v text; start_at timestamptz; payload jsonb; expected jsonb; result jsonb; b uuid;
        day date := (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date+1;
BEGIN
    BEGIN
        -- Fixtures remain inside this rollback subtransaction. Never publish
        -- these merchant values, contacts or settings to the real site.
        IF extract(isodow FROM day)=7 THEN day := day+1; END IF;
        start_at := (day::text||' 10:00:00 Asia/Kolkata')::timestamptz;
        SELECT policy_version INTO v FROM sarsa_booking.intake_settings;
        INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at)
          VALUES(c1,repeat('4',64),clock_timestamp()+interval '24 hours'),
                (c2,repeat('5',64),clock_timestamp()+interval '24 hours');
        payload := jsonb_build_object('service_id','kundli-prediction','quote_version',v,
           'starts_at',to_char(start_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'full_name','Synthetic Test','email','test@example.invalid','phone','+919876543210');
        SELECT jsonb_build_object('merchant_id',merchant_id,'mode',payment_mode,'credential_version',credential_version) INTO expected FROM sarsa_booking.intake_settings;
        GRANT sarsa_booking_runtime TO neondb_owner WITH SET TRUE;
        SET LOCAL ROLE sarsa_booking_runtime;
        ASSERT sarsa_booking.admit_checkout(c1,r1,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.admit_checkout(c1,r1,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.admit_checkout(c1,r1,repeat('c',64),repeat('b',64))='request_conflict';
        ASSERT sarsa_booking.admit_checkout(c2,r1,repeat('a',64),repeat('b',64))='request_conflict';
        ASSERT sarsa_booking.admit_checkout(c1,r1,NULL,repeat('b',64))='request_conflict';
        ASSERT sarsa_booking.reserve_configured_checkout(c1,r1,repeat('a',64),NULL,payload,expected)->>'code'='request_conflict';
        result := sarsa_booking.reserve_configured_checkout(c1,r1,repeat('a',64),repeat('b',64),payload,expected);
        ASSERT result->>'code'='intake_closed',result::text;
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.checkout_admissions WHERE context_id=c1);
        RESET ROLE;
        UPDATE sarsa_booking.intake_settings SET public_open=true,merchant_id='syntheticOnly',
          payment_mode='live',credential_version='syntheticOnly';
        expected:=jsonb_build_object('merchant_id','syntheticOnly','mode','live','credential_version','syntheticOnly');
        SET LOCAL ROLE sarsa_booking_runtime;
        ASSERT sarsa_booking.admit_checkout(c1,r2,repeat('a',64),repeat('b',64))='pending';
        result := sarsa_booking.reserve_configured_checkout(c1,r2,repeat('a',64),repeat('b',64),payload,expected);
        ASSERT result->>'code'='reserved',result::text;
        b := (result->>'booking_id')::uuid;
        ASSERT (SELECT amount_paise=250000 AND ends_at=starts_at+interval '30 minutes'
            AND service_snapshot->>'meeting_platform'='Google Meet' FROM sarsa_booking.bookings WHERE id=b);
        ASSERT (SELECT merchant_id='syntheticOnly' AND state='not_attempted'
                FROM sarsa_booking.payment_orders WHERE booking_id=b);
        ASSERT sarsa_booking.reserve_configured_checkout(c1,r2,repeat('a',64),repeat('b',64),payload,expected)->>'code'='existing';
        ASSERT sarsa_booking.admit_checkout(c1,r3,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.reserve_configured_checkout(c1,r3,repeat('a',64),repeat('b',64),payload,expected)->>'code'='checkout_in_progress';
        ASSERT sarsa_booking.admit_checkout(c2,r4,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.reserve_configured_checkout(c2,r4,repeat('a',64),repeat('b',64),payload,expected)->>'code'='time_unavailable';
        ASSERT sarsa_booking.abandon_unattempted(c1,b);
        -- A rejected request cannot mutate into a new attempt under its old ID.
        ASSERT sarsa_booking.reserve_configured_checkout(c2,r4,repeat('a',64),repeat('b',64),payload,expected)->>'code'='request_rejected';
        extra := gen_random_uuid();
        ASSERT sarsa_booking.admit_checkout(c2,extra,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.reserve_configured_checkout(c2,extra,repeat('a',64),repeat('b',64),
            payload||jsonb_build_object('quote_version',repeat('0',64)),expected)->>'code'='quote_changed';
        extra := gen_random_uuid();
        ASSERT sarsa_booking.admit_checkout(c2,extra,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.reserve_configured_checkout(c2,extra,repeat('a',64),repeat('b',64),
            payload||jsonb_build_object('starts_at',day::text||'T12:00:00+05:30'),expected)->>'code'='time_unavailable';
        extra := gen_random_uuid();
        ASSERT sarsa_booking.admit_checkout(c2,extra,repeat('a',64),repeat('b',64))='pending';
        ASSERT sarsa_booking.reserve_configured_checkout(c2,extra,repeat('a',64),repeat('b',64),
            payload||jsonb_build_object('starts_at',day::text||'T10:00:00'),expected)->>'code'='invalid_time';
        FOR i IN 1..2 LOOP
            ASSERT sarsa_booking.admit_checkout(c2,gen_random_uuid(),repeat('a',64),repeat('b',64))='pending';
        END LOOP;
        ASSERT sarsa_booking.admit_checkout(c2,gen_random_uuid(),repeat('a',64),repeat('b',64))='rate_limited';
        ASSERT (SELECT count(*)=6 FROM sarsa_booking.checkout_admissions WHERE context_id=c2);
        extra := gen_random_uuid();
        ASSERT sarsa_booking.admit_checkout(c1,extra,repeat('a',64),repeat('b',64))='pending';
        result := sarsa_booking.reserve_configured_checkout(c1,extra,repeat('a',64),repeat('b',64),payload,expected);
        ASSERT result->>'code'='reserved',result::text;
        b := (result->>'booking_id')::uuid;
        ASSERT sarsa_booking.start_order_creation(c1,b);
        ASSERT sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly',NULL)='creation_unknown';
        ASSERT NOT sarsa_booking.start_order_creation(c1,b);
        ASSERT sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly','order_synthetic')='ready';
        ASSERT sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly',NULL)='ready';
        ASSERT NOT sarsa_booking.abandon_unattempted(c1,b);
        BEGIN
            PERFORM sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly','order_other');
            RAISE EXCEPTION 'conflicting provider order was accepted';
        EXCEPTION WHEN SQLSTATE 'P0503' THEN NULL;
        END;
        ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
            'pay_primary','order_synthetic',repeat('d',64),'captured',250000,'INR',0,true)='confirmed';
        ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
            'pay_primary','order_synthetic',repeat('d',64),'captured',250000,'INR',0,true)='confirmed';
        ASSERT (SELECT count(*)=5 FROM sarsa_booking.delivery_jobs WHERE booking_id=b);
        ASSERT (SELECT active_checkout_id IS NULL FROM sarsa_booking.checkout_contexts WHERE id=c1);
        FOR i IN 1..2 LOOP
            ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
                'pay_extra'||i,'order_synthetic',repeat('e',64),'captured',250000,'INR',0,true)='payment_needs_review';
        END LOOP;
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.payment_cases WHERE booking_id=b);
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='payment_review');
        ASSERT (SELECT state='confirmed' FROM sarsa_booking.bookings WHERE id=b);
        ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
            'pay_primary','order_synthetic',repeat('f',64),'refunded',250000,'INR',250000,true)='payment_needs_review';
        ASSERT (SELECT state='confirmed' FROM sarsa_booking.bookings WHERE id=b);
        -- New checkout after confirmed booking, then a capture after its hold
        -- expires: money is preserved for review without stealing capacity.
        extra := gen_random_uuid();
        ASSERT sarsa_booking.admit_checkout(c1,extra,repeat('a',64),repeat('b',64))='pending';
        result := sarsa_booking.reserve_configured_checkout(c1,extra,repeat('a',64),repeat('b',64),
            payload||jsonb_build_object('starts_at',day::text||'T10:30:00+05:30'),expected);
        ASSERT result->>'code'='reserved',result::text;
        b := (result->>'booking_id')::uuid;
        ASSERT sarsa_booking.start_order_creation(c1,b);
        PERFORM sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly','order_late');
        UPDATE sarsa_booking.bookings SET created_at=clock_timestamp()-interval '20 minutes',
            hold_expires_at=clock_timestamp()-interval '10 minutes' WHERE id=b;
        ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
            'pay_late','order_late',repeat('1',64),'captured',250000,'INR',0,true)='payment_needs_review';
        ASSERT (SELECT state='payment_review' FROM sarsa_booking.bookings WHERE id=b);
        ASSERT (SELECT active_checkout_id=b FROM sarsa_booking.checkout_contexts WHERE id=c1);
        ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE booking_id=b AND released_at IS NULL);
        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');
        RESET ROLE;
        RAISE EXCEPTION USING ERRCODE='ZT002',MESSAGE='rollback synthetic reservations';
    EXCEPTION WHEN SQLSTATE 'ZT002' THEN NULL;
    END;
    ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.checkout_contexts WHERE id IN (c1,c2));
    ASSERT NOT (SELECT public_open FROM sarsa_booking.intake_settings);
END
$test$;
