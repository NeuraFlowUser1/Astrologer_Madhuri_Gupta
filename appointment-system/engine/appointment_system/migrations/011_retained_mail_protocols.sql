-- Explicit old sender protocols. Current mail still requires the full new
-- installation/account/job/version binding; no generic untagged sender exists.
CREATE OR REPLACE FUNCTION appointment_system.valid_mail_binding(p_binding jsonb, p_saved jsonb)
RETURNS boolean LANGUAGE plpgsql STABLE
SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE c appointment_system.mail_connection%ROWTYPE;
BEGIN
 SELECT * INTO c FROM appointment_system.mail_connection WHERE singleton;
 IF NOT FOUND OR NOT appointment_system.exact_keys(p_binding,ARRAY['account_id','event_account_id','credential_version','format','idempotency_key'])
  OR EXISTS(SELECT 1 FROM jsonb_each(p_binding) a WHERE jsonb_typeof(a.value)<>'string')
  OR p_binding->>'account_id' IS DISTINCT FROM c.account_id
  OR NOT coalesce(p_binding->>'credential_version'=ANY(c.retained_keys),false)
  OR p_binding->>'format' NOT IN ('resend-v1','resend-legacy-job-v1','resend-legacy-verification-v1',
    'resend-legacy-flat-job-v1','resend-legacy-untagged-job-v1')
  OR length(p_binding->>'idempotency_key') NOT BETWEEN 1 AND 256 OR p_binding->>'idempotency_key' ~ '[^!-~]'
 THEN RETURN false; END IF;
 IF p_saved->>'mail_account_id' IS NOT NULL THEN
  RETURN p_binding=jsonb_build_object('account_id',p_saved->>'mail_account_id','event_account_id',p_saved->>'mail_event_account_id',
    'credential_version',p_saved->>'mail_credential_version','format',p_saved->>'mail_format','idempotency_key',p_saved->>'mail_idempotency_key');
 END IF;
 RETURN p_saved->>'first_attempt_at' IS NULL AND p_saved->>'mail_format'='resend-v1'
  AND p_binding->>'event_account_id'=c.account_id AND p_binding->>'format'='resend-v1' AND p_binding->>'credential_version'=c.active_key_id
  AND p_binding->>'idempotency_key'='abs/'||appointment_system.installation_value('installation_id')||'/'||(p_saved->>'id')||'/v'||(p_saved->>'template_version');
END $$;
