-- Run as website role in a rollback-only transaction, using synthetic data.
DO $test$
DECLARE first jsonb; second jsonb; third jsonb;
BEGIN
    INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','refresh-subject');
    INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at)
      VALUES('client','refresh-subject','refresh-client',1,repeat('x',120),clock_timestamp());
    IF sarsa_booking.claim_google_refresh('client','wrong') IS NOT NULL THEN RAISE EXCEPTION 'wrong client'; END IF;
    first:=sarsa_booking.claim_google_refresh('client','refresh-client');
    IF first IS NULL THEN RAISE EXCEPTION 'missing claim'; END IF;
    IF sarsa_booking.claim_google_refresh('client','refresh-client') IS NOT NULL THEN RAISE EXCEPTION 'parallel claim'; END IF;
    IF sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',1,gen_random_uuid(),repeat('y',120),NULL) THEN RAISE EXCEPTION 'wrong lease'; END IF;
    UPDATE sarsa_booking.google_connections SET refresh_lease_until=clock_timestamp()-interval '1 second' WHERE role='client';
    IF sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',1,(first->>'lease')::uuid,repeat('y',120),NULL) THEN RAISE EXCEPTION 'expired lease'; END IF;
    second:=sarsa_booking.claim_google_refresh('client','refresh-client');
    IF second IS NULL OR second->>'lease'=first->>'lease' THEN RAISE EXCEPTION 'replacement lease'; END IF;
    IF sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',1,(first->>'lease')::uuid,repeat('y',120),NULL) THEN RAISE EXCEPTION 'stale lease'; END IF;
    -- Simulate a reconnect committed during network I/O. The new connection
    -- must be usable immediately and the older refresh must not overwrite it.
    UPDATE sarsa_booking.google_connections SET revision=2,encrypted_grant=repeat('n',120) WHERE role='client';
    third:=sarsa_booking.claim_google_refresh('client','refresh-client');
    IF third IS NULL THEN RAISE EXCEPTION 'new consent blocked'; END IF;
    IF sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',1,(second->>'lease')::uuid,repeat('y',120),NULL) THEN RAISE EXCEPTION 'old consent overwrite'; END IF;
    IF NOT sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',2,(third->>'lease')::uuid,repeat('z',120),NULL) THEN RAISE EXCEPTION 'valid save failed'; END IF;
    IF sarsa_booking.finish_google_refresh('client','refresh-client','refresh-subject',2,(third->>'lease')::uuid,repeat('y',120),NULL) THEN RAISE EXCEPTION 'replayed save'; END IF;
    IF (SELECT revision FROM sarsa_booking.google_connections WHERE role='client')<>2 THEN RAISE EXCEPTION 'refresh changed consent revision'; END IF;
    IF (SELECT encrypted_grant FROM sarsa_booking.google_connections WHERE role='client')<>repeat('z',120) THEN RAISE EXCEPTION 'saved grant lost'; END IF;
    UPDATE sarsa_booking.google_connections SET grant_expires_at=clock_timestamp()-interval '1 second' WHERE role='client';
    IF sarsa_booking.claim_google_refresh('client','refresh-client') IS NOT NULL THEN RAISE EXCEPTION 'expired grant'; END IF;
    BEGIN
      UPDATE sarsa_booking.google_connections SET refresh_lease=gen_random_uuid(),refresh_lease_until=clock_timestamp() WHERE role='client';
      RAISE EXCEPTION 'partial lease allowed';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
END
$test$;
