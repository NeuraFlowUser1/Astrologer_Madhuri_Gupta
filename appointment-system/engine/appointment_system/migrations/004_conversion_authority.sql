-- Offline handover: journal authority cannot perform ordinary business work.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='appointment_system_journal_access') THEN
  CREATE ROLE appointment_system_journal_access NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
 END IF;
END $$;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_journal_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_journal_access;
ALTER TABLE appointment_system.caller_logins DROP CONSTRAINT caller_logins_purpose_check;
ALTER TABLE appointment_system.caller_logins ADD CONSTRAINT caller_logins_purpose_check
 CHECK(purpose IN ('web','staff','worker','company','backup','maintenance','journal'));
CREATE TABLE appointment_system.conversion_handover (
 id uuid PRIMARY KEY,installation_id uuid NOT NULL,source_layout text NOT NULL,
 source_digest text NOT NULL CHECK(source_digest ~ '^[a-f0-9]{64}$'),
 target_digest text CHECK(target_digest ~ '^[a-f0-9]{64}$'),
 phase text NOT NULL CHECK(phase IN ('prepared','journal_only','fenced','imported','complete','aborted')),
 writer_roles text[] NOT NULL,provider_accounts jsonb NOT NULL,source_counts jsonb NOT NULL,target_counts jsonb,
 release_digest text NOT NULL CHECK(release_digest ~ '^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),completed_at timestamptz,
 CHECK(jsonb_typeof(source_counts)='object'),CHECK(jsonb_typeof(provider_accounts)='array'),
 CHECK(target_counts IS NULL OR jsonb_typeof(target_counts)='object')
);
CREATE UNIQUE INDEX one_active_conversion ON appointment_system.conversion_handover((true))
 WHERE phase NOT IN ('complete','aborted');
ALTER TABLE appointment_system.conversion_handover OWNER TO appointment_system_owner;
REVOKE ALL ON appointment_system.conversion_handover FROM PUBLIC;
GRANT SELECT ON appointment_system.conversion_handover TO appointment_system_backup_access;
ALTER TABLE appointment_system.provider_inbox ADD COLUMN journal_envelope jsonb;
ALTER TABLE appointment_system.provider_inbox ADD CONSTRAINT journal_envelope_shape
 CHECK(journal_envelope IS NULL OR (jsonb_typeof(journal_envelope)='object'
   AND journal_envelope ?& ARRAY['version','bytes','sha256','chunks']
   AND journal_envelope->'version'='1'::jsonb AND journal_envelope->>'sha256'=body_hash
   AND jsonb_typeof(journal_envelope->'bytes')='number'
   AND journal_envelope->>'bytes' ~ '^[1-9][0-9]{0,5}$'
   AND (journal_envelope->>'bytes')::integer BETWEEN 1 AND 131072
   AND jsonb_typeof(journal_envelope->'chunks')='array'
   AND jsonb_array_length(journal_envelope->'chunks')=((journal_envelope->>'bytes')::integer+65535)/65536
   AND octet_length(journal_envelope::text)<=200000) IS TRUE);

CREATE OR REPLACE FUNCTION appointment_system.provision_login(p_login text, p_purpose text) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE config jsonb; identifier uuid; stage text; existing record;
BEGIN
 -- Handover and restore acquire the exclusive side before changing authority.
 -- Acquire this before any caller check or business lock, even for owner tools.
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_purpose NOT IN ('web','staff','worker','company','backup','maintenance','journal')
  OR p_login !~ '^[a-z][a-z0-9_]{2,62}$' THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid login purpose'; END IF;
 SELECT specification#>ARRAY['database_targets',p_purpose],installation_id,environment
 INTO config,identifier,stage FROM appointment_system.installation WHERE singleton;
 IF config IS NULL OR config->>'role' IS DISTINCT FROM p_login OR config->>'database' IS DISTINCT FROM current_database()
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='declared login required'; END IF;
 SELECT * INTO existing FROM pg_roles WHERE rolname=p_login;
 IF FOUND AND (existing.rolsuper OR existing.rolcreatedb OR existing.rolcreaterole OR existing.rolreplication OR existing.rolbypassrls)
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='application login is privileged'; END IF;
 IF NOT FOUND THEN EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',p_login); END IF;
 IF EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles l ON l.oid=m.member
  WHERE l.rolname=p_login AND r.rolname<>'appointment_system_'||p_purpose||'_access')
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='login has unrelated membership'; END IF;
 EXECUTE format('GRANT %I TO %I','appointment_system_'||p_purpose||'_access',p_login);
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I',current_database(),p_login);
 INSERT INTO appointment_system.caller_logins(login_role,purpose,installation_id,environment,writer_contract)
 VALUES(p_login,p_purpose,identifier,stage,1) ON CONFLICT(login_role) DO UPDATE SET
  purpose=excluded.purpose,installation_id=excluded.installation_id,environment=excluded.environment,
  writer_contract=excluded.writer_contract,enabled=true;
 RETURN true;
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.require_registered_caller(p_purposes text[]) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 -- A controlled schema-maintenance login may use owner functions; a registered
 -- application login never gains an exemption through an accidental membership.
 IF pg_has_role(session_user,'appointment_system_owner','MEMBER') AND
  NOT EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user) THEN RETURN; END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.caller_logins c JOIN appointment_system.installation i ON i.singleton
  JOIN pg_roles r ON r.rolname=c.login_role
  WHERE c.login_role=session_user AND c.enabled AND c.purpose=ANY(p_purposes) AND c.environment=i.environment
   AND c.installation_id=i.installation_id AND c.writer_contract=i.writer_contract AND r.rolcanlogin
   AND NOT r.rolsuper AND NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolbypassrls
   AND i.specification#>>ARRAY['database_targets',c.purpose,'role']=session_user
   AND i.specification#>>ARRAY['database_targets',c.purpose,'database']=current_database()
   AND pg_has_role(session_user,'appointment_system_'||c.purpose||'_access','MEMBER')
   AND NOT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles other ON other.oid=m.roleid
    WHERE m.member=r.oid AND other.rolname<>'appointment_system_'||c.purpose||'_access')) THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='registered caller required'; END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose IN ('web','staff','worker','company'))
  AND EXISTS(SELECT 1 FROM appointment_system.conversion_handover WHERE phase IN ('journal_only','fenced','imported'))
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='controlled handover in progress'; END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose IN ('web','staff','worker','company','journal'))
  AND EXISTS(SELECT 1 FROM appointment_system.control_restore_operations r JOIN appointment_system.control_product_state s ON s.singleton
   WHERE r.result_snapshot->>'restore_generation'=s.restore_generation::text
    AND NOT EXISTS(SELECT 1 FROM appointment_system.control_restore_completions c WHERE c.restore_generation=s.restore_generation))
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='isolated recovery completion required'; END IF;
END $$;


