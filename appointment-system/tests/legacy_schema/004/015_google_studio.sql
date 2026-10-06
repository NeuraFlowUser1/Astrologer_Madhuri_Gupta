-- Private Google connection access, independent of customer checkout contexts.
CREATE TABLE sarsa_booking.studio_identities (
    role text PRIMARY KEY CHECK(role IN ('client','agency')),
    subject text NOT NULL UNIQUE CHECK(length(subject) BETWEEN 1 AND 255)
);
CREATE TABLE sarsa_booking.studio_sessions (
    digest text PRIMARY KEY CHECK(digest ~ '^[a-f0-9]{64}$'),
    role text NOT NULL REFERENCES sarsa_booking.studio_identities(role),
    subject text NOT NULL,
    client_id text NOT NULL,
    origin text NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE TABLE sarsa_booking.google_connections (
    role text PRIMARY KEY REFERENCES sarsa_booking.studio_identities(role),
    subject text NOT NULL,
    client_id text NOT NULL,
    revision bigint NOT NULL CHECK(revision>0),
    encrypted_grant text NOT NULL CHECK(length(encrypted_grant) BETWEEN 100 AND 32768),
    connected_at timestamptz NOT NULL,
    grant_expires_at timestamptz
);
CREATE TABLE sarsa_booking.google_attempts (
    state_digest text PRIMARY KEY CHECK(state_digest ~ '^[a-f0-9]{64}$'),
    browser_digest text NOT NULL CHECK(browser_digest ~ '^[a-f0-9]{64}$'),
    purpose text NOT NULL CHECK(purpose IN ('signin','connect')),
    role text NOT NULL CHECK(role IN ('client','agency')),
    encrypted_attempt text NOT NULL CHECK(length(encrypted_attempt) BETWEEN 100 AND 32768),
    session_digest text REFERENCES sarsa_booking.studio_sessions(digest),
    expected_revision bigint NOT NULL DEFAULT 0 CHECK(expected_revision>=0),
    client_id text NOT NULL,
    origin text NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    finished_at timestamptz,
    CHECK((purpose='signin' AND session_digest IS NULL) OR (purpose='connect' AND session_digest IS NOT NULL))
);
CREATE INDEX google_attempts_expiry ON sarsa_booking.google_attempts(expires_at);
CREATE TABLE sarsa_booking.studio_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    role text NOT NULL CHECK(role IN ('client','agency')),
    action text NOT NULL CHECK(action IN ('signin','connect','logout'))
);
REVOKE ALL ON sarsa_booking.studio_identities,sarsa_booking.studio_sessions,
    sarsa_booking.google_connections,sarsa_booking.google_attempts,sarsa_booking.studio_audit FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON sarsa_booking.studio_identities,sarsa_booking.studio_sessions,
    sarsa_booking.google_connections,sarsa_booking.google_attempts TO sarsa_booking_runtime;
GRANT SELECT,INSERT ON sarsa_booking.studio_audit TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.studio_session(p_digest text,p_client text,p_origin text)
RETURNS jsonb LANGUAGE sql AS $body$
    SELECT (SELECT jsonb_build_object('role',s.role,'subject',s.subject,'expires_at',s.expires_at)
      FROM sarsa_booking.studio_sessions s JOIN sarsa_booking.studio_identities i
        ON i.role=s.role AND i.subject=s.subject
      WHERE s.digest=p_digest AND s.client_id=p_client AND s.origin=p_origin
        AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp())
$body$;

