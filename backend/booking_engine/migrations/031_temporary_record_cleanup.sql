-- Approved housekeeping only. Permanent booking, provider and audit records
-- are deliberately outside this bounded function's deletion authority.
CREATE INDEX studio_sessions_expiry ON sarsa_booking.studio_sessions(expires_at);
CREATE INDEX google_attempts_session ON sarsa_booking.google_attempts(session_digest)
 WHERE session_digest IS NOT NULL;

CREATE FUNCTION sarsa_booking.cleanup_temporary_records()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog,sarsa_booking AS $body$
DECLARE cutoff timestamptz:=clock_timestamp()-interval '24 hours';
 attempts_removed integer; sessions_removed integer; limits_removed integer;
BEGIN
 IF NOT pg_try_advisory_xact_lock(4004311) THEN
  RETURN jsonb_build_object('processed',0,'removed',jsonb_build_object('attempts',0,'sessions',0,'limits',0));
 END IF;
 WITH expired AS (
  SELECT state_digest FROM sarsa_booking.google_attempts WHERE expires_at<cutoff
   ORDER BY expires_at,state_digest LIMIT 500 FOR UPDATE SKIP LOCKED
 ) DELETE FROM sarsa_booking.google_attempts a USING expired e WHERE a.state_digest=e.state_digest;
 GET DIAGNOSTICS attempts_removed=ROW_COUNT;
 WITH expired AS (
  SELECT s.digest FROM sarsa_booking.studio_sessions s WHERE s.expires_at<cutoff
   AND NOT EXISTS(SELECT 1 FROM sarsa_booking.google_attempts a WHERE a.session_digest=s.digest)
   ORDER BY s.expires_at,s.digest LIMIT 500 FOR UPDATE OF s SKIP LOCKED
 ) DELETE FROM sarsa_booking.studio_sessions s USING expired e WHERE s.digest=e.digest;
 GET DIAGNOSTICS sessions_removed=ROW_COUNT;
 WITH expired AS (
  SELECT scope,key_digest,window_start FROM sarsa_booking.request_limits WHERE expires_at<cutoff
   ORDER BY expires_at,scope,key_digest,window_start LIMIT 500 FOR UPDATE SKIP LOCKED
 ) DELETE FROM sarsa_booking.request_limits r USING expired e
   WHERE r.scope=e.scope AND r.key_digest=e.key_digest AND r.window_start=e.window_start;
 GET DIAGNOSTICS limits_removed=ROW_COUNT;
 RETURN jsonb_build_object('processed',CASE WHEN attempts_removed+sessions_removed+limits_removed>0 THEN 1 ELSE 0 END,
  'removed',jsonb_build_object('attempts',attempts_removed,'sessions',sessions_removed,'limits',limits_removed));
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.cleanup_temporary_records() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.cleanup_temporary_records() TO sarsa_booking_runtime;
