DO $test$
DECLARE i integer; result jsonb;
BEGIN
    BEGIN
        GRANT sarsa_booking_runtime TO neondb_owner WITH SET TRUE;
        SET LOCAL ROLE sarsa_booking_runtime;
        FOR i IN 1..20 LOOP
            result:=sarsa_booking.consume_request_limit('context',repeat('c',64));
            ASSERT (result->>'allowed')::boolean;
        END LOOP;
        result:=sarsa_booking.consume_request_limit('context',repeat('c',64));
        ASSERT NOT (result->>'allowed')::boolean;
        ASSERT (result->>'retry_after')::integer BETWEEN 1 AND 3600;
        ASSERT (sarsa_booking.consume_request_limit('receipt',repeat('c',64))->>'allowed')::boolean;
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.request_limits WHERE key_digest=repeat('c',64));
        RESET ROLE;
        RAISE EXCEPTION USING ERRCODE='ZT011',MESSAGE='rollback request counters';
    EXCEPTION WHEN SQLSTATE 'ZT011' THEN NULL;
    END;
    ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.request_limits WHERE key_digest=repeat('c',64));
END
$test$;
