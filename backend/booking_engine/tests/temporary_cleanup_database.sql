-- Isolated rollback fixture only; no permanent/customer data is deleted.
INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('agency','cleanup-fixture')
 ON CONFLICT(role) DO NOTHING;
INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES
 (repeat('1',64),'agency','cleanup-fixture','cleanup-test','https://cleanup.example',clock_timestamp()-interval '2 days'),
 (repeat('2',64),'agency','cleanup-fixture','cleanup-test','https://cleanup.example',clock_timestamp()-interval '2 days'),
 (repeat('3',64),'agency','cleanup-fixture','cleanup-test','https://cleanup.example',clock_timestamp()+interval '1 day');
INSERT INTO sarsa_booking.google_attempts(state_digest,browser_digest,purpose,role,encrypted_attempt,
 session_digest,client_id,origin,expires_at) VALUES
 (repeat('1',64),repeat('a',64),'connect','agency',repeat('x',120),repeat('1',64),'cleanup-test','https://cleanup.example',clock_timestamp()-interval '2 days'),
 (repeat('2',64),repeat('a',64),'connect','agency',repeat('x',120),repeat('2',64),'cleanup-test','https://cleanup.example',clock_timestamp()+interval '1 hour');
INSERT INTO sarsa_booking.google_attempts(state_digest,browser_digest,purpose,role,encrypted_attempt,
 client_id,origin,expires_at)
 SELECT md5(n::text)||md5(n::text),repeat('a',64),'signin','agency',repeat('x',120),
 'cleanup-test','https://cleanup.example',clock_timestamp()-interval '3 days' FROM generate_series(1,501)n;
INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
 SELECT 'context',md5(n::text)||md5(n::text),clock_timestamp()-interval '3 days',clock_timestamp()-interval '2 days',1
 FROM generate_series(1,501)n;
INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
 VALUES('context',repeat('a',64),clock_timestamp()-interval '2 hours',clock_timestamp()-interval '1 hour',1);
SET LOCAL ROLE sarsa_booking_web;
DO $test$ DECLARE first jsonb;second jsonb; BEGIN
 IF has_table_privilege(current_user,'sarsa_booking.request_limits','DELETE')
  OR has_table_privilege(current_user,'sarsa_booking.google_attempts','DELETE')
  OR has_table_privilege(current_user,'sarsa_booking.studio_sessions','DELETE') THEN
  RAISE EXCEPTION 'Broad deletion privilege leaked';END IF;
 first:=sarsa_booking.cleanup_temporary_records();
 IF first->'removed'->>'attempts'<>'500' OR first->'removed'->>'limits'<>'500' THEN
  RAISE EXCEPTION 'Batch limit failed %',first;END IF;
 second:=sarsa_booking.cleanup_temporary_records();
 IF second->'removed'->>'attempts'<>'2' OR second->'removed'->>'sessions'<>'1'
  OR second->'removed'->>'limits'<>'1' THEN RAISE EXCEPTION 'Continuation failed %',second;END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_sessions WHERE digest=repeat('2',64))
  OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_sessions WHERE digest=repeat('3',64))
  OR NOT EXISTS(SELECT 1 FROM sarsa_booking.request_limits WHERE key_digest=repeat('a',64)) THEN
  RAISE EXCEPTION 'Protected reference, live session or grace period deleted';END IF;
 IF sarsa_booking.cleanup_temporary_records()->>'processed'<>'0' THEN
  RAISE EXCEPTION 'Idempotent empty pass failed';END IF;
END $test$;
RESET ROLE;
SELECT 'Bounded cleanup and session-reference rollback fixture passed' AS result;
