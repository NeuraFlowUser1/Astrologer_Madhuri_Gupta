-- No public/observer read touches this table. Work and the existing rescue
-- plan retain small durable lane evidence; queue publication is not success.
CREATE TABLE sarsa_booking.recovery_lanes(
 lane text PRIMARY KEY CHECK(lane IN ('email','email_events','google','payment','payment_events','contact_email','contact_google','maintenance','control_publication')),
 latest_run uuid,last_attempt_at timestamptz,last_completed_at timestamptz,
 active_until timestamptz,outcome text NOT NULL DEFAULT 'unchecked' CHECK(outcome IN ('unchecked','attempted','completed','failed')),
 processed integer NOT NULL DEFAULT 0 CHECK(processed BETWEEN 0 AND 2)
);
INSERT INTO sarsa_booking.recovery_lanes(lane) SELECT unnest(ARRAY['email','email_events','google','payment','payment_events','contact_email','contact_google','maintenance','control_publication']);
CREATE TABLE sarsa_booking.recovery_lane_incidents(
 lane text NOT NULL REFERENCES sarsa_booking.recovery_lanes(lane),code text NOT NULL CHECK(code IN ('execution_failed','result_invalid','result_stale')),
 first_seen_at timestamptz NOT NULL,last_seen_at timestamptz NOT NULL,occurrences integer NOT NULL CHECK(occurrences>0),PRIMARY KEY(lane,code)
);
CREATE FUNCTION sarsa_booking.begin_recovery_lane(p_lane text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE id uuid:=gen_random_uuid();
BEGIN
 UPDATE sarsa_booking.recovery_lanes SET latest_run=id,last_attempt_at=clock_timestamp(),
   active_until=clock_timestamp()+interval '90 seconds',outcome='attempted'
 WHERE lane=p_lane AND (active_until IS NULL OR active_until<=clock_timestamp());
 IF NOT FOUND THEN RETURN NULL; END IF; RETURN id;
END $body$;
CREATE FUNCTION sarsa_booking.finish_recovery_lane(p_lane text,p_run uuid,p_success boolean,p_processed integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
BEGIN
 IF p_success IS NULL OR p_processed IS NULL OR p_processed<0 OR p_processed>(CASE WHEN p_lane='email_events' THEN 2 ELSE 1 END) THEN RETURN false; END IF;
 UPDATE sarsa_booking.recovery_lanes SET outcome=CASE WHEN p_success THEN 'completed' ELSE 'failed' END,
   last_completed_at=CASE WHEN p_success THEN clock_timestamp() ELSE last_completed_at END,processed=p_processed,active_until=NULL
 WHERE lane=p_lane AND latest_run=p_run AND outcome='attempted' AND active_until>clock_timestamp();
 IF NOT FOUND THEN RETURN false; END IF;
 IF NOT p_success THEN
  INSERT INTO sarsa_booking.recovery_lane_incidents(lane,code,first_seen_at,last_seen_at,occurrences)
   VALUES(p_lane,'execution_failed',clock_timestamp(),clock_timestamp(),1) ON CONFLICT(lane,code) DO UPDATE
   SET last_seen_at=excluded.last_seen_at,occurrences=least(2147483647,sarsa_booking.recovery_lane_incidents.occurrences::bigint+1)::integer;
 END IF;RETURN true;
END $body$;
CREATE FUNCTION sarsa_booking.recovery_progress(p_hints jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE evidence jsonb;
BEGIN
 IF jsonb_typeof(p_hints) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='recovery manifest invalid'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_hints))<>9 OR
   EXISTS(SELECT 1 FROM jsonb_object_keys(p_hints) k WHERE NOT EXISTS(SELECT 1 FROM sarsa_booking.recovery_lanes WHERE lane=k)) THEN
   RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='recovery manifest invalid'; END IF;
 -- An empty durable lane is a completed check. Deferred or failed work does
 -- not manufacture completion, and an active attempt cannot be overwritten.
 UPDATE sarsa_booking.recovery_lanes SET outcome='completed',last_attempt_at=clock_timestamp(),last_completed_at=clock_timestamp(),processed=0
 WHERE p_hints->lane='null'::jsonb AND (active_until IS NULL OR active_until<=clock_timestamp());
 SELECT jsonb_object_agg(lane,jsonb_build_object('attempted_at',floor(extract(epoch FROM last_attempt_at)*1000)::bigint,
   'completed_at',floor(extract(epoch FROM last_completed_at)*1000)::bigint,'outcome',outcome,'processed',processed)) INTO evidence FROM sarsa_booking.recovery_lanes;
 RETURN evidence;
END $body$;
REVOKE ALL ON sarsa_booking.recovery_lanes,sarsa_booking.recovery_lane_incidents FROM PUBLIC,sarsa_booking_runtime;
REVOKE ALL ON FUNCTION sarsa_booking.begin_recovery_lane(text),sarsa_booking.finish_recovery_lane(text,uuid,boolean,integer),sarsa_booking.recovery_progress(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.begin_recovery_lane(text),sarsa_booking.finish_recovery_lane(text,uuid,boolean,integer),sarsa_booking.recovery_progress(jsonb) TO sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION sarsa_booking.begin_recovery_lane(text),sarsa_booking.finish_recovery_lane(text,uuid,boolean,integer) TO sarsa_booking_control;
GRANT USAGE ON SCHEMA sarsa_booking TO sarsa_booking_control;
