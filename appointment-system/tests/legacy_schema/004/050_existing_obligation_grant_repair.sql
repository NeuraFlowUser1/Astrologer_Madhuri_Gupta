-- Existing-obligation owner consent, never a booking/dashboard session.
CREATE TABLE booking_control.grant_repairs (
 id uuid PRIMARY KEY, issuer text NOT NULL REFERENCES booking_control.company_identities(subject),
 body_hash text NOT NULL CHECK(body_hash~'^[a-f0-9]{64}$'),
 reference uuid NOT NULL, owner_role text NOT NULL CHECK(owner_role IN ('client','agency')),
 lane text NOT NULL CHECK(lane IN ('calendar','records')),
 owner_subject text NOT NULL CHECK(length(owner_subject) BETWEEN 1 AND 255),
 owner_email text NOT NULL, audience text NOT NULL, restore_generation uuid NOT NULL,
 expected_revision bigint NOT NULL CHECK(expected_revision>=0),
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 5 AND 300),
 link_hash text NOT NULL CHECK(link_hash~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '10 minutes',
 state_hash text UNIQUE CHECK(state_hash~'^[a-f0-9]{64}$'),
 browser_hash text CHECK(browser_hash~'^[a-f0-9]{64}$'), encrypted_attempt text,
 consumed_at timestamptz, finished_at timestamptz,
 result text CHECK(result IN ('saved','denied','failed','changed')),
 CHECK((state_hash IS NULL AND browser_hash IS NULL AND encrypted_attempt IS NULL)
    OR(state_hash IS NOT NULL AND browser_hash IS NOT NULL AND length(encrypted_attempt) BETWEEN 100 AND 32768)),
 CHECK((finished_at IS NULL)=(result IS NULL))
);
CREATE INDEX grant_repairs_expiry ON booking_control.grant_repairs(expires_at);
REVOKE ALL ON booking_control.grant_repairs FROM PUBLIC;

CREATE FUNCTION booking_control.repair_obligation(p_reference uuid,p_role text,p_lane text)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM sarsa_booking.bookings b JOIN sarsa_booking.accepted_payments p ON p.booking_id=b.id
 JOIN sarsa_booking.delivery_jobs j ON j.booking_id=b.id WHERE b.request_id=p_reference
 AND j.state IN ('pending','processing','failed','attention','uncertain') AND
 ((p_role='client' AND p_lane='calendar' AND(j.kind='booking_calendar' OR(j.kind='booking_cancelled' AND j.recipient_role='calendar')))
 OR(p_role IN ('client','agency') AND p_lane='records' AND j.kind='sheet_booking' AND j.recipient_role=p_role||'_sheet')))
$$;

