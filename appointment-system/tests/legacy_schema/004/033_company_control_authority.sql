-- Enrollment is maintenance-only; spreadsheet-copy and client identities do
-- not gain company authority. These functions expose no customer records.
CREATE TABLE booking_control.company_identities (
 subject text PRIMARY KEY CHECK(length(subject) BETWEEN 1 AND 255),
 email text NOT NULL CHECK(email='neuraflowindia@gmail.com'),
 audience text NOT NULL CHECK(length(audience) BETWEEN 20 AND 255),
 capabilities text[] NOT NULL CHECK(cardinality(capabilities) BETWEEN 1 AND 2
  AND capabilities <@ ARRAY['service_controller','obligation_handler']::text[]),
 enabled boolean NOT NULL DEFAULT true,
 enrolled_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.company_sessions (
 token_hash text PRIMARY KEY CHECK(token_hash~'^[a-f0-9]{64}$'),
 subject text NOT NULL REFERENCES booking_control.company_identities(subject),
 csrf_hash text NOT NULL CHECK(csrf_hash~'^[a-f0-9]{64}$'),
 restore_generation uuid NOT NULL,
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 fresh_until timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK(created_at<fresh_until AND fresh_until<=expires_at)
);
CREATE INDEX company_sessions_expiry ON booking_control.company_sessions(expires_at);
CREATE TABLE booking_control.login_challenges (
 state_hash text PRIMARY KEY CHECK(state_hash~'^[a-f0-9]{64}$'),
 browser_hash text NOT NULL CHECK(browser_hash~'^[a-f0-9]{64}$'),
 audience text NOT NULL,
 nonce_hash text NOT NULL CHECK(nonce_hash~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL
);
REVOKE ALL ON booking_control.company_identities,booking_control.company_sessions,booking_control.login_challenges FROM PUBLIC;

CREATE FUNCTION booking_control.login_start(p_state text,p_browser text,p_audience text,p_nonce text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM booking_control.company_identities WHERE enabled AND audience=p_audience) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='company identity not enrolled';
 END IF;
 DELETE FROM booking_control.login_challenges WHERE state_hash IN
  (SELECT state_hash FROM booking_control.login_challenges WHERE expires_at<=clock_timestamp() LIMIT 50);
 INSERT INTO booking_control.login_challenges VALUES(p_state,p_browser,p_audience,p_nonce,clock_timestamp()+interval '5 minutes');
 RETURN true;
END $body$;
CREATE FUNCTION booking_control.login_consume(p_state text,p_browser text,p_audience text,p_nonce text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 DELETE FROM booking_control.login_challenges WHERE state_hash=p_state AND browser_hash=p_browser
  AND audience=p_audience AND nonce_hash=p_nonce AND expires_at>clock_timestamp();
 RETURN FOUND;
END $body$;
CREATE FUNCTION booking_control.session_start(p_token text,p_subject text,p_email text,p_audience text,p_csrf text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE generation uuid; instant timestamptz:=clock_timestamp();
BEGIN
 IF NOT EXISTS(SELECT 1 FROM booking_control.company_identities WHERE enabled AND subject=p_subject
  AND email=p_email AND audience=p_audience) THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='company identity rejected'; END IF;
 SELECT restore_generation INTO generation FROM booking_control.product_state WHERE singleton;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='booking control unavailable'; END IF;
 INSERT INTO booking_control.company_sessions VALUES(p_token,p_subject,p_csrf,generation,
  instant,instant+interval '30 minutes',instant+interval '5 minutes',NULL);
 RETURN true;
END $body$;
CREATE FUNCTION booking_control.authorize(p_token text,p_capability text,p_csrf text DEFAULT NULL,p_fresh boolean DEFAULT false)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE principal text;
BEGIN
 IF p_capability IS NULL OR p_capability NOT IN ('service_controller','obligation_handler')
  OR (p_fresh AND p_csrf IS NULL) THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='company capability rejected';
 END IF;
 SELECT i.subject INTO principal FROM booking_control.company_sessions s
 JOIN booking_control.company_identities i ON i.subject=s.subject
 JOIN booking_control.product_state p ON p.singleton AND p.restore_generation=s.restore_generation
 WHERE s.token_hash=p_token AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() AND i.enabled
  AND p_capability=ANY(i.capabilities) AND (p_csrf IS NULL OR p_csrf=s.csrf_hash)
  AND (NOT p_fresh OR s.fresh_until>clock_timestamp());
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='company session rejected'; END IF;
 RETURN principal;
END $body$;
CREATE FUNCTION booking_control.session_end(p_token text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 UPDATE booking_control.company_sessions SET revoked_at=clock_timestamp() WHERE token_hash=p_token AND revoked_at IS NULL;
 RETURN FOUND;
END $body$;

CREATE FUNCTION booking_control.control_status(p_token text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE current_snapshot jsonb; publication text; operation uuid;
BEGIN
 PERFORM booking_control.authorize(p_token,'service_controller');
 current_snapshot:=booking_control.snapshot();
 SELECT p.state,p.operation_id INTO publication,operation FROM booking_control.publications p
 WHERE p.snapshot->>'restore_generation'=current_snapshot->>'restore_generation' AND p.snapshot->>'revision'=current_snapshot->>'revision';
 RETURN jsonb_build_object('snapshot',current_snapshot,'publication_state',COALESCE(publication,'initializing'),'operation_id',operation);
END $body$;

CREATE FUNCTION booking_control.command(p_token text,p_csrf text,p_operation uuid,p_generation uuid,
 p_revision bigint,p_enabled boolean,p_reason text,p_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE actor text; previous booking_control.operations%ROWTYPE; current booking_control.product_state%ROWTYPE;
 result jsonb; publication text;
BEGIN
 actor:=booking_control.authorize(p_token,'service_controller',p_csrf,true);
 IF p_enabled IS NULL OR p_revision IS NULL OR p_revision<1 OR p_generation IS NULL
  OR p_operation IS NULL OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 5 AND 300
  OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid control command';
 END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO previous FROM booking_control.operations WHERE id=p_operation;
 IF FOUND THEN
  IF previous.actor_subject IS DISTINCT FROM actor OR previous.body_hash IS DISTINCT FROM p_hash
   OR previous.expected_generation IS DISTINCT FROM p_generation OR previous.expected_revision IS DISTINCT FROM p_revision
   OR previous.target_enabled IS DISTINCT FROM p_enabled OR previous.reason IS DISTINCT FROM btrim(p_reason) THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='control operation conflict';
  END IF;
  SELECT state INTO publication FROM booking_control.publications WHERE operation_id=p_operation;
  RETURN jsonb_build_object('operation_id',p_operation,'snapshot',previous.result_snapshot,'publication_state',publication,'replayed',true);
 END IF;
 SELECT * INTO current FROM booking_control.product_state WHERE singleton FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='booking control unavailable'; END IF;
 IF current.restore_generation IS DISTINCT FROM p_generation OR current.revision IS DISTINCT FROM p_revision THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='control state changed';
 END IF;
 IF current.revision=9223372036854775807 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='control revision exhausted'; END IF;
 UPDATE booking_control.product_state SET enabled=p_enabled,revision=revision+1,
  activation_epoch=CASE WHEN NOT enabled AND p_enabled THEN gen_random_uuid() ELSE activation_epoch END,
  updated_at=clock_timestamp(),provenance='company_command' WHERE singleton;
 result:=booking_control.snapshot();
 INSERT INTO booking_control.operations(id,actor_subject,body_hash,expected_generation,expected_revision,target_enabled,reason,result_snapshot)
  VALUES(p_operation,actor,p_hash,p_generation,p_revision,p_enabled,btrim(p_reason),result);
 INSERT INTO booking_control.publications(operation_id,snapshot) VALUES(p_operation,result);
 RETURN jsonb_build_object('operation_id',p_operation,'snapshot',result,'publication_state','pending','replayed',false);
END $body$;

CREATE FUNCTION booking_control.claim_publication() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE job booking_control.publications%ROWTYPE; current jsonb;
BEGIN
 current:=booking_control.snapshot();
 UPDATE booking_control.publications SET state='superseded',lease_token=NULL,lease_until=NULL
 WHERE state IN ('pending','attention') AND
  (snapshot->>'restore_generation' IS DISTINCT FROM current->>'restore_generation'
   OR (snapshot->>'revision')::bigint<(current->>'revision')::bigint);
 SELECT * INTO job FROM booking_control.publications WHERE state='pending' AND next_attempt_at<=clock_timestamp()
  AND (lease_until IS NULL OR lease_until<=clock_timestamp()) ORDER BY next_attempt_at,operation_id
  LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE booking_control.publications SET lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '90 seconds',attempts=attempts+1
  WHERE operation_id=job.operation_id RETURNING * INTO job;
 RETURN jsonb_build_object('operation_id',job.operation_id,'lease_token',job.lease_token,'snapshot',job.snapshot,'attempts',job.attempts);
END $body$;
CREATE FUNCTION booking_control.finish_publication(p_operation uuid,p_lease uuid,p_ack jsonb,p_error text DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE job booking_control.publications%ROWTYPE; current jsonb;
BEGIN
 IF p_error IS NOT NULL AND p_error!~'^[a-z0-9_]{1,80}$' THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid publication result'; END IF;
 SELECT * INTO job FROM booking_control.publications WHERE operation_id=p_operation AND lease_token=p_lease
  AND lease_until>clock_timestamp() AND state='pending' FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 current:=booking_control.snapshot();
 IF job.snapshot IS DISTINCT FROM current THEN
  UPDATE booking_control.publications SET state='superseded',lease_token=NULL,lease_until=NULL WHERE operation_id=p_operation;
 ELSIF p_error IS NULL AND p_ack=job.snapshot THEN
  UPDATE booking_control.publications SET state='published',published_at=clock_timestamp(),lease_token=NULL,lease_until=NULL,last_error=NULL WHERE operation_id=p_operation;
 ELSE
  UPDATE booking_control.publications SET next_attempt_at=clock_timestamp()+make_interval(secs=>least(900,15*(2^least(attempts,5))::integer)),
   lease_token=NULL,lease_until=NULL,last_error=COALESCE(p_error,'publication_ack_invalid') WHERE operation_id=p_operation;
 END IF;
 RETURN true;
END $body$;

REVOKE ALL ON FUNCTION booking_control.login_start(text,text,text,text),booking_control.login_consume(text,text,text,text),
 booking_control.session_start(text,text,text,text,text),booking_control.authorize(text,text,text,boolean),booking_control.session_end(text),
 booking_control.control_status(text),booking_control.command(text,text,uuid,uuid,bigint,boolean,text,text),
 booking_control.claim_publication(),booking_control.finish_publication(uuid,uuid,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION booking_control.login_start(text,text,text,text),booking_control.login_consume(text,text,text,text),
 booking_control.session_start(text,text,text,text,text),booking_control.authorize(text,text,text,boolean),booking_control.session_end(text),
 booking_control.control_status(text),booking_control.command(text,text,uuid,uuid,bigint,boolean,text,text),
 booking_control.claim_publication(),booking_control.finish_publication(uuid,uuid,jsonb,text) TO sarsa_booking_control;
