-- Synthetic data only. Caller wraps in a transaction ending with ROLLBACK.
DO $test$
DECLARE first jsonb; again jsonb; other jsonb;
BEGIN
    INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','workbook-client'),('agency','workbook-agency');
    INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at)
      VALUES('client','workbook-client','workbook-app',1,repeat('x',120),clock_timestamp()),
            ('agency','workbook-agency','workbook-app',1,repeat('y',120),clock_timestamp());
    ASSERT sarsa_booking.claim_google_workbook('client','wrong') IS NULL;
    first:=sarsa_booking.claim_google_workbook('client','workbook-app');
    ASSERT first->>'action'='create';
    ASSERT sarsa_booking.claim_google_workbook('client','workbook-app') IS NULL;
    ASSERT NOT sarsa_booking.finish_google_workbook('client',gen_random_uuid(),'client-sheet');
    UPDATE sarsa_booking.google_workbooks SET lease_until=clock_timestamp()-interval '1 second' WHERE role='client';
    again:=sarsa_booking.claim_google_workbook('client','workbook-app');
    ASSERT again->>'action'='discover';
    ASSERT again->>'intent'=first->>'intent';
    ASSERT NOT sarsa_booking.finish_google_workbook('client',(first->>'lease')::uuid,'client-sheet');
    -- Reconnection during provisioning invalidates its completion, but never
    -- resets the once-only remote creation intent.
    UPDATE sarsa_booking.google_connections SET revision=revision+1 WHERE role='client';
    ASSERT NOT sarsa_booking.finish_google_workbook('client',(again->>'lease')::uuid,'client-sheet');
    again:=sarsa_booking.claim_google_workbook('client','workbook-app');
    ASSERT again->>'action'='discover';
    ASSERT sarsa_booking.finish_google_workbook('client',(again->>'lease')::uuid,'client-sheet');
    ASSERT sarsa_booking.claim_google_workbook('client','workbook-app')->>'action'='ready';
    other:=sarsa_booking.claim_google_workbook('agency','workbook-app');
    ASSERT other->>'action'='create';
    ASSERT other->>'intent'<>first->>'intent';
    BEGIN
      PERFORM sarsa_booking.finish_google_workbook('agency',(other->>'lease')::uuid,'client-sheet');
      RAISE EXCEPTION 'two owners accepted one spreadsheet';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    ASSERT sarsa_booking.finish_google_workbook('agency',(other->>'lease')::uuid,'agency-sheet');
END
$test$;