CREATE FUNCTION booking_control.repair_identity(p_role text,p_audience text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
 SELECT jsonb_build_object('subject',i.subject,'email',CASE WHEN p_role='client' THEN 'sarsajyotish@gmail.com' ELSE 'neuraflowindia@gmail.com' END,'revision',coalesce(g.revision,0))
 FROM sarsa_booking.studio_identities i LEFT JOIN sarsa_booking.google_connections g ON g.role=i.role
 WHERE i.role=p_role AND(g.subject IS NULL OR g.subject=i.subject) AND(g.client_id IS NULL OR g.client_id=p_audience)
$$;

CREATE FUNCTION booking_control.repair_issue(p_session text,p_csrf text,p_id uuid,p_reference uuid,
 p_role text,p_lane text,p_audience text,p_link text,p_reason text,p_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE principal text; old booking_control.grant_repairs%ROWTYPE; identity jsonb; generation uuid;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 principal:=booking_control.authorize(p_session,'obligation_handler',p_csrf,true);
 IF p_id IS NULL OR p_reference IS NULL OR p_role IS NULL OR p_lane IS NULL
  OR p_role NOT IN ('client','agency') OR p_lane NOT IN ('calendar','records')
  OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 5 AND 300
  OR p_link IS NULL OR p_link!~'^[a-f0-9]{64}$' OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$'
  OR NOT EXISTS(SELECT 1 FROM booking_control.company_identities WHERE subject=principal AND audience=p_audience AND enabled)
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid permission repair'; END IF;
 PERFORM pg_advisory_xact_lock(83126,4);
 SELECT * INTO old FROM booking_control.grant_repairs WHERE id=p_id;
 IF FOUND THEN
  IF old.issuer IS DISTINCT FROM principal OR old.body_hash IS DISTINCT FROM p_hash
   OR old.reference IS DISTINCT FROM p_reference OR old.owner_role IS DISTINCT FROM p_role
   OR old.lane IS DISTINCT FROM p_lane OR old.audience IS DISTINCT FROM p_audience
   OR old.link_hash IS DISTINCT FROM p_link OR old.reason IS DISTINCT FROM btrim(p_reason)
  THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='permission repair changed'; END IF;
  RETURN jsonb_build_object('operation_id',old.id,'expires_at',old.expires_at,'result',old.result,'replayed',true);
 END IF;
 IF NOT booking_control.repair_obligation(p_reference,p_role,p_lane)
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='existing permission obligation required'; END IF;
 identity:=booking_control.repair_identity(p_role,p_audience);
 IF identity IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='pinned owner required'; END IF;
 SELECT restore_generation INTO generation FROM booking_control.product_state WHERE singleton;
 INSERT INTO booking_control.grant_repairs(id,issuer,body_hash,reference,owner_role,lane,owner_subject,owner_email,
  audience,restore_generation,expected_revision,reason,link_hash)
 VALUES(p_id,principal,p_hash,p_reference,p_role,p_lane,identity->>'subject',identity->>'email',p_audience,
  generation,(identity->>'revision')::bigint,btrim(p_reason),p_link) RETURNING * INTO old;
 RETURN jsonb_build_object('operation_id',old.id,'expires_at',old.expires_at,'result',NULL,'replayed',false);
END $$;

CREATE FUNCTION booking_control.repair_current(p_id uuid) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM booking_control.grant_repairs r
 JOIN booking_control.product_state p ON p.singleton AND p.restore_generation=r.restore_generation
 JOIN booking_control.company_identities i ON i.subject=r.issuer AND i.enabled
  AND 'obligation_handler'=ANY(i.capabilities) AND i.audience=r.audience
 WHERE r.id=p_id AND r.expires_at>clock_timestamp() AND r.finished_at IS NULL
 AND booking_control.repair_identity(r.owner_role,r.audience)=jsonb_build_object(
  'subject',r.owner_subject,'email',r.owner_email,'revision',r.expected_revision)
 AND booking_control.repair_obligation(r.reference,r.owner_role,r.lane))
$$;

CREATE FUNCTION booking_control.repair_begin(p_id uuid,p_link text,p_role text,p_state text,p_browser text,p_encrypted text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE r booking_control.grant_repairs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO r FROM booking_control.grant_repairs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR r.link_hash IS DISTINCT FROM p_link OR r.owner_role IS DISTINCT FROM p_role OR r.state_hash IS NOT NULL
  OR NOT booking_control.repair_current(p_id) OR p_state IS NULL OR p_state!~'^[a-f0-9]{64}$'
  OR p_browser IS NULL OR p_browser!~'^[a-f0-9]{64}$' OR p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768
 THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='permission repair access rejected'; END IF;
 UPDATE booking_control.grant_repairs SET state_hash=p_state,browser_hash=p_browser,encrypted_attempt=p_encrypted WHERE id=p_id;
 RETURN jsonb_build_object('operation_id',r.id,'owner_role',r.owner_role,'owner_subject',r.owner_subject,
  'owner_email',r.owner_email,'audience',r.audience,'expires_at',r.expires_at);
END $$;

CREATE FUNCTION booking_control.repair_consume(p_state text,p_browser text,p_audience text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE r booking_control.grant_repairs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO r FROM booking_control.grant_repairs WHERE state_hash=p_state FOR UPDATE;
 IF NOT FOUND OR r.browser_hash IS DISTINCT FROM p_browser OR r.audience IS DISTINCT FROM p_audience
  OR r.consumed_at IS NOT NULL OR NOT booking_control.repair_current(r.id)
 THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='permission repair access rejected'; END IF;
 UPDATE booking_control.grant_repairs SET consumed_at=clock_timestamp() WHERE id=r.id;
 RETURN jsonb_build_object('operation_id',r.id,'owner_role',r.owner_role,'owner_subject',r.owner_subject,
  'owner_email',r.owner_email,'audience',r.audience,'encrypted_attempt',r.encrypted_attempt,'server_now',clock_timestamp());
END $$;

CREATE FUNCTION booking_control.repair_finish(p_id uuid,p_state text,p_subject text,p_email text,p_encrypted text,
 p_scopes text,p_expires timestamptz,p_result text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE r booking_control.grant_repairs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM pg_advisory_xact_lock(4004101);
 PERFORM 1 FROM sarsa_booking.google_connections WHERE role=(SELECT owner_role FROM booking_control.grant_repairs WHERE id=p_id) FOR UPDATE;
 SELECT * INTO r FROM booking_control.grant_repairs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR r.state_hash IS DISTINCT FROM p_state OR r.consumed_at IS NULL OR r.finished_at IS NOT NULL
  OR p_result IS NULL OR p_result NOT IN ('saved','denied','failed') THEN RETURN false; END IF;
 IF p_result='saved' THEN
  IF p_subject IS DISTINCT FROM r.owner_subject OR p_email IS DISTINCT FROM r.owner_email
   OR p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768
   OR (p_expires IS NOT NULL AND (NOT isfinite(p_expires) OR p_expires<=clock_timestamp()))
   OR NOT booking_control.repair_current(r.id) THEN
   UPDATE booking_control.grant_repairs SET finished_at=clock_timestamp(),result='changed' WHERE id=p_id; RETURN false;
  END IF;
  INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at,grant_expires_at)
   VALUES(r.owner_role,r.owner_subject,r.audience,r.expected_revision+1,p_encrypted,clock_timestamp(),p_expires)
   ON CONFLICT(role) DO UPDATE SET subject=excluded.subject,client_id=excluded.client_id,revision=excluded.revision,
    encrypted_grant=excluded.encrypted_grant,connected_at=excluded.connected_at,grant_expires_at=excluded.grant_expires_at,
    refresh_lease=NULL,refresh_lease_until=NULL,refresh_revision=NULL;
 END IF;
 UPDATE booking_control.grant_repairs SET finished_at=clock_timestamp(),result=p_result WHERE id=p_id;
 RETURN true;
END $$;

CREATE FUNCTION booking_control.repair_session(p_session text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $$
BEGIN PERFORM booking_control.authorize(p_session,'obligation_handler'); RETURN true; END $$;

CREATE FUNCTION booking_control.repair_result(p_id uuid,p_link text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
 SELECT jsonb_build_object('result',CASE WHEN r.result IS NOT NULL THEN r.result WHEN r.expires_at<=clock_timestamp() THEN 'expired'
  WHEN r.consumed_at IS NOT NULL THEN 'check' WHEN r.state_hash IS NOT NULL THEN 'started' ELSE 'ready' END)
 FROM booking_control.grant_repairs r WHERE r.id=p_id AND r.link_hash=p_link
$$;
REVOKE ALL ON FUNCTION booking_control.repair_obligation(uuid,text,text),booking_control.repair_identity(text,text),
 booking_control.repair_current(uuid),booking_control.repair_session(text),booking_control.repair_issue(text,text,uuid,uuid,text,text,text,text,text,text),
 booking_control.repair_begin(uuid,text,text,text,text,text),booking_control.repair_consume(text,text,text),
 booking_control.repair_finish(uuid,text,text,text,text,text,timestamptz,text),booking_control.repair_result(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION booking_control.repair_session(text),booking_control.repair_issue(text,text,uuid,uuid,text,text,text,text,text,text),
 booking_control.repair_begin(uuid,text,text,text,text,text),booking_control.repair_consume(text,text,text),
 booking_control.repair_finish(uuid,text,text,text,text,text,timestamptz,text),booking_control.repair_result(uuid,text) TO sarsa_booking_control;