CREATE FUNCTION sarsa_booking.start_google_attempt(p_state text,p_browser text,p_purpose text,
    p_role text,p_encrypted text,p_session text,p_client text,p_origin text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE actor jsonb; revision bigint;
BEGIN
    IF p_purpose='connect' THEN
        actor:=sarsa_booking.studio_session(p_session,p_client,p_origin);
        IF actor IS NULL OR actor->>'role' IS DISTINCT FROM p_role THEN RETURN false; END IF;
    END IF;
    SELECT g.revision INTO revision FROM sarsa_booking.google_connections g WHERE g.role=p_role;
    INSERT INTO sarsa_booking.google_attempts(state_digest,browser_digest,purpose,role,encrypted_attempt,
        session_digest,expected_revision,client_id,origin,expires_at)
      VALUES(p_state,p_browser,p_purpose,p_role,p_encrypted,p_session,coalesce(revision,0),
        p_client,p_origin,clock_timestamp()+interval '10 minutes');
    RETURN true;
END
$body$;

CREATE FUNCTION sarsa_booking.consume_google_attempt(p_state text,p_browser text,p_purpose text,p_client text,p_origin text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE a sarsa_booking.google_attempts%ROWTYPE; actor jsonb;
BEGIN
    SELECT * INTO a FROM sarsa_booking.google_attempts WHERE state_digest=p_state FOR UPDATE;
    IF NOT FOUND OR a.browser_digest IS DISTINCT FROM p_browser OR a.purpose IS DISTINCT FROM p_purpose
      OR a.client_id IS DISTINCT FROM p_client OR a.origin IS DISTINCT FROM p_origin
      OR a.consumed_at IS NOT NULL OR a.expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
    IF a.purpose='connect' THEN
        actor:=sarsa_booking.studio_session(a.session_digest,p_client,p_origin);
        IF actor IS NULL OR actor->>'role' IS DISTINCT FROM a.role THEN RETURN NULL; END IF;
    END IF;
    UPDATE sarsa_booking.google_attempts SET consumed_at=clock_timestamp() WHERE state_digest=p_state;
    RETURN jsonb_build_object('role',a.role,'encrypted_attempt',a.encrypted_attempt,
        'subject',actor->>'subject','server_now',clock_timestamp());
END
$body$;

CREATE FUNCTION sarsa_booking.finish_google_signin(p_state text,p_subject text,p_session text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE a sarsa_booking.google_attempts%ROWTYPE; pinned text;
BEGIN
    PERFORM pg_advisory_xact_lock(4004101);
    SELECT * INTO a FROM sarsa_booking.google_attempts WHERE state_digest=p_state FOR UPDATE;
    IF NOT FOUND OR a.purpose<>'signin' OR a.consumed_at IS NULL OR a.finished_at IS NOT NULL
      OR a.expires_at<=clock_timestamp() OR p_subject IS NULL THEN RETURN false; END IF;
    SELECT subject INTO pinned FROM sarsa_booking.studio_identities WHERE role=a.role;
    IF pinned IS NOT NULL AND pinned<>p_subject THEN RETURN false; END IF;
    INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES(a.role,p_subject) ON CONFLICT(role) DO NOTHING;
    INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at)
      VALUES(p_session,a.role,p_subject,a.client_id,a.origin,clock_timestamp()+interval '60 minutes');
    UPDATE sarsa_booking.google_attempts SET finished_at=clock_timestamp() WHERE state_digest=p_state;
    INSERT INTO sarsa_booking.studio_audit(role,action) VALUES(a.role,'signin');
    RETURN true;
END
$body$;

CREATE FUNCTION sarsa_booking.finish_google_connection(p_state text,p_subject text,p_encrypted text,p_expires timestamptz)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE a sarsa_booking.google_attempts%ROWTYPE; actor sarsa_booking.studio_sessions%ROWTYPE; current_revision bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(4004101);
    SELECT * INTO a FROM sarsa_booking.google_attempts WHERE state_digest=p_state FOR UPDATE;
    IF NOT FOUND OR a.purpose<>'connect' OR a.consumed_at IS NULL OR a.finished_at IS NOT NULL
      OR a.expires_at<=clock_timestamp() OR p_subject IS NULL THEN RETURN false; END IF;
    SELECT * INTO actor FROM sarsa_booking.studio_sessions WHERE digest=a.session_digest FOR SHARE;
    IF NOT FOUND OR actor.revoked_at IS NOT NULL OR actor.expires_at<=clock_timestamp()
      OR actor.role<>a.role OR actor.subject<>p_subject
      OR actor.client_id<>a.client_id OR actor.origin<>a.origin
      OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities WHERE role=a.role AND subject=p_subject)
      OR (p_expires IS NOT NULL AND p_expires<=clock_timestamp()) THEN RETURN false; END IF;
    SELECT revision INTO current_revision FROM sarsa_booking.google_connections WHERE role=a.role FOR UPDATE;
    IF coalesce(current_revision,0)<>a.expected_revision THEN RETURN false; END IF;
    INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at,grant_expires_at)
      VALUES(a.role,p_subject,a.client_id,a.expected_revision+1,p_encrypted,clock_timestamp(),p_expires)
      ON CONFLICT(role) DO UPDATE SET subject=excluded.subject,client_id=excluded.client_id,
        revision=excluded.revision,encrypted_grant=excluded.encrypted_grant,
        connected_at=excluded.connected_at,grant_expires_at=excluded.grant_expires_at;
    UPDATE sarsa_booking.google_attempts SET finished_at=clock_timestamp() WHERE state_digest=p_state;
    INSERT INTO sarsa_booking.studio_audit(role,action) VALUES(a.role,'connect');
    RETURN true;
