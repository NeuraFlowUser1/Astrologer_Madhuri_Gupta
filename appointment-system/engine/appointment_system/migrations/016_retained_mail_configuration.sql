-- Protected metadata accepts the same explicit readers as the mail transport.
CREATE OR REPLACE FUNCTION appointment_system.configure_mail_connection(p_spec jsonb, p_daily integer, p_rolling integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE keys text[];key text;identity jsonb;
BEGIN
 IF NOT pg_has_role(session_user,'appointment_system_owner','MEMBER') THEN RAISE EXCEPTION 'Owner setup required'; END IF;
 IF NOT appointment_system.exact_keys(p_spec,ARRAY['account_id','active_key_id','retained_keys','legacy_identities'])
  OR p_spec->>'account_id' !~ '^[A-Za-z0-9_-]{1,80}$' OR p_spec->>'active_key_id' !~ '^[A-Za-z0-9_-]{1,80}$'
  OR jsonb_typeof(p_spec->'retained_keys') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'retained_keys') NOT BETWEEN 1 AND 8
  OR jsonb_typeof(p_spec->'legacy_identities') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'legacy_identities')>2
  OR p_daily IS NULL OR p_daily NOT BETWEEN 0 AND 100 OR p_rolling IS NULL OR p_rolling NOT BETWEEN 0 AND 3000
 THEN RAISE EXCEPTION 'Invalid mail configuration'; END IF;
 SELECT array_agg(value#>>'{}') INTO keys FROM jsonb_array_elements(p_spec->'retained_keys');
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_spec->'retained_keys') a WHERE jsonb_typeof(a)<>'string' OR a#>>'{}' !~ '^[A-Za-z0-9_-]{1,80}$')
  OR cardinality(keys)<>(SELECT count(DISTINCT k) FROM unnest(keys) k)
  OR NOT p_spec->>'active_key_id'=ANY(keys) THEN RAISE EXCEPTION 'Invalid mail credential registry'; END IF;
 FOR identity IN SELECT value FROM jsonb_array_elements(p_spec->'legacy_identities') LOOP
  IF NOT appointment_system.exact_keys(identity,ARRAY['format','project','sender','address','reply_to','event_account_id'])
   OR identity->>'format' NOT IN ('resend-legacy-job-v1','resend-legacy-verification-v1','resend-legacy-flat-job-v1','resend-legacy-untagged-job-v1')
   OR identity->>'project' !~ '^[A-Za-z0-9_-]{1,75}$'
   OR EXISTS(SELECT 1 FROM jsonb_each(identity) a WHERE jsonb_typeof(a.value)<>'string' OR length(a.value#>>'{}') NOT BETWEEN 1 AND 320 OR a.value#>>'{}' ~ '[[:cntrl:]]')
  THEN RAISE EXCEPTION 'Invalid retained mail reader'; END IF;
 END LOOP;
 IF (SELECT count(DISTINCT value->>'format') FROM jsonb_array_elements(p_spec->'legacy_identities'))<>jsonb_array_length(p_spec->'legacy_identities') THEN RAISE EXCEPTION 'Duplicate retained reader'; END IF;
 PERFORM pg_advisory_xact_lock(4004003);
 IF EXISTS(SELECT 1 FROM appointment_system.mail_connection WHERE account_id<>p_spec->>'account_id') THEN RAISE EXCEPTION 'An account replacement requires an explicit data conversion'; END IF;
 INSERT INTO appointment_system.mail_connection(singleton,account_id,active_key_id,retained_keys,legacy_identities,daily_allowance,rolling_allowance)
 VALUES(true,p_spec->>'account_id',p_spec->>'active_key_id',keys,p_spec->'legacy_identities',p_daily,p_rolling)
 ON CONFLICT(singleton) DO UPDATE SET active_key_id=excluded.active_key_id,retained_keys=excluded.retained_keys,
  legacy_identities=excluded.legacy_identities,daily_allowance=excluded.daily_allowance,rolling_allowance=excluded.rolling_allowance;
 RETURN true;
END $_$;
