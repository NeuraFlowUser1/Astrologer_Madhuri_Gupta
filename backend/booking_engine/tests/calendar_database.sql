DO $test$
DECLARE operation uuid := gen_random_uuid(); claim uuid; result jsonb;
        instant timestamptz := clock_timestamp()+interval '2 days';
BEGIN
    BEGIN
        result := sarsa_booking.close_calendar(operation,'synthetic-staff','Phone appointment',instant,instant+interval '45 minutes');
        ASSERT result->>'code'='closed',result::text;
        claim := (result->>'claim_id')::uuid;
        ASSERT sarsa_booking.close_calendar(operation,'synthetic-staff','Phone appointment',instant,instant+interval '45 minutes')->>'code'='existing';
        ASSERT sarsa_booking.close_calendar(operation,'other-staff','Phone appointment',instant,instant+interval '45 minutes')->>'code'='request_conflict';
        ASSERT sarsa_booking.close_calendar(gen_random_uuid(),'synthetic-staff','Overlapping',instant+interval '30 minutes',instant+interval '1 hour')->>'code'='time_already_reserved';
        ASSERT sarsa_booking.close_calendar(gen_random_uuid(),'synthetic-staff','Adjacent',instant+interval '45 minutes',instant+interval '1 hour')->>'code'='closed';
        ASSERT sarsa_booking.reopen_calendar(gen_random_uuid(),claim,'synthetic-staff','Phone appointment moved')->>'code'='reopened';
        ASSERT sarsa_booking.reopen_calendar(gen_random_uuid(),claim,'synthetic-staff','Repeated')->>'code'='already_open';
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.staff_calendar_actions WHERE claim_id=claim);
        ASSERT NOT has_function_privilege('sarsa_booking_runtime','sarsa_booking.close_calendar(uuid,text,text,timestamptz,timestamptz)','EXECUTE');
        RAISE EXCEPTION USING ERRCODE='ZT003',MESSAGE='rollback calendar fixtures';
    EXCEPTION WHEN SQLSTATE 'ZT003' THEN NULL;
    END;
    ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.staff_calendar_actions WHERE operation_id=operation);
END
$test$;