END
$body$;

CREATE FUNCTION sarsa_booking.studio_logout(p_digest text,p_client text,p_origin text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed_role text;
BEGIN
    UPDATE sarsa_booking.studio_sessions SET revoked_at=clock_timestamp()
      WHERE digest=p_digest AND client_id=p_client AND origin=p_origin AND revoked_at IS NULL
      RETURNING role INTO changed_role;
    IF changed_role IS NOT NULL THEN
      INSERT INTO sarsa_booking.studio_audit(role,action) VALUES(changed_role,'logout');
    END IF;
    RETURN changed_role IS NOT NULL;
END
$body$;

REVOKE ALL ON FUNCTION sarsa_booking.studio_session(text,text,text),
    sarsa_booking.start_google_attempt(text,text,text,text,text,text,text,text),
    sarsa_booking.consume_google_attempt(text,text,text,text,text),
    sarsa_booking.finish_google_signin(text,text,text),
    sarsa_booking.finish_google_connection(text,text,text,timestamptz),
    sarsa_booking.studio_logout(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_session(text,text,text),
    sarsa_booking.start_google_attempt(text,text,text,text,text,text,text,text),
    sarsa_booking.consume_google_attempt(text,text,text,text,text),
    sarsa_booking.finish_google_signin(text,text,text),
    sarsa_booking.finish_google_connection(text,text,text,timestamptz),
    sarsa_booking.studio_logout(text,text,text) TO sarsa_booking_runtime;

-- Independent private-access quotas; do not consume customer checkout budgets.
ALTER TABLE sarsa_booking.request_limits DROP CONSTRAINT request_limits_scope_check;
ALTER TABLE sarsa_booking.request_limits ADD CONSTRAINT request_limits_scope_check
    CHECK(scope IN ('context','availability','receipt','checkout','studio','studio_status'));
CREATE OR REPLACE FUNCTION sarsa_booking.consume_request_limit(p_scope text,p_key text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE instant timestamptz := clock_timestamp();
        start_at timestamptz; width integer; maximum integer; used integer;
BEGIN
    CASE p_scope
      WHEN 'studio' THEN width:=3600; maximum:=20;
      WHEN 'studio_status' THEN width:=60; maximum:=60;
      WHEN 'context' THEN width:=3600; maximum:=20;
      WHEN 'availability' THEN width:=60; maximum:=60;
      WHEN 'receipt' THEN width:=60; maximum:=30;
      WHEN 'checkout' THEN width:=3600; maximum:=30;
      ELSE RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='unsupported request scope';
    END CASE;
    start_at:=to_timestamp(floor(extract(epoch FROM instant)/width)*width);
    INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
      VALUES(p_scope,p_key,start_at,start_at+make_interval(secs=>width)+interval '24 hours',1)
      ON CONFLICT(scope,key_digest,window_start) DO UPDATE
      SET attempts=least(sarsa_booking.request_limits.attempts+1,maximum+1)
      RETURNING attempts INTO used;
    RETURN jsonb_build_object('allowed',used<=maximum,
      'retry_after',greatest(1,ceil(extract(epoch FROM start_at+make_interval(secs=>width)-instant))::integer));
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.consume_request_limit(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.consume_request_limit(text,text) TO sarsa_booking_runtime;