CREATE FUNCTION appointment_system.journal_provider_event(p_provider text,p_account text,p_mode text,p_event text,p_hash text,p_payload jsonb,p_envelope jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['journal']);
 IF p_provider NOT IN ('razorpay','resend') OR p_provider IS NULL OR p_mode NOT IN ('test','live')
  OR p_mode IS NULL OR p_account IS NULL OR length(p_account) NOT BETWEEN 1 AND 320
  OR p_event IS NULL OR length(p_event) NOT BETWEEN 1 AND 200 OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR octet_length(p_payload::text)>262144
  OR jsonb_typeof(p_envelope) IS DISTINCT FROM 'object' OR p_envelope->>'sha256' IS DISTINCT FROM p_hash
  OR (p_provider='resend' AND p_mode<>'live')
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid provider journal event'; END IF;
 IF NOT (p_envelope ?& ARRAY['version','bytes','sha256','chunks'])
  OR (SELECT count(*) FROM jsonb_object_keys(p_envelope))<>4
  OR p_envelope->'version' IS DISTINCT FROM '1'::jsonb
  OR jsonb_typeof(p_envelope->'bytes') IS DISTINCT FROM 'number'
  OR p_envelope->>'bytes' !~ '^[1-9][0-9]{0,5}$'
  OR jsonb_typeof(p_envelope->'chunks') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid provider journal envelope'; END IF;
 IF (p_envelope->>'bytes')::integer NOT BETWEEN 1 AND 131072
  OR jsonb_array_length(p_envelope->'chunks')<>((p_envelope->>'bytes')::integer+65535)/65536
  OR octet_length(p_envelope::text)>200000
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_envelope->'chunks') x WHERE jsonb_typeof(x)<>'object')
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid provider journal envelope'; END IF;
 IF NOT (
  (p_provider='razorpay' AND (
    EXISTS(SELECT 1 FROM appointment_system.intake_settings WHERE merchant_id=p_account AND payment_mode=p_mode)
    OR EXISTS(SELECT 1 FROM appointment_system.payment_orders WHERE merchant_id=p_account AND mode=p_mode)))
  OR (p_provider='resend' AND EXISTS(SELECT 1 FROM appointment_system.mail_connection m
    WHERE m.account_id=p_account OR EXISTS(SELECT 1 FROM jsonb_array_elements(m.legacy_identities) x
      WHERE x->>'event_account_id'=p_account)))
  OR EXISTS(SELECT 1 FROM appointment_system.conversion_handover h CROSS JOIN LATERAL jsonb_array_elements(h.provider_accounts) x
    WHERE h.phase IN ('prepared','journal_only','fenced','imported') AND x->>'provider'=p_provider
      AND x->>'account_id'=p_account AND x->>'mode'=p_mode)
 )
 THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='provider account not registered'; END IF;
 INSERT INTO appointment_system.provider_inbox(provider,account_id,environment,event_id,body_hash,payload,journal_envelope)
 VALUES(p_provider,p_account,p_mode,p_event,p_hash,p_payload,p_envelope)
 ON CONFLICT(provider,account_id,environment,event_id) DO NOTHING;
 RETURN (SELECT body_hash FROM appointment_system.provider_inbox WHERE provider=p_provider AND account_id=p_account
  AND environment=p_mode AND event_id=p_event AND body_hash=p_hash AND payload=p_payload);
END $$;
ALTER FUNCTION appointment_system.journal_provider_event(text,text,text,text,text,jsonb,jsonb) OWNER TO appointment_system_owner;
REVOKE ALL ON FUNCTION appointment_system.journal_provider_event(text,text,text,text,text,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.journal_provider_event(text,text,text,text,text,jsonb,jsonb) TO appointment_system_journal_access;
