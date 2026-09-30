-- Execute inside a transaction with the runtime role, then ROLLBACK.
-- Only synthetic digests, identities and ciphertext-shaped fixtures.
DO $test$
DECLARE a text:=repeat('a',64); b text:=repeat('b',64); s text:=repeat('c',64);
        c1 text:=repeat('d',64); c2 text:=repeat('e',64); c3 text:=repeat('f',64);
        c4 text:=repeat('1',64); c5 text:=repeat('2',64); payload text:=repeat('x',120);
        result jsonb; revision bigint;
BEGIN
    IF sarsa_booking.start_google_attempt(a,b,'signin','client',payload,NULL,'synthetic-client','https://sarsa.example') IS NOT TRUE THEN RAISE EXCEPTION 'start failed'; END IF;
    IF sarsa_booking.finish_google_signin(a,'synthetic-subject',s) IS NOT FALSE THEN RAISE EXCEPTION 'unconsumed finish'; END IF;
    IF sarsa_booking.consume_google_attempt(a,repeat('0',64),'signin','synthetic-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'wrong browser'; END IF;
    IF sarsa_booking.consume_google_attempt(a,b,'connect','synthetic-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'wrong flow'; END IF;
    result:=sarsa_booking.consume_google_attempt(a,b,'signin','synthetic-client','https://sarsa.example');
    IF result->>'role' IS DISTINCT FROM 'client' THEN RAISE EXCEPTION 'consume failed'; END IF;
    IF sarsa_booking.consume_google_attempt(a,b,'signin','synthetic-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'replayed consume'; END IF;
    IF sarsa_booking.finish_google_signin(a,'synthetic-subject',s) IS NOT TRUE THEN RAISE EXCEPTION 'signin failed'; END IF;
    IF sarsa_booking.finish_google_signin(a,'synthetic-subject',repeat('3',64)) IS NOT FALSE THEN RAISE EXCEPTION 'replayed finish'; END IF;
    IF sarsa_booking.studio_session(s,'synthetic-client','https://wrong.example') IS NOT NULL THEN RAISE EXCEPTION 'wrong origin'; END IF;
    IF sarsa_booking.studio_session(s,'wrong-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'wrong client'; END IF;
    IF sarsa_booking.start_google_attempt(c1,b,'connect','agency',payload,s,'synthetic-client','https://sarsa.example') IS NOT FALSE THEN RAISE EXCEPTION 'cross role'; END IF;
    PERFORM sarsa_booking.start_google_attempt(c1,b,'connect','client',payload,s,'synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.start_google_attempt(c2,b,'connect','client',payload,s,'synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.consume_google_attempt(c1,b,'connect','synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.consume_google_attempt(c2,b,'connect','synthetic-client','https://sarsa.example');
    IF sarsa_booking.finish_google_connection(c2,'other-subject',payload,NULL) IS NOT FALSE THEN RAISE EXCEPTION 'wrong subject'; END IF;
    IF sarsa_booking.finish_google_connection(c2,'synthetic-subject',payload,NULL) IS NOT TRUE THEN RAISE EXCEPTION 'connection failed'; END IF;
    IF sarsa_booking.finish_google_connection(c1,'synthetic-subject',repeat('z',120),NULL) IS NOT FALSE THEN RAISE EXCEPTION 'stale overwrite'; END IF;
    IF sarsa_booking.finish_google_connection(c2,'synthetic-subject',payload,NULL) IS NOT FALSE THEN RAISE EXCEPTION 'repeat connection'; END IF;
    SELECT g.revision INTO revision FROM sarsa_booking.google_connections g WHERE role='client';
    IF revision IS DISTINCT FROM 1::bigint THEN RAISE EXCEPTION 'revision changed'; END IF;
    PERFORM sarsa_booking.start_google_attempt(c3,b,'signin','client',payload,NULL,'synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.consume_google_attempt(c3,b,'signin','synthetic-client','https://sarsa.example');
    IF sarsa_booking.finish_google_signin(c3,'changed-subject',repeat('4',64)) IS NOT FALSE THEN RAISE EXCEPTION 'identity changed'; END IF;
    UPDATE sarsa_booking.google_attempts SET expires_at=clock_timestamp()-interval '1 second' WHERE state_digest=c3;
    IF sarsa_booking.finish_google_signin(c3,'synthetic-subject',repeat('4',64)) IS NOT FALSE THEN RAISE EXCEPTION 'expired attempt'; END IF;
    PERFORM sarsa_booking.start_google_attempt(c4,b,'connect','client',payload,s,'synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.consume_google_attempt(c4,b,'connect','synthetic-client','https://sarsa.example');
    IF sarsa_booking.finish_google_connection(c4,'synthetic-subject',payload,clock_timestamp()-interval '1 second') IS NOT FALSE THEN RAISE EXCEPTION 'expired grant'; END IF;
    PERFORM sarsa_booking.start_google_attempt(c5,b,'connect','client',payload,s,'synthetic-client','https://sarsa.example');
    PERFORM sarsa_booking.studio_logout(s,'synthetic-client','https://sarsa.example');
    IF sarsa_booking.studio_session(s,'synthetic-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'revoked session accepted'; END IF;
    IF sarsa_booking.consume_google_attempt(c5,b,'connect','synthetic-client','https://sarsa.example') IS NOT NULL THEN RAISE EXCEPTION 'revoked consume'; END IF;
    IF sarsa_booking.finish_google_connection(c4,'synthetic-subject',repeat('z',120),NULL) IS NOT FALSE THEN RAISE EXCEPTION 'logout during exchange'; END IF;
    IF (SELECT encrypted_grant FROM sarsa_booking.google_connections WHERE role='client') IS DISTINCT FROM payload THEN RAISE EXCEPTION 'old grant lost'; END IF;
    FOR i IN 1..20 LOOP
      result:=sarsa_booking.consume_request_limit('studio',repeat('8',64));
      IF result->>'allowed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'quota early'; END IF;
    END LOOP;
    result:=sarsa_booking.consume_request_limit('studio',repeat('8',64));
    IF result->>'allowed' IS DISTINCT FROM 'false' THEN RAISE EXCEPTION 'quota not enforced'; END IF;
END
$test$;
