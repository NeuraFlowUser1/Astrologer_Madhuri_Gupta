-- Canonical effective initial schema. No customer/account/installation rows.
CREATE EXTENSION IF NOT EXISTS btree_gist;
DO $roles$ DECLARE role_name text; role_record record; BEGIN
 FOREACH role_name IN ARRAY ARRAY['appointment_system_owner','appointment_system_web_access','appointment_system_staff_access','appointment_system_worker_access','appointment_system_company_access','appointment_system_backup_access','appointment_system_maintenance_access'] LOOP
  SELECT * INTO role_record FROM pg_roles WHERE rolname=role_name;
  IF NOT FOUND THEN EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',role_name);
  ELSIF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb OR role_record.rolcreaterole OR role_record.rolreplication OR role_record.rolbypassrls THEN
   RAISE EXCEPTION 'canonical non-login role is privileged';
  END IF;
 END LOOP;
 EXECUTE format('GRANT appointment_system_owner TO %I',session_user);
END $roles$;
SET ROLE appointment_system_owner;


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

RESET ROLE;
CREATE SCHEMA appointment_system AUTHORIZATION appointment_system_owner;
SET ROLE appointment_system_owner;

CREATE FUNCTION appointment_system.abandon_unattempted(p_context uuid, p_booking uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_abandon_unattempted(p_context, p_booking); END $$;

CREATE FUNCTION appointment_system.admit_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_admit_checkout(p_context, p_request, p_receipt, p_fingerprint); END $$;

CREATE FUNCTION appointment_system.adopt_mail_acceptance(p_kind text, p_job uuid, p_lease uuid) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_adopt_mail_acceptance(p_kind, p_job, p_lease); END $$;

CREATE FUNCTION appointment_system.advance_order_search(p_booking uuid, p_lease uuid, p_skip integer, p_candidates text[], p_complete boolean) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_advance_order_search(p_booking, p_lease, p_skip, p_candidates, p_complete); END $$;

CREATE FUNCTION appointment_system.api_checkout_launchable(p1 uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_checkout_launchable(p1); END $$;

CREATE FUNCTION appointment_system.api_consume_limit(p1 text, p2 text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_consume_limit(p1, p2); END $$;

CREATE FUNCTION appointment_system.api_context_snapshot(p1 uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_context_snapshot(p1); END $$;

CREATE FUNCTION appointment_system.api_create_context(p1 uuid, p2 text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_create_context(p1, p2); END $$;

CREATE FUNCTION appointment_system.api_create_context(p1 uuid, p2 text, p_format text, p_key_id text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE epoch uuid;expiry timestamptz;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_format IS DISTINCT FROM 'v1' OR coalesce(p_key_id,'') !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid context metadata'; END IF;
 epoch:=appointment_system.control_admission(NULL);
 INSERT INTO appointment_system.checkout_contexts(id,credential_digest,expires_at,activation_epoch,credential_format,credential_key_id)
 VALUES(p1,p2,clock_timestamp()+interval '24 hours',epoch,p_format,p_key_id) RETURNING expires_at INTO expiry;
 RETURN to_jsonb(expiry);
END $_$;

CREATE FUNCTION appointment_system.api_enquiry_protection(p_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 RETURN (SELECT jsonb_build_object('receipt_format',receipt_format,'receipt_key_id',receipt_key_id)
  FROM appointment_system.enquiries WHERE request_id=p_id AND receipt_expires_at>clock_timestamp());
END $$;

CREATE FUNCTION appointment_system.api_enquiry_verification_context(p1 uuid, p2 text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_enquiry_verification_context(p1, p2); END $$;

CREATE FUNCTION appointment_system.api_find_order(p1 text, p2 text, p3 text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_api_find_order(p1, p2, p3); END $$;

CREATE FUNCTION appointment_system.api_order_intent(p1 uuid, p2 uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']);
 RETURN (SELECT appointment_system.entry_api_order_intent(p1,p2)||jsonb_build_object('provider_receipt_format',b.provider_receipt_format)
 FROM appointment_system.bookings b WHERE b.id=p1 AND b.context_id=p2);
END $$;

CREATE FUNCTION appointment_system.api_payment_intake() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_payment_intake(); END $$;

CREATE FUNCTION appointment_system.api_receipt_snapshot(p1 uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;format text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']);
 result:=appointment_system.entry_api_receipt_snapshot(p1);
 SELECT provider_receipt_format INTO format FROM appointment_system.bookings WHERE request_id=p1;
 IF result->'booking' IS NOT NULL AND result->'booking'<>'null'::jsonb THEN
  result:=jsonb_set(result,'{booking}',(result->'booking')||jsonb_build_object('provider_receipt_format',format));
 END IF;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.api_resend_enquiry(p_id uuid, p_receipt text, p_operation uuid, p_generation integer, p_digest text, p_cipher text, p_code_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE previous integer;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_code_key IS NULL OR p_code_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$' THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 SELECT generation INTO previous FROM appointment_system.enquiries WHERE request_id=p_id FOR UPDATE;
 result:=appointment_system.resend_enquiry(p_id,p_receipt,p_operation,p_generation,p_digest,p_cipher);
 IF result->>'code'='ok' AND previous<p_generation THEN
  UPDATE appointment_system.enquiries SET code_format='v1',code_digest_format='v1',code_digest_key_id=p_code_key WHERE request_id=p_id;
 END IF;
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.api_save_provider_event(p1 text, p2 text, p3 text, p4 text, p5 text, p6 jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_api_save_provider_event(p1, p2, p3, p4, p5, p6); END $$;

CREATE FUNCTION appointment_system.api_scheduling_snapshot(p1 timestamp with time zone, p2 timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_api_scheduling_snapshot(p1, p2); END $$;

CREATE FUNCTION appointment_system.api_start_enquiry(p_id uuid, p_receipt text, p_fingerprint text, p_payload jsonb, p_digest text, p_cipher text, p_email_key text, p_receipt_key text, p_code_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved boolean;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-contact:'||p_id::text,0));
 saved:=EXISTS(SELECT 1 FROM appointment_system.enquiries WHERE request_id=p_id);
 IF NOT saved AND (p_receipt_key IS NULL OR p_code_key IS NULL OR p_receipt_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$' OR p_code_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$') THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 result:=appointment_system.start_enquiry(p_id,p_receipt,p_fingerprint,p_payload,p_digest,p_cipher,p_email_key);
 IF NOT saved AND result->>'code'='ok' THEN
  UPDATE appointment_system.enquiries SET receipt_key_id=p_receipt_key,code_digest_key_id=p_code_key WHERE request_id=p_id;
 END IF;
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.api_wake_payment_recovery(p1 uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_api_wake_payment_recovery(p1); END $$;

CREATE FUNCTION appointment_system.append_mail_acceptance(p_kind text, p_job uuid, p_hash text, p_provider uuid) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE data jsonb;acceptance_result text:='accepted';
BEGIN
 IF p_kind IS NULL OR p_hash IS NULL OR p_kind NOT IN('booking','contact','verification') OR p_job IS NULL OR p_provider IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RETURN 'invalid'; END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(j) INTO data FROM appointment_system.delivery_jobs j WHERE id=p_job AND appointment_system.is_email_job(j.kind,j.recipient_role) FOR UPDATE;
 ELSIF p_kind='verification' THEN
  SELECT to_jsonb(j) INTO data FROM appointment_system.booking_verification_mail j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT to_jsonb(j) INTO data FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_job AND kind IN('verification','acknowledgement','practice_notice') FOR UPDATE;
 END IF;
 IF data IS NULL OR data->>'first_attempt_at' IS NULL OR coalesce(data->>'message_hash',data->>'message_digest') IS DISTINCT FROM p_hash THEN RETURN 'invalid'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||p_provider::text,0));
 IF EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE provider_id=p_provider AND result='accepted' AND(kind<>p_kind OR job_id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='accepted' AND(provider_id<>p_provider OR message_hash<>p_hash))
 OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=p_provider::text AND recipient_role IN('customer','client') AND(p_kind<>'booking' OR id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=p_provider::text AND kind IN('verification','acknowledgement','practice_notice') AND(p_kind<>'contact' OR id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail WHERE provider_id=p_provider AND (p_kind<>'verification' OR id<>p_job))
 OR(data->>'provider_id' IS NOT NULL AND data->>'provider_id'<>p_provider::text) THEN acceptance_result:='conflict'; END IF;
 INSERT INTO appointment_system.mail_acceptance_claims(kind,job_id,provider_id,message_hash,result)
 VALUES(p_kind,p_job,p_provider,p_hash,acceptance_result) ON CONFLICT DO NOTHING;
 RETURN acceptance_result;
END $_$;

CREATE FUNCTION appointment_system.append_transport_attempt() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE kind text:=TG_ARGV[0];outcome text;
BEGIN
 IF TG_OP='UPDATE' AND OLD.state='processing' AND (NEW.state<>'processing' OR NEW.lease_token IS DISTINCT FROM OLD.lease_token) THEN
  outcome:=CASE WHEN NEW.state='processing' THEN 'delivery_unknown' ELSE NEW.state END;
  INSERT INTO appointment_system.transport_attempt_events(installation_id,job_kind,job_id,attempt,lease_token,generation,release_digest,contract,phase,state,error_code)
  VALUES(OLD.claim_installation,kind,OLD.id,OLD.attempts,OLD.lease_token,OLD.claim_generation,OLD.claim_release,OLD.claim_contract,'result',outcome,
   CASE WHEN NEW.last_error_code~'^[a-z0-9_]{1,80}$' THEN NEW.last_error_code ELSE NULL END);
 END IF;
 IF NEW.state='processing' AND (TG_OP='INSERT' OR OLD.state<>'processing' OR NEW.lease_token IS DISTINCT FROM OLD.lease_token) THEN
  INSERT INTO appointment_system.transport_attempt_events(installation_id,job_kind,job_id,attempt,lease_token,generation,release_digest,contract,phase,state)
  VALUES(NEW.claim_installation,kind,NEW.id,NEW.attempts,NEW.lease_token,NEW.claim_generation,NEW.claim_release,NEW.claim_contract,'claimed','processing');
 END IF;
 RETURN NEW;
END $_$;

CREATE FUNCTION appointment_system.assign_enquiry_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_assign_enquiry_row(p_role, p_job, p_values); END $$;

CREATE FUNCTION appointment_system.assign_enquiry_row(p_role text, p_job uuid, p_lease uuid, p_attempt integer, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.enquiry_delivery_jobs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_role NOT IN('client','agency') OR p_role IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 PERFORM 1 FROM appointment_system.google_workbooks WHERE role=p_role FOR UPDATE;
 SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR SHARE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM appointment_system.require_job_claim('contact',p_job,p_lease,p_attempt,j.claim_installation,j.claim_generation,j.claim_release,j.claim_contract);
 RETURN appointment_system.entry_assign_enquiry_row(p_role,p_job,p_values);
END $$;

CREATE FUNCTION appointment_system.assign_sheet_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_assign_sheet_row(p_role, p_job, p_values); END $$;

CREATE FUNCTION appointment_system.assign_sheet_row(p_role text, p_job uuid, p_lease uuid, p_attempt integer, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.delivery_jobs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_role NOT IN('client','agency') OR p_role IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 PERFORM 1 FROM appointment_system.google_workbooks WHERE role=p_role FOR UPDATE;
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR SHARE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM appointment_system.require_job_claim('booking',p_job,p_lease,p_attempt,j.claim_installation,j.claim_generation,j.claim_release,j.claim_contract);
 RETURN appointment_system.entry_assign_sheet_row(p_role,p_job,p_values);
END $$;

CREATE FUNCTION appointment_system.audit_credential_attempt() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE outcome appointment_system.company_login_attempts%ROWTYPE;
BEGIN
 SELECT * INTO outcome FROM appointment_system.company_login_attempts WHERE id=NEW.id;
 IF outcome.consumed_at IS NOT NULL THEN
  INSERT INTO appointment_system.company_security_events(attempt_id,subject,purpose,success,credential_revision,happened_at)
  VALUES(outcome.id,outcome.subject,outcome.purpose,outcome.success,outcome.credential_revision,outcome.consumed_at)
  ON CONFLICT(attempt_id) DO NOTHING;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.authorize_resource_operation(p_parent text, p_csrf text, p_signin_client text, p_resource text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF p_resource IS NULL OR p_resource NOT IN ('client_sheet','agency_sheet') THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='resource operation rejected';
 END IF;
 PERFORM appointment_system.resource_parent('company',p_parent,p_csrf,p_signin_client,p_resource,true);
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.available_times(p_service text, p_day date, p_questions integer DEFAULT 1) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_available_times(p_service, p_day, p_questions); END $$;

CREATE FUNCTION appointment_system.begin_booking_code(p_job uuid, p_lease uuid, p_cipher text, p_digest text, p_binding jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.booking_verification_mail%ROWTYPE;c appointment_system.booking_verification_challenges%ROWTYPE;
 ctx appointment_system.checkout_contexts%ROWTYPE;owner_id uuid;challenge uuid;spec jsonb;product jsonb;blocked text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT p.specification INTO spec FROM appointment_system.intake_settings s JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 SELECT context_id,challenge_id INTO owner_id,challenge FROM appointment_system.booking_verification_mail WHERE id=p_job;
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=owner_id FOR SHARE;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=challenge FOR SHARE;
 SELECT * INTO j FROM appointment_system.booking_verification_mail WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) OR j.provider_id IS NOT NULL THEN RETURN NULL; END IF;
 product:=appointment_system.control_snapshot();
 IF NOT coalesce((product->>'enabled')::boolean,false) OR (product->>'activation_epoch')::uuid<>ctx.activation_epoch
  OR ctx.expires_at<=clock_timestamp() OR ctx.verification_id<>c.id OR c.generation<>j.generation OR c.expires_at<=clock_timestamp() OR c.attempts>=5 OR c.verified_at IS NOT NULL
  OR c.policy_digest IS DISTINCT FROM appointment_system.verification_policy(spec) OR spec#>'{booking_verification,email}' IS DISTINCT FROM 'true'::jsonb THEN
  UPDATE appointment_system.booking_verification_mail SET state='suppressed',code_ciphertext=NULL,message_ciphertext=NULL,
   lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_obsolete' WHERE id=j.id;RETURN NULL;
 END IF;
 IF p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 32768 OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
  OR NOT appointment_system.valid_mail_binding(p_binding,to_jsonb(j))
  OR (j.message_ciphertext IS NOT NULL AND ROW(j.message_ciphertext,j.message_digest) IS DISTINCT FROM ROW(p_cipher,p_digest)) THEN RETURN NULL; END IF;
 blocked:=appointment_system.reserve_delivery_budget('booking_code',j.id);
 IF blocked IS NOT NULL THEN UPDATE appointment_system.booking_verification_mail SET state='retry_wait',last_error_code=blocked,
  next_attempt_at=least(c.expires_at,clock_timestamp()+interval '60 seconds'),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;RETURN NULL; END IF;
 UPDATE appointment_system.booking_verification_mail SET message_ciphertext=p_cipher,message_digest=p_digest,first_attempt_at=coalesce(first_attempt_at,clock_timestamp()),
  mail_account_id=p_binding->>'account_id',mail_event_account_id=p_binding->>'event_account_id',mail_credential_version=p_binding->>'credential_version',
  mail_format=p_binding->>'format',mail_idempotency_key=p_binding->>'idempotency_key' WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j)||jsonb_build_object('code_expires_at',c.expires_at);
END $_$;

CREATE FUNCTION appointment_system.begin_contact_send(p_job uuid, p_lease uuid, p_cipher text, p_digest text, p_revision bigint, p_generation uuid, p_template integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_begin_contact_send(p_job, p_lease, p_cipher, p_digest, p_revision, p_generation, p_template); END $$;

CREATE FUNCTION appointment_system.begin_email_send(p_job uuid, p_lease uuid, p_message jsonb, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_begin_email_send(p_job, p_lease, p_message, p_hash); END $$;

CREATE FUNCTION appointment_system.begin_enquiry_send(p_job uuid, p_lease uuid, p_cipher text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_begin_enquiry_send(p_job, p_lease, p_cipher, p_digest); END $$;

CREATE FUNCTION appointment_system.begin_google_workbook_create(p_role text, p_lease uuid, p_intent uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','staff','company']); IF p_role='agency' AND EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose='staff') THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource access denied'; END IF; RETURN appointment_system.entry_begin_google_workbook_create(p_role, p_lease, p_intent); END $$;

CREATE FUNCTION appointment_system.begin_recovery_run(p_run uuid, p_release text, p_scheduled bigint) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE runtime appointment_system.worker_release%ROWTYPE;product appointment_system.control_product_state%ROWTYPE;
 previous appointment_system.worker_runs%ROWTYPE;instant timestamptz:=clock_timestamp();result jsonb;items jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_run IS NULL OR p_run='00000000-0000-0000-0000-000000000000' OR p_scheduled IS NULL
  OR p_scheduled < floor(extract(epoch FROM instant-interval '24 hours')*1000)::bigint
  OR p_scheduled > floor(extract(epoch FROM instant+interval '60 seconds')*1000)::bigint
 THEN RETURN jsonb_build_object('code','run_invalid'); END IF;
 SELECT * INTO product FROM appointment_system.control_product_state WHERE singleton FOR SHARE;
 SELECT * INTO runtime FROM appointment_system.worker_release WHERE singleton FOR UPDATE;
 IF NOT FOUND OR runtime.release_digest IS DISTINCT FROM p_release THEN RETURN jsonb_build_object('code','release_mismatch'); END IF;
 SELECT * INTO previous FROM appointment_system.worker_runs WHERE id=p_run;
 IF FOUND THEN
  IF previous.release_digest<>p_release OR previous.generation<>product.restore_generation
   OR previous.scheduled_at<>to_timestamp(p_scheduled::numeric/1000) OR previous.expires_at<=instant
  THEN RETURN jsonb_build_object('code','run_conflict'); END IF;
  RETURN previous.plan;
 END IF;
 IF runtime.active_until>instant THEN RETURN jsonb_build_object('code','run_busy'); END IF;
 WITH work AS MATERIALIZED (SELECT * FROM appointment_system.recovery_due_work WHERE due IS NOT NULL)
 SELECT jsonb_object_agg(lane,jsonb_build_object('remaining_due',remaining_due,'next_due_at',next_due_at)) INTO items
 FROM (SELECT t.lane,least(10000,count(w.due) FILTER(WHERE w.due<=instant))::integer remaining_due,
  floor(extract(epoch FROM min(w.due))*1000)::bigint next_due_at
 FROM appointment_system.worker_lane_turns t LEFT JOIN work w USING(lane) GROUP BY t.lane) lane_work;
 result:=jsonb_build_object('contract',1,'application',product.project,'environment',product.environment,
  'installation_id',(SELECT installation_id FROM appointment_system.installation WHERE singleton),
  'generation',product.restore_generation,'release_digest',p_release,'run_id',p_run,
  'evaluated_at',floor(extract(epoch FROM instant)*1000)::bigint,'cursor',runtime.next_cursor,
  'lanes',items,'attention',appointment_system.recovery_attention());
 INSERT INTO appointment_system.worker_runs VALUES(p_run,product.restore_generation,p_release,
  to_timestamp(p_scheduled::numeric/1000),instant,instant+interval '90 seconds',result);
 UPDATE appointment_system.worker_release SET active_run=p_run,active_until=instant+interval '90 seconds',
  next_cursor=(next_cursor+1)%9 WHERE singleton;
 IF NOT EXISTS(SELECT 1 FROM jsonb_each(items) a WHERE (a.value->>'remaining_due')::integer>0) THEN
  UPDATE appointment_system.worker_release SET active_run=NULL,active_until=NULL WHERE singleton AND active_run=p_run;
 END IF;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.begin_scoped_contact_mail(p_job uuid, p_lease uuid, p_cipher text, p_digest text, p_binding jsonb, p_revision bigint, p_generation uuid, p_template integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.enquiry_delivery_jobs%ROWTYPE;owner_id uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
 PERFORM 1 FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j))
  OR NOT appointment_system.valid_mail_binding(p_binding,to_jsonb(j)||jsonb_build_object('template_version',coalesce(p_template,j.template_version))) THEN RETURN NULL; END IF;
 UPDATE appointment_system.enquiry_delivery_jobs SET mail_event_account_id=p_binding->>'event_account_id',mail_account_id=p_binding->>'account_id',mail_credential_version=p_binding->>'credential_version',
  mail_format=p_binding->>'format',mail_idempotency_key=p_binding->>'idempotency_key' WHERE id=p_job;
 IF p_template IS NOT NULL THEN result:=appointment_system.entry_begin_contact_send(p_job,p_lease,p_cipher,p_digest,p_revision,p_generation,p_template);
 ELSE result:=appointment_system.entry_begin_enquiry_send(p_job,p_lease,p_cipher,p_digest); END IF;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.begin_scoped_mail(p_kind text, p_job uuid, p_lease uuid, p_message jsonb, p_hash text, p_binding jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.delivery_jobs%ROWTYPE;owner_id uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_kind IS DISTINCT FROM 'booking' THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT booking_id INTO owner_id FROM appointment_system.delivery_jobs WHERE id=p_job;
 PERFORM 1 FROM appointment_system.bookings WHERE id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j))
  OR NOT appointment_system.valid_mail_binding(p_binding,to_jsonb(j)) THEN RETURN NULL; END IF;
 UPDATE appointment_system.delivery_jobs SET mail_event_account_id=p_binding->>'event_account_id',mail_account_id=p_binding->>'account_id',mail_credential_version=p_binding->>'credential_version',
  mail_format=p_binding->>'format',mail_idempotency_key=p_binding->>'idempotency_key' WHERE id=p_job;
 result:=appointment_system.entry_begin_email_send(p_job,p_lease,p_message,p_hash);
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.bind_order_search_window() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.attempted_at IS NOT NULL AND NEW.attempted_at IS DISTINCT FROM OLD.attempted_at THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='first order attempt is immutable';END IF;
 IF TG_OP='UPDATE' AND OLD.order_search_from IS NOT NULL AND (NEW.order_search_from,NEW.order_search_until) IS DISTINCT FROM
  (OLD.order_search_from,OLD.order_search_until) THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='order search window is immutable';END IF;
 IF NEW.attempted_at IS NOT NULL AND NEW.order_search_from IS NULL THEN
  NEW.order_search_from:=NEW.attempted_at-interval '5 minutes';NEW.order_search_until:=NEW.attempted_at+interval '1 day';END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.booking_snapshot(p_booking uuid) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_object('id',id,'request_id',request_id,'revision',revision,'state',state,
  'service_snapshot',service_snapshot,'starts_at',starts_at,'ends_at',ends_at,'practice_timezone',practice_timezone,
  'calendar_protocol',calendar_protocol,'policy_version',policy_version,'service_id',service_id,'verification_policy_revision',(SELECT appointment_system.verification_policy(specification) FROM appointment_system.booking_policies WHERE version=b.policy_version),'meet_url',(SELECT meet_url FROM appointment_system.meeting_events WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready'),'payment_identity',(SELECT jsonb_build_object('merchant_id',merchant_id,'mode',mode,'credential_version',credential_version,'provider_order_id',provider_order_id) FROM appointment_system.payment_orders WHERE booking_id=b.id),'created_at',created_at,'cancelled_at',cancelled_at,'original_starts_at',original_starts_at,'full_name',full_name,'email',email,'phone',phone,
  'amount_paise',amount_paise,'currency',currency,'preparation',preparation,
  'questions',coalesce((service_snapshot->>'questions')::integer,1),
  'payment_reference',(SELECT a.payment_id FROM appointment_system.accepted_payments a WHERE a.booking_id=b.id))
 FROM appointment_system.bookings b WHERE id=p_booking
$$;

CREATE FUNCTION appointment_system.booking_verification_metadata(p_context uuid, p_challenge uuid, p_email text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE locked jsonb;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);locked:=appointment_system.lock_booking_verification_context(p_context);
 IF locked->>'code'<>'ok' THEN RETURN NULL; END IF;
 SELECT jsonb_build_object('digest_key_id',digest_key_id) INTO result FROM appointment_system.booking_verification_challenges
  WHERE id=p_challenge AND context_id=p_context AND email=p_email AND id::text=locked#>>'{context,verification_id}';RETURN result;
END $$;

CREATE FUNCTION appointment_system.bounded_integer(p_value jsonb, p_min bigint, p_max bigint) RETURNS boolean
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
 SELECT coalesce(CASE WHEN jsonb_typeof(p_value)='number' AND p_value::text ~ '^(0|[1-9][0-9]{0,18})$'
  THEN p_value::text::numeric BETWEEN p_min AND p_max ELSE false END,false)
$_$;

CREATE FUNCTION appointment_system.calendar_event_identity(p_booking uuid, p_revision integer, p_protocol text) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF p_booking IS NULL OR p_revision IS NULL OR p_revision<1 THEN RETURN NULL; END IF;
 IF p_protocol='v1' THEN RETURN 'ab'||encode(sha256(convert_to(appointment_system.installation_value('installation_id')||':'||p_booking::text||':'||p_revision::text,'UTF8')),'hex');
 ELSIF p_protocol='legacy-sarsa004' THEN RETURN 'appointment'||encode(sha256(convert_to('004:'||p_booking::text||':'||p_revision::text,'UTF8')),'hex');
 ELSIF p_protocol IN ('legacy-astro003','legacy-astro003-unversioned') THEN RETURN 'astro'||replace(p_booking::text,'-','')||CASE WHEN p_revision=1 THEN '' ELSE 'r'||to_hex(p_revision) END;
 ELSE RETURN NULL; END IF;
END $$;

CREATE FUNCTION appointment_system.canonical_json(p_value jsonb) RETURNS text
    LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result text;
BEGIN
 CASE jsonb_typeof(p_value)
 WHEN 'object' THEN
  SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||
    appointment_system.canonical_json(value),',' ORDER BY key COLLATE "C"),'')||'}'
  INTO result FROM jsonb_each(p_value);
 WHEN 'array' THEN
  SELECT '['||coalesce(string_agg(appointment_system.canonical_json(value),',' ORDER BY n),'')||']'
  INTO result FROM jsonb_array_elements(p_value) WITH ORDINALITY a(value,n);
 ELSE result:=p_value::text;
 END CASE;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.claim_booking_code(p_job uuid DEFAULT NULL::uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record;j appointment_system.booking_verification_mail%ROWTYPE;c appointment_system.booking_verification_challenges%ROWTYPE;
 ctx appointment_system.checkout_contexts%ROWTYPE;product jsonb;spec jsonb;fact record;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT p.specification INTO spec FROM appointment_system.intake_settings s JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 product:=appointment_system.control_snapshot();
 FOR candidate IN SELECT id,context_id,challenge_id FROM appointment_system.booking_verification_mail
  WHERE (p_job IS NULL OR id=p_job) AND state IN ('pending','processing','retry_wait','delivery_unknown')
   AND next_attempt_at<=clock_timestamp() AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) ORDER BY next_attempt_at,id LIMIT 25 LOOP
  SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=candidate.context_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=candidate.challenge_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.booking_verification_mail WHERE id=candidate.id
   AND state IN ('pending','processing','retry_wait','delivery_unknown') AND next_attempt_at<=clock_timestamp()
   AND(lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE kind='verification' AND job_id=j.id AND result='conflict') THEN
   UPDATE appointment_system.booking_verification_mail SET state='needs_review',last_error_code='email_event_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE;
  END IF;
  SELECT provider_id INTO fact FROM appointment_system.mail_acceptance_claims WHERE kind='verification' AND job_id=j.id AND result='accepted' AND message_hash=j.message_digest ORDER BY observed_at LIMIT 1;
  IF FOUND THEN UPDATE appointment_system.booking_verification_mail SET state='completed',provider_id=fact.provider_id,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE; END IF;
  IF NOT coalesce((product->>'enabled')::boolean,false) OR (product->>'activation_epoch')::uuid<>ctx.activation_epoch
   OR ctx.expires_at<=clock_timestamp() OR ctx.verification_id<>c.id OR c.generation<>j.generation OR c.expires_at<=clock_timestamp()
   OR c.attempts>=5 OR c.verified_at IS NOT NULL OR c.policy_digest IS DISTINCT FROM appointment_system.verification_policy(spec)
   OR spec#>'{booking_verification,email}' IS DISTINCT FROM 'true'::jsonb THEN
   UPDATE appointment_system.booking_verification_mail SET state='suppressed',code_ciphertext=NULL,message_ciphertext=NULL,
    lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_obsolete' WHERE id=j.id;CONTINUE;
  END IF;
  IF j.attempts>=20 THEN UPDATE appointment_system.booking_verification_mail SET state='needs_review',last_error_code='email_attempt_limit',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE; END IF;
  UPDATE appointment_system.booking_verification_mail SET state='processing',attempts=attempts+1,lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds' WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j)||jsonb_build_object('code_expires_at',c.expires_at);
 END LOOP;RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.claim_checkout_resume(p_booking uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_claim_checkout_resume(p_booking); END $$;

CREATE FUNCTION appointment_system.claim_email_delivery() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_claim_email_delivery(); END $$;

CREATE FUNCTION appointment_system.claim_enquiry_delivery(p_lane text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_claim_enquiry_delivery(p_lane); END $$;

CREATE FUNCTION appointment_system.claim_financial_resources(p_merchant text, p_mode text, p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_claim_financial_resources(p_merchant, p_mode, p_limit); END $$;

CREATE FUNCTION appointment_system.claim_google_delivery() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_claim_google_delivery(); END $$;

CREATE FUNCTION appointment_system.claim_google_resource(p_resource text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record; j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_resource IS NOT NULL AND p_resource NOT IN('calendar','client_sheet','agency_sheet') THEN RETURN NULL; END IF;
 FOR candidate IN SELECT d.id,d.booking_id FROM appointment_system.delivery_jobs d
  WHERE (p_resource IS NULL OR (p_resource='calendar' AND (d.kind='booking_calendar' OR d.recipient_role='calendar'))
    OR (p_resource='client_sheet' AND d.kind='sheet_booking' AND d.recipient_role='client_sheet')
    OR (p_resource='agency_sheet' AND d.kind='sheet_booking' AND d.recipient_role='agency_sheet'))
   AND (d.kind IN('booking_calendar','sheet_booking') OR (d.kind='booking_cancelled' AND d.recipient_role='calendar'))
   AND d.state IN('pending','retry_wait','delivery_unknown','processing') AND d.next_attempt_at<=clock_timestamp()
   AND (d.lease_expires_at IS NULL OR d.lease_expires_at<=clock_timestamp()) ORDER BY d.next_attempt_at,d.id LIMIT 20 LOOP
  SELECT * INTO b FROM appointment_system.bookings WHERE id=candidate.booking_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=candidate.id
   AND state IN('pending','retry_wait','delivery_unknown','processing') AND next_attempt_at<=clock_timestamp()
   AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF j.payload IS NULL AND j.kind IN('booking_calendar','sheet_booking') AND (b.state<>'confirmed' OR b.revision<>j.booking_revision) THEN
   UPDATE appointment_system.delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE;
  END IF;
  IF j.kind='booking_cancelled' AND j.payload IS NULL AND b.revision<>j.booking_revision THEN
   UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='google_cancellation_snapshot_missing',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE;
  END IF;
  IF j.attempts>=20 THEN
   UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='job_attempt_limit',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE;
  END IF;
  UPDATE appointment_system.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds',
   attempts=attempts+1,first_attempt_at=coalesce(first_attempt_at,clock_timestamp()),
   payload=coalesce(payload,appointment_system.booking_snapshot(b.id))||jsonb_build_object('practice_timezone',b.practice_timezone,'calendar_protocol',b.calendar_protocol)
   WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j)||jsonb_build_object('obsolete',j.kind='booking_calendar' AND (b.state<>'confirmed' OR b.revision<>j.booking_revision));
 END LOOP;
 RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.claim_google_resource_refresh(p_resource text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$ SELECT appointment_system.claim_google_resource_refresh(p_resource,NULL::uuid); $$;

CREATE FUNCTION appointment_system.claim_google_resource_refresh(p_resource text, p_grant uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE target appointment_system.google_resources%ROWTYPE;g appointment_system.google_resource_grants%ROWTYPE;token uuid:=gen_random_uuid();
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker','staff','company']);
 IF EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose='staff')
  AND p_resource='agency_sheet' THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource access denied'; END IF;
 SELECT * INTO target FROM appointment_system.google_resources WHERE resource=p_resource FOR SHARE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO g FROM appointment_system.google_resource_grants WHERE id=CASE WHEN p_grant IS NOT NULL AND EXISTS(SELECT 1 FROM appointment_system.google_resource_grants old JOIN appointment_system.google_resource_grants current ON current.id=target.grant_id WHERE old.id=p_grant AND old.client_id=current.client_id AND old.subject=current.subject AND old.owner_email=current.owner_email) THEN target.grant_id ELSE coalesce(p_grant,target.grant_id) END FOR UPDATE;
 IF NOT FOUND OR (g.id<>target.grant_id AND NOT EXISTS(SELECT 1 FROM appointment_system.google_workbook_volumes v WHERE v.grant_id=g.id AND v.subject=g.subject AND v.client_id=g.client_id AND v.role=CASE WHEN p_resource='client_sheet' THEN 'client' WHEN p_resource='agency_sheet' THEN 'agency' ELSE '' END)) OR g.revoked_at IS NOT NULL OR g.owner_email<>target.owner_email OR NOT p_resource=ANY(g.resources)
  OR NOT g.client_id=ANY(target.retained_clients) OR (g.grant_expires_at IS NOT NULL AND g.grant_expires_at<=clock_timestamp()) THEN RETURN NULL; END IF;
 IF g.last_error_code='google_reconnect_required' THEN RETURN jsonb_build_object('code','google_reconnect_required'); END IF;
 IF g.refresh_lease_until>clock_timestamp() THEN RETURN NULL; END IF;
 UPDATE appointment_system.google_resource_grants SET refresh_lease=token,refresh_lease_until=clock_timestamp()+interval '90 seconds',refresh_revision=revision WHERE id=g.id;
 RETURN jsonb_build_object('grant_id',g.id,'resource',p_resource,'resource_revision',target.revision,'owner_email',g.owner_email,
  'subject',g.subject,'client_id',g.client_id,'resources',g.resources,'scopes',g.scopes,'revision',g.revision,
  'lease',token,'encrypted_grant',g.encrypted_grant,'grant_format',g.grant_format,'grant_expires_at',g.grant_expires_at,'server_now',clock_timestamp());
END $$;

CREATE FUNCTION appointment_system.claim_google_workbook_v2(p_role text, p_client text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','staff','company']); IF p_role='agency' AND EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose='staff') THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource access denied'; END IF; RETURN appointment_system.entry_claim_google_workbook_v2(p_role, p_client); END $$;

CREATE FUNCTION appointment_system.claim_payment_events(p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_claim_payment_events(p_limit); END $$;

CREATE FUNCTION appointment_system.claim_payment_recovery(p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT coalesce(jsonb_agg(j.value||jsonb_build_object('provider_receipt_format',b.provider_receipt_format)),'[]'::jsonb)
 INTO result FROM jsonb_array_elements(appointment_system.entry_claim_payment_recovery(p_limit)) j
 JOIN appointment_system.bookings b ON b.id=(j.value->>'booking_id')::uuid;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.claim_payment_recovery_v1(p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 20 OR p_limit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid recovery batch';
    END IF;
    WITH due AS (
        SELECT p.booking_id FROM appointment_system.payment_orders p
        WHERE (p.resolved_at IS NULL OR (p.recovery_followup AND p.resolution='confirmed')) AND p.next_check_at<=clock_timestamp()
          AND (p.lease_expires_at IS NULL OR p.lease_expires_at<=clock_timestamp())
          AND (p.state<>'creating' OR p.attempted_at<=clock_timestamp()-interval '30 seconds')
        ORDER BY p.next_check_at,p.booking_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), claimed AS (
        UPDATE appointment_system.payment_orders p
          SET recovery_followup=true,lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=p.attempts+1
          FROM due WHERE p.booking_id=due.booking_id RETURNING p.*
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('booking_id',p.booking_id,'context_id',b.context_id,
        'lease_token',p.lease_token,'attempts',p.attempts,'merchant_id',p.merchant_id,'mode',p.mode,
        'credential_version',p.credential_version,'provider_order_id',p.provider_order_id,'state',p.state,
        'amount_paise',b.amount_paise,'currency',b.currency,'hold_expires_at',b.hold_expires_at,
        'server_now',clock_timestamp(),'recovery_cursor',p.recovery_cursor,'order_search_skip',p.order_search_skip)), '[]'::jsonb)
        INTO result FROM claimed p JOIN appointment_system.bookings b ON b.id=p.booking_id;
    RETURN result;
END
$$;

CREATE FUNCTION appointment_system.claim_recovery_turn(p_run uuid, p_lane text, p_generation uuid, p_release text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE choices text[];cursor integer;selected text;position integer;token uuid:=gen_random_uuid();
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 PERFORM 1 FROM appointment_system.control_product_state WHERE singleton AND restore_generation=p_generation FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','generation_mismatch'); END IF;
 PERFORM 1 FROM appointment_system.worker_release WHERE singleton AND release_digest=p_release
  AND active_run=p_run AND active_until>clock_timestamp() FOR SHARE;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM appointment_system.worker_runs WHERE id=p_run
  AND generation=p_generation AND release_digest=p_release AND expires_at>clock_timestamp())
 THEN RETURN jsonb_build_object('code','run_expired'); END IF;
 choices:=CASE p_lane WHEN 'verification_email' THEN ARRAY['booking_code','enquiry_code']
  WHEN 'payment_events' THEN ARRAY['resource','inbox'] WHEN 'payment' THEN ARRAY['order']
  WHEN 'booking_records' THEN ARRAY['calendar','client_sheet','agency_sheet']
  WHEN 'email_events' THEN ARRAY['booking','enquiry','verification']
  WHEN 'notification_email' THEN ARRAY['booking','enquiry']
  WHEN 'enquiry_records' THEN ARRAY['client_sheet','agency_sheet']
  WHEN 'maintenance' THEN ARRAY['temporary'] WHEN 'control_publication' THEN ARRAY['display'] END;
 IF choices IS NULL THEN RETURN jsonb_build_object('code','lane_invalid'); END IF;
 SELECT next_resource INTO cursor FROM appointment_system.worker_lane_turns WHERE lane=p_lane FOR UPDATE;
 IF EXISTS(SELECT 1 FROM appointment_system.worker_lane_evaluations WHERE run_id=p_run AND lane=p_lane)
 THEN RETURN jsonb_build_object('code','turn_repeated'); END IF;
 SELECT u.resource,u.n::integer INTO selected,position FROM unnest(choices) WITH ORDINALITY u(resource,n)
 WHERE EXISTS(SELECT 1 FROM appointment_system.recovery_due_work w WHERE w.lane=p_lane AND w.resource=u.resource AND w.due<=clock_timestamp())
 ORDER BY (u.n-1-cursor+cardinality(choices))%cardinality(choices) LIMIT 1;
 IF selected IS NULL THEN selected:=choices[cursor%cardinality(choices)+1];position:=cursor%cardinality(choices)+1; END IF;
 UPDATE appointment_system.worker_lane_turns SET next_resource=position%cardinality(choices) WHERE lane=p_lane;
 INSERT INTO appointment_system.worker_lane_evaluations(run_id,lane,lease_token,resource) VALUES(p_run,p_lane,token,selected);
 RETURN jsonb_build_object('code','ok','lease_token',token,'resource',selected);
END $$;

CREATE FUNCTION appointment_system.cleanup_temporary_records() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_cleanup_temporary_records(); END $$;

CREATE FUNCTION appointment_system.close_calendar(p_operation uuid, p_actor text, p_reason text, p_start timestamp with time zone, p_end timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE old appointment_system.staff_calendar_actions%ROWTYPE; claim uuid;
BEGIN
    PERFORM pg_advisory_xact_lock_shared(83124,4);
    PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
    IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('staff-calendar-operation:'||p_operation::text,0));
    SELECT * INTO old FROM appointment_system.staff_calendar_actions WHERE operation_id=p_operation;
    IF FOUND THEN
        IF old.action <> 'close' OR old.actor IS DISTINCT FROM p_actor
           OR old.reason IS DISTINCT FROM p_reason OR old.starts_at IS DISTINCT FROM p_start
           OR old.ends_at IS DISTINCT FROM p_end THEN
            RETURN jsonb_build_object('code','request_conflict');
        END IF;
        RETURN jsonb_build_object('code','existing','claim_id',old.claim_id);
    END IF;
    IF p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end)
       OR p_end <= p_start OR p_end <= clock_timestamp() OR p_end-p_start>interval '366 days'
       OR coalesce(length(btrim(p_actor)),0) NOT BETWEEN 1 AND 200
       OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 1 AND 500 THEN
        RETURN jsonb_build_object('code','invalid_closure');
    END IF;
    PERFORM appointment_system.lock_capacity_window(p_start,p_end);
    PERFORM appointment_system.expire_relevant(p_start,p_end);
    IF EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE released_at IS NULL
        AND tstzrange(starts_at,ends_at,'[)') && tstzrange(p_start,p_end,'[)')) THEN
        RETURN jsonb_build_object('code','time_already_reserved');
    END IF;
    claim := gen_random_uuid();
    BEGIN
        INSERT INTO appointment_system.slot_claims(id,closure_reason,starts_at,ends_at)
          VALUES(claim,p_reason,p_start,p_end);
        INSERT INTO appointment_system.staff_calendar_actions(operation_id,claim_id,action,actor,reason,starts_at,ends_at)
          VALUES(p_operation,claim,'close',p_actor,p_reason,p_start,p_end);
    EXCEPTION WHEN exclusion_violation THEN
        RETURN jsonb_build_object('code','time_already_reserved');
    END;
    RETURN jsonb_build_object('code','closed','claim_id',claim);
END
$$;

CREATE FUNCTION appointment_system.company_business_settings(p_session text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.control_authorize(p_session,'service_controller');
 RETURN (SELECT jsonb_build_object('revision',s.configuration_revision::text,'quote_version',s.policy_version,
  'settings',p.specification) FROM appointment_system.intake_settings s
  JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton);
END $$;

CREATE FUNCTION appointment_system.company_credential_begin(p_token text, p_csrf text, p_risk text, p_action text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text; account text; attempt jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 IF p_action NOT IN ('reauthenticate','password') THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid credential action'; END IF;
 principal:=appointment_system.control_authorize(p_token,'service_controller',p_csrf,false);
 SELECT username INTO account FROM appointment_system.company_credentials WHERE subject=principal AND enabled;
 attempt:=appointment_system.company_login_begin(account,p_risk,encode(sha256(convert_to(account,'UTF8')),'hex'));
 IF attempt ? 'attempt_id' THEN
  UPDATE appointment_system.company_login_attempts SET purpose=p_action,bound_token=p_token
   WHERE id=(attempt->>'attempt_id')::uuid;
 END IF;
 RETURN attempt;
END $$;

CREATE FUNCTION appointment_system.company_credential_finish(p_token text, p_csrf text, p_attempt uuid, p_revision bigint, p_verified boolean, p_action text, p_new_hash text, p_new_token text, p_new_csrf text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE principal text; attempt appointment_system.company_login_attempts%ROWTYPE;
 generation uuid; instant timestamptz:=clock_timestamp(); revision bigint;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT subject INTO principal FROM appointment_system.control_company_sessions WHERE token_hash=p_token;
 IF principal IS NULL THEN RETURN false; END IF;
 -- Serialize credential upgrades for one principal before taking shared authority locks.
 PERFORM pg_advisory_xact_lock(hashtextextended(principal,82177));
 principal:=appointment_system.control_authorize(p_token,'service_controller',p_csrf,false);
 SELECT * INTO attempt FROM appointment_system.company_login_attempts WHERE id=p_attempt FOR UPDATE;
 IF NOT FOUND OR attempt.consumed_at IS NOT NULL OR attempt.expires_at<=instant
  OR attempt.subject IS DISTINCT FROM principal OR attempt.bound_token IS DISTINCT FROM p_token
  OR attempt.purpose IS DISTINCT FROM p_action OR p_action NOT IN ('reauthenticate','password') THEN RETURN false; END IF;
 UPDATE appointment_system.company_login_attempts SET consumed_at=instant WHERE id=p_attempt;
 SELECT credential_revision INTO revision FROM appointment_system.company_credentials WHERE subject=principal AND enabled;
 IF p_verified IS DISTINCT FROM true OR revision IS DISTINCT FROM p_revision
  OR attempt.credential_revision IS DISTINCT FROM p_revision
  OR coalesce(p_new_token,'') !~ '^[a-f0-9]{64}$' OR coalesce(p_new_csrf,'') !~ '^[a-f0-9]{64}$'
 THEN RETURN false; END IF;
 IF p_action='password' THEN
  IF coalesce(p_new_hash,'') !~ '^\$argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$'
  THEN RETURN false; END IF;
  UPDATE appointment_system.company_credentials SET password_hash=p_new_hash,
   credential_revision=credential_revision+1,changed_at=instant WHERE subject=principal
   RETURNING credential_revision INTO revision;
  UPDATE appointment_system.control_company_sessions SET revoked_at=instant WHERE subject=principal AND revoked_at IS NULL;
 ELSE
  IF p_new_hash IS NOT NULL THEN RETURN false; END IF;
  UPDATE appointment_system.control_company_sessions SET revoked_at=instant WHERE token_hash=p_token;
 END IF;
 SELECT restore_generation INTO generation FROM appointment_system.control_product_state WHERE singleton;
 INSERT INTO appointment_system.control_company_sessions
  (token_hash,subject,csrf_hash,restore_generation,created_at,expires_at,fresh_until,credential_revision,last_used_at)
 SELECT p_new_token,principal,p_new_csrf,generation,instant,
  CASE WHEN p_action='reauthenticate' THEN expires_at ELSE instant+interval '8 hours' END,
  least(CASE WHEN p_action='reauthenticate' THEN expires_at ELSE instant+interval '8 hours' END,
   instant+interval '10 minutes'),revision,instant
 FROM appointment_system.control_company_sessions WHERE token_hash=p_token;
 UPDATE appointment_system.company_login_attempts SET success=true WHERE id=p_attempt;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.company_login_begin(p_username text, p_risk text, p_username_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_company_login_begin(p_username, p_risk, p_username_digest); END $$;

CREATE FUNCTION appointment_system.company_login_finish(p_attempt uuid, p_revision bigint, p_verified boolean, p_token text, p_csrf text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_company_login_finish(p_attempt, p_revision, p_verified, p_token, p_csrf); END $$;

CREATE FUNCTION appointment_system.company_save_business_settings(p_session text, p_csrf text, p_operation uuid, p_expected bigint, p_spec jsonb, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text;old appointment_system.company_configuration_actions%ROWTYPE;
 config appointment_system.intake_settings%ROWTYPE;digest text;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 IF p_operation IS NULL OR p_expected IS NULL OR p_expected<1 OR p_expected>=9223372036854775807
 OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 5 AND 300 OR p_reason ~ '[[:cntrl:]]'
 OR appointment_system.validate_business(p_spec) IS DISTINCT FROM true THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid business settings'; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 actor:=appointment_system.control_authorize(p_session,'service_controller',p_csrf,false);
 SELECT * INTO config FROM appointment_system.intake_settings WHERE singleton FOR UPDATE;
 SELECT * INTO old FROM appointment_system.company_configuration_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.actor IS DISTINCT FROM actor OR old.expected_revision IS DISTINCT FROM p_expected
   OR old.specification IS DISTINCT FROM p_spec OR old.reason IS DISTINCT FROM p_reason THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='configuration operation changed'; END IF;
  RETURN old.result;
 END IF;
 PERFORM appointment_system.control_authorize(p_session,'service_controller',p_csrf,true);
 IF config.configuration_revision<>p_expected THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='business settings changed'; END IF;
 digest:=appointment_system.settings_digest(p_spec);
 INSERT INTO appointment_system.booking_policies(version,specification) VALUES(digest,p_spec)
 ON CONFLICT(version) DO NOTHING;
 UPDATE appointment_system.intake_settings SET policy_version=digest,configuration_revision=configuration_revision+1 WHERE singleton;
 result:=jsonb_build_object('saved',true,'revision',(config.configuration_revision+1)::text,'quote_version',digest);
 INSERT INTO appointment_system.company_configuration_actions(operation_id,actor,expected_revision,
  configuration_revision,settings_digest,specification,reason,result)
 VALUES(p_operation,actor,p_expected,config.configuration_revision+1,digest,p_spec,p_reason,result);
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.company_session_touch(p_token text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_company_session_touch(p_token); END $$;

CREATE FUNCTION appointment_system.complete_recovery_turn(p_run uuid, p_lane text, p_token uuid, p_generation uuid, p_release text, p_processed integer, p_retry boolean, p_attention boolean) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE response jsonb;instant timestamptz:=clock_timestamp();due integer;next_due bigint;product appointment_system.control_product_state%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 IF p_processed IS NULL OR p_processed NOT BETWEEN 0 AND 1 OR p_retry IS NULL OR p_attention IS NULL THEN RETURN jsonb_build_object('code','result_invalid'); END IF;
 SELECT * INTO product FROM appointment_system.control_product_state WHERE singleton AND restore_generation=p_generation FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','generation_mismatch'); END IF;
 PERFORM 1 FROM appointment_system.worker_release WHERE singleton AND release_digest=p_release AND active_run=p_run AND active_until>instant FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','run_expired'); END IF;
 PERFORM 1 FROM appointment_system.worker_lane_evaluations WHERE run_id=p_run AND lane=p_lane AND lease_token=p_token AND completed_at IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','turn_conflict'); END IF;
 SELECT least(10000,count(*) FILTER(WHERE w.due<=instant))::integer,floor(extract(epoch FROM min(w.due))*1000)::bigint INTO due,next_due
 FROM appointment_system.recovery_due_work w WHERE w.lane=p_lane;
 response:=jsonb_build_object('contract',1,'application',product.project,'environment',product.environment,
  'installation_id',(SELECT installation_id FROM appointment_system.installation WHERE singleton),
  'generation',p_generation,'release_digest',p_release,'run_id',p_run,'lane',p_lane,
  'code',CASE WHEN p_retry OR p_attention THEN 'deferred' WHEN p_processed=0 THEN 'evaluated-empty' ELSE 'completed-work' END,
  'evaluated_at',floor(extract(epoch FROM instant)*1000)::bigint,'processed',p_processed,
  'remaining_due',due,'next_due_at',next_due,'attention',p_retry OR p_attention OR appointment_system.recovery_attention());
 UPDATE appointment_system.worker_lane_evaluations SET completed_at=instant,result=response WHERE run_id=p_run AND lane=p_lane;
 RETURN response;
END $$;

CREATE FUNCTION appointment_system.configure_google_resources(p_resources jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE item record;expected text;previous appointment_system.google_resources%ROWTYPE;clients text[];
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY[]::text[]);
 IF jsonb_typeof(p_resources) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(p_resources)) NOT BETWEEN 1 AND 3
 THEN RETURN false; END IF;
 FOR item IN SELECT * FROM jsonb_each(p_resources) ORDER BY key LOOP
  expected:=appointment_system.installation_value(CASE WHEN item.key='agency_sheet' THEN 'owners.agency_email' ELSE 'owners.client_email' END);
  IF item.key NOT IN ('calendar','client_sheet','agency_sheet')
   OR NOT appointment_system.exact_keys(item.value,ARRAY['owner_email','active_client','retained_clients'])
   OR item.value->>'owner_email' IS DISTINCT FROM expected
   OR jsonb_typeof(item.value->'retained_clients') IS DISTINCT FROM 'array'
   OR jsonb_array_length(item.value->'retained_clients') NOT BETWEEN 1 AND 8
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(item.value->'retained_clients') k WHERE jsonb_typeof(k)<>'string' OR k#>>'{}' !~ '^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$')
  THEN RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='resource configuration invalid'; END IF;
  SELECT array_agg(k#>>'{}') INTO clients FROM jsonb_array_elements(item.value->'retained_clients') k;
  IF cardinality(clients)<>(SELECT count(DISTINCT c) FROM unnest(clients)c) OR NOT (item.value->>'active_client'=ANY(clients))
  THEN RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='resource clients invalid'; END IF;
  SELECT * INTO previous FROM appointment_system.google_resources WHERE resource=item.key FOR UPDATE;
  IF FOUND AND (previous.owner_email<>expected OR previous.grant_id IS NOT NULL AND EXISTS(
    SELECT 1 FROM appointment_system.google_resource_grants g WHERE g.id=previous.grant_id AND NOT g.client_id=ANY(clients)) OR EXISTS(SELECT 1 FROM appointment_system.google_workbook_volumes v WHERE v.role=CASE WHEN item.key='client_sheet' THEN 'client' WHEN item.key='agency_sheet' THEN 'agency' ELSE '' END AND NOT v.client_id=ANY(clients)))
  THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='saved resource connection must be retained'; END IF;
  INSERT INTO appointment_system.google_resources(resource,owner_email,active_client,retained_clients)
   VALUES(item.key,expected,item.value->>'active_client',clients) ON CONFLICT(resource) DO UPDATE
   SET active_client=excluded.active_client,retained_clients=excluded.retained_clients,updated_at=clock_timestamp();
 END LOOP;RETURN true;
END $_$;

CREATE FUNCTION appointment_system.configure_installation(p_manifest jsonb, p_business jsonb, p_enabled boolean) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE identifier uuid; old appointment_system.installation%ROWTYPE; digest text;
BEGIN
 IF p_enabled IS NULL OR NOT appointment_system.exact_keys(p_manifest,ARRAY[
  'version','installation_id','project_id','label','environment','origin','aliases','database_targets',
  'owners','sender','providers','worker','surfaces'])
  OR p_manifest->'version' IS DISTINCT FROM '1'::jsonb
  OR coalesce(p_manifest->>'project_id','') !~ '^[a-z0-9][a-z0-9-]{0,79}$'
  OR coalesce(p_manifest->>'environment','') NOT IN ('development','test','production')
  OR coalesce(p_manifest->>'origin','') !~ '^https?://[a-z0-9.-]+(:[0-9]+)?$'
  OR NOT appointment_system.validate_business(p_business)
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid installation settings'; END IF;
 BEGIN identifier:=(p_manifest->>'installation_id')::uuid;
 EXCEPTION WHEN invalid_text_representation THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid installation identity';
 END;
 IF identifier IS NULL OR identifier::text IS DISTINCT FROM p_manifest->>'installation_id'
  OR identifier='00000000-0000-0000-0000-000000000000'::uuid
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid installation identity'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO old FROM appointment_system.installation WHERE singleton FOR UPDATE;
 IF FOUND AND (old.installation_id IS DISTINCT FROM identifier
  OR old.specification IS DISTINCT FROM p_manifest)
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='installation identity cannot be replaced'; END IF;
 INSERT INTO appointment_system.installation(installation_id,project_id,environment,specification)
 VALUES(identifier,p_manifest->>'project_id',p_manifest->>'environment',p_manifest)
 ON CONFLICT(singleton) DO NOTHING;
 digest:=appointment_system.settings_digest(p_business);
 INSERT INTO appointment_system.booking_policies(version,specification) VALUES(digest,p_business)
 ON CONFLICT(version) DO NOTHING;
 INSERT INTO appointment_system.intake_settings(policy_version,public_open,schedule_browsing_open)
 VALUES(digest,false,true) ON CONFLICT(singleton) DO NOTHING;
 -- Bootstrap respects a pre-existing switch and never reactivates a restored installation.
 INSERT INTO appointment_system.control_product_state
  (singleton,project,environment,origin,enabled,requested_enabled,restore_generation,generation_sequence,revision,activation_epoch,updated_at,provenance)
 VALUES(true,p_manifest->>'project_id',p_manifest->>'environment',p_manifest->>'origin',
  p_enabled,p_enabled,gen_random_uuid(),1,1,gen_random_uuid(),clock_timestamp(),'existing_service') ON CONFLICT(singleton) DO NOTHING;
 RETURN jsonb_build_object('installation_id',identifier,'policy_version',digest);
END $_$;

CREATE FUNCTION appointment_system.configure_mail_connection(p_spec jsonb, p_daily integer, p_rolling integer) RETURNS boolean
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
   OR identity->>'format' NOT IN ('resend-legacy-job-v1','resend-legacy-verification-v1')
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

CREATE FUNCTION appointment_system.configure_payment_account(p_merchant text, p_mode text, p_version text) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE affected uuid[];previous appointment_system.intake_settings%ROWTYPE;instant timestamptz:=clock_timestamp();
BEGIN
 IF coalesce(p_merchant,'') !~ '^[A-Za-z0-9]{1,64}$' OR p_mode NOT IN ('test','live')
  OR coalesce(p_version,'') !~ '^[A-Za-z0-9_-]{1,80}$'
  OR (appointment_system.installation_value('environment')='production' AND p_mode<>'live') THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid owned payment account'; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO previous FROM appointment_system.intake_settings WHERE singleton FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF previous.merchant_id IS DISTINCT FROM p_merchant OR previous.payment_mode IS DISTINCT FROM p_mode
  OR previous.credential_version IS DISTINCT FROM p_version THEN
  SELECT coalesce(array_agg(b.id ORDER BY b.id),'{}'::uuid[]) INTO affected
  FROM appointment_system.bookings b JOIN appointment_system.payment_orders p ON p.booking_id=b.id
  WHERE b.state IN ('held','expired') AND p.state='not_attempted' AND p.attempted_at IS NULL
   AND p.provider_order_id IS NULL AND p.resolved_at IS NULL
   AND (p.merchant_id IS DISTINCT FROM p_merchant OR p.mode IS DISTINCT FROM p_mode OR p.credential_version IS DISTINCT FROM p_version)
   AND NOT EXISTS(SELECT 1 FROM appointment_system.payment_observations o WHERE o.booking_id=b.id);
  PERFORM 1 FROM appointment_system.checkout_contexts c WHERE c.id IN
   (SELECT b.context_id FROM appointment_system.bookings b WHERE b.id=ANY(affected)) ORDER BY c.id FOR UPDATE;
  PERFORM 1 FROM appointment_system.bookings WHERE id=ANY(affected) ORDER BY id FOR UPDATE;
  PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=ANY(affected) ORDER BY id FOR UPDATE;
  PERFORM 1 FROM appointment_system.payment_orders WHERE booking_id=ANY(affected) ORDER BY booking_id FOR UPDATE;
  UPDATE appointment_system.bookings SET state='expired' WHERE id=ANY(affected);
  UPDATE appointment_system.slot_claims SET released_at=instant WHERE booking_id=ANY(affected) AND released_at IS NULL;
  UPDATE appointment_system.payment_orders SET resolution='never_attempted_abandoned',resolved_at=instant,
   lease_token=NULL,lease_expires_at=NULL,recovery_followup=false WHERE booking_id=ANY(affected);
  UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL WHERE active_checkout_id=ANY(affected);
 END IF;
 UPDATE appointment_system.intake_settings SET merchant_id=p_merchant,payment_mode=p_mode,
  credential_version=p_version,public_open=true WHERE singleton;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.configure_worker_release(p_digest text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
BEGIN
 PERFORM pg_advisory_xact_lock(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY[]::text[]);
 IF p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='release invalid'; END IF;
 INSERT INTO appointment_system.worker_release(release_digest) VALUES(p_digest) ON CONFLICT(singleton) DO UPDATE
 SET release_digest=excluded.release_digest,active_run=NULL,active_until=NULL;
END $_$;

CREATE FUNCTION appointment_system.consume_request_limit(p_scope text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','staff']); RETURN appointment_system.entry_consume_request_limit(p_scope, p_key); END $$;

CREATE FUNCTION appointment_system.consume_resource_consent(p_authority text, p_state text, p_browser text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_resource_attempts%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE state_digest=p_state AND authority=p_authority;
 IF NOT FOUND OR a.browser_digest IS DISTINCT FROM p_browser OR a.consumed_at IS NOT NULL
  OR NOT appointment_system.resource_consent_current(a) THEN RETURN NULL; END IF;
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE id=a.id AND consumed_at IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE appointment_system.google_resource_attempts SET consumed_at=clock_timestamp() WHERE id=a.id;
 RETURN jsonb_build_object('id',a.id,'grant_id',a.grant_id,'resource',a.resource,'client_id',a.client_id,'owner_email',a.owner_email,
  'previous_subject',a.previous_subject,'delegated',EXISTS(SELECT 1 FROM appointment_system.google_resource_owner_links WHERE attempt_id=a.id),'encrypted_attempt',a.encrypted_attempt,'server_now',clock_timestamp());
END $$;

SET default_tablespace = '';

CREATE TABLE appointment_system.enquiries (
    request_id uuid NOT NULL,
    email_key text NOT NULL,
    receipt_digest text NOT NULL,
    request_fingerprint text NOT NULL,
    payload jsonb NOT NULL,
    generation integer DEFAULT 1 NOT NULL,
    code_digest text,
    code_ciphertext text,
    code_expires_at timestamp with time zone NOT NULL,
    resend_after timestamp with time zone NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    verified_at timestamp with time zone,
    receipt_expires_at timestamp with time zone DEFAULT (clock_timestamp() + '24:00:00'::interval) NOT NULL,
    receipt_format text DEFAULT 'v1'::text NOT NULL,
    receipt_key_id text,
    code_format text DEFAULT 'v1'::text NOT NULL,
    code_digest_format text DEFAULT 'v1'::text NOT NULL,
    code_digest_key_id text,
    CONSTRAINT enquiries_attempts_check CHECK (((attempts >= 0) AND (attempts <= 5))),
    CONSTRAINT enquiries_check CHECK (((code_digest IS NULL) = (code_ciphertext IS NULL))),
    CONSTRAINT enquiries_check1 CHECK (((verified_at IS NULL) OR ((code_digest IS NULL) AND (code_ciphertext IS NULL)))),
    CONSTRAINT enquiries_code_ciphertext_check CHECK (((length(code_ciphertext) >= 100) AND (length(code_ciphertext) <= 8192))),
    CONSTRAINT enquiries_code_digest_check CHECK ((code_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT enquiries_email_key_check CHECK ((email_key ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT enquiries_generation_check CHECK (((generation >= 1) AND (generation <= 3))),
    CONSTRAINT enquiries_payload_check CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT enquiries_receipt_digest_check CHECK ((receipt_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT enquiries_request_fingerprint_check CHECK ((request_fingerprint ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.enquiry_delivery_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    kind text NOT NULL,
    generation integer NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    deadline_at timestamp with time zone NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_token uuid,
    lease_expires_at timestamp with time zone,
    first_attempt_at timestamp with time zone,
    provider_id text,
    last_error_code text,
    destination text,
    message_ciphertext text,
    message_digest text,
    template_version integer DEFAULT 1 NOT NULL,
    send_uncertain boolean DEFAULT false NOT NULL,
    prior_send_uncertain boolean DEFAULT false NOT NULL,
    product_revision bigint,
    product_generation uuid,
    message_format text DEFAULT 'v1'::text NOT NULL,
    message_digest_format text DEFAULT 'v1'::text NOT NULL,
    mail_account_id text,
    mail_credential_version text,
    mail_format text DEFAULT 'resend-v1'::text NOT NULL,
    mail_idempotency_key text,
    mail_event_account_id text,
    claim_installation uuid,
    claim_generation uuid,
    claim_release text,
    claim_contract integer,
    CONSTRAINT enquiry_delivery_jobs_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT enquiry_delivery_jobs_check CHECK ((((kind = 'verification'::text) AND (generation > 0)) OR ((kind <> 'verification'::text) AND (generation = 0)))),
    CONSTRAINT enquiry_delivery_jobs_check1 CHECK (((state <> 'processing'::text) OR ((lease_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (claim_installation IS NOT NULL) AND (claim_generation IS NOT NULL) AND (claim_release IS NOT NULL) AND (claim_release ~ '^[a-f0-9]{64}$'::text) AND (claim_contract IS NOT NULL) AND (claim_contract = 1)))),
    CONSTRAINT enquiry_delivery_jobs_generation_check CHECK (((generation >= 0) AND (generation <= 3))),
    CONSTRAINT enquiry_delivery_jobs_kind_check CHECK ((kind = ANY (ARRAY['verification'::text, 'acknowledgement'::text, 'practice_notice'::text, 'client_sheet'::text, 'agency_sheet'::text]))),
    CONSTRAINT enquiry_delivery_jobs_message_ciphertext_check CHECK (((length(message_ciphertext) >= 100) AND (length(message_ciphertext) <= 32768))),
    CONSTRAINT enquiry_delivery_jobs_message_digest_check CHECK ((message_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT enquiry_delivery_jobs_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'suppressed'::text, 'retry_wait'::text, 'delivery_unknown'::text, 'needs_review'::text, 'failed'::text]))),
    CONSTRAINT enquiry_delivery_jobs_template_version_check CHECK ((template_version = ANY (ARRAY[1, 2, 3])))
);

CREATE FUNCTION appointment_system.contact_job_eligible(e appointment_system.enquiries, j appointment_system.enquiry_delivery_jobs) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT CASE WHEN j.kind='verification' THEN e.verified_at IS NULL AND e.generation=j.generation
    AND e.code_digest IS NOT NULL AND e.attempts<5 AND e.code_expires_at>clock_timestamp()
   ELSE e.verified_at IS NOT NULL END
$$;

CREATE FUNCTION appointment_system.control_admission(p_epoch uuid DEFAULT NULL::uuid) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','staff','worker']); RETURN appointment_system.entry_control_admission(p_epoch); END $$;

CREATE FUNCTION appointment_system.control_authorize(p_token text, p_capability text, p_csrf text DEFAULT NULL::text, p_fresh boolean DEFAULT false) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text;
BEGIN
 SELECT s.subject INTO principal FROM appointment_system.control_company_sessions s
 JOIN appointment_system.control_company_identities i ON i.subject=s.subject AND i.enabled
 JOIN appointment_system.company_credentials c ON c.subject=s.subject AND c.enabled AND c.credential_revision=s.credential_revision
 JOIN appointment_system.control_product_state p ON p.singleton AND p.restore_generation=s.restore_generation
 WHERE s.token_hash=p_token AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
  AND s.last_used_at>clock_timestamp()-interval '30 minutes'
  AND p_capability=ANY(i.capabilities) AND (p_csrf IS NULL OR p_csrf=s.csrf_hash)
  AND (NOT p_fresh OR s.fresh_until>clock_timestamp()) FOR SHARE OF s,c,i;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='company session rejected'; END IF;
 RETURN principal;
END $$;

CREATE FUNCTION appointment_system.control_claim_probe() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE job appointment_system.control_publications%ROWTYPE; product appointment_system.control_product_state%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company','worker']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO product FROM appointment_system.control_product_state WHERE singleton FOR SHARE;
 SELECT p.* INTO job FROM appointment_system.control_publications p
 JOIN appointment_system.control_command_progress c USING(operation_id)
 WHERE p.operation_id=product.winning_operation AND p.state='published' AND c.state='published'
 AND p.snapshot=appointment_system.control_snapshot() AND p.next_attempt_at<=clock_timestamp()
 AND (p.lease_until IS NULL OR p.lease_until<=clock_timestamp())
 FOR UPDATE OF p SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE appointment_system.control_publications SET lease_token=gen_random_uuid(),
  lease_until=clock_timestamp()+interval '90 seconds' WHERE operation_id=job.operation_id RETURNING * INTO job;
 RETURN jsonb_build_object('operation_id',job.operation_id,'lease_token',job.lease_token,'snapshot',job.snapshot);
END $$;

CREATE FUNCTION appointment_system.control_claim_publication() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','company']); RETURN appointment_system.entry_control_claim_publication(); END $$;

CREATE FUNCTION appointment_system.control_command(p_token text, p_csrf text, p_operation uuid, p_generation uuid, p_revision bigint, p_enabled boolean, p_reason text, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_command(p_token, p_csrf, p_operation, p_generation, p_revision, p_enabled, p_reason, p_hash); END $$;

CREATE FUNCTION appointment_system.control_command_result(p_token text, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_command_result(p_token, p_operation); END $$;

CREATE FUNCTION appointment_system.control_confirm_restore(p_operation uuid, p_projection jsonb, p_sequence bigint, p_head_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_restore_operations%ROWTYPE;completed appointment_system.control_restore_completions%ROWTYPE;
 current jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_operation IS NULL OR p_sequence IS NULL OR p_sequence<0 OR p_head_hash IS NULL OR p_head_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery completion'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO saved FROM appointment_system.control_restore_operations WHERE id=p_operation;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery operation unavailable'; END IF;
 current:=appointment_system.control_snapshot();
 IF current IS DISTINCT FROM saved.result_snapshot OR p_projection IS DISTINCT FROM current OR
   current->'enabled' IS DISTINCT FROM 'false'::jsonb OR current->>'revision' IS DISTINCT FROM '1' THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery state changed'; END IF;
 SELECT * INTO completed FROM appointment_system.control_restore_completions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF completed.projection_snapshot IS DISTINCT FROM p_projection OR completed.privacy_sequence IS DISTINCT FROM p_sequence OR
     completed.privacy_head_hash IS DISTINCT FROM p_head_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery proof changed'; END IF;
  RETURN jsonb_build_object('operation_id',p_operation,'verified',true,'replayed',true);
 END IF;
 INSERT INTO appointment_system.control_restore_completions(operation_id,restore_generation,projection_snapshot,privacy_sequence,privacy_head_hash)
 VALUES(p_operation,(current->>'restore_generation')::uuid,p_projection,p_sequence,p_head_hash);
 RETURN jsonb_build_object('operation_id',p_operation,'verified',true,'replayed',false);
END $_$;

CREATE FUNCTION appointment_system.control_control_status(p_token text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_control_status(p_token); END $$;

CREATE FUNCTION appointment_system.control_finish_publication(p_operation uuid, p_lease uuid, p_ack jsonb, p_error text DEFAULT NULL::text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','company']); RETURN appointment_system.entry_control_finish_publication(p_operation, p_lease, p_ack, p_error); END $$;

CREATE FUNCTION appointment_system.control_guard_booking() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE epoch uuid;
BEGIN
 SELECT activation_epoch INTO epoch FROM appointment_system.checkout_contexts WHERE id=NEW.context_id;
 NEW.activation_epoch:=appointment_system.control_admission(epoch);
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.control_guard_checkout_admission() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE epoch uuid;
BEGIN
 SELECT activation_epoch INTO epoch FROM appointment_system.checkout_contexts WHERE id=NEW.context_id;
 IF NOT FOUND OR epoch IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout context required'; END IF;
 NEW.activation_epoch:=appointment_system.control_admission(epoch);
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.control_guard_context() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN NEW.activation_epoch:=appointment_system.control_admission(NEW.activation_epoch); RETURN NEW; END $$;

CREATE FUNCTION appointment_system.control_guard_erased_enquiry() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM appointment_system.control_privacy_completions c JOIN appointment_system.control_privacy_intents i ON i.id=c.intent_id
   JOIN appointment_system.control_privacy_policies p ON p.id=i.policy_id WHERE c.outcome='applied' AND p.kind='abandoned_enquiry' AND i.target_id=OLD.request_id) THEN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='erased enquiry ownership is retained'; END IF;
  IF NEW.payload IS DISTINCT FROM '{}'::jsonb OR NEW.verified_at IS NOT NULL OR NEW.code_digest IS NOT NULL OR NEW.code_ciphertext IS NOT NULL
    OR NEW.request_id IS DISTINCT FROM OLD.request_id OR NEW.receipt_digest IS DISTINCT FROM OLD.receipt_digest
    OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR NEW.receipt_expires_at IS DISTINCT FROM OLD.receipt_expires_at THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='erased enquiry cannot be recreated'; END IF;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE FUNCTION appointment_system.control_guard_order_attempt() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE epoch uuid;
BEGIN
 IF NEW.attempted_at IS NOT NULL AND (TG_OP='INSERT' OR OLD.attempted_at IS NULL) THEN
  SELECT activation_epoch INTO epoch FROM appointment_system.bookings WHERE id=NEW.booking_id;
  PERFORM appointment_system.control_admission(epoch);
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.control_guard_privacy_completion() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_replay_progress
   WHERE restore_operation=NEW.operation_id AND sequence=NEW.privacy_sequence AND head_hash=NEW.privacy_head_hash) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='verified privacy replay required'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.control_guard_restored_activation() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF NEW.enabled AND EXISTS(SELECT 1 FROM appointment_system.control_restore_operations WHERE result_snapshot->>'restore_generation'=NEW.restore_generation::text)
  AND NOT EXISTS(SELECT 1 FROM appointment_system.control_restore_completions WHERE restore_generation=NEW.restore_generation) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery completion required'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.control_obligation_action(p_session text, p_csrf text, p_client text, p_action text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_obligation_action(p_session, p_csrf, p_client, p_action, p_data); END $$;

CREATE FUNCTION appointment_system.control_obligation_actor(p_session text, p_client text, p_origin text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text; expected text;
BEGIN
 IF p_origin IS DISTINCT FROM (appointment_system.installation_value('origin')||'/company/booking-support') THEN RETURN NULL; END IF;
 principal:=appointment_system.control_authorize(p_session,'obligation_handler');
 expected:='installation:'||(SELECT installation_id::text FROM appointment_system.installation WHERE singleton);
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_company_identities WHERE subject=principal AND audience=expected AND enabled)
 THEN RETURN NULL; END IF;
 RETURN 'company:'||encode(sha256(convert_to(principal,'UTF8')),'hex');
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.control_obligation_summary(p_session text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_obligation_summary(p_session); END $$;

CREATE FUNCTION appointment_system.control_privacy_apply(p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    SET "TimeZone" TO 'UTC'
    AS $$
DECLARE intent appointment_system.control_privacy_intents%ROWTYPE;completed appointment_system.control_privacy_completions%ROWTYPE;
 policy appointment_system.control_privacy_policies%ROWTYPE;target record;eligible boolean:=false;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_operation IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention operation'; END IF;
 PERFORM pg_advisory_xact_lock(83125,4);
 SELECT * INTO intent FROM appointment_system.control_privacy_intents WHERE id=p_operation;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_exports WHERE intent_id=p_operation) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='independent retention intent required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_documents WHERE intent_id=p_operation) THEN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='frozen independent document required'; END IF;
 SELECT * INTO completed FROM appointment_system.control_privacy_completions WHERE intent_id=p_operation;
 IF FOUND THEN RETURN to_jsonb(completed)||jsonb_build_object('replayed',true); END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_policy_approvals WHERE policy_id=intent.policy_id) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='owner retention approval required'; END IF;
 SELECT * INTO policy FROM appointment_system.control_privacy_policies WHERE id=intent.policy_id;
 IF policy.kind='routine_incident' THEN
  SELECT * INTO target FROM appointment_system.operational_incidents WHERE id=intent.target_id FOR UPDATE;
  eligible:=FOUND AND target.last_seen_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
    AND encode(sha256(convert_to(to_jsonb(target)::text,'UTF8')),'hex')=intent.target_hash;
  IF eligible THEN DELETE FROM appointment_system.operational_incidents WHERE id=intent.target_id; END IF;
 ELSIF policy.kind='abandoned_enquiry' THEN
  SELECT * INTO target FROM appointment_system.enquiries WHERE request_id=intent.target_id FOR UPDATE;
  IF FOUND THEN
   PERFORM 1 FROM appointment_system.enquiry_delivery_jobs WHERE request_id=intent.target_id ORDER BY id FOR UPDATE;
   eligible:=EXISTS(SELECT 1 FROM jsonb_array_elements(appointment_system.control_privacy_candidates(intent.policy_id,1,NULL,intent.target_id)->'targets') x
    WHERE x->>'target_hash'=intent.target_hash);
   IF eligible THEN
    UPDATE appointment_system.enquiries SET payload='{}'::jsonb,code_digest=NULL,code_ciphertext=NULL WHERE request_id=intent.target_id;
    -- Terminalization clears frozen ciphertext through the existing invariant;
    -- only then is expired addressing erased. Identity/evidence hashes remain.
    UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL,message_ciphertext=NULL WHERE request_id=intent.target_id;
    UPDATE appointment_system.enquiry_delivery_jobs SET destination=NULL WHERE request_id=intent.target_id;
   END IF;
  END IF;
 ELSIF policy.kind='resolved_transport' THEN
  SELECT * INTO target FROM appointment_system.transport_attempt_events WHERE id=intent.target_id;
  IF FOUND AND appointment_system.transport_job_resolved(target.job_kind,target.job_id,true) THEN
   SELECT * INTO target FROM appointment_system.transport_attempt_events WHERE id=intent.target_id FOR UPDATE;
   eligible:=FOUND AND target.occurred_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
    AND encode(sha256(convert_to(to_jsonb(target)::text,'UTF8')),'hex')=intent.target_hash;
   IF eligible THEN DELETE FROM appointment_system.transport_attempt_events WHERE id=intent.target_id; END IF;
  END IF;
 END IF;
 INSERT INTO appointment_system.control_privacy_completions(intent_id,outcome,reason)
 VALUES(p_operation,CASE WHEN eligible THEN 'applied' ELSE 'cancelled' END,CASE WHEN eligible THEN 'content_erased' ELSE 'eligibility_changed' END) RETURNING * INTO completed;
 RETURN to_jsonb(completed)||jsonb_build_object('replayed',false);
END $$;

CREATE FUNCTION appointment_system.control_privacy_attach_export(p_operation uuid, p_sequence bigint, p_entry_hash text, p_head_hash text, p_file text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_privacy_exports%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_operation IS NULL OR p_sequence IS NULL OR p_sequence<1 OR p_entry_hash IS NULL OR p_entry_hash!~'^[a-f0-9]{64}$'
  OR p_head_hash IS NULL OR p_head_hash!~'^[a-f0-9]{64}$' OR p_file IS NULL OR p_file!~'^[A-Za-z0-9_-]{10,180}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid independent retention proof'; END IF;
 PERFORM pg_advisory_xact_lock(83125,4);
 SELECT * INTO saved FROM appointment_system.control_privacy_exports WHERE intent_id=p_operation;
 IF FOUND THEN
  IF saved.sequence IS DISTINCT FROM p_sequence OR saved.entry_hash IS DISTINCT FROM p_entry_hash OR saved.head_hash IS DISTINCT FROM p_head_hash OR saved.file_id IS DISTINCT FROM p_file THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='independent retention proof changed'; END IF;
  RETURN true;
 END IF;
 INSERT INTO appointment_system.control_privacy_exports(intent_id,sequence,entry_hash,head_hash,file_id) VALUES(p_operation,p_sequence,p_entry_hash,p_head_hash,p_file);
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.control_privacy_candidates(p_policy text, p_limit integer DEFAULT 100, p_after uuid DEFAULT NULL::uuid, p_exact uuid DEFAULT NULL::uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    SET "TimeZone" TO 'UTC'
    AS $$
DECLARE policy appointment_system.control_privacy_policies%ROWTYPE;records jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_policy IS NULL OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention inspection'; END IF;
 SELECT * INTO policy FROM appointment_system.control_privacy_policies WHERE id=p_policy;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='unknown retention policy'; END IF;
 IF policy.kind='routine_incident' THEN
  SELECT coalesce(jsonb_agg(x ORDER BY x.id),'[]'::jsonb) INTO records FROM
   (SELECT id,encode(sha256(convert_to(to_jsonb(i)::text,'UTF8')),'hex') AS target_hash
    FROM appointment_system.operational_incidents i WHERE last_seen_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
      AND (p_after IS NULL OR id>p_after) AND (p_exact IS NULL OR id=p_exact) ORDER BY id LIMIT p_limit) x;
 ELSIF policy.kind='abandoned_enquiry' THEN
  SELECT coalesce(jsonb_agg(x ORDER BY x.id),'[]'::jsonb) INTO records FROM
   (SELECT e.request_id AS id,encode(sha256(convert_to(e.payload::text,'UTF8')),'hex') AS target_hash
    FROM appointment_system.enquiries e WHERE e.verified_at IS NULL AND e.payload<>'{}'::jsonb
     AND e.created_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
     AND e.receipt_expires_at<=clock_timestamp() AND e.code_expires_at<=clock_timestamp()
     AND (p_after IS NULL OR e.request_id>p_after) AND (p_exact IS NULL OR e.request_id=p_exact)
     AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs j WHERE j.request_id=e.request_id
       AND (j.kind<>'verification' OR j.state NOT IN('completed','suppressed')
        OR j.send_uncertain OR j.prior_send_uncertain OR j.deadline_at>clock_timestamp()
        OR j.lease_expires_at>clock_timestamp())) ORDER BY e.request_id LIMIT p_limit) x;
 ELSIF policy.kind='resolved_transport' THEN
  SELECT coalesce(jsonb_agg(x ORDER BY x.id),'[]'::jsonb) INTO records FROM
   (SELECT e.id,encode(sha256(convert_to(to_jsonb(e)::text,'UTF8')),'hex') AS target_hash
    FROM appointment_system.transport_attempt_events e WHERE e.occurred_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
     AND appointment_system.transport_job_resolved(e.job_kind,e.job_id)
     AND (p_after IS NULL OR e.id>p_after) AND (p_exact IS NULL OR e.id=p_exact) ORDER BY e.id LIMIT p_limit) x;
 ELSE
  -- Payment/provider/audit history is never a resolved transport log.
  records:='[]'::jsonb;
 END IF;
 RETURN jsonb_build_object('project',appointment_system.installation_value('project_id'),'environment',appointment_system.installation_value('environment'),'policy_id',policy.id,'version',policy.version,
  'approved',EXISTS(SELECT 1 FROM appointment_system.control_privacy_policy_approvals WHERE policy_id=policy.id),'targets',records);
END $$;

CREATE FUNCTION appointment_system.control_privacy_record_intent(p_operation uuid, p_policy text, p_target uuid, p_hash text, p_base bigint DEFAULT 0) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    SET "TimeZone" TO 'UTC'
    AS $_$
DECLARE saved appointment_system.control_privacy_intents%ROWTYPE;candidate jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_operation IS NULL OR p_target IS NULL OR p_base IS NULL OR p_base<0 OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention intent'; END IF;
 PERFORM pg_advisory_xact_lock(83125,4);
 SELECT * INTO saved FROM appointment_system.control_privacy_intents WHERE id=p_operation;
 IF FOUND THEN
  IF saved.policy_id IS DISTINCT FROM p_policy OR saved.target_id IS DISTINCT FROM p_target OR saved.target_hash IS DISTINCT FROM p_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retention intent changed'; END IF;
  RETURN to_jsonb(saved)||jsonb_build_object('replayed',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_policy_approvals WHERE policy_id=p_policy) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='owner retention approval required'; END IF;
 SELECT x INTO candidate FROM jsonb_array_elements(appointment_system.control_privacy_candidates(p_policy,1,NULL,p_target)->'targets') x
  WHERE x->>'id'=p_target::text AND x->>'target_hash'=p_hash;
 IF candidate IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retention target changed'; END IF;
 INSERT INTO appointment_system.control_privacy_intents(id,policy_id,target_id,target_hash,base_sequence) VALUES(p_operation,p_policy,p_target,p_hash,p_base) RETURNING * INTO saved;
 RETURN to_jsonb(saved)||jsonb_build_object('replayed',false);
END $_$;

CREATE FUNCTION appointment_system.control_privacy_replay_apply(p_restore uuid, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    SET "TimeZone" TO 'UTC'
    AS $$
DECLARE intent appointment_system.control_privacy_intents%ROWTYPE;completed appointment_system.control_privacy_completions%ROWTYPE;
 policy appointment_system.control_privacy_policies%ROWTYPE;document jsonb;current_state jsonb;restore_state jsonb;
 target record;intent_time timestamptz;cutoff timestamptz;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_restore IS NULL OR p_operation IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid privacy recovery operation'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 PERFORM pg_advisory_xact_lock(83125,4);
 SELECT appointment_system.control_snapshot() INTO current_state;
 SELECT result_snapshot INTO restore_state FROM appointment_system.control_restore_operations WHERE id=p_restore;
 IF restore_state IS NULL OR current_state IS DISTINCT FROM restore_state OR current_state->'enabled'<>'false'::jsonb THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='isolated restored generation required'; END IF;
 SELECT * INTO intent FROM appointment_system.control_privacy_intents WHERE id=p_operation;
 SELECT body INTO document FROM appointment_system.control_privacy_documents WHERE intent_id=p_operation;
 IF intent.id IS NULL OR document IS NULL OR NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_exports WHERE intent_id=p_operation) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='verified independent privacy intent required'; END IF;
 SELECT * INTO completed FROM appointment_system.control_privacy_completions WHERE intent_id=p_operation;
 IF FOUND THEN
  IF completed.outcome<>'applied' THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy recovery outcome changed'; END IF;
  RETURN to_jsonb(completed)||jsonb_build_object('replayed',true);
 END IF;
 SELECT * INTO policy FROM appointment_system.control_privacy_policies WHERE id=intent.policy_id;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_policy_approvals WHERE policy_id=intent.policy_id)
  OR document->>'operation_id' IS DISTINCT FROM intent.id::text OR document->>'policy_id' IS DISTINCT FROM intent.policy_id
  OR document->>'target_id' IS DISTINCT FROM intent.target_id::text OR document->>'target_hash' IS DISTINCT FROM intent.target_hash
  OR document->>'policy_version' IS DISTINCT FROM policy.version::text OR document->>'minimum_days' IS DISTINCT FROM policy.minimum_days::text
  OR document->>'intent_created_at' IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='privacy recovery authorization changed'; END IF;
 intent_time:=(document->>'intent_created_at')::timestamptz;
 IF intent_time>clock_timestamp() THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='future privacy intent rejected'; END IF;
 cutoff:=intent_time-make_interval(days=>policy.minimum_days);
 IF policy.kind='routine_incident' THEN
  SELECT * INTO target FROM appointment_system.operational_incidents WHERE id=intent.target_id FOR UPDATE;
  IF FOUND THEN
   IF target.last_seen_at>=cutoff THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='newer activity requires privacy review'; END IF;
   DELETE FROM appointment_system.operational_incidents WHERE id=intent.target_id;
  END IF;
 ELSIF policy.kind='abandoned_enquiry' THEN
  SELECT * INTO target FROM appointment_system.enquiries WHERE request_id=intent.target_id FOR UPDATE;
  IF FOUND THEN
   PERFORM 1 FROM appointment_system.enquiry_delivery_jobs WHERE request_id=intent.target_id ORDER BY id FOR UPDATE;
   IF target.verified_at IS NOT NULL OR target.created_at>=cutoff OR target.receipt_expires_at>intent_time OR target.code_expires_at>intent_time
    OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE request_id=intent.target_id AND (kind<>'verification' OR deadline_at>intent_time OR lease_expires_at>intent_time)) THEN
    RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='newer enquiry activity requires privacy review'; END IF;
   UPDATE appointment_system.enquiries SET payload='{}'::jsonb,code_digest=NULL,code_ciphertext=NULL WHERE request_id=intent.target_id;
   UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL,message_ciphertext=NULL WHERE request_id=intent.target_id;
   UPDATE appointment_system.enquiry_delivery_jobs SET destination=NULL WHERE request_id=intent.target_id;
  END IF;
 ELSIF policy.kind='resolved_transport' THEN
  SELECT * INTO target FROM appointment_system.transport_attempt_events WHERE id=intent.target_id;
  IF FOUND THEN
   IF NOT appointment_system.transport_job_resolved(target.job_kind,target.job_id,true) THEN
    RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='unresolved transport requires privacy review'; END IF;
   SELECT * INTO target FROM appointment_system.transport_attempt_events WHERE id=intent.target_id FOR UPDATE;
   IF FOUND THEN
    IF target.occurred_at>=cutoff OR encode(sha256(convert_to(to_jsonb(target)::text,'UTF8')),'hex') IS DISTINCT FROM intent.target_hash THEN
     RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='newer transport activity requires privacy review'; END IF;
    DELETE FROM appointment_system.transport_attempt_events WHERE id=intent.target_id;
   END IF;
  END IF;
 ELSE RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='unsupported privacy recovery policy';
 END IF;
 INSERT INTO appointment_system.control_privacy_completions(intent_id,outcome,reason) VALUES(p_operation,'applied','content_erased') RETURNING * INTO completed;
 RETURN to_jsonb(completed)||jsonb_build_object('replayed',false);
END $$;

CREATE FUNCTION appointment_system.control_probe_retry(p_operation uuid, p_lease uuid, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company','worker']);
 IF p_error IS NULL OR p_error !~ '^[a-z0-9_]{1,80}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid probe result'; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 UPDATE appointment_system.control_publications SET lease_token=NULL,lease_until=NULL,
  next_attempt_at=clock_timestamp()+interval '15 seconds',last_error=p_error
 WHERE operation_id=p_operation AND lease_token=p_lease AND state='published'
 AND operation_id=(SELECT winning_operation FROM appointment_system.control_product_state WHERE singleton);
 RETURN FOUND;
END $_$;

CREATE FUNCTION appointment_system.control_protect_maintenance_evidence() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='company maintenance evidence is immutable'; END $$;

CREATE FUNCTION appointment_system.control_protect_restore_history() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='restore history is immutable'; END $$;

CREATE FUNCTION appointment_system.control_publication_schedule() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','company']); RETURN appointment_system.entry_control_publication_schedule(); END $$;

CREATE FUNCTION appointment_system.control_record_probe(p_operation uuid, p_snapshot jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','company']); RETURN appointment_system.entry_control_record_probe(p_operation, p_snapshot); END $$;

CREATE FUNCTION appointment_system.control_repair_obligation(p_reference uuid, p_role text, p_lane text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.bookings b JOIN appointment_system.accepted_payments p ON p.booking_id=b.id
 JOIN appointment_system.delivery_jobs j ON j.booking_id=b.id WHERE b.request_id=p_reference
 AND j.state IN ('pending','processing','retry_wait','needs_review','delivery_unknown') AND
 ((p_role='client' AND p_lane='calendar' AND(j.kind='booking_calendar' OR(j.kind='booking_cancelled' AND j.recipient_role='calendar')))
 OR(p_role IN ('client','agency') AND p_lane='records' AND j.kind='sheet_booking' AND j.recipient_role=p_role||'_sheet')))
$$;

CREATE FUNCTION appointment_system.control_restore_barrier(p_operation uuid, p_external jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE previous appointment_system.control_restore_operations%ROWTYPE;current appointment_system.control_product_state%ROWTYPE;
 external_sequence bigint;result jsonb;archived jsonb;instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000'
  OR p_external IS NULL OR jsonb_typeof(p_external) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery state'; END IF;
 IF (SELECT array_agg(n ORDER BY n) FROM jsonb_object_keys(p_external) n) IS DISTINCT FROM
   ARRAY['activation_epoch','enabled','environment','generation_sequence','installation_id','origin','project','restore_generation','revision','version']::text[]
  OR p_external->>'installation_id' IS DISTINCT FROM (SELECT installation_id::text FROM appointment_system.installation WHERE singleton)
  OR p_external->>'project' IS DISTINCT FROM appointment_system.installation_value('project_id')
  OR p_external->>'environment' IS DISTINCT FROM appointment_system.installation_value('environment')
  OR p_external->>'origin' IS DISTINCT FROM appointment_system.installation_value('origin')
  OR p_external->'version' IS DISTINCT FROM '1'::jsonb OR jsonb_typeof(p_external->'enabled') IS DISTINCT FROM 'boolean'
  OR jsonb_typeof(p_external->'generation_sequence') IS DISTINCT FROM 'string'
  OR jsonb_typeof(p_external->'revision') IS DISTINCT FROM 'string'
  OR coalesce(p_external->>'generation_sequence','')!~'^[1-9][0-9]{0,18}$'
  OR coalesce(p_external->>'revision','')!~'^[1-9][0-9]{0,18}$'
  OR coalesce(p_external->>'restore_generation','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
  OR coalesce(p_external->>'activation_epoch','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery state'; END IF;
 IF (p_external->>'generation_sequence')::numeric>=9223372036854775807
  OR (p_external->>'revision')::numeric>9223372036854775807
  OR (p_external->>'restore_generation')::uuid='00000000-0000-0000-0000-000000000000'
  OR (p_external->>'activation_epoch')::uuid='00000000-0000-0000-0000-000000000000'
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery sequence invalid'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO previous FROM appointment_system.control_restore_operations WHERE id=p_operation;
 IF FOUND THEN
  IF previous.external_snapshot IS DISTINCT FROM p_external OR previous.result_snapshot IS DISTINCT FROM appointment_system.control_snapshot()
  THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery operation changed'; END IF;
  RETURN jsonb_build_object('operation_id',p_operation,'snapshot',previous.result_snapshot,'replayed',true);
 END IF;
 SELECT * INTO current FROM appointment_system.control_product_state WHERE singleton FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery state unavailable'; END IF;
 external_sequence:=(p_external->>'generation_sequence')::bigint;
 IF external_sequence<current.generation_sequence OR
  (external_sequence=current.generation_sequence AND p_external->>'restore_generation' IS DISTINCT FROM current.restore_generation::text)
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='external recovery generation is inconsistent'; END IF;
 archived:=appointment_system.control_snapshot();
 UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false,winning_operation=p_operation,
  restore_generation=gen_random_uuid(),generation_sequence=external_sequence+1,revision=1,activation_epoch=gen_random_uuid(),
  updated_at=instant,provenance='restore_reconciliation' WHERE singleton;
 result:=appointment_system.control_snapshot();
 UPDATE appointment_system.control_company_sessions SET revoked_at=instant WHERE revoked_at IS NULL;
 DELETE FROM appointment_system.control_login_challenges;
 UPDATE appointment_system.company_login_attempts SET consumed_at=instant WHERE consumed_at IS NULL;
 UPDATE appointment_system.studio_sessions SET revoked_at=instant WHERE revoked_at IS NULL;
 UPDATE appointment_system.google_attempts SET consumed_at=coalesce(consumed_at,instant),finished_at=instant WHERE finished_at IS NULL;
 UPDATE appointment_system.google_resource_attempts SET consumed_at=coalesce(consumed_at,instant),finished_at=instant,
  encrypted_grant=NULL,result=jsonb_build_object('code','restore_invalidated') WHERE finished_at IS NULL;
 UPDATE appointment_system.google_resource_owner_links SET expires_at=least(expires_at,instant);
 UPDATE appointment_system.google_resource_grants SET refresh_lease=NULL,refresh_lease_until=NULL,refresh_revision=NULL;
 UPDATE appointment_system.checkout_contexts SET expires_at=least(expires_at,instant),verification_id=NULL;
 UPDATE appointment_system.booking_verification_grants SET revoked_at=instant WHERE revoked_at IS NULL;
 UPDATE appointment_system.booking_verification_challenges SET expires_at=least(expires_at,instant),code_ciphertext=NULL,grant_digest=NULL;
 UPDATE appointment_system.booking_verification_mail SET state='suppressed',lease_token=NULL,lease_expires_at=NULL,
  code_ciphertext=NULL,last_error_code='restore_invalidated' WHERE state IN ('pending','processing','retry_wait','delivery_unknown');
 UPDATE appointment_system.enquiries SET code_expires_at=least(code_expires_at,instant),code_digest=NULL,code_ciphertext=NULL;
 UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL,message_ciphertext=NULL
  WHERE kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
 UPDATE appointment_system.enquiry_delivery_jobs SET state='delivery_unknown',lease_token=NULL,lease_expires_at=NULL
  WHERE kind<>'verification' AND state='processing';
 UPDATE appointment_system.delivery_jobs SET state='delivery_unknown',lease_token=NULL,lease_expires_at=NULL WHERE state='processing';
 UPDATE appointment_system.payment_orders SET state=CASE WHEN state='creating' THEN 'creation_unknown' ELSE state END,
  lease_token=NULL,lease_expires_at=NULL WHERE lease_token IS NOT NULL OR state='creating';
 UPDATE appointment_system.payment_cases SET financial_lease_token=NULL,financial_lease_until=NULL;
 UPDATE appointment_system.provider_inbox SET lease_token=NULL,lease_expires_at=NULL;
 UPDATE appointment_system.control_publications SET state='superseded',lease_token=NULL,lease_until=NULL
  WHERE state IN ('pending','attention');
 UPDATE appointment_system.control_command_progress SET state='superseded',updated_at=instant
  WHERE state IN ('accepted','publishing','published');
 UPDATE appointment_system.recovery_lanes SET latest_run=NULL,last_attempt_at=NULL,last_completed_at=NULL,
  active_until=NULL,outcome='unchecked',processed=0;
 UPDATE appointment_system.worker_release SET active_run=NULL,active_until=NULL WHERE singleton;
 INSERT INTO appointment_system.control_restore_operations(id,external_snapshot,archived_snapshot,result_snapshot)
  VALUES(p_operation,p_external,archived,result);
 INSERT INTO appointment_system.control_operations(id,actor_subject,body_hash,expected_generation,expected_revision,target_enabled,reason,result_snapshot)
  VALUES(p_operation,'recovery-maintenance',encode(sha256(convert_to(p_external::text,'UTF8')),'hex'),
   current.restore_generation,current.revision,false,'Restore reconciliation; fresh company sign-in required',result);
 INSERT INTO appointment_system.control_command_progress(operation_id,state) VALUES(p_operation,'accepted');
 INSERT INTO appointment_system.control_publications(operation_id,snapshot) VALUES(p_operation,result);
 RETURN jsonb_build_object('operation_id',p_operation,'snapshot',result,'replayed',false);
END $_$;

CREATE FUNCTION appointment_system.control_session_end(p_token text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_session_end(p_token); END $$;

CREATE FUNCTION appointment_system.control_snapshot() RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_object('version',1,'installation_id',i.installation_id,'project',p.project,
  'environment',p.environment,'origin',p.origin,'enabled',p.requested_enabled,
  'restore_generation',p.restore_generation,'generation_sequence',p.generation_sequence::text,
  'revision',p.revision::text,'activation_epoch',p.activation_epoch)
 FROM appointment_system.control_product_state p CROSS JOIN appointment_system.installation i WHERE p.singleton AND i.singleton
$$;

CREATE FUNCTION appointment_system.current_business() RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT p.specification FROM appointment_system.intake_settings s
 JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton
$$;

CREATE FUNCTION appointment_system.email_delivery_state(p_job uuid) RETURNS text
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT CASE
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.complained') THEN 'complained'
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.bounced') THEN 'bounced'
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.suppressed') THEN 'suppressed'
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.delivered') THEN 'delivered'
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.failed') THEN 'failed'
 WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations WHERE job_id=d.id AND event_type='email.delivery_delayed') THEN 'delayed'
 WHEN d.provider_id IS NOT NULL THEN 'accepted'
 ELSE d.state END FROM appointment_system.delivery_jobs d WHERE id=p_job AND appointment_system.is_email_job(d.kind,d.recipient_role)
$$;

CREATE FUNCTION appointment_system.email_recipient_suppressed(p_destination text) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.email_observations o JOIN appointment_system.delivery_jobs j ON j.id=o.job_id
  WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
 OR EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o JOIN appointment_system.enquiry_delivery_jobs j ON j.id=o.job_id
  WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
 OR EXISTS(SELECT 1 FROM appointment_system.booking_verification_email_observations o JOIN appointment_system.booking_verification_mail j ON j.id=o.job_id
  WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
$$;

CREATE FUNCTION appointment_system.enquiry_view(p_id uuid, p_receipt text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_enquiry_view(p_id, p_receipt); END $$;

CREATE FUNCTION appointment_system.entry_abandon_unattempted(p_context uuid, p_booking uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE context appointment_system.checkout_contexts%ROWTYPE;booking appointment_system.bookings%ROWTYPE;
 payment appointment_system.payment_orders%ROWTYPE;instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT * INTO context FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
 SELECT * INTO booking FROM appointment_system.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
 PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking ORDER BY id FOR UPDATE;
 SELECT * INTO payment FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='order intent missing'; END IF;
 IF payment.resolution='never_attempted_abandoned' THEN RETURN true; END IF;
 IF context.active_checkout_id IS DISTINCT FROM p_booking THEN RETURN false; END IF;
 IF payment.state<>'not_attempted' OR payment.attempted_at IS NOT NULL OR payment.provider_order_id IS NOT NULL
  OR payment.resolved_at IS NOT NULL OR booking.state NOT IN ('held','expired')
  OR EXISTS(SELECT 1 FROM appointment_system.payment_observations WHERE booking_id=p_booking) THEN RETURN false; END IF;
 UPDATE appointment_system.bookings SET state='expired' WHERE id=p_booking;
 UPDATE appointment_system.slot_claims SET released_at=instant WHERE booking_id=p_booking AND released_at IS NULL;
 UPDATE appointment_system.payment_orders SET resolution='never_attempted_abandoned',resolved_at=instant,
  lease_token=NULL,lease_expires_at=NULL,recovery_followup=false WHERE booking_id=p_booking;
 UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL WHERE id=p_context AND active_checkout_id=p_booking;
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.entry_admit_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE ctx appointment_system.checkout_contexts%ROWTYPE; admission appointment_system.checkout_admissions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND OR ctx.expires_at<=clock_timestamp() THEN RETURN 'context_expired'; END IF;
 PERFORM appointment_system.control_admission(ctx.activation_epoch);
 IF p_request IS NULL OR coalesce(p_receipt,'') !~ '^[a-f0-9]{64}$'
  OR coalesce(p_fingerprint,'') !~ '^[a-f0-9]{64}$' THEN RETURN 'request_conflict'; END IF;
 SELECT * INTO admission FROM appointment_system.checkout_admissions WHERE request_id=p_request;
 IF FOUND THEN
  IF admission.context_id IS DISTINCT FROM p_context OR admission.receipt_digest IS DISTINCT FROM p_receipt
   OR admission.request_fingerprint IS DISTINCT FROM p_fingerprint THEN RETURN 'request_conflict'; END IF;
  RETURN admission.outcome;
 END IF;
 IF (SELECT count(*) FROM appointment_system.checkout_admissions
  WHERE context_id=p_context AND created_at>clock_timestamp()-interval '1 hour')>=6
 THEN RETURN 'rate_limited'; END IF;
 BEGIN
  INSERT INTO appointment_system.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint,activation_epoch)
  VALUES(p_request,p_context,p_receipt,p_fingerprint,ctx.activation_epoch);
 EXCEPTION WHEN unique_violation THEN RETURN 'request_conflict'; END;
 RETURN 'pending';
END $_$;

CREATE FUNCTION appointment_system.entry_adopt_mail_acceptance(p_kind text, p_job uuid, p_lease uuid) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE data jsonb;fact appointment_system.mail_acceptance_claims%ROWTYPE;owner_id uuid;conflict boolean;
BEGIN
 IF p_kind NOT IN('booking','contact') OR p_lease IS NULL THEN RETURN 'missing';END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_kind='booking' THEN
  SELECT booking_id INTO owner_id FROM appointment_system.delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM appointment_system.bookings WHERE id=owner_id FOR SHARE;
  SELECT to_jsonb(j) INTO data FROM appointment_system.delivery_jobs j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
  SELECT to_jsonb(j) INTO data FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_job FOR UPDATE;
 END IF;
 IF data IS NULL OR(data->>'lease_token')::uuid IS DISTINCT FROM p_lease OR(data->>'lease_expires_at')::timestamptz<=clock_timestamp() THEN RETURN 'missing';END IF;
 conflict:=EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='conflict');
 SELECT * INTO fact FROM appointment_system.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='accepted' ORDER BY observed_at,id LIMIT 1;
 IF NOT FOUND AND NOT conflict THEN RETURN 'missing';END IF;
 IF NOT conflict AND coalesce(data->>'message_hash',data->>'message_digest') IS DISTINCT FROM fact.message_hash THEN conflict:=true;END IF;
 IF p_kind='booking' THEN
  UPDATE appointment_system.delivery_jobs SET state=CASE WHEN conflict THEN 'needs_review' ELSE 'completed' END,
   provider_id=CASE WHEN conflict THEN provider_id ELSE fact.provider_id::text END,
   accepted_at=CASE WHEN conflict THEN accepted_at ELSE coalesce(accepted_at,fact.observed_at) END,
   last_error_code=CASE WHEN conflict THEN 'email_provider_conflict' ELSE NULL END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
 ELSE
  UPDATE appointment_system.enquiry_delivery_jobs SET state=CASE WHEN conflict THEN 'needs_review' ELSE 'completed' END,
   provider_id=CASE WHEN conflict THEN provider_id ELSE fact.provider_id::text END,
   last_error_code=CASE WHEN conflict THEN 'email_provider_conflict' ELSE NULL END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
 END IF;
 RETURN CASE WHEN conflict THEN 'conflict' ELSE 'accepted' END;
END $$;

CREATE FUNCTION appointment_system.entry_advance_order_search(p_booking uuid, p_lease uuid, p_skip integer, p_candidates text[], p_complete boolean) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE row appointment_system.payment_orders%ROWTYPE;candidate text;conflict boolean;
BEGIN
 IF p_candidates IS NULL OR cardinality(p_candidates)>2 OR p_complete IS NULL OR p_skip IS NULL OR p_skip<0
  OR EXISTS(SELECT 1 FROM unnest(p_candidates)c WHERE c IS NULL OR c !~ '^order_[A-Za-z0-9]{1,64}$') THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid order search page';END IF;
 SELECT * INTO row FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
 IF NOT FOUND OR row.lease_token IS DISTINCT FROM p_lease OR row.lease_expires_at<=clock_timestamp()
  OR row.order_search_skip<>p_skip OR row.provider_order_id IS NOT NULL THEN RETURN jsonb_build_object('code','lease_lost');END IF;
 SELECT min(c) INTO candidate FROM(SELECT unnest(p_candidates)c UNION SELECT row.order_search_match WHERE row.order_search_match IS NOT NULL)q;
 conflict:=row.order_search_conflict OR (SELECT count(DISTINCT c)>1 FROM(SELECT unnest(p_candidates)c UNION SELECT row.order_search_match WHERE row.order_search_match IS NOT NULL)q);
 UPDATE appointment_system.payment_orders SET order_search_skip=CASE WHEN p_complete THEN 0 ELSE p_skip+90 END,
  order_search_match=candidate,order_search_conflict=conflict WHERE booking_id=p_booking;
 IF conflict THEN
  INSERT INTO appointment_system.payment_cases(id,booking_id,event_key,reason) VALUES(gen_random_uuid(),p_booking,'unknown-order:'||p_booking,'multiple_provider_orders') ON CONFLICT DO NOTHING;
 END IF;
 RETURN jsonb_build_object('code',CASE WHEN conflict THEN 'conflict' WHEN p_complete AND candidate IS NOT NULL THEN 'match'
  WHEN p_complete THEN 'not_found' ELSE 'pending' END,'order_id',CASE WHEN p_complete AND NOT conflict THEN candidate END);
END $_$;

CREATE FUNCTION appointment_system.entry_api_checkout_launchable(p1 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (SELECT EXISTS(SELECT 1 FROM appointment_system.bookings b
            JOIN appointment_system.payment_orders p ON p.booking_id=b.id
            JOIN appointment_system.checkout_contexts c ON c.id=b.context_id
            WHERE b.id=p1 AND b.state='held' AND b.hold_expires_at>clock_timestamp()
              AND c.active_checkout_id=b.id AND p.state='ready' AND p.resolved_at IS NULL
              AND EXISTS(SELECT 1 FROM appointment_system.slot_claims s WHERE s.booking_id=b.id
                AND s.released_at IS NULL AND s.starts_at<=b.starts_at AND s.ends_at>=b.ends_at)
              AND NOT EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL)
              AND NOT EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=b.id)
              AND coalesce((SELECT enabled FROM appointment_system.control_product_state WHERE singleton),false))) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_consume_limit(p1 text, p2 text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (SELECT CASE WHEN appointment_system.control_admission(NULL) IS NOT NULL THEN appointment_system.consume_request_limit(p1,p2) END) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_context_snapshot(p1 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_object('server_now',clock_timestamp(),'context',
   (SELECT jsonb_build_object('credential_digest',credential_digest,'expires_at',expires_at,
    'credential_format',credential_format,'credential_key_id',credential_key_id,'activation_epoch',activation_epoch)
    FROM appointment_system.checkout_contexts WHERE id=p1))
$$;

CREATE FUNCTION appointment_system.entry_api_create_context(p1 uuid, p2 text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE epoch uuid;expiry timestamptz;
BEGIN
 epoch:=appointment_system.control_admission(NULL);
 INSERT INTO appointment_system.checkout_contexts(id,credential_digest,expires_at,activation_epoch)
 VALUES(p1,p2,clock_timestamp()+interval '24 hours',epoch) RETURNING expires_at INTO expiry;
 RETURN to_jsonb(expiry);
END
$$;

CREATE FUNCTION appointment_system.entry_api_enquiry_verification_context(p1 uuid, p2 text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_object('email',payload->>'email','generation',generation,
 'code_digest_key_id',code_digest_key_id,'code_digest_format',code_digest_format)
 FROM appointment_system.enquiries WHERE request_id=p1 AND receipt_digest=p2 AND receipt_expires_at>clock_timestamp()
$$;

CREATE FUNCTION appointment_system.entry_api_find_order(p1 text, p2 text, p3 text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (SELECT (SELECT jsonb_build_object('booking_id',b.id,'context_id',b.context_id,
            'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
            'amount_paise',b.amount_paise,'currency',b.currency,'provider_order_id',p.provider_order_id)
            FROM appointment_system.payment_orders p JOIN appointment_system.bookings b ON b.id=p.booking_id
            WHERE p.merchant_id=p1 AND p.mode=p2 AND p.provider_order_id=p3)) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_order_intent(p1 uuid, p2 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (SELECT (SELECT jsonb_build_object(
            'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
            'amount_paise',b.amount_paise,'currency',b.currency)
            FROM appointment_system.bookings b JOIN appointment_system.payment_orders p ON p.booking_id=b.id
            WHERE b.id=p1 AND b.context_id=p2)) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_payment_intake() RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (SELECT jsonb_build_object('merchant_id',merchant_id,'mode',payment_mode,'credential_version',credential_version) FROM appointment_system.intake_settings WHERE singleton) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_receipt_snapshot(p1 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
SELECT jsonb_build_object('server_now',instant.at,'booking_product_enabled',appointment_system.control_snapshot()->'enabled','booking',(
    SELECT jsonb_build_object(
        'request_id',b.request_id,'receipt_digest',a.receipt_digest,
        'receipt_format',b.receipt_format,'receipt_key_id',b.receipt_key_id,
        'booking_id',b.id,'context_id',b.context_id,
        'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
        'receipt_expires_at',b.receipt_expires_at,'receipt_revoked_at',b.receipt_revoked_at,
        'state',b.state,'order_state',p.state,'attempted_at',p.attempted_at,
        'provider_order_id',p.provider_order_id,'resolution',p.resolution,'resolved_at',p.resolved_at,
        'hold_expires_at',b.hold_expires_at,'service_name',b.service_snapshot->>'name',
        'amount_paise',b.amount_paise,'currency',b.currency,'starts_at',b.starts_at,'ends_at',b.ends_at,
        'practice_timezone',b.practice_timezone,
        'payment_state',CASE
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL) THEN 'needs_attention'
          WHEN amounts.captured_paise>0 AND amounts.refunded_paise>=amounts.captured_paise THEN 'refunded'
          WHEN amounts.refunded_paise>0 THEN 'partially_refunded'
          WHEN EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=b.id) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_observations WHERE booking_id=b.id AND status='captured' AND captured) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM (
            SELECT DISTINCT ON (merchant_id,mode,payment_id) status
            FROM appointment_system.payment_observations WHERE booking_id=b.id
            ORDER BY merchant_id,mode,payment_id,observed_at DESC,
              CASE status WHEN 'refunded' THEN 5 WHEN 'captured' THEN 4
                WHEN 'failed' THEN 3 WHEN 'authorized' THEN 2 ELSE 1 END DESC,id DESC
          ) latest WHERE status IN ('created','authorized')) THEN 'pending'
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_observations WHERE booking_id=b.id AND status='failed') THEN 'failed_observed'
          ELSE 'unobserved' END,
        'captured_paise',coalesce(amounts.captured_paise,0),'refunded_paise',coalesce(amounts.refunded_paise,0),
        'payment_checked_at',(SELECT max(observed_at) FROM appointment_system.payment_observations WHERE booking_id=b.id),
        'meeting_state',CASE
          WHEN b.state='cancelled' THEN 'cancelled'
          WHEN EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND booking_revision=b.revision
                       AND kind='booking_calendar' AND state='needs_review') THEN 'needs_attention'
          WHEN b.state='confirmed' AND EXISTS(SELECT 1 FROM appointment_system.meeting_events WHERE booking_id=b.id
                       AND booking_revision=b.revision AND state='ready') THEN 'ready'
          WHEN b.state='confirmed' THEN 'preparing' ELSE 'not_created' END,
        'meet_url',CASE WHEN b.state='confirmed' THEN (SELECT meet_url FROM appointment_system.meeting_events
          WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready') ELSE NULL END,
        'acknowledgement_state',coalesce((SELECT appointment_system.email_delivery_state(id) FROM appointment_system.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_ack' AND recipient_role='customer'),'not_queued'),
        'meeting_email_state',coalesce((SELECT appointment_system.email_delivery_state(id) FROM appointment_system.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_details' AND recipient_role='customer'),'not_queued')
    ) FROM appointment_system.bookings b
      JOIN appointment_system.checkout_admissions a ON a.request_id=b.request_id
      JOIN appointment_system.payment_orders p ON p.booking_id=b.id
      LEFT JOIN LATERAL (
        SELECT accepted.amount_paise AS captured_paise,coalesce(max(o.refunded_paise),0) AS refunded_paise
        FROM appointment_system.accepted_payments a
        JOIN appointment_system.payment_observations accepted ON accepted.id=a.observation_id
        JOIN appointment_system.payment_observations o ON o.booking_id=a.booking_id AND o.merchant_id=a.merchant_id
          AND o.mode=a.mode AND o.payment_id=a.payment_id
        WHERE a.booking_id=b.id
        GROUP BY accepted.amount_paise
      ) amounts ON true
    WHERE b.request_id=p1
)) FROM instant) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_save_provider_event(p1 text, p2 text, p3 text, p4 text, p5 text, p6 jsonb) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
WITH inserted AS (
            INSERT INTO appointment_system.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
            VALUES(p1,p2,p3,p4,p5,p6)
            ON CONFLICT(provider,account_id,environment,event_id) DO UPDATE
              SET event_id=EXCLUDED.event_id
            RETURNING body_hash
        ) SELECT to_jsonb(body_hash) FROM inserted
$$;

CREATE FUNCTION appointment_system.entry_api_scheduling_snapshot(p1 timestamp with time zone, p2 timestamp with time zone) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
            SELECT jsonb_build_object('server_now',instant.at,
                'policy_version',s.policy_version,'public_open',s.public_open,'schedule_browsing_open',s.schedule_browsing_open,
                'specification',p.specification,
                'claims',coalesce((SELECT jsonb_agg(jsonb_build_object('starts_at',c.starts_at,'ends_at',c.ends_at))
                    FROM appointment_system.slot_claims c LEFT JOIN appointment_system.bookings b ON b.id=c.booking_id
                    WHERE c.released_at IS NULL AND c.starts_at<p1 AND c.ends_at>p2
                      AND NOT coalesce(b.state='held' AND b.hold_expires_at<=instant.at,false)), '[]'::jsonb))
            FROM instant CROSS JOIN appointment_system.intake_settings s
              JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton) q(value))
$$;

CREATE FUNCTION appointment_system.entry_api_wake_payment_recovery(p1 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
WITH changed AS (UPDATE appointment_system.payment_orders
            SET next_check_at=least(next_check_at,clock_timestamp()) WHERE booking_id=p1 AND resolved_at IS NULL
            RETURNING booking_id) SELECT to_jsonb(count(*)) FROM changed
$$;

CREATE FUNCTION appointment_system.entry_assign_enquiry_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE w appointment_system.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (10,12,15) OR p_values->>0 IS DISTINCT FROM appointment_system.installation_value('project_id')
  OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 IF NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs j JOIN appointment_system.enquiries e USING(request_id)
  WHERE j.id=p_job AND j.kind=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
  AND j.request_id::text=p_values->>2 AND e.verified_at IS NOT NULL
  AND (p_values->>3)::timestamptz=e.verified_at AND p_values->>4=e.payload->>'name'
  AND p_values->>5=e.payload->>'email' AND p_values->>6=e.payload->>'phone'
  AND p_values->>7=e.payload->>'subject' AND p_values->>8=e.payload->>'message' AND p_values->>9='received'
  AND (jsonb_array_length(p_values)=10 OR (p_values->>10=coalesce(e.payload->>'source','unknown')
   AND p_values->>11=coalesce(e.payload->>'service_interest','')))) THEN RETURN NULL; END IF;
 IF jsonb_array_length(p_values)=15 AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiries e JOIN appointment_system.enquiry_delivery_jobs j USING(request_id) WHERE j.id=p_job AND p_values->>12=coalesce(e.payload->>'kind','contact') AND p_values->>13=coalesce(e.payload->>'dob','') AND p_values->>14=coalesce(e.payload->>'location','')) THEN RETURN NULL; END IF;
 old:=appointment_system.mapped_google_row(p_role,p_job,'enquiry');
 IF old IS NOT NULL THEN
  IF old->'values' IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN old;
 END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF (w.layout_version=1 AND jsonb_array_length(p_values)<>10) OR (w.layout_version=2 AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>15) THEN RETURN NULL; END IF;
 INSERT INTO appointment_system.enquiry_sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_enquiry_row,p_values,w.volume_number);
 UPDATE appointment_system.google_workbooks SET next_enquiry_row=next_enquiry_row+1 WHERE role=p_role;
 RETURN appointment_system.mapped_google_row(p_role,p_job,'enquiry');
END $$;

CREATE FUNCTION appointment_system.entry_assign_sheet_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE w appointment_system.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (12,33) OR p_values->>0 IS DISTINCT FROM appointment_system.installation_value('project_id')
  OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 IF NOT EXISTS(SELECT 1 FROM appointment_system.delivery_jobs j WHERE j.id=p_job AND j.kind='sheet_booking'
  AND j.recipient_role=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
  AND j.booking_id::text=p_values->>2 AND j.booking_revision::text=p_values->>3) THEN RETURN NULL; END IF;
 old:=appointment_system.mapped_google_row(p_role,p_job,'booking');
 IF old IS NOT NULL THEN
  IF old->'values' IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN old;
 END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF (w.layout_version IN (1,2) AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>33) THEN RETURN NULL; END IF;
 INSERT INTO appointment_system.sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_row,p_values,w.volume_number);
 UPDATE appointment_system.google_workbooks SET next_row=next_row+1 WHERE role=p_role;
 RETURN appointment_system.mapped_google_row(p_role,p_job,'booking');
END $$;

CREATE FUNCTION appointment_system.entry_available_times(p_service text, p_day date, p_questions integer DEFAULT 1) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE spec jsonb; service jsonb; version text; instant timestamptz:=clock_timestamp(); slots jsonb;
BEGIN
 PERFORM appointment_system.control_admission(NULL);
 SELECT p.specification,p.version INTO spec,version FROM appointment_system.intake_settings s
 JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 service:=appointment_system.service_quote(spec,p_service,p_questions);
 IF service IS NULL THEN RETURN jsonb_build_object('code','service_unavailable'); END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('starts_at',offer.starts_at,'ends_at',offer.ends_at)
  ORDER BY offer.starts_at),'[]'::jsonb) INTO slots
 FROM appointment_system.schedule_starts(spec,(service->>'duration_minutes')::integer,p_day,instant) offer
 WHERE NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims c
  LEFT JOIN appointment_system.bookings b ON b.id=c.booking_id
  WHERE c.released_at IS NULL
   AND NOT coalesce(b.state='held' AND b.hold_expires_at<=instant,false)
   AND tstzrange(c.starts_at,c.ends_at,'[)') && tstzrange(offer.occupied_start,offer.occupied_end,'[)'));
 RETURN jsonb_build_object('service',service||jsonb_build_object('quote_version',version,'timezone',spec->>'timezone'),
  'date',p_day,'server_now',instant,'slots',slots);
END $$;

CREATE FUNCTION appointment_system.entry_begin_contact_send(p_job uuid, p_lease uuid, p_cipher text, p_digest text, p_revision bigint, p_generation uuid, p_template integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.enquiry_delivery_jobs%ROWTYPE;snapshot jsonb;owner_id uuid;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
 PERFORM 1 FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN NULL; END IF;
 IF j.first_attempt_at IS NULL AND j.message_ciphertext IS NULL THEN
  snapshot:=appointment_system.control_snapshot();
  IF p_revision IS DISTINCT FROM (snapshot->>'revision')::bigint OR p_generation IS DISTINCT FROM (snapshot->>'generation')::uuid
   OR p_template IS DISTINCT FROM (CASE WHEN coalesce((snapshot->>'enabled')::boolean,false) THEN 2 ELSE 3 END) THEN
   UPDATE appointment_system.enquiry_delivery_jobs SET state='pending',next_attempt_at=clock_timestamp(),lease_token=NULL,lease_expires_at=NULL,last_error_code='message_policy_changed' WHERE id=j.id;
   RETURN NULL;
  END IF;
  UPDATE appointment_system.enquiry_delivery_jobs SET product_revision=p_revision,product_generation=p_generation,template_version=p_template WHERE id=j.id;
 END IF;
 RETURN appointment_system.begin_enquiry_send(p_job,p_lease,p_cipher,p_digest);
END $$;

CREATE FUNCTION appointment_system.entry_begin_email_send(p_job uuid, p_lease uuid, p_message jsonb, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE; owner_id uuid;
 policy appointment_system.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp(); blocked text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT booking_id INTO owner_id FROM appointment_system.delivery_jobs WHERE id=p_job;
 SELECT * INTO b FROM appointment_system.bookings WHERE id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT appointment_system.is_email_job(j.kind,j.recipient_role) OR p_lease IS NULL
   OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN NULL; END IF;
 IF j.provider_id IS NOT NULL THEN
   UPDATE appointment_system.delivery_jobs SET state='completed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF j.kind<>'payment_review' AND (b.revision<>j.booking_revision OR
   (j.kind='booking_cancelled' AND b.state<>'cancelled') OR(j.kind<>'booking_cancelled' AND b.state<>'confirmed')) THEN
   blocked:='email_obsolete_revision';
 ELSIF j.send_deadline_at IS NULL OR j.send_deadline_at<=instant THEN blocked:='email_deadline_passed';
 ELSIF j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours' THEN blocked:='email_retry_window_closed';
 ELSIF appointment_system.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed';
 END IF;
 IF blocked IS NOT NULL THEN
   UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code=blocked,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF p_message IS NULL OR jsonb_typeof(p_message)<>'object' OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$'
  OR p_message->'to' IS DISTINCT FROM jsonb_build_array(j.destination)
  OR (j.message_snapshot IS NOT NULL AND (j.message_snapshot IS DISTINCT FROM p_message OR j.message_hash IS DISTINCT FROM p_hash))
  OR (j.mail_format='resend-v1' AND (p_message->>'from' IS DISTINCT FROM appointment_system.installation_value('sender.formatted')
   OR p_message->>'reply_to' IS DISTINCT FROM appointment_system.installation_value('sender.reply_to')
   OR p_message->'tags' IS DISTINCT FROM appointment_system.mail_tags(j.id,j.template_version)))
  OR (j.mail_format<>'resend-v1' AND j.message_snapshot IS NULL) THEN RETURN NULL; END IF;
 blocked:=appointment_system.reserve_mail_budget(j.id,NULL,false);
 IF blocked IS NOT NULL THEN
  UPDATE appointment_system.delivery_jobs SET state='pending',last_error_code=blocked,next_attempt_at=instant+interval '15 minutes',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
  RETURN NULL;
 END IF;
 UPDATE appointment_system.delivery_jobs SET message_snapshot=p_message,message_hash=p_hash,
   first_attempt_at=coalesce(first_attempt_at,instant),prior_send_uncertain=send_uncertain,send_uncertain=true,ever_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $_$;

CREATE FUNCTION appointment_system.entry_begin_enquiry_send(p_job uuid, p_lease uuid, p_cipher text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE e appointment_system.enquiries%ROWTYPE;j appointment_system.enquiry_delivery_jobs%ROWTYPE;
 owner_id uuid; policy appointment_system.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp();blocked text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
 SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.kind NOT IN ('verification','acknowledgement','practice_notice') OR p_lease IS NULL
  OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN NULL; END IF;
 IF NOT appointment_system.contact_job_eligible(e,j) OR (j.deadline_at<=instant AND (j.kind NOT IN('acknowledgement','practice_notice') OR j.send_uncertain OR coalesce(j.last_error_code,'') NOT IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) THEN blocked:='contact_deadline_or_state';
 ELSIF j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours' THEN blocked:='email_retry_window_closed';
 ELSIF appointment_system.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed'; END IF;
 IF blocked IS NOT NULL THEN
  UPDATE appointment_system.enquiry_delivery_jobs SET state=CASE WHEN kind='verification' THEN 'suppressed' ELSE 'needs_review' END,
   last_error_code=blocked,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 IF j.provider_id IS NOT NULL THEN
  UPDATE appointment_system.enquiry_delivery_jobs SET state='completed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 IF p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 32768 OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
  OR (j.first_attempt_at IS NOT NULL AND (j.message_ciphertext IS DISTINCT FROM p_cipher OR j.message_digest IS DISTINCT FROM p_digest)) THEN RETURN NULL; END IF;
 blocked:=appointment_system.reserve_mail_budget(NULL,j.id,j.kind='verification');
 IF blocked IS NOT NULL THEN
  UPDATE appointment_system.enquiry_delivery_jobs SET state='pending',last_error_code=blocked,
   next_attempt_at=CASE WHEN kind='verification' THEN least(deadline_at,instant+interval '15 minutes') ELSE instant+interval '15 minutes' END,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
  RETURN NULL;
 END IF;
 UPDATE appointment_system.enquiry_delivery_jobs SET message_ciphertext=p_cipher,message_digest=p_digest,message_format=CASE WHEN j.message_ciphertext IS NULL THEN 'v1' ELSE j.message_format END,message_digest_format=CASE WHEN j.message_ciphertext IS NULL THEN 'v1' ELSE j.message_digest_format END,
  first_attempt_at=coalesce(first_attempt_at,instant),prior_send_uncertain=send_uncertain,send_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $_$;

CREATE FUNCTION appointment_system.entry_begin_google_workbook_create(p_role text, p_lease uuid, p_intent uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE changed integer;
BEGIN
 UPDATE appointment_system.google_workbooks w SET creation_attempt_at=clock_timestamp()
 WHERE role=p_role AND lease=p_lease AND intent=p_intent AND state='creating' AND creation_attempt_at IS NULL
  AND lease_until>clock_timestamp() AND EXISTS(SELECT 1 FROM appointment_system.google_sheet_connections g WHERE g.role=w.role
   AND g.subject=w.subject AND g.client_id=w.client_id AND g.revision=w.connection_revision);
 GET DIAGNOSTICS changed=ROW_COUNT;
 RETURN changed=1;
END $$;

CREATE FUNCTION appointment_system.entry_claim_checkout_resume(p_booking uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
    WITH claimed AS (
        UPDATE appointment_system.payment_orders p
        SET lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds',
            resume_started_at=clock_timestamp()
        WHERE p.booking_id=p_booking AND p.state='ready' AND p.provider_order_id IS NOT NULL
          AND p.resolved_at IS NULL
          AND (p.lease_expires_at IS NULL OR p.lease_expires_at<=clock_timestamp())
          AND (p.resume_started_at IS NULL OR p.resume_started_at<=clock_timestamp()-interval '15 seconds')
          AND EXISTS(SELECT 1 FROM appointment_system.bookings b
            JOIN appointment_system.checkout_contexts c ON c.id=b.context_id
            WHERE b.id=p.booking_id AND b.state='held' AND b.hold_expires_at>clock_timestamp()
              AND c.active_checkout_id=b.id)
        RETURNING p.*
    ) SELECT (SELECT jsonb_build_object('booking_id',booking_id,'lease_token',lease_token,
        'recovery_cursor',recovery_cursor,'order_search_skip',order_search_skip) FROM claimed)
$$;

CREATE FUNCTION appointment_system.entry_claim_email_delivery() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE; candidate record; link text;
BEGIN
 FOR candidate IN SELECT id,booking_id FROM appointment_system.delivery_jobs
   WHERE appointment_system.is_email_job(kind,recipient_role) AND state IN ('pending','retry_wait','delivery_unknown','processing')
   AND next_attempt_at<=clock_timestamp() AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
   ORDER BY next_attempt_at,id LIMIT 20 LOOP
  SELECT * INTO b FROM appointment_system.bookings WHERE id=candidate.booking_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=candidate.id
    AND state IN ('pending','retry_wait','delivery_unknown','processing') AND next_attempt_at<=clock_timestamp()
    AND(lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF j.provider_id IS NOT NULL THEN
    UPDATE appointment_system.delivery_jobs SET state='completed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF j.kind<>'payment_review' AND (j.booking_revision<>b.revision OR
    (j.kind='booking_cancelled' AND b.state<>'cancelled') OR (j.kind<>'booking_cancelled' AND b.state<>'confirmed')) THEN
    UPDATE appointment_system.delivery_jobs SET state=CASE WHEN first_attempt_at IS NULL THEN 'suppressed' ELSE 'needs_review' END,
      last_error_code='email_obsolete_revision',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF j.kind='booking_details' THEN
    SELECT meet_url INTO link FROM appointment_system.meeting_events WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready';
    IF link IS NULL THEN
      UPDATE appointment_system.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '30 seconds' WHERE id=j.id;
      CONTINUE;
    END IF;
  END IF;
  IF j.attempts>=20 THEN UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='job_attempt_limit',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE; END IF;
  UPDATE appointment_system.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
    lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=attempts+1,
    send_deadline_at=coalesce(send_deadline_at,CASE WHEN kind IN ('booking_ack','booking_details') THEN b.starts_at
      ELSE clock_timestamp()+interval '24 hours' END),
    destination=coalesce(destination,CASE WHEN recipient_role='customer' THEN b.email ELSE appointment_system.installation_value('owners.client_email') END),
    payload=CASE WHEN message_snapshot IS NULL AND first_attempt_at IS NULL THEN coalesce(payload,'{}'::jsonb)||jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name',
      'starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'practice_timezone',b.practice_timezone,'meeting',b.service_snapshot->>'meeting',
      'meet_url',CASE WHEN kind='booking_details' THEN link ELSE NULL END) ELSE payload END
    WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j);
 END LOOP;
 RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.entry_claim_enquiry_delivery(p_lane text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record;e appointment_system.enquiries%ROWTYPE;j appointment_system.enquiry_delivery_jobs%ROWTYPE;
BEGIN
 IF p_lane IS NULL OR p_lane NOT IN ('email','google','verification','notification','client_sheet','agency_sheet') THEN RETURN NULL; END IF;
 FOR candidate IN SELECT id,request_id FROM appointment_system.enquiry_delivery_jobs
  WHERE ((p_lane='google' AND kind IN ('client_sheet','agency_sheet')) OR (p_lane='email' AND kind NOT IN ('client_sheet','agency_sheet')) OR (p_lane='verification' AND kind='verification') OR (p_lane='notification' AND kind NOT IN ('client_sheet','agency_sheet','verification')) OR kind=p_lane)
   AND state IN ('pending','retry_wait','delivery_unknown','processing') AND next_attempt_at<=clock_timestamp()
   AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) ORDER BY (kind='verification') DESC,next_attempt_at,id LIMIT 20 LOOP
  SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=candidate.request_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=candidate.id
    AND state IN ('pending','retry_wait','delivery_unknown','processing') AND next_attempt_at<=clock_timestamp()
    AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF NOT appointment_system.contact_job_eligible(e,j) OR (j.deadline_at<=clock_timestamp() AND (j.kind NOT IN('acknowledgement','practice_notice') OR j.send_uncertain OR coalesce(j.last_error_code,'') NOT IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) THEN
   UPDATE appointment_system.enquiry_delivery_jobs SET state=CASE WHEN kind='verification' THEN 'suppressed' ELSE 'needs_review' END,
    last_error_code='contact_deadline_or_state',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   CONTINUE;
  END IF;
  IF j.provider_id IS NOT NULL THEN
   UPDATE appointment_system.enquiry_delivery_jobs SET state=CASE WHEN kind IN ('client_sheet','agency_sheet') THEN 'completed' ELSE 'completed' END,
    lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; CONTINUE;
  END IF;
  IF j.attempts>=20 THEN UPDATE appointment_system.enquiry_delivery_jobs SET state='needs_review',last_error_code='job_attempt_limit',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE; END IF;
  UPDATE appointment_system.enquiry_delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
   lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=attempts+1,
   destination=coalesce(destination,CASE WHEN kind='practice_notice' THEN appointment_system.installation_value('owners.client_email')
    WHEN kind NOT IN ('client_sheet','agency_sheet') THEN e.payload->>'email' ELSE NULL END) WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j)||jsonb_build_object('payload',e.payload,'verified_at',e.verified_at,
    'render_version',CASE WHEN j.first_attempt_at IS NULL AND j.message_ciphertext IS NULL THEN CASE WHEN coalesce((appointment_system.control_snapshot()->>'enabled')::boolean,false) THEN 2 ELSE 3 END ELSE j.template_version END,
    'observed_product_revision',(appointment_system.control_snapshot()->>'revision')::bigint,
    'observed_product_generation',appointment_system.control_snapshot()->>'generation',
    'code_format',e.code_format,'code_ciphertext',CASE WHEN j.kind='verification' THEN e.code_ciphertext END,'code_expires_at',e.code_expires_at);
 END LOOP;
 RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.entry_claim_financial_resources(p_merchant text, p_mode text, p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE result jsonb;inbox_due timestamptz;
BEGIN
 IF p_limit IS NULL OR p_limit<>1 OR (p_merchant IS NOT NULL AND p_merchant !~ '^[A-Za-z0-9]{1,64}$')
 OR (p_mode IS NOT NULL AND p_mode NOT IN('test','live')) THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial claim';END IF;
 SELECT coalesce((SELECT min(next_attempt_at) FROM appointment_system.provider_inbox WHERE provider='razorpay' AND processed_at IS NULL AND (p_merchant IS NULL OR account_id=p_merchant) AND (p_mode IS NULL OR environment=p_mode)),clock_timestamp()) INTO inbox_due;
 WITH due AS(
  SELECT c.id FROM appointment_system.payment_cases c JOIN appointment_system.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2)
  WHERE c.resolved_at IS NULL AND (NOT f.verified OR f.attention_reason IS NOT NULL OR f.status IN('pending','open','under_review'))
  AND (p_merchant IS NULL OR f.merchant_id=p_merchant) AND (p_mode IS NULL OR f.mode=p_mode)
  AND c.next_check_at<=clock_timestamp() 
  AND (c.financial_lease_until IS NULL OR c.financial_lease_until<=clock_timestamp())
  ORDER BY c.next_check_at,c.id LIMIT 1 FOR UPDATE OF c SKIP LOCKED
 ),claimed AS(
  UPDATE appointment_system.payment_cases c SET financial_lease_token=gen_random_uuid(),financial_lease_until=clock_timestamp()+interval '90 seconds',
   financial_attempts=c.financial_attempts+1 FROM due WHERE c.id=due.id RETURNING c.*
 )SELECT coalesce(jsonb_agg(jsonb_build_object('case_id',c.id,'booking_id',c.booking_id,'lease_token',c.financial_lease_token,
  'attempts',c.financial_attempts,'created_at',c.financial_first_seen,'server_now',clock_timestamp(),'merchant_id',f.merchant_id,'mode',f.mode,
  'credential_version',o.credential_version,'payment_id',f.payment_id,'order_id',o.provider_order_id,'fact',f.fact,'amount_paise',b.amount_paise,'context_id',b.context_id)), '[]'::jsonb)
 INTO result FROM claimed c JOIN appointment_system.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2)
 JOIN appointment_system.payment_orders o ON o.booking_id=c.booking_id JOIN appointment_system.bookings b ON b.id=c.booking_id;
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.entry_claim_google_delivery() RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT appointment_system.claim_google_resource(NULL);
$$;

CREATE FUNCTION appointment_system.entry_claim_google_workbook_v2(p_role text, p_client text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE g appointment_system.google_sheet_connections%ROWTYPE; w appointment_system.google_workbooks%ROWTYPE;
 v appointment_system.google_workbook_volumes%ROWTYPE; token uuid; action text;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_client IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 SELECT * INTO g FROM appointment_system.google_sheet_connections WHERE role=p_role AND client_id=p_client;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role FOR UPDATE;
 token:=gen_random_uuid();
 IF NOT FOUND THEN
  INSERT INTO appointment_system.google_workbooks(role,subject,client_id,layout_version,state,lease,lease_until,connection_revision)
   VALUES(p_role,g.subject,p_client,3,'creating',token,clock_timestamp()+interval '180 seconds',g.revision) RETURNING * INTO w;
  action:='create';
 ELSE
  IF w.state='creating' AND (w.client_id<>p_client OR w.subject<>g.subject) THEN RETURN jsonb_build_object('action','review','code','google_workbook_client_changed_unresolved'); END IF;
  IF w.state='ready' AND (greatest(w.next_row,w.next_enquiry_row)>=9000 OR w.layout_version<3 OR w.client_id<>p_client OR w.subject<>g.subject) THEN
   UPDATE appointment_system.google_workbook_volumes SET state='retired' WHERE role=p_role AND volume_number=w.volume_number;
   UPDATE appointment_system.google_workbooks SET volume_number=volume_number+1,intent=gen_random_uuid(),spreadsheet_id=NULL,
    state='creating',layout_version=3,client_id=p_client,subject=g.subject,creation_attempt_at=NULL,next_row=2,next_enquiry_row=2,lease=token,lease_until=clock_timestamp()+interval '180 seconds',
    connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
   INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,state,grant_id)
    VALUES(p_role,w.volume_number,3,w.intent,w.subject,w.client_id,'creating',(SELECT grant_id FROM appointment_system.google_resources WHERE resource=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END));
   action:='create';
  ELSIF w.state='ready' THEN action:='ready';
  ELSE
   IF w.lease_until>clock_timestamp() AND w.connection_revision=g.revision THEN RETURN NULL; END IF;
   UPDATE appointment_system.google_workbooks SET lease=token,lease_until=clock_timestamp()+interval '180 seconds',
    connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
   action:=CASE WHEN w.creation_attempt_at IS NULL THEN 'create' ELSE 'discover' END;
  END IF;
 END IF;
 SELECT * INTO v FROM appointment_system.google_workbook_volumes WHERE role=p_role AND volume_number=w.volume_number;
 RETURN to_jsonb(w)||jsonb_build_object('action',action,'generation',v.generation,'layout_version',v.layout_version);
END $$;

CREATE FUNCTION appointment_system.entry_claim_payment_events(p_limit integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 20 OR p_limit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event batch';
    END IF;
    WITH due AS (
        SELECT provider,account_id,environment,event_id FROM appointment_system.provider_inbox
        WHERE provider='razorpay' AND processed_at IS NULL AND next_attempt_at<=clock_timestamp()
          AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
        ORDER BY next_attempt_at,received_at,event_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), claimed AS (
        UPDATE appointment_system.provider_inbox p SET lease_token=gen_random_uuid(),
          lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=p.attempts+1
        FROM due d WHERE (p.provider,p.account_id,p.environment,p.event_id)=(d.provider,d.account_id,d.environment,d.event_id)
        RETURNING p.*
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('provider',provider,'account_id',account_id,
        'environment',environment,'event_id',event_id,'payload',payload,'body_hash',body_hash,'received_at',received_at,'server_now',clock_timestamp(),'lease_token',lease_token,'attempts',attempts)), '[]'::jsonb)
        INTO result FROM claimed;
    RETURN result;
END
$$;

CREATE FUNCTION appointment_system.entry_claim_payment_recovery(p_limit integer) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT coalesce(jsonb_agg(j.value||jsonb_build_object('order_search_match',p.order_search_match,
  'order_search_conflict',p.order_search_conflict,'order_search_from',p.order_search_from,
  'order_search_until',p.order_search_until,'attempted_at',p.attempted_at,'created_at',b.created_at)), '[]'::jsonb)
 FROM jsonb_array_elements(appointment_system.claim_payment_recovery_v1(p_limit))j
 JOIN appointment_system.payment_orders p ON p.booking_id=(j.value->>'booking_id')::uuid
 JOIN appointment_system.bookings b ON b.id=p.booking_id;
$$;

CREATE FUNCTION appointment_system.entry_cleanup_temporary_records() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE cutoff timestamptz:=clock_timestamp()-interval '24 hours';
 attempts_removed integer; sessions_removed integer; limits_removed integer;
BEGIN
 IF NOT pg_try_advisory_xact_lock(4004311) THEN
  RETURN jsonb_build_object('processed',0,'removed',jsonb_build_object('attempts',0,'sessions',0,'limits',0));
 END IF;
 WITH expired AS (
  SELECT state_digest FROM appointment_system.google_attempts WHERE expires_at<cutoff
   ORDER BY expires_at,state_digest LIMIT 500 FOR UPDATE SKIP LOCKED
 ) DELETE FROM appointment_system.google_attempts a USING expired e WHERE a.state_digest=e.state_digest;
 GET DIAGNOSTICS attempts_removed=ROW_COUNT;
 WITH expired AS (
  SELECT s.digest FROM appointment_system.studio_sessions s WHERE s.expires_at<cutoff
   AND NOT EXISTS(SELECT 1 FROM appointment_system.google_attempts a WHERE a.session_digest=s.digest)
   ORDER BY s.expires_at,s.digest LIMIT 500 FOR UPDATE OF s SKIP LOCKED
 ) DELETE FROM appointment_system.studio_sessions s USING expired e WHERE s.digest=e.digest;
 GET DIAGNOSTICS sessions_removed=ROW_COUNT;
 WITH expired AS (
  SELECT scope,key_digest,window_start FROM appointment_system.request_limits WHERE expires_at<cutoff
   ORDER BY expires_at,scope,key_digest,window_start LIMIT 500 FOR UPDATE SKIP LOCKED
 ) DELETE FROM appointment_system.request_limits r USING expired e
   WHERE r.scope=e.scope AND r.key_digest=e.key_digest AND r.window_start=e.window_start;
 GET DIAGNOSTICS limits_removed=ROW_COUNT;
 RETURN jsonb_build_object('processed',CASE WHEN attempts_removed+sessions_removed+limits_removed>0 THEN 1 ELSE 0 END,
  'removed',jsonb_build_object('attempts',attempts_removed,'sessions',sessions_removed,'limits',limits_removed));
END $$;

CREATE FUNCTION appointment_system.entry_company_login_begin(p_username text, p_risk text, p_username_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE credential appointment_system.company_credentials%ROWTYPE; attempt uuid; instant timestamptz:=clock_timestamp();
BEGIN
 IF coalesce(p_username,'') !~ '^[a-z0-9][a-z0-9_.-]{2,63}$'
  OR coalesce(p_risk,'') !~ '^[a-f0-9]{64}$' OR coalesce(p_username_digest,'') !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='company login rejected'; END IF;
 -- Sorted digest locks serialize admission without locking customer work.
 PERFORM pg_advisory_xact_lock(hashtextextended(digest,82176))
 FROM unnest(ARRAY[p_risk,p_username_digest]) digest ORDER BY digest;
 IF (SELECT count(*) FROM appointment_system.company_login_attempts WHERE risk_digest=p_risk
      AND created_at>instant-interval '1 hour')>=20
  OR (SELECT count(*) FROM appointment_system.company_login_attempts WHERE username_digest=p_username_digest
      AND created_at>instant-interval '15 minutes')>=5
 THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 SELECT * INTO credential FROM appointment_system.company_credentials WHERE username=p_username AND enabled;
 attempt:=gen_random_uuid();
 INSERT INTO appointment_system.company_login_attempts(id,subject,credential_revision,risk_digest,username_digest)
 VALUES(attempt,credential.subject,credential.credential_revision,p_risk,p_username_digest);
 RETURN jsonb_build_object('attempt_id',attempt,'subject',credential.subject,
  'credential_revision',credential.credential_revision,'password_hash',credential.password_hash);
END $_$;

CREATE FUNCTION appointment_system.entry_company_login_finish(p_attempt uuid, p_revision bigint, p_verified boolean, p_token text, p_csrf text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE attempt appointment_system.company_login_attempts%ROWTYPE; credential appointment_system.company_credentials%ROWTYPE;
 generation uuid; instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT restore_generation INTO generation FROM appointment_system.control_product_state WHERE singleton;
 SELECT * INTO attempt FROM appointment_system.company_login_attempts WHERE id=p_attempt;
 IF NOT FOUND OR attempt.purpose<>'login' OR attempt.bound_token IS NOT NULL THEN RETURN false; END IF;
 SELECT * INTO credential FROM appointment_system.company_credentials
  WHERE subject=attempt.subject AND enabled AND credential_revision=p_revision FOR SHARE;
 SELECT * INTO attempt FROM appointment_system.company_login_attempts WHERE id=p_attempt FOR UPDATE;
 IF attempt.consumed_at IS NOT NULL OR attempt.expires_at<=instant OR attempt.purpose<>'login' THEN RETURN false; END IF;
 UPDATE appointment_system.company_login_attempts SET consumed_at=instant WHERE id=p_attempt;
 IF p_verified IS DISTINCT FROM true OR coalesce(p_token,'') !~ '^[a-f0-9]{64}$'
  OR coalesce(p_csrf,'') !~ '^[a-f0-9]{64}$' OR p_revision IS DISTINCT FROM attempt.credential_revision
  OR credential.subject IS NULL OR generation IS NULL
  OR NOT EXISTS(SELECT 1 FROM appointment_system.control_company_identities WHERE subject=credential.subject AND enabled)
 THEN RETURN false; END IF;
 INSERT INTO appointment_system.control_company_sessions
  (token_hash,subject,csrf_hash,restore_generation,created_at,expires_at,fresh_until,credential_revision,last_used_at)
 VALUES(p_token,credential.subject,p_csrf,generation,instant,instant+interval '8 hours',
  instant+interval '10 minutes',credential.credential_revision,instant);
 UPDATE appointment_system.company_login_attempts SET success=true WHERE id=p_attempt;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.entry_company_session_touch(p_token text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 UPDATE appointment_system.control_company_sessions s SET last_used_at=clock_timestamp()
 FROM appointment_system.company_credentials c,appointment_system.control_product_state p
 WHERE s.token_hash=p_token AND s.subject=c.subject AND c.enabled AND p.singleton
  AND c.credential_revision=s.credential_revision AND s.restore_generation=p.restore_generation
  AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
  AND s.last_used_at>clock_timestamp()-interval '30 minutes';
 RETURN FOUND;
END $$;

CREATE FUNCTION appointment_system.entry_consume_google_attempt(p_state text, p_browser text, p_purpose text, p_client text, p_origin text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_attempts%ROWTYPE; actor jsonb;
BEGIN
    SELECT * INTO a FROM appointment_system.google_attempts WHERE state_digest=p_state FOR UPDATE;
    IF NOT FOUND OR a.browser_digest IS DISTINCT FROM p_browser OR a.purpose IS DISTINCT FROM p_purpose
      OR a.client_id IS DISTINCT FROM p_client OR a.origin IS DISTINCT FROM p_origin
      OR a.consumed_at IS NOT NULL OR a.expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
    IF a.purpose='connect' THEN
        actor:=appointment_system.studio_session(a.session_digest,p_client,p_origin);
        IF actor IS NULL OR actor->>'role' IS DISTINCT FROM a.role THEN RETURN NULL; END IF;
    END IF;
    UPDATE appointment_system.google_attempts SET consumed_at=clock_timestamp() WHERE state_digest=p_state;
    RETURN jsonb_build_object('role',a.role,'encrypted_attempt',a.encrypted_attempt,
        'subject',actor->>'subject','server_now',clock_timestamp());
END
$$;

CREATE FUNCTION appointment_system.entry_consume_request_limit(p_scope text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE instant timestamptz := clock_timestamp();
        start_at timestamptz; width integer; maximum integer; used integer;
BEGIN
    CASE p_scope
      WHEN 'contact_start' THEN width:=3600; maximum:=10;
      WHEN 'contact_email' THEN width:=3600; maximum:=3;
      WHEN 'contact_read' THEN width:=60; maximum:=30;
      WHEN 'contact_verify' THEN width:=3600; maximum:=30;
      WHEN 'studio' THEN width:=3600; maximum:=20;
      WHEN 'studio_status' THEN width:=60; maximum:=60;
      WHEN 'context' THEN width:=3600; maximum:=20;
      WHEN 'availability' THEN width:=60; maximum:=60;
      WHEN 'receipt' THEN width:=60; maximum:=30;
      WHEN 'checkout' THEN width:=3600; maximum:=30;
      ELSE RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='unsupported request scope';
    END CASE;
    start_at:=to_timestamp(floor(extract(epoch FROM instant)/width)*width);
    INSERT INTO appointment_system.request_limits(scope,key_digest,window_start,expires_at,attempts)
      VALUES(p_scope,p_key,start_at,start_at+make_interval(secs=>width)+interval '24 hours',1)
      ON CONFLICT(scope,key_digest,window_start) DO UPDATE
      SET attempts=least(appointment_system.request_limits.attempts+1,maximum+1)
      RETURNING attempts INTO used;
    RETURN jsonb_build_object('allowed',used<=maximum,
      'retry_after',greatest(1,ceil(extract(epoch FROM start_at+make_interval(secs=>width)-instant))::integer));
END
$$;

CREATE FUNCTION appointment_system.entry_control_admission(p_epoch uuid DEFAULT NULL::uuid) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE s appointment_system.control_product_state%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO s FROM appointment_system.control_product_state WHERE singleton;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='booking control unavailable'; END IF;
 IF NOT s.enabled THEN RAISE EXCEPTION USING ERRCODE='P0444',MESSAGE='booking disabled'; END IF;
 IF p_epoch IS NOT NULL AND p_epoch IS DISTINCT FROM s.activation_epoch THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='booking activation changed';
 END IF;
 RETURN s.activation_epoch;
END $$;

CREATE FUNCTION appointment_system.entry_control_claim_publication() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE job appointment_system.control_publications%ROWTYPE; current jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 current:=appointment_system.control_snapshot();
 UPDATE appointment_system.control_publications SET state='superseded',lease_token=NULL,lease_until=NULL
 WHERE state IN ('pending','attention') AND snapshot IS DISTINCT FROM current;
 SELECT * INTO job FROM appointment_system.control_publications p WHERE p.state='pending'
  AND p.snapshot=current AND p.next_attempt_at<=clock_timestamp()
  AND (p.lease_until IS NULL OR p.lease_until<=clock_timestamp())
 ORDER BY p.operation_id LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE appointment_system.control_publications SET lease_token=gen_random_uuid(),
  lease_until=clock_timestamp()+interval '90 seconds',attempts=attempts+1
 WHERE operation_id=job.operation_id RETURNING * INTO job;
 UPDATE appointment_system.control_command_progress SET state='publishing',updated_at=clock_timestamp()
 WHERE operation_id=job.operation_id;
 RETURN jsonb_build_object('operation_id',job.operation_id,'lease_token',job.lease_token,'snapshot',job.snapshot,'attempts',job.attempts);
END $$;

CREATE FUNCTION appointment_system.entry_control_command(p_token text, p_csrf text, p_operation uuid, p_generation uuid, p_revision bigint, p_enabled boolean, p_reason text, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text; prior appointment_system.control_operations%ROWTYPE;
 current appointment_system.control_product_state%ROWTYPE; accepted jsonb;
BEGIN
 -- Acquire the exclusive barrier before a principal row, matching business work.
 PERFORM pg_advisory_xact_lock(83124,4);
 actor:=appointment_system.control_authorize(p_token,'service_controller',p_csrf,false);
 IF p_operation IS NULL OR p_generation IS NULL OR p_revision IS NULL OR p_revision<1
  OR p_enabled IS NULL OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 5 AND 300
  OR p_reason ~ '[[:cntrl:]]' OR coalesce(p_hash,'') !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid control command'; END IF;
 SELECT * INTO prior FROM appointment_system.control_operations WHERE id=p_operation;
 IF FOUND THEN
  IF prior.actor_subject IS DISTINCT FROM actor OR prior.body_hash IS DISTINCT FROM p_hash
   OR prior.expected_generation IS DISTINCT FROM p_generation OR prior.expected_revision IS DISTINCT FROM p_revision
   OR prior.target_enabled IS DISTINCT FROM p_enabled OR prior.reason IS DISTINCT FROM btrim(p_reason)
  THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='control operation conflict'; END IF;
  RETURN appointment_system.control_command_result(p_token,p_operation);
 END IF;
 PERFORM appointment_system.control_authorize(p_token,'service_controller',p_csrf,true);
 SELECT * INTO current FROM appointment_system.control_product_state WHERE singleton FOR UPDATE;
 IF NOT FOUND OR current.restore_generation IS DISTINCT FROM p_generation OR current.revision IS DISTINCT FROM p_revision
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='control state changed'; END IF;
 IF current.revision=9223372036854775807 THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='control revision exhausted'; END IF;
 UPDATE appointment_system.control_command_progress SET state='superseded',updated_at=clock_timestamp()
 WHERE operation_id=current.winning_operation AND state<>'superseded';
 UPDATE appointment_system.control_product_state SET requested_enabled=p_enabled,
  enabled=false,revision=revision+1,activation_epoch=gen_random_uuid(),winning_operation=p_operation,
  updated_at=clock_timestamp(),provenance='company_command' WHERE singleton;
 accepted:=appointment_system.control_snapshot();
 INSERT INTO appointment_system.control_operations(id,actor_subject,body_hash,expected_generation,expected_revision,
  target_enabled,reason,result_snapshot) VALUES(p_operation,actor,p_hash,p_generation,p_revision,p_enabled,btrim(p_reason),accepted);
 INSERT INTO appointment_system.control_command_progress(operation_id,state) VALUES(p_operation,'accepted');
 INSERT INTO appointment_system.control_publications(operation_id,snapshot) VALUES(p_operation,accepted);
 RETURN appointment_system.control_command_result(p_token,p_operation);
END $_$;

CREATE FUNCTION appointment_system.entry_control_command_result(p_token text, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text; operation appointment_system.control_operations%ROWTYPE; progress appointment_system.control_command_progress%ROWTYPE;
BEGIN
 actor:=appointment_system.control_authorize(p_token,'service_controller');
 SELECT * INTO operation FROM appointment_system.control_operations WHERE id=p_operation AND actor_subject=actor;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO progress FROM appointment_system.control_command_progress WHERE operation_id=p_operation;
 RETURN jsonb_build_object('receipt',jsonb_build_object('operation_id',operation.id,
  'requested_enabled',operation.target_enabled,'accepted_snapshot',operation.result_snapshot,
  'accepted_at',operation.created_at),'progress',progress.state,'error_code',progress.error_code,
  'current',appointment_system.control_control_status(p_token));
END $$;

CREATE FUNCTION appointment_system.entry_control_control_status(p_token text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE current appointment_system.control_product_state%ROWTYPE; progress text;
BEGIN
 PERFORM appointment_system.control_authorize(p_token,'service_controller');
 SELECT * INTO current FROM appointment_system.control_product_state WHERE singleton;
 SELECT state INTO progress FROM appointment_system.control_command_progress WHERE operation_id=current.winning_operation;
 RETURN jsonb_build_object('snapshot',appointment_system.control_snapshot(),
  'requested_mode',CASE WHEN current.requested_enabled THEN 'on' ELSE 'off' END,
  'admission_mode',CASE WHEN current.enabled THEN 'on' ELSE 'off' END,
  'operation_id',current.winning_operation,'progress',coalesce(progress,'initializing'));
END $$;

CREATE FUNCTION appointment_system.entry_control_finish_publication(p_operation uuid, p_lease uuid, p_ack jsonb, p_error text DEFAULT NULL::text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE job appointment_system.control_publications%ROWTYPE; current appointment_system.control_product_state%ROWTYPE;
BEGIN
 IF p_error IS NOT NULL AND p_error !~ '^[a-z0-9_]{1,80}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid publication result'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO current FROM appointment_system.control_product_state WHERE singleton FOR UPDATE;
 SELECT * INTO job FROM appointment_system.control_publications WHERE operation_id=p_operation
  AND lease_token=p_lease AND lease_until>clock_timestamp() AND state='pending' FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF current.winning_operation IS DISTINCT FROM p_operation OR job.snapshot IS DISTINCT FROM appointment_system.control_snapshot() THEN
  UPDATE appointment_system.control_publications SET state='superseded',lease_token=NULL,lease_until=NULL WHERE operation_id=p_operation;
  UPDATE appointment_system.control_command_progress SET state='superseded',updated_at=clock_timestamp() WHERE operation_id=p_operation;
  RETURN false;
 END IF;
 IF p_error IS NULL AND p_ack=job.snapshot THEN
  UPDATE appointment_system.control_publications SET state='published',published_at=clock_timestamp(),
   lease_token=NULL,lease_until=NULL,last_error=NULL WHERE operation_id=p_operation;
  UPDATE appointment_system.control_product_state SET enabled=requested_enabled WHERE singleton;
  UPDATE appointment_system.control_command_progress SET state='published',updated_at=clock_timestamp(),error_code=NULL WHERE operation_id=p_operation;
 ELSE
  UPDATE appointment_system.control_publications SET lease_token=NULL,lease_until=NULL,
   next_attempt_at=clock_timestamp()+make_interval(secs=>least(900,15*(2^least(attempts,5))::integer)),
   last_error=coalesce(p_error,'publication_ack_invalid') WHERE operation_id=p_operation;
  UPDATE appointment_system.control_command_progress SET state='accepted',updated_at=clock_timestamp(),
   error_code=coalesce(p_error,'publication_ack_invalid') WHERE operation_id=p_operation;
 END IF;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.entry_control_obligation_action(p_session text, p_csrf text, p_client text, p_action text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text; target uuid; owned boolean;
 private_origin text:=(appointment_system.installation_value('origin')||'/company/booking-support');
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_action IS NULL OR p_action NOT IN ('lookup','detail','cancel','reschedule','support','verified_refund','resource_reviewed')
  OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 principal:=appointment_system.control_authorize(p_session,'obligation_handler',p_csrf,p_action NOT IN ('lookup','detail'));
 IF appointment_system.control_obligation_actor(p_session,p_client,private_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_action IN ('lookup','support') THEN
  SELECT id INTO target FROM appointment_system.bookings WHERE request_id=(p_data->>'reference')::uuid;
 ELSIF p_action IN('verified_refund','resource_reviewed') THEN
  SELECT booking_id INTO target FROM appointment_system.payment_cases WHERE id=(p_data->>'case_id')::uuid;
 ELSE SELECT booking_id INTO target FROM appointment_system.slot_claims WHERE id=(p_data->>'claim_id')::uuid; END IF;
 owned:=EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=target);
 IF target IS NULL OR NOT owned THEN RETURN jsonb_build_object('code','booking_unavailable'); END IF;
 IF p_action='lookup' THEN
  RETURN appointment_system.studio_booking_lookup(p_session,p_client,private_origin,(p_data->>'reference')::uuid);
 ELSIF p_action='detail' THEN
  RETURN appointment_system.studio_appointment_detail(p_session,p_client,private_origin,(p_data->>'claim_id')::uuid);
 ELSIF p_action='cancel' THEN
  RETURN appointment_system.studio_appointment_cancel(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSIF p_action='reschedule' THEN
  RETURN appointment_system.studio_appointment_reschedule(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason',(p_data->>'starts_at')::timestamptz);
 ELSIF p_action='support' THEN
  IF p_data->'verification_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
  RETURN appointment_system.studio_support_change(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'reference')::uuid,(p_data->>'expected_revision')::integer,p_data->>'action',p_data->>'reason',
   p_data->>'verified_payment_id',p_data->>'email',p_data->>'phone',p_data->>'code_digest');
 ELSIF p_action='resource_reviewed' THEN
  RETURN appointment_system.studio_inbox_resource_reviewed(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSE
  RETURN appointment_system.studio_inbox_refund_verified(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 END IF;
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

CREATE FUNCTION appointment_system.entry_control_obligation_summary(p_session text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.control_authorize(p_session,'obligation_handler');
 RETURN jsonb_build_object('code','ok','appointments',coalesce((
  SELECT jsonb_agg(row) FROM (SELECT b.request_id AS reference,b.full_name AS name,b.service_snapshot->>'name' AS service,
   b.starts_at,b.ends_at,b.state,b.revision,
   (SELECT id FROM appointment_system.slot_claims WHERE booking_id=b.id) AS claim_id
   FROM appointment_system.bookings b WHERE EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=b.id)
   AND b.state='confirmed' AND b.ends_at>=clock_timestamp() ORDER BY b.starts_at,b.id LIMIT 50)row),'[]'::jsonb),
  'reviews',coalesce((SELECT jsonb_agg(row) FROM(SELECT c.id AS case_id,b.request_id AS reference,c.reason,f.kind AS resource_kind,f.status AS resource_status,f.verified AS resource_verified,f.attention_reason AS resource_attention,
    coalesce((SELECT max(revision) FROM appointment_system.staff_reviews WHERE item_key='payment:'||c.id),0) AS revision
    FROM appointment_system.payment_cases c JOIN appointment_system.bookings b ON b.id=c.booking_id
    LEFT JOIN appointment_system.financial_resource_states f ON f.booking_id=b.id AND f.resource_id=split_part(c.event_key,':',2)
    WHERE c.resolved_at IS NULL ORDER BY c.next_check_at,c.id LIMIT 50)row),'[]'::jsonb));
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

CREATE FUNCTION appointment_system.entry_control_publication_schedule() RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_object('due',
  (SELECT greatest(0,least(900,ceil(extract(epoch FROM min(greatest(p.next_attempt_at,
    coalesce(p.lease_until,p.next_attempt_at)))-statement_timestamp()))))::integer
   FROM appointment_system.control_publications p JOIN appointment_system.control_command_progress c USING(operation_id)
   WHERE p.state='pending' OR p.state='published' AND c.state='published'),
  'attention',EXISTS(SELECT 1 FROM appointment_system.control_publications p
   JOIN appointment_system.control_command_progress c USING(operation_id)
   WHERE p.state='attention' OR p.state IN ('pending','published') AND c.state<>'effective'
    AND p.last_error IS NOT NULL AND p.next_attempt_at<statement_timestamp()-interval '5 minutes'))
$$;

CREATE FUNCTION appointment_system.entry_control_record_probe(p_operation uuid, p_snapshot jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE product appointment_system.control_product_state%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO product FROM appointment_system.control_product_state WHERE singleton FOR SHARE;
 IF product.winning_operation IS DISTINCT FROM p_operation OR product.enabled IS DISTINCT FROM product.requested_enabled
  OR p_snapshot IS DISTINCT FROM appointment_system.control_snapshot()
  OR NOT EXISTS(SELECT 1 FROM appointment_system.control_publications p WHERE p.operation_id=p_operation AND p.state='published')
 THEN RETURN false; END IF;
 UPDATE appointment_system.control_command_progress SET state='effective',updated_at=clock_timestamp(),probed_at=clock_timestamp()
 WHERE operation_id=p_operation AND state='published';
 RETURN FOUND;
END $$;

CREATE FUNCTION appointment_system.entry_control_session_end(p_token text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 UPDATE appointment_system.control_company_sessions SET revoked_at=clock_timestamp() WHERE token_hash=p_token AND revoked_at IS NULL;
 RETURN FOUND;
END $$;

CREATE FUNCTION appointment_system.entry_enquiry_view(p_id uuid, p_receipt text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT coalesce((SELECT jsonb_build_object('code','ok','request_id',e.request_id,
  'state',CASE WHEN e.verified_at IS NOT NULL THEN 'received' WHEN e.attempts>=5 THEN 'locked'
    WHEN e.code_expires_at<=clock_timestamp() OR e.code_digest IS NULL THEN 'expired' ELSE 'awaiting_verification' END,
  'generation',e.generation,'server_now',clock_timestamp(),'code_expires_at',e.code_expires_at,
  'resend_after',e.resend_after,'sends_remaining',3-e.generation,
  'verification_delivery',coalesce((SELECT CASE
    WHEN EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type IN ('email.bounced','email.complained','email.suppressed')) THEN 'failed'
    WHEN EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.delivered') THEN 'delivered'
    WHEN EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.failed') THEN 'failed'
    WHEN j.state IN ('needs_review','suppressed','suppressed') OR (j.state='pending' AND j.last_error_code IN ('email_budget_unconfigured','email_budget_exhausted')) THEN 'unavailable'
    WHEN EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.delivery_delayed') THEN 'delayed'
    WHEN j.provider_id IS NOT NULL THEN 'accepted' ELSE 'queued' END
   FROM appointment_system.enquiry_delivery_jobs j WHERE j.request_id=e.request_id AND j.kind='verification' AND j.generation=e.generation),'unavailable'))
  FROM appointment_system.enquiries e WHERE e.request_id=p_id AND e.receipt_digest=p_receipt
   AND e.receipt_expires_at>clock_timestamp()),jsonb_build_object('code','access_unavailable'));
$$;

CREATE FUNCTION appointment_system.entry_expire_enquiry_codes() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE e record; used integer:=0;
BEGIN
 FOR e IN SELECT request_id FROM appointment_system.enquiries WHERE code_ciphertext IS NOT NULL
   AND code_expires_at<=clock_timestamp() ORDER BY code_expires_at LIMIT 100 FOR UPDATE SKIP LOCKED LOOP
  UPDATE appointment_system.enquiries SET code_digest=NULL,code_ciphertext=NULL WHERE request_id=e.request_id;
  UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
   WHERE request_id=e.request_id AND kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
  used:=used+1;
 END LOOP;
 RETURN used;
END $$;

CREATE FUNCTION appointment_system.entry_expire_holds() RETURNS integer
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT appointment_system.expire_relevant(NULL,NULL)
$$;

CREATE FUNCTION appointment_system.entry_finish_enquiry_delivery(p_job uuid, p_lease uuid, p_provider text, p_error text, p_attention boolean, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE e appointment_system.enquiries%ROWTYPE;j appointment_system.enquiry_delivery_jobs%ROWTYPE;owner_id uuid;is_mail boolean;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 86400 OR p_attention IS NULL
   OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
 SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
 SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR p_lease IS NULL OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing'
   OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN false; END IF;
 is_mail:=j.kind IN ('verification','acknowledgement','practice_notice');
 IF NOT appointment_system.contact_job_eligible(e,j) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL THEN
  IF is_mail THEN
   IF j.first_attempt_at IS NULL OR j.message_digest IS NULL OR p_provider !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN RETURN false; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||p_provider,0));
   IF EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=p_provider AND recipient_role IN ('customer','client'))
    OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=p_provider AND id<>j.id AND kind IN ('verification','acknowledgement','practice_notice')) THEN
    UPDATE appointment_system.enquiry_delivery_jobs SET state='needs_review',last_error_code='email_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    RETURN false;
   END IF;
  ELSIF p_provider !~ '^[A-Za-z0-9_-]{1,200}$' THEN RETURN false; END IF;
  IF j.provider_id IS NOT NULL AND j.provider_id<>p_provider THEN RETURN false; END IF;
 END IF;
 UPDATE appointment_system.enquiry_delivery_jobs SET provider_id=coalesce(p_provider,provider_id),
  state=CASE WHEN p_provider IS NOT NULL OR provider_id IS NOT NULL THEN CASE WHEN is_mail THEN 'completed' ELSE 'completed' END
   WHEN p_attention THEN 'needs_review' ELSE 'delivery_unknown' END,last_error_code=p_error,
  next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.entry_finish_financial_resource(p_case uuid, p_lease uuid, p_delay integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE changed integer;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 900 AND 86400 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$')
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial completion';END IF;
 UPDATE appointment_system.payment_cases SET financial_lease_token=NULL,financial_lease_until=NULL,
  next_check_at=clock_timestamp()+make_interval(secs=>p_delay),financial_error=p_error
 WHERE id=p_case AND financial_lease_token=p_lease AND financial_lease_until>clock_timestamp();
 GET DIAGNOSTICS changed=ROW_COUNT;RETURN changed=1;
END $_$;

CREATE FUNCTION appointment_system.entry_finish_google_delivery(p_job uuid, p_lease uuid, p_state text, p_provider text, p_meet text, p_error text, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE; booking uuid; stale boolean; expected_event text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
    IF p_state IS NULL OR p_state NOT IN ('done','waiting','failed','attention','obsolete') OR p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 3600
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
    SELECT booking_id INTO booking FROM appointment_system.delivery_jobs WHERE id=p_job;
    SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR SHARE;
    IF NOT FOUND THEN RETURN false; END IF;
    SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR UPDATE;
    IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR p_lease IS NULL OR j.state<>'processing'
       OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN false; END IF;
    IF j.kind NOT IN ('booking_calendar','sheet_booking') AND NOT(j.kind='booking_cancelled' AND j.recipient_role='calendar') THEN RETURN false; END IF;
    stale:=b.state<>'confirmed' OR b.revision<>j.booking_revision;
    IF p_state='obsolete' THEN
      IF j.kind<>'booking_calendar' OR NOT stale THEN RETURN false; END IF;
      UPDATE appointment_system.meeting_events SET state='cancelled',meet_url=NULL WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    ELSIF j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN
      expected_event:=appointment_system.calendar_event_identity(b.id,j.booking_revision,b.calendar_protocol);
      IF p_provider IS DISTINCT FROM expected_event THEN RETURN false; END IF;
      INSERT INTO appointment_system.meeting_events(booking_id,booking_revision,event_id,state,meet_url)
        VALUES(b.id,j.booking_revision,p_provider,CASE WHEN p_state='done' THEN 'ready' ELSE 'waiting' END,p_meet)
        ON CONFLICT(booking_id,booking_revision) DO UPDATE SET state=excluded.state,meet_url=excluded.meet_url;
      IF stale THEN
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
          VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',j.booking_revision,j.payload)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO UPDATE
          SET state='pending',next_attempt_at=clock_timestamp(),lease_token=NULL,lease_expires_at=NULL;
      ELSIF p_state='done' THEN
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key,payload) SELECT gen_random_uuid(),b.id,'sheet_booking',destination,j.booking_revision,'meeting-ready',appointment_system.booking_snapshot(b.id) FROM unnest(ARRAY['client_sheet','agency_sheet'])destination ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
          VALUES(gen_random_uuid(),b.id,'booking_details','customer',j.booking_revision)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
      END IF;
    ELSIF j.kind='booking_cancelled' AND p_state='done' THEN
      UPDATE appointment_system.meeting_events SET state='cancelled',meet_url=NULL
        WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    END IF;
    UPDATE appointment_system.delivery_jobs SET state=CASE WHEN p_state='obsolete' THEN 'suppressed' WHEN stale AND j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN 'suppressed'
      WHEN p_state='done' THEN 'completed' WHEN p_state='attention' THEN 'needs_review' WHEN p_state='waiting' THEN 'retry_wait' ELSE 'retry_wait' END,
      provider_id=coalesce(p_provider,provider_id),last_error_code=p_error,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
    RETURN true;
END
$_$;

CREATE FUNCTION appointment_system.entry_finish_google_signin(p_state text, p_subject text, p_session text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_attempts%ROWTYPE; pinned text;
BEGIN
    PERFORM pg_advisory_xact_lock(4004101);
    SELECT * INTO a FROM appointment_system.google_attempts WHERE state_digest=p_state FOR UPDATE;
    IF NOT FOUND OR a.purpose<>'signin' OR a.consumed_at IS NULL OR a.finished_at IS NOT NULL
      OR a.expires_at<=clock_timestamp() OR p_subject IS NULL THEN RETURN false; END IF;
    SELECT subject INTO pinned FROM appointment_system.studio_identities WHERE role=a.role;
    IF pinned IS NOT NULL AND pinned<>p_subject THEN RETURN false; END IF;
    INSERT INTO appointment_system.studio_identities(role,subject) VALUES(a.role,p_subject) ON CONFLICT(role) DO NOTHING;
    INSERT INTO appointment_system.studio_sessions(digest,role,subject,client_id,origin,expires_at)
      VALUES(p_session,a.role,p_subject,a.client_id,a.origin,clock_timestamp()+interval '60 minutes');
    UPDATE appointment_system.google_attempts SET finished_at=clock_timestamp() WHERE state_digest=p_state;
    INSERT INTO appointment_system.studio_audit(role,action) VALUES(a.role,'signin');
    RETURN true;
END
$$;

CREATE FUNCTION appointment_system.entry_finish_google_workbook(p_role text, p_lease uuid, p_file text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE w appointment_system.google_workbooks%ROWTYPE;
BEGIN
 IF p_file IS NULL OR p_file !~ '^[A-Za-z0-9_-]{1,200}$' THEN RETURN false; END IF;
 UPDATE appointment_system.google_workbooks x SET spreadsheet_id=p_file,state='ready',lease=NULL,lease_until=NULL
 WHERE role=p_role AND lease=p_lease AND lease_until>clock_timestamp() AND state='creating'
 AND EXISTS(SELECT 1 FROM appointment_system.google_sheet_connections g WHERE g.role=x.role AND g.subject=x.subject
  AND g.client_id=x.client_id AND g.revision=x.connection_revision) RETURNING * INTO w;
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE appointment_system.google_workbook_volumes SET spreadsheet_id=p_file,state='ready'
  WHERE role=p_role AND volume_number=w.volume_number AND intent=w.intent AND state='creating';
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='missing workbook identity'; END IF;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.entry_finish_mail_attempt(p_kind text, p_job uuid, p_lease uuid, p_provider uuid, p_hash text, p_error text, p_attention boolean, p_delay integer, p_rejected boolean) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE data jsonb;saved boolean;appended text;previous_uncertainty boolean;quota boolean;owner_id uuid;
BEGIN
 IF p_kind NOT IN('booking','contact') OR p_delay NOT BETWEEN 15 AND 86400 OR p_rejected IS NULL THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_kind='booking' THEN
  SELECT booking_id INTO owner_id FROM appointment_system.delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM appointment_system.bookings WHERE id=owner_id FOR SHARE;
 ELSE
  SELECT request_id INTO owner_id FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM appointment_system.enquiries WHERE request_id=owner_id FOR SHARE;
 END IF;
 IF p_provider IS NOT NULL THEN
  appended:=appointment_system.append_mail_acceptance(p_kind,p_job,p_hash,p_provider);
  IF appended<>'accepted' THEN p_provider:=NULL;p_attention:=true;p_error:='email_provider_conflict';END IF;
 END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(j) INTO data FROM appointment_system.delivery_jobs j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT to_jsonb(j) INTO data FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_job FOR UPDATE;
 END IF;
 IF data IS NULL OR (data->>'lease_token')::uuid IS DISTINCT FROM p_lease OR(data->>'lease_expires_at')::timestamptz<=clock_timestamp() OR data->>'state'<>'processing' OR NOT appointment_system.transport_claim_current(data) THEN RETURN false; END IF;
 previous_uncertainty:=(data->>'prior_send_uncertain')::boolean;
 quota:=p_provider IS NULL AND p_rejected AND NOT previous_uncertainty AND p_error IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited');
 IF p_kind='booking' THEN
  saved:=appointment_system.finish_email_delivery(p_job,p_lease,p_provider,p_error,p_attention,p_delay);
  IF saved THEN
   UPDATE appointment_system.delivery_jobs SET send_uncertain=previous_uncertainty OR(NOT p_rejected AND p_provider IS NULL),
    first_attempt_at=CASE WHEN quota THEN NULL ELSE first_attempt_at END,
    state=CASE WHEN quota THEN 'pending' ELSE state END,attempts=greatest(0,attempts-CASE WHEN quota THEN 1 ELSE 0 END) WHERE id=p_job;
  END IF;
 ELSE
  saved:=appointment_system.finish_enquiry_delivery(p_job,p_lease,p_provider::text,p_error,p_attention,p_delay);
  IF saved THEN
   UPDATE appointment_system.enquiry_delivery_jobs SET send_uncertain=previous_uncertainty OR(NOT p_rejected AND p_provider IS NULL),
    first_attempt_at=CASE WHEN quota THEN NULL ELSE first_attempt_at END,
    state=CASE WHEN quota THEN 'pending' ELSE state END,attempts=greatest(0,attempts-CASE WHEN quota THEN 1 ELSE 0 END) WHERE id=p_job;
  END IF;
 END IF;
 RETURN saved;
END $$;

CREATE FUNCTION appointment_system.entry_finish_payment_event(p_account text, p_mode text, p_event text, p_lease uuid, p_done boolean, p_delay integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 86400 OR p_delay IS NULL OR p_done IS NULL
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event outcome';
    END IF;
    UPDATE appointment_system.provider_inbox SET lease_token=NULL,lease_expires_at=NULL,
      processed_at=CASE WHEN p_done THEN clock_timestamp() ELSE NULL END,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),last_error_code=p_error
      WHERE provider='razorpay' AND account_id=p_account AND environment=p_mode AND event_id=p_event
        AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$_$;

CREATE FUNCTION appointment_system.entry_finish_payment_recovery(p_booking uuid, p_lease uuid, p_delay integer, p_cursor integer, p_skip integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 86400 OR p_delay IS NULL OR p_cursor IS NULL OR p_cursor<0 OR p_skip IS NULL OR p_skip<0 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid recovery delay';
    END IF;
    UPDATE appointment_system.payment_orders SET lease_token=NULL,lease_expires_at=NULL,
      next_check_at=clock_timestamp()+make_interval(secs=>p_delay),recovery_cursor=p_cursor,order_search_skip=p_skip,recovery_followup=(p_cursor>0 OR p_error IS NOT NULL OR EXISTS(SELECT 1 FROM appointment_system.payment_cases c WHERE c.booking_id=p_booking AND c.resolved_at IS NULL)),last_recovery_error=p_error
      WHERE booking_id=p_booking AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$_$;

CREATE FUNCTION appointment_system.entry_mapped_google_row(p_role text, p_job uuid, p_kind text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;
BEGIN
 IF p_role NOT IN ('client','agency') OR p_role IS NULL THEN RETURN NULL; END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(v)||jsonb_build_object('row',r.row_number,'values',r.values_json,'action','mapped') INTO result
   FROM appointment_system.sheet_rows r JOIN appointment_system.google_workbook_volumes v USING(role,volume_number)
   WHERE r.role=p_role AND r.job_id=p_job AND v.state IN ('ready','retired');
 ELSIF p_kind='enquiry' THEN
  SELECT to_jsonb(v)||jsonb_build_object('row',r.row_number,'values',r.values_json,'action','mapped') INTO result
   FROM appointment_system.enquiry_sheet_rows r JOIN appointment_system.google_workbook_volumes v USING(role,volume_number)
   WHERE r.role=p_role AND r.job_id=p_job AND v.state IN ('ready','retired');
 END IF;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.entry_observe_financial_resource(p_booking uuid, p_merchant text, p_mode text, p_version text, p_fact jsonb, p_provenance text, p_hash text, p_parent jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE owned record;prior appointment_system.financial_resource_states%ROWTYPE;previous_fact jsonb;
 identity text;payment text;family text;state text;chosen text;outcome text;reason text;fact_id uuid;total bigint;
 instant timestamptz:=clock_timestamp();p_refunded bigint;parent_hash text;verified boolean;projection jsonb;projection_id uuid;projection_time timestamptz;changed boolean;inserted integer;
BEGIN
 IF p_booking IS NULL OR p_merchant IS NULL OR p_merchant !~ '^[A-Za-z0-9]{1,64}$' OR p_mode IS NULL OR p_mode NOT IN('test','live')
 OR p_version IS NULL OR length(p_version) NOT BETWEEN 1 AND 128 OR p_provenance IS NULL OR p_provenance NOT IN('signed_webhook','provider_fetch')
 OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_fact) IS DISTINCT FROM 'object'
 OR octet_length(p_fact::text)>4096 OR (p_fact->>'version') IS DISTINCT FROM '1'
 OR (SELECT count(*) FROM jsonb_object_keys(p_fact))<>12 OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_fact)k WHERE k NOT IN
 ('version','kind','id','payment_id','status','amount','currency','created_at','updated_at','respond_by','speed_requested','speed_processed'))
 OR coalesce(p_fact->>'amount','') !~ '^[1-9][0-9]{0,9}$' OR coalesce(p_fact->>'created_at','') !~ '^[1-9][0-9]{0,9}$'
 OR jsonb_typeof(p_fact->'amount') IS DISTINCT FROM 'number' OR jsonb_typeof(p_fact->'created_at') IS DISTINCT FROM 'number'
 OR (p_fact->>'amount')::bigint>2147483647 OR (p_fact->>'created_at')::bigint>4102444800
 OR p_fact->>'currency' IS DISTINCT FROM 'INR' THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource';END IF;
 identity:=p_fact->>'id';payment:=p_fact->>'payment_id';family:=p_fact->>'kind';state:=p_fact->>'status';
 IF payment IS NULL OR payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR family IS NULL OR identity IS NULL OR state IS NULL
 OR (family='refund' AND (identity !~ '^rfnd_[A-Za-z0-9]{1,64}$' OR state NOT IN('pending','processed','failed')))
 OR (family='dispute' AND (identity !~ '^disp_[A-Za-z0-9]{1,64}$' OR state NOT IN('open','under_review','won','lost','closed')))
 OR family NOT IN('refund','dispute') THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource identity';END IF;
 FOR projection IN SELECT jsonb_build_object('field',k,'value',p_fact->k) FROM unnest(ARRAY['updated_at','respond_by'])k LOOP
  IF jsonb_typeof(projection->'value')<>'null' AND (jsonb_typeof(projection->'value')<>'number'
   OR projection->>'value' !~ '^[1-9][0-9]{0,9}$' OR (projection->>'value')::bigint NOT BETWEEN (p_fact->>'created_at')::bigint AND 4102444800) THEN
   RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource time';END IF;
 END LOOP;
 IF (family='refund' AND p_fact->>'respond_by' IS NOT NULL)
 OR (family='dispute' AND (p_fact->>'speed_requested' IS NOT NULL OR p_fact->>'speed_processed' IS NOT NULL))
 OR (p_fact->>'speed_requested' IS NOT NULL AND p_fact->>'speed_requested' NOT IN('normal','optimum','instant'))
 OR (p_fact->>'speed_processed' IS NOT NULL AND p_fact->>'speed_processed' NOT IN('normal','optimum','instant')) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource metadata';END IF;
 -- Serialize resource projections per original booking. No remote request holds this lock.
 SELECT o.merchant_id,o.mode,o.credential_version,o.provider_order_id AS order_id,b.amount_paise,b.currency INTO owned FROM appointment_system.payment_orders o JOIN appointment_system.bookings b ON b.id=o.booking_id
 WHERE b.id=p_booking FOR UPDATE OF o;
 IF NOT FOUND OR owned.merchant_id IS DISTINCT FROM p_merchant OR owned.mode IS DISTINCT FROM p_mode OR owned.credential_version IS DISTINCT FROM p_version
 OR owned.order_id IS NULL OR (p_fact->>'amount')::bigint>owned.amount_paise OR owned.currency<>'INR' THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial resource ownership mismatch';END IF;
 IF jsonb_typeof(p_parent) IS DISTINCT FROM 'object' OR octet_length(p_parent::text)>2048
 OR (SELECT count(*) FROM jsonb_object_keys(p_parent))<>8
 OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_parent)k WHERE k NOT IN('entity','id','order_id','status','amount','currency','amount_refunded','captured'))
 OR p_parent->>'entity' IS DISTINCT FROM 'payment' OR p_parent->>'id' IS DISTINCT FROM payment
 OR p_parent->>'order_id' IS DISTINCT FROM owned.order_id OR p_parent->>'currency' IS DISTINCT FROM owned.currency
 OR jsonb_typeof(p_parent->'amount') IS DISTINCT FROM 'number' OR coalesce(p_parent->>'amount','') !~ '^[1-9][0-9]{0,9}$'
 OR (p_parent->>'amount')::bigint IS DISTINCT FROM owned.amount_paise
 OR jsonb_typeof(p_parent->'amount_refunded') IS DISTINCT FROM 'number' OR coalesce(p_parent->>'amount_refunded','') !~ '^[0-9]{1,10}$'
 OR (p_parent->>'amount_refunded')::bigint NOT BETWEEN 0 AND owned.amount_paise
 OR jsonb_typeof(p_parent->'captured') IS DISTINCT FROM 'boolean'
 OR p_parent->>'status' IS NULL OR p_parent->>'status' NOT IN('created','authorized','captured','refunded','failed') THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial parent evidence mismatch';END IF;
 p_refunded:=(p_parent->>'amount_refunded')::bigint;
 parent_hash:=encode(sha256(convert_to(p_parent::text,'UTF8')),'hex');
 INSERT INTO appointment_system.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,
 amount_paise,currency,refunded_paise) VALUES(gen_random_uuid(),p_booking,p_merchant,p_mode,payment,owned.order_id,parent_hash,
 p_parent->>'status',owned.amount_paise,owned.currency,p_refunded)
 ON CONFLICT(merchant_id,mode,payment_id,evidence_hash) DO NOTHING;
 PERFORM pg_advisory_xact_lock(hashtextextended('project004-financial-resource:'||p_merchant||':'||p_mode||':'||identity,0));
 SELECT * INTO prior FROM appointment_system.financial_resource_states WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity FOR UPDATE;
 IF FOUND AND (prior.booking_id,prior.payment_id,prior.order_id,prior.kind,prior.amount_paise,prior.currency,prior.fact->>'created_at') IS DISTINCT FROM
 (p_booking,payment,owned.order_id,family,(p_fact->>'amount')::bigint,'INR',p_fact->>'created_at') THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial resource association changed';END IF;
 INSERT INTO appointment_system.financial_resource_facts(booking_id,merchant_id,mode,credential_version,resource_id,provenance,evidence_hash,fact)
 VALUES(p_booking,p_merchant,p_mode,p_version,identity,p_provenance,p_hash,p_fact) ON CONFLICT DO NOTHING RETURNING id INTO fact_id;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 IF fact_id IS NULL THEN
  SELECT id,fact INTO fact_id,previous_fact FROM appointment_system.financial_resource_facts WHERE merchant_id=p_merchant AND mode=p_mode
   AND resource_id=identity AND provenance=p_provenance AND evidence_hash=p_hash;
  IF previous_fact IS DISTINCT FROM p_fact THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='financial evidence identity conflict';END IF;
 END IF;
 chosen:=state;projection:=p_fact;verified:=p_provenance='provider_fetch';outcome:=CASE WHEN family='dispute' AND state IN('won','lost') THEN state END;
 IF prior.verified AND p_provenance='signed_webhook' THEN
  chosen:=prior.status;projection:=prior.fact;verified:=true;outcome:=prior.outcome;reason:=prior.attention_reason;
 ELSIF prior.verified AND p_provenance='provider_fetch' THEN
  outcome:=coalesce(outcome,prior.outcome);
  IF (prior.fact->>'updated_at' IS NOT NULL AND p_fact->>'updated_at' IS NOT NULL
      AND (p_fact->>'updated_at')::bigint<(prior.fact->>'updated_at')::bigint)
   OR (family='refund' AND prior.status='processed' AND state<>'processed')
   OR (family='refund' AND prior.status='failed' AND state='pending')
   OR (family='dispute' AND prior.status IN('won','lost','closed') AND state IN('open','under_review'))
   OR (family='dispute' AND prior.status='under_review' AND state='open')
   OR (family='dispute' AND prior.outcome IS NOT NULL AND state IN('won','lost') AND state<>prior.outcome) THEN
    chosen:=prior.status;projection:=prior.fact;outcome:=prior.outcome;reason:='financial_resource_conflict';
  END IF;
 END IF;
 IF NOT verified THEN reason:='signed_resource_unfetched';END IF;
 projection_id:=fact_id;projection_time:=instant;
 IF prior.resource_id IS NOT NULL AND projection=prior.fact AND verified=prior.verified THEN
  projection_id:=prior.latest_fact_id;projection_time:=prior.observed_at;END IF;
 INSERT INTO appointment_system.financial_resource_states(merchant_id,mode,resource_id,booking_id,payment_id,order_id,kind,status,outcome,amount_paise,currency,
  fact,verified,attention_reason,latest_fact_id,observed_at) VALUES(p_merchant,p_mode,identity,p_booking,payment,owned.order_id,family,chosen,outcome,
  (p_fact->>'amount')::bigint,'INR',projection,verified,reason,projection_id,projection_time)
 ON CONFLICT(merchant_id,mode,resource_id) DO UPDATE SET status=excluded.status,outcome=excluded.outcome,fact=excluded.fact,verified=excluded.verified,
  attention_reason=excluded.attention_reason,latest_fact_id=excluded.latest_fact_id,observed_at=excluded.observed_at;
 IF family='refund' AND p_provenance='provider_fetch' THEN
  SELECT coalesce(sum(rs.amount_paise),0) INTO total FROM appointment_system.financial_resource_states rs WHERE rs.merchant_id=p_merchant AND rs.mode=p_mode
   AND rs.payment_id=payment AND rs.kind='refund' AND rs.status='processed' AND rs.verified;
  IF total>owned.amount_paise OR total>p_refunded THEN
   reason:='refund_totals_conflict';UPDATE appointment_system.financial_resource_states SET attention_reason=reason
     WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity;
  END IF;
 END IF;
 changed:=prior.resource_id IS NULL OR (prior.status,prior.outcome,prior.verified,prior.attention_reason) IS DISTINCT FROM (chosen,outcome,verified,reason);
 reason:=coalesce(reason,'financial_'||family||'_'||chosen);
 IF changed THEN
  INSERT INTO appointment_system.payment_cases(id,booking_id,event_key,reason) VALUES(gen_random_uuid(),p_booking,payment||':'||identity,reason) ON CONFLICT(booking_id,event_key) DO UPDATE SET reason=excluded.reason,resolved_at=NULL,resolution_actor=NULL,resolution_note=NULL;
  IF p_provenance='provider_fetch' THEN
   INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
   SELECT gen_random_uuid(),p_booking,'payment_review','client',revision,'financial:'||identity||':'||chosen||':'||reason
   FROM appointment_system.bookings WHERE id=p_booking ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  END IF;
 END IF;
 RETURN jsonb_build_object('code','recorded','status',chosen,'outcome',outcome,'verified',verified,'attention_reason',CASE WHEN reason LIKE 'financial_refund_%' OR reason LIKE 'financial_dispute_%' THEN NULL ELSE reason END);
END $_$;

CREATE FUNCTION appointment_system.entry_observe_payment(p_context uuid, p_booking uuid, p_merchant text, p_mode text, p_version text, p_payment text, p_order text, p_hash text, p_status text, p_amount bigint, p_currency text, p_refunded bigint, p_captured boolean) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE booking appointment_system.bookings%ROWTYPE;
        payment appointment_system.payment_orders%ROWTYPE;
        accepted appointment_system.accepted_payments%ROWTYPE;
        observation uuid; reason text; financial_event_key text;
BEGIN
    PERFORM pg_advisory_xact_lock_shared(83124,4);
    PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
    PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO booking FROM appointment_system.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking ORDER BY id FOR UPDATE;
    SELECT * INTO payment FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND OR payment.merchant_id IS DISTINCT FROM p_merchant
       OR payment.mode IS DISTINCT FROM p_mode OR payment.credential_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='payment identity mismatch';
    END IF;
    IF p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$'
       OR p_order IS NULL OR p_order !~ '^order_[A-Za-z0-9]{1,64}$'
       OR p_status IS NULL OR p_status NOT IN ('created','authorized','captured','refunded','failed')
       OR p_captured IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid payment evidence';
    END IF;
    INSERT INTO appointment_system.payment_observations(
        id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,
        amount_paise,currency,refunded_paise,captured
    ) VALUES(gen_random_uuid(),p_booking,p_merchant,p_mode,p_payment,p_order,p_hash,p_status,
             p_amount,p_currency,p_refunded,p_captured)
    ON CONFLICT(merchant_id,mode,payment_id,evidence_hash) DO NOTHING;
    SELECT id INTO observation FROM appointment_system.payment_observations
      WHERE booking_id=p_booking AND merchant_id=p_merchant AND mode=p_mode
        AND payment_id=p_payment AND evidence_hash=p_hash;
    IF observation IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='payment evidence belongs to another booking';
    END IF;
    -- Uncaptured attempts are recorded, but cannot resolve the entire order.
    IF p_status NOT IN ('captured','refunded') AND NOT p_captured AND p_refunded=0 THEN RETURN 'observed'; END IF;
    SELECT * INTO accepted FROM appointment_system.accepted_payments WHERE booking_id=p_booking;
    IF p_order IS DISTINCT FROM payment.provider_order_id OR p_amount <> booking.amount_paise
       OR p_currency <> booking.currency THEN reason := 'payment_mismatch';
    ELSIF p_refunded > 0 OR p_status='refunded' THEN reason := 'refund_observed';
    ELSIF p_status <> 'captured' OR NOT p_captured THEN reason := 'capture_inconsistent';
    ELSIF accepted.payment_id=p_payment AND booking.state IN ('confirmed','cancelled') THEN
        RETURN CASE WHEN booking.state='confirmed' THEN 'confirmed' ELSE 'observed' END;
    ELSIF accepted.payment_id IS NOT NULL THEN reason := 'additional_payment';
    ELSIF EXISTS(SELECT 1 FROM appointment_system.accepted_payments
        WHERE merchant_id=p_merchant AND mode=p_mode AND payment_id=p_payment) THEN reason := 'payment_already_assigned';
    ELSIF NOT EXISTS(SELECT 1 FROM appointment_system.control_product_state WHERE singleton AND enabled
        AND activation_epoch=booking.activation_epoch) THEN reason := 'booking_disabled';
    ELSIF booking.state <> 'held' OR booking.hold_expires_at <= clock_timestamp()
       OR payment.resolved_at IS NOT NULL THEN reason := 'late_payment';
    ELSIF NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking
        AND released_at IS NULL AND starts_at<=booking.starts_at AND ends_at>=booking.ends_at) THEN reason := 'claim_missing';
    END IF;
    IF reason IS NOT NULL THEN
        financial_event_key := p_payment||':'||reason;
        INSERT INTO appointment_system.payment_cases(id,booking_id,event_key,reason)
          VALUES(gen_random_uuid(),p_booking,financial_event_key,reason)
          ON CONFLICT(booking_id,event_key) DO NOTHING;
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
          VALUES(gen_random_uuid(),p_booking,'payment_review','client',booking.revision,financial_event_key)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        IF booking.state IN ('held','expired') THEN
            UPDATE appointment_system.bookings SET state='payment_review' WHERE id=p_booking;
            UPDATE appointment_system.slot_claims SET released_at=clock_timestamp()
              WHERE booking_id=p_booking AND released_at IS NULL;
        END IF;
        RETURN 'payment_needs_review';
    END IF;
    INSERT INTO appointment_system.accepted_payments(booking_id,observation_id,merchant_id,mode,payment_id)
      VALUES(p_booking,observation,p_merchant,p_mode,p_payment);
    UPDATE appointment_system.bookings SET state='confirmed' WHERE id=p_booking;
    UPDATE appointment_system.payment_orders SET resolution='confirmed',resolved_at=clock_timestamp(),recovery_followup=true,next_check_at=clock_timestamp()
      WHERE booking_id=p_booking;
    UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL
      WHERE id=p_context AND active_checkout_id=p_booking;
    INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
      SELECT gen_random_uuid(),p_booking,kind,role,booking.revision
      FROM (VALUES ('booking_ack','customer'),('booking_ack','client'),('booking_calendar','calendar'),
                   ('sheet_booking','client_sheet'),('sheet_booking','agency_sheet')) jobs(kind,role)
      WHERE kind<>'booking_calendar' OR booking.service_snapshot->>'meeting'='google_meet'
      ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
    RETURN 'confirmed';
END
$_$;

CREATE FUNCTION appointment_system.entry_public_policy() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE spec jsonb; version text; browsing boolean;
BEGIN
 PERFORM appointment_system.control_admission(NULL);
 SELECT p.specification,p.version,s.schedule_browsing_open INTO spec,version,browsing FROM appointment_system.intake_settings s
 JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 RETURN jsonb_build_object('policy',spec,'quote_version',version,'server_now',clock_timestamp(),
  'schedule_browsing_open',browsing);
END $$;

CREATE FUNCTION appointment_system.entry_read_operation_incidents(p_session text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb; facts appointment_system.installation%ROWTYPE;
BEGIN
 PERFORM appointment_system.control_authorize(p_session,'service_controller');
 SELECT * INTO STRICT facts FROM appointment_system.installation WHERE singleton;
 SELECT coalesce(jsonb_agg(row),'[]'::jsonb) INTO result FROM
 (SELECT id,version,project,operation,stage,code,first_seen_at,last_seen_at,last_reference,occurrences,elapsed_ms
  FROM appointment_system.operational_incidents ORDER BY last_seen_at DESC,id LIMIT 100) row;
 RETURN jsonb_build_object('version',1,'installation_id',facts.installation_id,'project',facts.project_id,'environment',facts.environment,'incidents',result);
END $$;

CREATE FUNCTION appointment_system.entry_reconcile_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE e appointment_system.provider_inbox%ROWTYPE; j appointment_system.delivery_jobs%ROWTYPE;
 candidate record; provider_uuid uuid; job_uuid uuid; occurred timestamptz; code text;
BEGIN
 FOR candidate IN SELECT p.account_id,p.event_id,p.payload FROM appointment_system.provider_inbox p
   WHERE p.provider='resend' AND p.environment='live' AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp()
    AND (p.account_id=appointment_system.installation_value('sender.email')
     OR EXISTS(SELECT 1 FROM appointment_system.mail_connection m WHERE p.account_id=m.account_id
      OR EXISTS(SELECT 1 FROM jsonb_array_elements(m.legacy_identities) a WHERE a->>'event_account_id'=p.account_id)))
    AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs c WHERE c.id::text=p.payload->>'job_id')
    AND NOT EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail c WHERE c.id::text=p.payload->>'job_id')
   ORDER BY p.next_attempt_at,p.received_at,p.event_id LIMIT 20 LOOP
  code:=NULL;
  BEGIN
    job_uuid:=(candidate.payload->>'job_id')::uuid;
    provider_uuid:=(candidate.payload->>'email_id')::uuid;
    occurred:=(candidate.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN
    job_uuid:=NULL;provider_uuid:=NULL;occurred:=NULL;
  END;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=job_uuid FOR UPDATE SKIP LOCKED;
  IF NOT FOUND AND EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE id=job_uuid) THEN CONTINUE; END IF;
  SELECT * INTO e FROM appointment_system.provider_inbox WHERE provider='resend'
    AND account_id=candidate.account_id AND environment='live' AND event_id=candidate.event_id
    AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.id IS NULL OR e.account_id IS DISTINCT FROM coalesce(j.mail_event_account_id,appointment_system.installation_value('sender.email')) OR provider_uuid IS NULL OR occurred IS NULL OR
    NOT appointment_system.is_email_job(j.kind,j.recipient_role) OR j.first_attempt_at IS NULL OR j.message_snapshot IS NULL THEN
    code:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text) OR
    EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id AND recipient_role IN ('customer','client')) OR
    EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND kind IN ('verification','acknowledgement','practice_notice')) THEN
    code:='email_event_provider_conflict';
  ELSIF e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed')
    OR e.payload->>'event' IS NULL THEN code:='email_event_invalid';
  END IF;
  IF code IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   code:='email_event_invalid'; END IF;
  IF code IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR (e.payload->>'mail_format' IS NOT NULL AND e.payload->>'mail_format' IS DISTINCT FROM j.mail_format) OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   code:='email_event_job_unmatched'; END IF;
  IF code IS NULL AND appointment_system.append_mail_acceptance('booking',j.id,j.message_hash,provider_uuid)<>'accepted' THEN
   code:='email_event_provider_conflict'; END IF;
  IF code IS NOT NULL THEN
    UPDATE appointment_system.provider_inbox SET attempts=attempts+1,last_error_code=code,
      next_attempt_at=clock_timestamp()+interval '1 hour' WHERE provider=e.provider AND account_id=e.account_id
      AND environment=e.environment AND event_id=e.event_id;
    RETURN false;
  END IF;
  INSERT INTO appointment_system.email_observations(event_id,job_id,provider_id,event_type,occurred_at)
    VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE appointment_system.delivery_jobs SET provider_id=provider_uuid::text,accepted_at=coalesce(accepted_at,clock_timestamp()),
    state=CASE WHEN state IN ('needs_review','suppressed') THEN state ELSE 'completed' END
    WHERE id=j.id AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE appointment_system.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP;
 RETURN false;
END $$;

CREATE FUNCTION appointment_system.entry_reconcile_enquiry_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record;e appointment_system.provider_inbox%ROWTYPE;j appointment_system.enquiry_delivery_jobs%ROWTYPE;provider_uuid uuid;occurred timestamptz;fault text;
BEGIN
 FOR candidate IN SELECT p.account_id,p.event_id,p.payload FROM appointment_system.provider_inbox p
  JOIN appointment_system.enquiry_delivery_jobs d ON d.id::text=p.payload->>'job_id'
  WHERE p.provider='resend' AND p.account_id=coalesce(d.mail_event_account_id,appointment_system.installation_value('sender.email')) AND p.environment='live'
    AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp() ORDER BY p.next_attempt_at,p.received_at LIMIT 20 LOOP
  SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id::text=candidate.payload->>'job_id' FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO e FROM appointment_system.provider_inbox WHERE provider='resend' AND account_id=candidate.account_id
   AND environment='live' AND event_id=candidate.event_id AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  fault:=NULL;
  BEGIN
   provider_uuid:=(e.payload->>'email_id')::uuid;occurred:=(e.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN provider_uuid:=NULL;occurred:=NULL; END;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.kind NOT IN ('verification','acknowledgement','practice_notice') OR j.first_attempt_at IS NULL OR j.message_digest IS NULL
   OR provider_uuid IS NULL OR occurred IS NULL OR NOT isfinite(occurred)
   OR e.payload->>'event' IS NULL OR e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed') THEN fault:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text)
   OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id)
   OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=provider_uuid::text AND recipient_role IN ('customer','client'))
   THEN fault:='email_event_provider_conflict'; END IF;
  IF fault IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   fault:='email_event_invalid'; END IF;
  IF fault IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR (e.payload->>'mail_format' IS NOT NULL AND e.payload->>'mail_format' IS DISTINCT FROM j.mail_format) OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   fault:='email_event_job_unmatched'; END IF;
  IF fault IS NULL AND appointment_system.append_mail_acceptance('contact',j.id,j.message_digest,provider_uuid)<>'accepted' THEN
   fault:='email_event_provider_conflict'; END IF;
  IF fault IS NOT NULL THEN
   UPDATE appointment_system.provider_inbox SET attempts=attempts+1,last_error_code=fault,next_attempt_at=clock_timestamp()+interval '1 hour'
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id; RETURN false;
  END IF;
  INSERT INTO appointment_system.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
   VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE appointment_system.enquiry_delivery_jobs SET provider_id=provider_uuid::text,
   state=CASE WHEN state IN ('needs_review','suppressed','suppressed') THEN state ELSE 'completed' END WHERE id=j.id
    AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE appointment_system.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
   WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP; RETURN false;
END $$;

CREATE FUNCTION appointment_system.entry_record_operation_incident(p_reference uuid, p_operation text, p_stage text, p_code text, p_elapsed integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE project_name text;
BEGIN
 IF p_reference IS NULL OR p_operation IS NULL OR p_stage IS NULL OR p_code IS NULL OR p_elapsed IS NULL
  OR p_elapsed NOT BETWEEN 0 AND 60000 THEN RETURN false; END IF;
 SELECT project_id INTO project_name FROM appointment_system.installation WHERE singleton;
 IF project_name IS NULL THEN RETURN false; END IF;
 INSERT INTO appointment_system.operational_incidents(project,operation,stage,code,first_seen_at,last_seen_at,first_reference,last_reference,occurrences,elapsed_ms)
 VALUES(project_name,p_operation,p_stage,p_code,clock_timestamp(),clock_timestamp(),p_reference,p_reference,1,p_elapsed)
 ON CONFLICT(operation,stage,code) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_reference=excluded.last_reference,
 occurrences=CASE WHEN operational_incidents.last_reference=excluded.last_reference THEN operational_incidents.occurrences ELSE
  least(2147483647,operational_incidents.occurrences::bigint+1)::integer END,elapsed_ms=excluded.elapsed_ms;
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.entry_record_order_creation(p_context uuid, p_booking uuid, p_merchant text, p_mode text, p_version text, p_order text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE payment appointment_system.payment_orders%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock_shared(83124,4);
    PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
    PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM 1 FROM appointment_system.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking ORDER BY id FOR UPDATE;
    SELECT * INTO payment FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND OR payment.merchant_id IS DISTINCT FROM p_merchant
       OR payment.mode IS DISTINCT FROM p_mode OR payment.credential_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='payment identity mismatch';
    END IF;
    IF payment.state NOT IN ('creating','creation_unknown','ready') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='payment creation was not claimed';
    END IF;
    IF p_order IS NOT NULL AND p_order !~ '^order_[A-Za-z0-9]{1,64}$' THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid provider order';
    END IF;
    IF payment.provider_order_id IS NOT NULL THEN
        IF p_order IS NOT NULL AND p_order <> payment.provider_order_id THEN
            RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='provider order conflict';
        END IF;
        RETURN payment.state;
    END IF;
    UPDATE appointment_system.payment_orders SET
      state=CASE WHEN p_order IS NULL THEN 'creation_unknown' ELSE 'ready' END,
      provider_order_id=p_order,next_check_at=clock_timestamp()
      WHERE booking_id=p_booking;
    RETURN CASE WHEN p_order IS NULL THEN 'creation_unknown' ELSE 'ready' END;
END
$_$;

CREATE FUNCTION appointment_system.entry_redeem_receipt_recovery(p_reference uuid, p_code text, p_receipt text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE context uuid;b appointment_system.bookings%ROWTYPE;r appointment_system.receipt_recoveries%ROWTYPE;
BEGIN
 IF p_reference IS NULL OR p_code IS NULL OR p_code !~ '^[a-f0-9]{64}$' OR p_receipt IS NULL OR p_receipt !~ '^[a-f0-9]{64}$' THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference FOR UPDATE;
 SELECT * INTO r FROM appointment_system.receipt_recoveries WHERE request_id=p_reference AND superseded_at IS NULL ORDER BY created_at DESC,operation_id DESC LIMIT 1 FOR UPDATE;
 IF NOT FOUND OR r.expires_at<=clock_timestamp() OR r.attempts>=5 THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF r.code_digest<>p_code THEN
  UPDATE appointment_system.receipt_recoveries SET attempts=least(5,attempts+1) WHERE operation_id=r.operation_id;
  RETURN jsonb_build_object('code','access_unavailable');
 END IF;
 IF r.redeemed_at IS NOT NULL THEN
  IF r.redeemed_digest=p_receipt AND b.receipt_revoked_at IS NULL AND EXISTS(SELECT 1 FROM appointment_system.checkout_admissions WHERE request_id=p_reference AND receipt_digest=p_receipt)
  THEN RETURN jsonb_build_object('code','receipt_restored');END IF;
  RETURN jsonb_build_object('code','access_unavailable');
 END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.checkout_admissions WHERE request_id=p_reference AND receipt_digest=p_receipt) THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 -- A contact correction after issuance supersedes the grant. Other time changes are safe.
 UPDATE appointment_system.checkout_admissions SET receipt_digest=p_receipt WHERE request_id=p_reference;
 UPDATE appointment_system.bookings SET receipt_revoked_at=NULL,receipt_expires_at=greatest(ends_at+interval '24 hours',clock_timestamp()+interval '24 hours') WHERE id=b.id;
 UPDATE appointment_system.receipt_recoveries SET redeemed_digest=p_receipt,redeemed_at=clock_timestamp() WHERE operation_id=r.operation_id;
 RETURN jsonb_build_object('code','receipt_restored');
END $_$;

CREATE FUNCTION appointment_system.entry_resend_enquiry(p_id uuid, p_receipt text, p_operation uuid, p_generation integer, p_digest text, p_cipher text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE e appointment_system.enquiries%ROWTYPE; old appointment_system.enquiry_resends%ROWTYPE; inserted uuid; opened boolean; quota jsonb;
BEGIN
 SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=p_id FOR UPDATE;
 IF NOT FOUND OR e.receipt_digest IS DISTINCT FROM p_receipt OR e.receipt_expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM appointment_system.enquiry_resends WHERE operation_id=p_operation;
 IF FOUND THEN
   IF old.request_id<>p_id THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
   RETURN appointment_system.enquiry_view(p_id,p_receipt);
 END IF;
 IF e.verified_at IS NOT NULL THEN RETURN appointment_system.enquiry_view(p_id,p_receipt); END IF;
 opened:=appointment_system.lock_contact_intake();
 IF opened IS DISTINCT FROM true THEN RETURN jsonb_build_object('code','contact_unavailable'); END IF;
 IF e.generation>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF e.resend_after>clock_timestamp() THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 IF p_generation IS DISTINCT FROM e.generation+1 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF p_operation IS NULL OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
   OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 quota:=appointment_system.consume_request_limit('contact_email',e.email_key);
 IF quota->>'allowed' IS DISTINCT FROM 'true' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 INSERT INTO appointment_system.enquiry_resends(operation_id,request_id,generation) VALUES(p_operation,p_id,p_generation)
 ON CONFLICT(operation_id) DO NOTHING RETURNING operation_id INTO inserted;
 IF inserted IS NULL THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
 UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
  WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
 UPDATE appointment_system.enquiries SET generation=p_generation,code_digest=p_digest,code_ciphertext=p_cipher,
   code_expires_at=clock_timestamp()+interval '5 minutes',resend_after=clock_timestamp()+interval '60 seconds',attempts=0 WHERE request_id=p_id;
 INSERT INTO appointment_system.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT request_id,'verification',generation,code_expires_at FROM appointment_system.enquiries WHERE request_id=p_id;
 RETURN appointment_system.enquiry_view(p_id,p_receipt);
END $_$;

CREATE FUNCTION appointment_system.entry_reserve_configured_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text, p_input jsonb, p_expected jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE ctx appointment_system.checkout_contexts%ROWTYPE; admission appointment_system.checkout_admissions%ROWTYPE;
 settings appointment_system.intake_settings%ROWTYPE; spec jsonb; service jsonb; instant timestamptz:=clock_timestamp();
 starts timestamptz; offer record; identifier uuid; existing_id uuid; reason text; quantity integer;
 grant_row appointment_system.booking_verification_grants%ROWTYPE; preparation jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO settings FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT specification INTO spec FROM appointment_system.booking_policies WHERE version=settings.policy_version;
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND OR ctx.expires_at<=instant THEN RETURN jsonb_build_object('code','context_expired'); END IF;
 PERFORM appointment_system.control_admission(ctx.activation_epoch);
 SELECT * INTO admission FROM appointment_system.checkout_admissions WHERE request_id=p_request AND context_id=p_context;
 IF NOT FOUND OR admission.receipt_digest IS DISTINCT FROM p_receipt
  OR admission.request_fingerprint IS DISTINCT FROM p_fingerprint
  OR p_input->>'request_id' IS DISTINCT FROM p_request::text
  OR appointment_system.settings_digest(p_input) IS DISTINCT FROM p_fingerprint
 THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
 IF admission.outcome='committed' THEN
  SELECT id INTO existing_id FROM appointment_system.bookings WHERE request_id=p_request;
  RETURN jsonb_build_object('code','existing','booking_id',existing_id);
 END IF;
 IF admission.outcome<>'pending' THEN RETURN jsonb_build_object('code','request_rejected'); END IF;
 IF settings.policy_version IS DISTINCT FROM p_input->>'quote_version' THEN reason:='quote_changed';
 ELSIF p_expected IS NULL OR NOT settings.public_open OR p_expected IS DISTINCT FROM
  jsonb_build_object('merchant_id',settings.merchant_id,'mode',settings.payment_mode,'credential_version',settings.credential_version)
 THEN reason:='payment_not_configured';
 ELSIF NOT appointment_system.bounded_integer(coalesce(p_input->'questions','1'::jsonb),1,10)
 THEN reason:='invalid_details'; END IF;
 IF reason IS NULL THEN
  quantity:=coalesce((p_input->>'questions')::integer,1);
  service:=appointment_system.service_quote(spec,p_input->>'service_id',quantity);
  IF service IS NULL THEN reason:='service_unavailable'; END IF;
 END IF;
 IF reason IS NULL THEN
  IF coalesce(p_input->>'starts_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
  THEN reason:='invalid_time';
  ELSE
   BEGIN starts:=(p_input->>'starts_at')::timestamptz;
   EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN reason:='invalid_time'; END;
  END IF;
 END IF;
 IF reason IS NULL THEN
  SELECT * INTO offer FROM appointment_system.schedule_starts(spec,(service->>'duration_minutes')::integer,
   (starts AT TIME ZONE(spec->>'timezone'))::date,instant) WHERE starts_at=starts;
  IF NOT FOUND OR NOT isfinite(starts) THEN reason:='time_unavailable'; END IF;
 END IF;
 IF reason IS NULL THEN
  IF jsonb_typeof(p_input->'full_name') IS DISTINCT FROM 'string'
   OR coalesce(length(btrim(p_input->>'full_name')),0) NOT BETWEEN 2 AND 100
   OR p_input->>'full_name' ~ '[[:cntrl:]]'
   OR jsonb_typeof(p_input->'email') IS DISTINCT FROM 'string'
   OR coalesce(p_input->>'email','') !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$'
   OR length(p_input->>'email')>254
   OR (spec->'required_contacts' @> '["phone"]'::jsonb AND coalesce(p_input->>'phone','') !~ '^\+[1-9][0-9]{6,14}$')
   OR (coalesce(p_input->>'phone','')<>'' AND p_input->>'phone' !~ '^\+[1-9][0-9]{6,14}$')
  THEN reason:='invalid_details'; END IF;
  preparation:=jsonb_build_object('birth_date',p_input->'birth_date','birth_time',p_input->'birth_time',
   'birth_place',p_input->'birth_place','notes',p_input->'notes');
  IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(service->'required_preparation') field
   WHERE coalesce(length(btrim(p_input->>field)),0)=0)
  THEN reason:='preparation_required'; END IF;
 END IF;
 IF reason IS NULL AND spec#>'{booking_verification,email}'='true'::jsonb THEN
  SELECT * INTO grant_row FROM appointment_system.booking_verification_grants
  WHERE digest=p_input->>'verification_grant' AND context_id=p_context AND email=p_input->>'email'
   AND purpose='booking' AND policy_digest=appointment_system.verification_policy(spec)
   AND expires_at>instant AND consumed_request IS NULL AND revoked_at IS NULL;
  IF NOT FOUND THEN reason:='verification_required'; END IF;
 END IF;
 IF reason IS NOT NULL THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code',reason);
 END IF;
 -- Lock relevant expired bookings in sorted order before touching capacity.
 PERFORM appointment_system.lock_capacity_window(offer.occupied_start,offer.occupied_end);
 instant:=clock_timestamp();
 IF offer.starts_at<instant+make_interval(mins=>(spec->>'notice_minutes')::integer) THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END IF;
 IF spec#>'{booking_verification,email}'='true'::jsonb THEN
  SELECT * INTO grant_row FROM appointment_system.booking_verification_grants
   WHERE digest=p_input->>'verification_grant' AND context_id=p_context AND email=p_input->>'email'
    AND purpose='booking' AND policy_digest=appointment_system.verification_policy(spec)
    AND expires_at>instant AND consumed_request IS NULL AND revoked_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN
   UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
   RETURN jsonb_build_object('code','verification_required');
  END IF;
 END IF;
 PERFORM appointment_system.expire_relevant(offer.occupied_start,offer.occupied_end);
 IF ctx.active_checkout_id IS NOT NULL THEN
  -- Clear only this context's pointer after proving the old order is resolved.
  IF EXISTS(SELECT 1 FROM appointment_system.payment_orders WHERE booking_id=ctx.active_checkout_id AND resolved_at IS NOT NULL)
  THEN UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL WHERE id=p_context;
  ELSE
   UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
   RETURN jsonb_build_object('code','checkout_in_progress');
  END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE released_at IS NULL
  AND tstzrange(starts_at,ends_at,'[)')&&tstzrange(offer.occupied_start,offer.occupied_end,'[)'))
 THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END IF;
 identifier:=gen_random_uuid();
 BEGIN
  INSERT INTO appointment_system.bookings(id,request_id,context_id,state,service_id,policy_version,service_snapshot,
   amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,preparation,
   hold_expires_at,receipt_expires_at,created_at,original_starts_at,activation_epoch,receipt_format,receipt_key_id)
  VALUES(identifier,p_request,p_context,'held',service->>'id',settings.policy_version,service,
   (service->>'amount_paise')::bigint,'INR',offer.starts_at,offer.ends_at,spec->>'timezone',
   p_input->>'full_name',p_input->>'email',nullif(p_input->>'phone',''),preparation,
   least(offer.starts_at,instant+interval '10 minutes'),offer.ends_at+interval '24 hours',instant,
   offer.starts_at,ctx.activation_epoch,'v1',p_input#>>'{_receipt,key_id}');
  INSERT INTO appointment_system.slot_claims(id,booking_id,starts_at,ends_at)
  VALUES(gen_random_uuid(),identifier,offer.occupied_start,offer.occupied_end);
  INSERT INTO appointment_system.payment_orders(booking_id,merchant_id,mode,credential_version)
  VALUES(identifier,settings.merchant_id,settings.payment_mode,settings.credential_version);
  IF grant_row.digest IS NOT NULL THEN
   UPDATE appointment_system.booking_verification_grants SET consumed_request=p_request
   WHERE digest=grant_row.digest AND consumed_request IS NULL AND expires_at>clock_timestamp() AND revoked_at IS NULL;
   IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='verification changed'; END IF;
  END IF;
  UPDATE appointment_system.checkout_contexts SET active_checkout_id=identifier WHERE id=p_context;
  UPDATE appointment_system.checkout_admissions SET outcome='committed' WHERE request_id=p_request;
 EXCEPTION WHEN exclusion_violation THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END;
 RETURN jsonb_build_object('code','reserved','booking_id',identifier);
END $_$;

CREATE FUNCTION appointment_system.entry_start_enquiry(p_id uuid, p_receipt text, p_fingerprint text, p_payload jsonb, p_digest text, p_cipher text, p_email_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE e appointment_system.enquiries%ROWTYPE; opened boolean; quota jsonb;
BEGIN
 -- Scope request lock before row access; exact retries never replace code/content.
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-contact:'||p_id::text,0));
 SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=p_id FOR UPDATE;
 IF FOUND THEN
   IF e.receipt_digest IS DISTINCT FROM p_receipt OR e.request_fingerprint IS DISTINCT FROM p_fingerprint
     OR e.payload IS DISTINCT FROM p_payload THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
   RETURN appointment_system.enquiry_view(p_id,p_receipt);
 END IF;
 opened:=appointment_system.lock_contact_intake();
 IF opened IS DISTINCT FROM true THEN RETURN jsonb_build_object('code','contact_unavailable'); END IF;
 IF p_id IS NULL OR p_receipt IS NULL OR p_receipt !~ '^[a-f0-9]{64}$' OR p_fingerprint IS NULL OR p_fingerprint !~ '^[a-f0-9]{64}$'
   OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192
   OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR octet_length(p_payload::text)>16000
   OR p_email_key IS NULL OR p_email_key !~ '^[a-f0-9]{64}$' OR p_payload->>'email' IS NULL THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 quota:=appointment_system.consume_request_limit('contact_email',p_email_key);
 IF quota->>'allowed' IS DISTINCT FROM 'true' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 INSERT INTO appointment_system.enquiries(request_id,email_key,receipt_digest,request_fingerprint,payload,code_digest,code_ciphertext,code_expires_at,resend_after)
 VALUES(p_id,p_email_key,p_receipt,p_fingerprint,p_payload,p_digest,p_cipher,clock_timestamp()+interval '5 minutes',clock_timestamp()+interval '60 seconds');
 INSERT INTO appointment_system.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT request_id,'verification',generation,code_expires_at FROM appointment_system.enquiries WHERE request_id=p_id;
 RETURN appointment_system.enquiry_view(p_id,p_receipt);
END $_$;

CREATE FUNCTION appointment_system.entry_start_google_attempt(p_state text, p_browser text, p_purpose text, p_role text, p_encrypted text, p_session text, p_client text, p_origin text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor jsonb; revision bigint;
BEGIN
    IF p_purpose='connect' THEN
        actor:=appointment_system.studio_session(p_session,p_client,p_origin);
        IF actor IS NULL OR actor->>'role' IS DISTINCT FROM p_role THEN RETURN false; END IF;
    END IF;
    SELECT g.revision INTO revision FROM appointment_system.google_connections g WHERE g.role=p_role;
    INSERT INTO appointment_system.google_attempts(state_digest,browser_digest,purpose,role,encrypted_attempt,
        session_digest,expected_revision,client_id,origin,expires_at)
      VALUES(p_state,p_browser,p_purpose,p_role,p_encrypted,p_session,coalesce(revision,0),
        p_client,p_origin,clock_timestamp()+interval '10 minutes');
    RETURN true;
END
$$;

CREATE FUNCTION appointment_system.entry_start_order_creation(p_context uuid, p_booking uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE ctx appointment_system.checkout_contexts%ROWTYPE; b appointment_system.bookings%ROWTYPE;
 p appointment_system.payment_orders%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND OR ctx.active_checkout_id IS DISTINCT FROM p_booking THEN RETURN false; END IF;
 PERFORM appointment_system.control_admission(ctx.activation_epoch);
 SELECT * INTO b FROM appointment_system.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
 IF NOT FOUND OR b.state<>'held' OR b.hold_expires_at<=clock_timestamp() THEN RETURN false; END IF;
 PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking ORDER BY id FOR UPDATE;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking
  AND released_at IS NULL AND starts_at<=b.starts_at AND ends_at>=b.ends_at) THEN RETURN false; END IF;
 SELECT * INTO p FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
 IF NOT FOUND OR p.state<>'not_attempted' OR p.attempted_at IS NOT NULL OR p.resolved_at IS NOT NULL THEN RETURN false; END IF;
 UPDATE appointment_system.payment_orders SET state='creating',attempted_at=clock_timestamp() WHERE booking_id=p_booking;
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.entry_studio_action_result(p_session text, p_client text, p_origin text, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal_actor text; appointment appointment_system.staff_appointment_actions%ROWTYPE;
 recovery appointment_system.receipt_recoveries%ROWTYPE;review appointment_system.staff_reviews%ROWTYPE;
 target uuid;reference uuid;matches integer;result jsonb;
BEGIN
 principal_actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF principal_actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT * INTO appointment FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation AND staff_appointment_actions.actor=principal_actor;
 SELECT * INTO recovery FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation AND receipt_recoveries.actor=principal_actor;
 SELECT * INTO review FROM appointment_system.staff_reviews WHERE operation_id=p_operation AND staff_reviews.actor=principal_actor;
 matches:=(CASE WHEN appointment.operation_id IS NOT NULL THEN 1 ELSE 0 END)
  +(CASE WHEN recovery.operation_id IS NOT NULL THEN 1 ELSE 0 END)+(CASE WHEN review.operation_id IS NOT NULL THEN 1 ELSE 0 END);
 IF matches=0 THEN RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 IF matches<>1 THEN RETURN jsonb_build_object('code','operation_conflict','operation_id',p_operation);END IF;
 IF appointment.operation_id IS NOT NULL THEN
  target:=appointment.booking_id;
  result:=jsonb_build_object('code',CASE WHEN appointment.action='cancel' THEN 'cancelled' ELSE 'rescheduled' END,
   'revision',appointment.revision,'operation_id',p_operation,'starts_at',appointment.new_starts_at,'ends_at',appointment.new_ends_at);
 ELSIF recovery.operation_id IS NOT NULL THEN
  SELECT id INTO target FROM appointment_system.bookings WHERE request_id=recovery.request_id;
  result:=jsonb_build_object('code','support_saved','revision',recovery.revision,'operation_id',p_operation,'reference',recovery.request_id,
   'expires_at',recovery.expires_at,'active',recovery.superseded_at IS NULL AND recovery.redeemed_at IS NULL AND recovery.attempts<5 AND recovery.expires_at>clock_timestamp());
 ELSE
  IF review.item_key NOT LIKE 'payment:%' OR review.action NOT IN('verified_refund','resource_reviewed') THEN
   RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
  SELECT booking_id INTO target FROM appointment_system.payment_cases WHERE id=substring(review.item_key FROM 9)::uuid;
  result:=jsonb_build_object('code',CASE WHEN review.action='verified_refund' THEN 'refund_verified' ELSE 'resource_reviewed' END,
   'revision',review.revision,'operation_id',p_operation);
 END IF;
 IF principal_actor LIKE 'company:%' AND NOT(EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=target)) THEN
  RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 SELECT request_id INTO reference FROM appointment_system.bookings WHERE id=target;
 RETURN result||jsonb_build_object('reference',reference);
END $$;

CREATE FUNCTION appointment_system.entry_studio_appointment_cancel(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text;old appointment_system.staff_appointment_actions%ROWTYPE;b appointment_system.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;guidance text;snapshot jsonb;old_snapshot jsonb;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('staff-appointment-operation:'||p_operation::text,0));
 SELECT s.booking_id,bk.context_id INTO booking,context FROM appointment_system.slot_claims s JOIN appointment_system.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'cancel' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision OR old.reason IS DISTINCT FROM p_reason THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','cancelled','revision',old.revision,'policy_guidance',old.policy_guidance);
 END IF;
 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id=p_claim AND released_at IS NULL) THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 guidance:=CASE WHEN EXISTS(SELECT 1 FROM appointment_system.staff_appointment_actions WHERE booking_id=b.id AND action='reschedule') THEN 'staff_review' WHEN b.starts_at>=instant+interval '24 hours' THEN 'full_refund_review' WHEN b.starts_at>=instant+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END;
 old_snapshot:=appointment_system.booking_snapshot(b.id);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'state','cancelled','cancelled_at',instant);
 INSERT INTO appointment_system.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance)
 VALUES(p_operation,p_claim,b.id,'cancel',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,guidance);
 UPDATE appointment_system.bookings SET state='cancelled',cancelled_at=instant,revision=revision+1 WHERE id=b.id;
 UPDATE appointment_system.slot_claims SET released_at=instant WHERE id=p_claim;
 -- Never erase accepted evidence or revoke an in-flight completion lease.
 UPDATE appointment_system.delivery_jobs SET state='suppressed',last_error_code='appointment_cancelled'
 WHERE booking_id=b.id AND booking_revision=b.revision AND kind IN ('booking_ack','booking_details','booking_calendar')
 AND state IN ('pending','retry_wait') AND first_attempt_at IS NULL AND payload IS NULL AND provider_id IS NULL AND lease_token IS NULL;
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot)
 ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 SELECT gen_random_uuid(),b.id,'sheet_booking',role,b.revision+1,snapshot FROM (VALUES('client_sheet'),('agency_sheet')) roles(role);
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
 SELECT gen_random_uuid(),b.id,'booking_cancelled',role,b.revision+1 FROM (VALUES('customer'),('client')) roles(role);
 RETURN jsonb_build_object('code','cancelled','revision',b.revision+1,'policy_guidance',guidance);
END $$;

CREATE FUNCTION appointment_system.entry_studio_appointment_detail(p_session text, p_client text, p_origin text, p_claim uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE b appointment_system.bookings%ROWTYPE;
BEGIN
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT booking.* INTO b FROM appointment_system.bookings booking JOIN appointment_system.slot_claims s ON s.booking_id=booking.id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 RETURN jsonb_build_object('code','ok','claim_id',p_claim,'revision',b.revision,'state',b.state,'name',b.full_name,
 'service',b.service_snapshot->>'name','reference',b.request_id,'starts_at',b.starts_at,'ends_at',b.ends_at,
 'can_cancel',b.state='confirmed' AND b.starts_at>clock_timestamp(),
 'can_reschedule',b.state='confirmed' AND b.starts_at>clock_timestamp(),
 'policy_guidance',CASE WHEN EXISTS(SELECT 1 FROM appointment_system.staff_appointment_actions WHERE booking_id=b.id AND action='reschedule') THEN 'staff_review' WHEN b.starts_at>=clock_timestamp()+interval '24 hours' THEN 'full_refund_review'
 WHEN b.starts_at>=clock_timestamp()+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END);
END $$;

CREATE FUNCTION appointment_system.entry_studio_appointment_reschedule(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text, p_start timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text;old appointment_system.staff_appointment_actions%ROWTYPE;b appointment_system.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;spec jsonb;local_start timestamp;offer record;new_end timestamptz;deadline timestamptz;late boolean;old_snapshot jsonb;snapshot jsonb;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_start IS NULL OR NOT isfinite(p_start) OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('staff-appointment-operation:'||p_operation::text,0));
 SELECT s.booking_id,bk.context_id INTO booking,context FROM appointment_system.slot_claims s JOIN appointment_system.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 SELECT p.specification INTO spec FROM appointment_system.intake_settings s JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','time_unavailable'); END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO old FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'reschedule' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision
  OR old.reason IS DISTINCT FROM p_reason OR old.new_starts_at IS DISTINCT FROM p_start THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','rescheduled','revision',old.revision,'starts_at',old.new_starts_at,'ends_at',old.new_ends_at);
 END IF;

 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking;
 PERFORM appointment_system.lock_capacity_window(
  p_start-make_interval(mins=>(spec->>'buffer_before_minutes')::integer),
  p_start+(b.ends_at-b.starts_at)+make_interval(mins=>(spec->>'buffer_after_minutes')::integer),
  (SELECT starts_at FROM appointment_system.slot_claims WHERE id=p_claim),
  (SELECT ends_at FROM appointment_system.slot_claims WHERE id=p_claim));

 PERFORM appointment_system.lock_move_capacity(booking,
  p_start-make_interval(mins=>(spec->>'buffer_before_minutes')::integer),
  p_start+(b.ends_at-b.starts_at)+make_interval(mins=>(spec->>'buffer_after_minutes')::integer));
 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id=p_claim AND released_at IS NULL)
 THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 IF p_start=b.starts_at THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 late:=b.starts_at<instant+interval '12 hours';
 IF late AND EXISTS(SELECT 1 FROM appointment_system.staff_appointment_actions WHERE booking_id=b.id AND late_exception)
 THEN RETURN jsonb_build_object('code','late_reschedule_used');END IF;
 deadline:=coalesce(b.reschedule_deadline_at,CASE WHEN late THEN coalesce(b.original_starts_at,b.starts_at)+interval '14 days' END);
 SELECT * INTO offer FROM appointment_system.schedule_starts(spec,
  (extract(epoch FROM b.ends_at-b.starts_at)/60)::integer,
  (p_start AT TIME ZONE (spec->>'timezone'))::date,instant,deadline) s WHERE s.starts_at=p_start;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','time_unavailable'); END IF;
 new_end:=offer.ends_at;
 IF EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id<>p_claim AND released_at IS NULL
  AND tstzrange(starts_at,ends_at,'[)')&&tstzrange(offer.occupied_start,offer.occupied_end,'[)'))
 THEN RETURN jsonb_build_object('code','time_already_reserved'); END IF;
 old_snapshot:=appointment_system.booking_snapshot(b.id);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
 BEGIN
  UPDATE appointment_system.slot_claims SET starts_at=offer.occupied_start,ends_at=offer.occupied_end WHERE id=p_claim;
  UPDATE appointment_system.bookings SET starts_at=p_start,ends_at=new_end,revision=revision+1,
  hold_expires_at=least(hold_expires_at,p_start),receipt_expires_at=greatest(receipt_expires_at,new_end+interval '24 hours'),reschedule_deadline_at=deadline WHERE id=b.id;
  INSERT INTO appointment_system.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance,new_starts_at,new_ends_at,late_exception)
  VALUES(p_operation,p_claim,b.id,'reschedule',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,
  CASE WHEN late THEN 'late_reschedule_review' ELSE 'free_reschedule' END,p_start,new_end,late);
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,b.revision+1,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar')) jobs(kind,role) WHERE kind<>'booking_calendar' OR spec->>'meeting'='google_meet';
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,b.revision+1,jsonb_build_object('booking_id',b.id,'reference',b.request_id,
  'service',b.service_snapshot->>'name','starts_at',p_start,'ends_at',new_end,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','rescheduled') FROM(VALUES('customer'),('client')) roles(role);
 EXCEPTION WHEN exclusion_violation THEN RETURN jsonb_build_object('code','time_already_reserved');END;
 RETURN jsonb_build_object('code','rescheduled','revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
END $$;

CREATE FUNCTION appointment_system.entry_studio_booking_lookup(p_session text, p_client text, p_origin text, p_reference uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE b appointment_system.bookings%ROWTYPE;result jsonb;
BEGIN
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 SELECT jsonb_build_object('code','ok','reference',b.request_id,'revision',b.revision,'state',b.state,'name',b.full_name,'email',b.email,'phone',b.phone,
 'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,
 'claim_id',(SELECT id FROM appointment_system.slot_claims WHERE booking_id=b.id),
 'unresolved_payments',(SELECT count(*) FROM appointment_system.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL),
 'payments',coalesce((SELECT jsonb_agg(x ORDER BY x.observed_at DESC,x.id DESC) FROM (SELECT id,payment_id,status,amount_paise,refunded_paise,currency,captured,observed_at FROM appointment_system.payment_observations WHERE booking_id=b.id ORDER BY observed_at DESC,id DESC LIMIT 20)x),'[]'::jsonb)) INTO result;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.entry_studio_calendar_close(p_session text, p_client text, p_origin text, p_operation uuid, p_reason text, p_start timestamp with time zone, p_end timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text; result jsonb; active boolean;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end)
   OR p_end<=p_start OR p_end-p_start>interval '31 days'
   OR p_end>clock_timestamp()+interval '366 days' OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500
 THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 result:=appointment_system.close_calendar(p_operation,actor,p_reason,p_start,p_end);
 IF result ? 'claim_id' THEN
   SELECT released_at IS NULL INTO active FROM appointment_system.slot_claims WHERE id=(result->>'claim_id')::uuid;
   result:=result||jsonb_build_object('active',active);
 END IF;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.entry_studio_calendar_list(p_session text, p_client text, p_origin text, p_day date, p_after uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb; from_time timestamptz; to_time timestamptz; actor text;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_day IS NULL OR NOT isfinite(p_day) OR p_day<(clock_timestamp() AT TIME ZONE (appointment_system.current_business()->>'timezone'))::date-31
    OR p_day>(clock_timestamp() AT TIME ZONE (appointment_system.current_business()->>'timezone'))::date+366 THEN
   RETURN jsonb_build_object('code','invalid_calendar_date'); END IF;
 from_time:=p_day::timestamp AT TIME ZONE (appointment_system.current_business()->>'timezone');
 to_time:=(p_day+1)::timestamp AT TIME ZONE (appointment_system.current_business()->>'timezone');
 WITH page AS (
  SELECT s.id,s.booking_id,coalesce(b.starts_at,s.starts_at) AS starts_at,coalesce(b.ends_at,s.ends_at) AS ends_at,s.closure_reason,b.full_name,b.state,b.service_snapshot
  FROM appointment_system.slot_claims s LEFT JOIN appointment_system.bookings b ON b.id=s.booking_id
  WHERE s.released_at IS NULL AND (s.booking_id IS NULL OR b.state='confirmed') AND coalesce(b.starts_at,s.starts_at)<to_time AND coalesce(b.ends_at,s.ends_at)>from_time
    AND (p_after IS NULL OR s.id>p_after) ORDER BY s.id LIMIT 51
 ), shown AS (SELECT * FROM page ORDER BY id LIMIT 50)
 SELECT jsonb_build_object('code','ok','day',p_day,'timezone',(appointment_system.current_business()->>'timezone'),
   'items',coalesce((SELECT jsonb_agg(jsonb_build_object('id',id,'kind',CASE WHEN booking_id IS NULL THEN 'closure' ELSE 'appointment' END,
      'starts_at',starts_at,'ends_at',ends_at,'reason',CASE WHEN booking_id IS NULL THEN closure_reason ELSE NULL END,
      'name',CASE WHEN booking_id IS NOT NULL THEN full_name ELSE NULL END,
      'service',CASE WHEN booking_id IS NOT NULL THEN service_snapshot->>'name' ELSE NULL END,
      'state',CASE WHEN booking_id IS NOT NULL THEN state ELSE NULL END) ORDER BY id) FROM shown),'[]'::jsonb),
   'next_cursor',CASE WHEN (SELECT count(*) FROM page)>50 THEN (SELECT id FROM shown ORDER BY id DESC LIMIT 1) ELSE NULL END)
 INTO result;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.entry_studio_calendar_reopen(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text; result jsonb; active boolean;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500
 THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 RETURN appointment_system.reopen_calendar(p_operation,p_claim,actor,p_reason);
END $$;

CREATE FUNCTION appointment_system.entry_studio_inbox_detail(p_session text, p_client text, p_origin text, p_item text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE result jsonb;booking uuid;resources jsonb;
BEGIN
 result:=appointment_system.studio_inbox_detail_before_resources(p_session,p_client,p_origin,p_item);
 IF result->>'code'<>'ok' OR result#>>'{item,category}'<>'payment' THEN RETURN result;END IF;
 SELECT booking_id INTO booking FROM appointment_system.payment_cases WHERE id=split_part(p_item,':',2)::uuid;
 SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) INTO resources FROM
 (SELECT resource_id AS id,kind,status,outcome,amount_paise,currency,verified,attention_reason,
  fact->'respond_by' AS respond_by,fact->'created_at' AS created_at
  FROM appointment_system.financial_resource_states WHERE booking_id=booking ORDER BY resource_id LIMIT 20)r;
 result:=jsonb_set(result,'{item,financial_resources}',resources,true);
 RETURN jsonb_set(result,'{item,financial_resource_id}',coalesce((SELECT to_jsonb(split_part(event_key,':',2)) FROM appointment_system.payment_cases WHERE id=split_part(p_item,':',2)::uuid),'null'::jsonb),true);
END $$;

CREATE FUNCTION appointment_system.entry_studio_inbox_list(p_session text, p_client text, p_origin text, p_view text, p_after text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE a jsonb;result jsonb;
BEGIN
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_view IN ('enquiries','enquiry-issues') THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL OR (p_view IN ('enquiries','enquiry-issues') AND a->>'role'<>'client') THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_view IS NULL OR p_view NOT IN ('enquiries','issues','enquiry-issues') OR (p_after IS NOT NULL AND p_after !~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$') THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 WITH page AS (
 SELECT i.*,coalesce((SELECT max(r.revision) FROM appointment_system.staff_reviews r WHERE r.item_key=i.item_key),0) review_revision
 FROM appointment_system.staff_items(a->>'role') i WHERE CASE WHEN p_view='enquiries' THEN i.category='enquiry' WHEN p_view='enquiry-issues' THEN i.category='enquiry-delivery' ELSE i.category<>'enquiry' END
 AND (p_after IS NULL OR i.item_key>p_after) ORDER BY i.item_key LIMIT 51
 ),shown AS (SELECT * FROM page ORDER BY item_key LIMIT 50)
 SELECT jsonb_build_object('code','ok','view',p_view,'items',coalesce((SELECT jsonb_agg(to_jsonb(shown) ORDER BY item_key) FROM shown),'[]'::jsonb),
  'next_cursor',CASE WHEN (SELECT count(*) FROM page)>50 THEN (SELECT item_key FROM shown ORDER BY item_key DESC LIMIT 1) END) INTO result;
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.entry_studio_inbox_refund_verified(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.staff_reviews%ROWTYPE;c appointment_system.payment_cases%ROWTYPE;b appointment_system.bookings%ROWTYPE;
 p appointment_system.payment_orders%ROWTYPE;proof appointment_system.payment_observations%ROWTYPE;current_revision integer;booking uuid;identity uuid;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^payment:[a-f0-9-]{36}$' OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-staff-review:'||p_item,0));
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'verified_refund' OR prior.item_key<>p_item OR prior.actor<>actor OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','refund_verified','revision',prior.revision);
 END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM appointment_system.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 identity:=split_part(p_item,':',2)::uuid;
 SELECT booking_id INTO booking FROM appointment_system.payment_cases WHERE id=identity;
 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT * INTO p FROM appointment_system.payment_orders WHERE booking_id=booking FOR SHARE;
 SELECT * INTO c FROM appointment_system.payment_cases WHERE id=identity FOR UPDATE;
 IF c.resolved_at IS NOT NULL THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 IF split_part(c.event_key,':',2) ~ '^disp_' OR c.reason LIKE 'financial_dispute_%'
 OR EXISTS(SELECT 1 FROM appointment_system.financial_resource_states f WHERE f.booking_id=booking
  AND f.payment_id=split_part(c.event_key,':',1) AND (NOT f.verified OR f.attention_reason IS NOT NULL OR (f.kind='refund' AND f.status='pending'))) THEN
  RETURN jsonb_build_object('code','refund_not_verified');END IF;

 SELECT * INTO proof FROM appointment_system.payment_observations WHERE booking_id=booking AND merchant_id=p.merchant_id AND mode=p.mode
 AND provider_order_id=p.provider_order_id AND payment_id=split_part(c.event_key,':',1) AND currency=b.currency AND amount_paise>0
 AND refunded_paise=amount_paise AND status='refunded' ORDER BY observed_at DESC,id DESC LIMIT 1;
 IF NOT FOUND OR (b.state='confirmed' AND EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=booking AND payment_id=proof.payment_id AND merchant_id=proof.merchant_id AND mode=proof.mode))
 THEN RETURN jsonb_build_object('code','refund_not_verified');END IF;
 INSERT INTO appointment_system.staff_reviews(operation_id,item_key,revision,actor,note,action,evidence_id) VALUES(p_operation,p_item,current_revision+1,actor,p_note,'verified_refund',proof.id);
 UPDATE appointment_system.payment_cases SET resolved_at=clock_timestamp(),resolution_actor=actor,
 resolution_note='Verified full refund observation '||proof.id||'. '||p_note WHERE id=identity;
 RETURN jsonb_build_object('code','refund_verified','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

CREATE FUNCTION appointment_system.entry_studio_inbox_resource_reviewed(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.staff_reviews%ROWTYPE;c appointment_system.payment_cases%ROWTYPE;f appointment_system.financial_resource_states%ROWTYPE;
 current_revision integer;booking uuid;identity uuid;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^payment:[a-f0-9-]{36}$' OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-staff-review:'||p_item,0));
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'resource_reviewed' OR prior.item_key<>p_item OR prior.actor<>actor OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','resource_reviewed','revision',prior.revision);
 END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM appointment_system.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 identity:=split_part(p_item,':',2)::uuid;
 SELECT booking_id INTO booking FROM appointment_system.payment_cases WHERE id=identity;
 PERFORM 1 FROM appointment_system.payment_orders WHERE booking_id=booking FOR SHARE;
 SELECT * INTO c FROM appointment_system.payment_cases WHERE id=identity FOR UPDATE;
 IF NOT FOUND OR c.resolved_at IS NOT NULL THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT * INTO f FROM appointment_system.financial_resource_states WHERE booking_id=booking AND resource_id=split_part(c.event_key,':',2);
 IF NOT FOUND OR f.kind<>'dispute' OR NOT f.verified OR f.attention_reason IS NOT NULL OR f.status NOT IN('won','lost','closed') THEN
  RETURN jsonb_build_object('code','resource_not_verified');END IF;
 INSERT INTO appointment_system.staff_reviews(operation_id,item_key,revision,actor,note,action,resource_evidence_id)
 VALUES(p_operation,p_item,current_revision+1,actor,p_note,'resource_reviewed',f.latest_fact_id);
 UPDATE appointment_system.payment_cases SET resolved_at=clock_timestamp(),resolution_actor=actor,
 resolution_note='Recorded dispute outcome '||f.status||' from evidence '||f.latest_fact_id||'. '||p_note WHERE id=identity;
 RETURN jsonb_build_object('code','resource_reviewed','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

CREATE FUNCTION appointment_system.entry_studio_inbox_retry(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE a jsonb;prior appointment_system.staff_reviews%ROWTYPE;current_revision integer;identity uuid;booking uuid;enquiry uuid;b appointment_system.bookings%ROWTYPE;
 j appointment_system.delivery_jobs%ROWTYPE;e appointment_system.enquiry_delivery_jobs%ROWTYPE;p appointment_system.payment_orders%ROWTYPE;instant timestamptz;
BEGIN
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_item LIKE 'enquiry:%' OR p_item LIKE 'enquiry-delivery:%' THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^(payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'
 OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]'
 THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-staff-review:'||p_item,0));
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_item LIKE 'enquiry:%' OR p_item LIKE 'enquiry-delivery:%' THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'retry' OR prior.item_key<>p_item OR prior.actor<>a->>'actor' OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','retry_queued','revision',prior.revision);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.staff_items(a->>'role') WHERE item_key=p_item) THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM appointment_system.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.staff_reviews WHERE item_key=p_item AND action='retry' AND created_at>clock_timestamp()-interval '1 minute') THEN RETURN jsonb_build_object('code','retry_wait');END IF;
 identity:=split_part(p_item,':',2)::uuid;instant:=clock_timestamp();
 IF p_item LIKE 'delivery:%' THEN
  SELECT booking_id INTO booking FROM appointment_system.delivery_jobs WHERE id=identity;
  SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR SHARE;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=identity FOR UPDATE;
  IF j.state NOT IN ('needs_review','retry_wait','delivery_unknown','pending','processing') OR j.lease_expires_at>instant THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  IF appointment_system.is_email_job(j.kind,j.recipient_role) THEN
   IF j.provider_id IS NOT NULL OR (j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours')
    OR (j.send_deadline_at IS NOT NULL AND j.send_deadline_at<=instant)
    OR (j.kind IN ('booking_ack','booking_details') AND b.starts_at<=instant)
    OR (j.kind<>'payment_review' AND (j.booking_revision<>b.revision OR (j.kind='booking_cancelled' AND b.state<>'cancelled') OR(j.kind<>'booking_cancelled' AND b.state<>'confirmed')))
    OR EXISTS(SELECT 1 FROM appointment_system.email_observations o JOIN appointment_system.delivery_jobs d ON d.id=o.job_id WHERE d.destination=j.destination AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
   THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  ELSIF j.kind NOT IN ('booking_calendar','sheet_booking','booking_cancelled') THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE appointment_system.delivery_jobs SET state='pending',next_attempt_at=instant,lease_token=NULL,lease_expires_at=NULL WHERE id=identity;
 ELSIF p_item LIKE 'enquiry-delivery:%' THEN
  SELECT request_id INTO enquiry FROM appointment_system.enquiry_delivery_jobs WHERE id=identity;
  PERFORM 1 FROM appointment_system.enquiries WHERE request_id=enquiry FOR SHARE;
  SELECT * INTO e FROM appointment_system.enquiry_delivery_jobs WHERE id=identity FOR UPDATE;
  IF e.kind='verification' OR e.state NOT IN ('needs_review','retry_wait','delivery_unknown','pending','processing') OR e.lease_expires_at>instant OR e.deadline_at<=instant THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  IF e.kind IN ('acknowledgement','practice_notice') AND(e.provider_id IS NOT NULL OR(e.first_attempt_at IS NOT NULL AND instant>=e.first_attempt_at+interval '23 hours')
   OR EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations WHERE job_id=e.id AND event_type IN ('email.bounced','email.complained','email.suppressed')))
  THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE appointment_system.enquiry_delivery_jobs SET state='pending',next_attempt_at=instant,lease_token=NULL,lease_expires_at=NULL WHERE id=identity;
 ELSE
  IF a->>'role'<>'client' THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
  SELECT booking_id INTO booking FROM appointment_system.payment_cases WHERE id=identity AND resolved_at IS NULL;
  SELECT * INTO p FROM appointment_system.payment_orders WHERE booking_id=booking FOR UPDATE;
  IF NOT FOUND OR p.lease_expires_at>instant OR (p.resolved_at IS NOT NULL AND p.resolution<>'confirmed') THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE appointment_system.payment_orders SET recovery_followup=true,next_check_at=instant WHERE booking_id=booking;
 END IF;
 INSERT INTO appointment_system.staff_reviews(operation_id,item_key,revision,actor,note,action) VALUES(p_operation,p_item,current_revision+1,a->>'actor',p_note,'retry');
 RETURN jsonb_build_object('code','retry_queued','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

CREATE FUNCTION appointment_system.entry_studio_inbox_review(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE a jsonb;prior appointment_system.staff_reviews%ROWTYPE;current_revision integer;
BEGIN
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_item LIKE 'enquiry:%' OR p_item LIKE 'enquiry-delivery:%' THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'
  OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000
  OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 -- Actor/session lock precedes per-item serialization; no provider call or money mutation.
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-staff-review:'||p_item,0));
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_item LIKE 'enquiry:%' OR p_item LIKE 'enquiry-delivery:%' THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO prior FROM appointment_system.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'note' OR prior.item_key<>p_item OR prior.actor<>a->>'actor' OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','review_saved','revision',prior.revision);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.staff_items(a->>'role') WHERE item_key=p_item) THEN RETURN jsonb_build_object('code','item_unavailable'); END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM appointment_system.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 BEGIN
 INSERT INTO appointment_system.staff_reviews(operation_id,item_key,revision,actor,note) VALUES(p_operation,p_item,current_revision+1,a->>'actor',p_note);
 EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict'); END;
 RETURN jsonb_build_object('code','review_saved','revision',current_revision+1);
END $_$;

CREATE FUNCTION appointment_system.entry_studio_logout(p_digest text, p_client text, p_origin text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE changed_role text;
BEGIN
    UPDATE appointment_system.studio_sessions SET revoked_at=clock_timestamp()
      WHERE digest=p_digest AND client_id=p_client AND origin=p_origin AND revoked_at IS NULL
      RETURNING role INTO changed_role;
    IF changed_role IS NOT NULL THEN
      INSERT INTO appointment_system.studio_audit(role,action) VALUES(changed_role,'logout');
    END IF;
    RETURN changed_role IS NOT NULL;
END
$$;

CREATE FUNCTION appointment_system.entry_studio_session(p_digest text, p_client text, p_origin text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
    SELECT (SELECT jsonb_build_object('role',s.role,'subject',s.subject,'expires_at',s.expires_at)
      FROM appointment_system.studio_sessions s JOIN appointment_system.studio_identities i
        ON i.role=s.role AND i.subject=s.subject
      WHERE s.digest=p_digest AND s.client_id=p_client AND s.origin=p_origin
        AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp())
$$;

CREATE FUNCTION appointment_system.entry_studio_support_change(p_session text, p_client text, p_origin text, p_operation uuid, p_reference uuid, p_revision integer, p_action text, p_reason text, p_payment text, p_email text, p_phone text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.receipt_recoveries%ROWTYPE;b appointment_system.bookings%ROWTYPE;context uuid;instant timestamptz;old_snapshot jsonb;snapshot jsonb;new_revision integer;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_reference IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_action IS NULL OR p_action NOT IN ('receipt_recovery','contact_correction') OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 OR p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR (p_action='contact_correction' AND(coalesce(length(p_email),0) NOT BETWEEN 3 AND 254 OR p_email ~ '[[:cntrl:]]' OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$'))
 OR (p_action='receipt_recovery' AND(p_email IS NOT NULL OR p_phone IS NOT NULL)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.request_id<>p_reference OR prior.actor<>actor OR prior.action<>p_action OR prior.reason<>p_reason OR prior.previous_revision<>p_revision OR prior.verified_payment_id<>p_payment
  OR prior.new_email IS DISTINCT FROM p_email OR prior.new_phone IS DISTINCT FROM p_phone OR prior.code_digest<>p_digest THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','support_saved','revision',prior.revision,'expires_at',prior.expires_at,'active',prior.superseded_at IS NULL AND prior.redeemed_at IS NULL AND prior.attempts<5 AND prior.expires_at>clock_timestamp());
 END IF;
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 instant:=clock_timestamp();
 IF b.state='held' OR NOT EXISTS(SELECT 1 FROM appointment_system.payment_observations o JOIN appointment_system.payment_orders p ON p.booking_id=o.booking_id
 WHERE o.booking_id=b.id AND o.payment_id=p_payment AND o.merchant_id=p.merchant_id AND o.mode=p.mode AND o.provider_order_id=p.provider_order_id
 AND o.currency=b.currency AND o.amount_paise>0 AND(o.captured OR o.refunded_paise>0)) THEN RETURN jsonb_build_object('code','support_verification_unavailable');END IF;
 IF (SELECT count(*) FROM appointment_system.receipt_recoveries WHERE request_id=b.request_id AND created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','support_wait');END IF;
 IF p_action='contact_correction' AND(b.state<>'confirmed' OR b.starts_at<=instant OR (b.email=p_email AND b.phone=p_phone)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 new_revision:=b.revision+CASE WHEN p_action='contact_correction' THEN 1 ELSE 0 END;
 UPDATE appointment_system.receipt_recoveries SET superseded_at=instant WHERE request_id=b.request_id AND superseded_at IS NULL;
 INSERT INTO appointment_system.receipt_recoveries(operation_id,request_id,action,actor,reason,verified_payment_id,previous_revision,revision,previous_email,previous_phone,new_email,new_phone,code_digest)
 VALUES(p_operation,b.request_id,p_action,actor,p_reason,p_payment,b.revision,new_revision,CASE WHEN p_action='contact_correction' THEN b.email END,CASE WHEN p_action='contact_correction' THEN b.phone END,p_email,p_phone,p_digest) RETURNING * INTO prior;
 -- A verified support replacement invalidates old receipt access immediately.
 -- The new digest is installed only by the one-use customer redemption below.
 UPDATE appointment_system.bookings SET receipt_revoked_at=instant WHERE id=b.id;
 IF p_action='contact_correction' THEN
  old_snapshot:=jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,'service_snapshot',b.service_snapshot,'starts_at',b.starts_at,'ends_at',b.ends_at,'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise);
  snapshot:=old_snapshot||jsonb_build_object('revision',new_revision,'email',p_email,'phone',p_phone);
  UPDATE appointment_system.bookings SET email=p_email,phone=p_phone,revision=new_revision WHERE id=b.id;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,new_revision,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar'))jobs(kind,role);
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,new_revision,jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','contact_corrected') FROM(VALUES('customer'),('client'))roles(role);
 END IF;
 RETURN jsonb_build_object('code','support_saved','revision',new_revision,'expires_at',prior.expires_at,'active',true);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

CREATE FUNCTION appointment_system.entry_verify_enquiry(p_id uuid, p_receipt text, p_generation integer, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE e appointment_system.enquiries%ROWTYPE;
BEGIN
 SELECT * INTO e FROM appointment_system.enquiries WHERE request_id=p_id FOR UPDATE;
 IF NOT FOUND OR e.receipt_digest IS DISTINCT FROM p_receipt OR e.receipt_expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 -- Retrying the original enquiry's completed request never consumes another code.
 IF e.verified_at IS NOT NULL THEN RETURN appointment_system.enquiry_view(p_id,p_receipt); END IF;
 IF p_generation IS DISTINCT FROM e.generation THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF e.attempts>=5 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF e.code_expires_at<=clock_timestamp() OR e.code_digest IS NULL THEN
   UPDATE appointment_system.enquiries SET code_digest=NULL,code_ciphertext=NULL WHERE request_id=p_id;
   UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
     WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
   RETURN jsonb_build_object('code','verification_expired'); END IF;
 IF p_digest IS NULL OR p_digest IS DISTINCT FROM e.code_digest THEN
   UPDATE appointment_system.enquiries SET attempts=attempts+1,
     code_digest=CASE WHEN attempts>=4 THEN NULL ELSE code_digest END,
     code_ciphertext=CASE WHEN attempts>=4 THEN NULL ELSE code_ciphertext END WHERE request_id=p_id;
   IF e.attempts>=4 THEN
     UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
       WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
   END IF;
   RETURN jsonb_build_object('code',CASE WHEN e.attempts>=4 THEN 'verification_limit' ELSE 'verification_incorrect' END);
 END IF;
 UPDATE appointment_system.enquiries SET verified_at=clock_timestamp(),code_digest=NULL,code_ciphertext=NULL WHERE request_id=p_id;
 UPDATE appointment_system.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
   WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','delivery_unknown','retry_wait');
 INSERT INTO appointment_system.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT p_id,k,0,clock_timestamp()+interval '24 hours' FROM unnest(ARRAY['acknowledgement','practice_notice','client_sheet','agency_sheet']) k;
 RETURN appointment_system.enquiry_view(p_id,p_receipt);
END $$;

CREATE FUNCTION appointment_system.exact_keys(p_value jsonb, p_keys text[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT CASE WHEN jsonb_typeof(p_value)='object' THEN
  ARRAY(SELECT jsonb_object_keys(p_value) ORDER BY 1)=ARRAY(SELECT unnest(p_keys) ORDER BY 1)
 ELSE false END
$$;

CREATE FUNCTION appointment_system.expire_enquiry_codes() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_expire_enquiry_codes(); END $$;

CREATE FUNCTION appointment_system.expire_holds() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_expire_holds(); END $$;

CREATE FUNCTION appointment_system.expire_locked(p_identifiers uuid[], p_instant timestamp with time zone) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE expired uuid[]; changed integer;
BEGIN
 SELECT coalesce(array_agg(id ORDER BY id),'{}'::uuid[]) INTO expired FROM appointment_system.bookings
 WHERE id=ANY(p_identifiers) AND state='held' AND hold_expires_at<=p_instant;
 PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=ANY(p_identifiers) ORDER BY id FOR UPDATE;
 PERFORM 1 FROM appointment_system.payment_orders WHERE booking_id=ANY(p_identifiers) ORDER BY booking_id FOR UPDATE;
 UPDATE appointment_system.bookings SET state='expired' WHERE id=ANY(expired);
 GET DIAGNOSTICS changed=ROW_COUNT;
 UPDATE appointment_system.slot_claims SET released_at=p_instant WHERE booking_id=ANY(expired) AND released_at IS NULL;
 UPDATE appointment_system.payment_orders SET resolution='never_attempted_abandoned',resolved_at=p_instant
 WHERE booking_id=ANY(expired) AND state='not_attempted' AND attempted_at IS NULL AND resolved_at IS NULL;
 RETURN changed;
END $$;

CREATE FUNCTION appointment_system.expire_relevant(p_start timestamp with time zone DEFAULT NULL::timestamp with time zone, p_end timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE identifiers uuid[]; instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT coalesce(array_agg(id ORDER BY id),'{}'::uuid[]) INTO identifiers FROM (
  SELECT b.id FROM appointment_system.bookings b WHERE b.state='held' AND b.hold_expires_at<=instant
  AND (p_start IS NULL OR EXISTS(SELECT 1 FROM appointment_system.slot_claims c WHERE c.booking_id=b.id
   AND c.released_at IS NULL AND tstzrange(c.starts_at,c.ends_at,'[)')&&tstzrange(p_start,p_end,'[)')))
  ORDER BY b.id LIMIT 25 FOR UPDATE OF b SKIP LOCKED) locked;
 RETURN appointment_system.expire_locked(identifiers,instant);
END $$;

CREATE FUNCTION appointment_system.finish_booking_code(p_job uuid, p_lease uuid, p_provider uuid, p_error text, p_review boolean, p_delay integer, p_rejected boolean) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.booking_verification_mail%ROWTYPE;context uuid;challenge uuid;acceptance text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT context_id,challenge_id INTO context,challenge FROM appointment_system.booking_verification_mail WHERE id=p_job;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR SHARE;
 PERFORM 1 FROM appointment_system.booking_verification_challenges WHERE id=challenge FOR SHARE;
 SELECT * INTO j FROM appointment_system.booking_verification_mail WHERE id=p_job FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF p_provider IS NOT NULL THEN
  acceptance:=appointment_system.append_mail_acceptance('verification',p_job,j.message_digest,p_provider);
  IF acceptance='invalid' THEN RETURN false; END IF;
 END IF;
 IF p_lease IS NULL OR j.lease_token IS DISTINCT FROM p_lease OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) OR j.state<>'processing' THEN RETURN false; END IF;
 IF p_delay IS NULL OR p_delay NOT BETWEEN 1 AND 3600 OR p_review IS NULL OR p_rejected IS NULL OR (p_error IS NOT NULL AND p_error !~ '^[a-z0-9_]{1,80}$') THEN RETURN false; END IF;
 UPDATE appointment_system.booking_verification_mail SET provider_id=CASE WHEN acceptance='accepted' THEN p_provider ELSE provider_id END,
  state=CASE WHEN acceptance='conflict' OR p_review THEN 'needs_review' WHEN p_provider IS NOT NULL THEN 'completed' WHEN p_rejected THEN 'retry_wait' ELSE 'delivery_unknown' END,
  last_error_code=CASE WHEN acceptance='conflict' THEN 'email_event_provider_conflict' ELSE p_error END,
  lease_token=NULL,lease_expires_at=NULL,next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay) WHERE id=j.id;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.finish_email_delivery(p_job uuid, p_lease uuid, p_provider uuid, p_error text, p_attention boolean, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.delivery_jobs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 86400 OR p_attention IS NULL
   OR(p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT appointment_system.is_email_job(j.kind,j.recipient_role) OR j.lease_token IS DISTINCT FROM p_lease
   OR p_lease IS NULL OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL AND (j.first_attempt_at IS NULL OR j.message_snapshot IS NULL) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||p_provider::text,0)); END IF;
 IF p_provider IS NOT NULL AND ((j.provider_id IS NOT NULL AND j.provider_id<>p_provider::text)
   OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=p_provider::text AND id<>j.id AND recipient_role IN ('customer','client'))
   OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=p_provider::text AND kind IN ('verification','acknowledgement','practice_notice'))) THEN
   UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='email_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN false;
 END IF;
 UPDATE appointment_system.delivery_jobs SET provider_id=coalesce(p_provider::text,provider_id),
   accepted_at=CASE WHEN p_provider IS NOT NULL THEN coalesce(accepted_at,clock_timestamp()) ELSE accepted_at END,
   state=CASE WHEN p_provider IS NOT NULL OR provider_id IS NOT NULL THEN 'completed' WHEN p_attention THEN 'needs_review' ELSE 'delivery_unknown' END,
   last_error_code=p_error,next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.finish_enquiry_delivery(p_job uuid, p_lease uuid, p_provider text, p_error text, p_attention boolean, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_enquiry_delivery(p_job, p_lease, p_provider, p_error, p_attention, p_delay); END $$;

CREATE FUNCTION appointment_system.finish_financial_resource(p_case uuid, p_lease uuid, p_delay integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_financial_resource(p_case, p_lease, p_delay, p_error); END $$;

CREATE FUNCTION appointment_system.finish_google_delivery(p_job uuid, p_lease uuid, p_state text, p_provider text, p_meet text, p_error text, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_google_delivery(p_job, p_lease, p_state, p_provider, p_meet, p_error, p_delay); END $$;

CREATE FUNCTION appointment_system.finish_google_resource_refresh(p_resource text, p_id uuid, p_revision bigint, p_resource_revision bigint, p_lease uuid, p_encrypted text, p_expires timestamp with time zone, p_scopes jsonb, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE target appointment_system.google_resources%ROWTYPE;g appointment_system.google_resource_grants%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker','staff','company']);
 IF EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose='staff')
  AND p_resource='agency_sheet' THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource access denied'; END IF;
 SELECT * INTO target FROM appointment_system.google_resources WHERE resource=p_resource AND revision=p_resource_revision AND (grant_id=p_id OR EXISTS(SELECT 1 FROM appointment_system.google_workbook_volumes v WHERE v.grant_id=p_id AND v.role=CASE WHEN p_resource='client_sheet' THEN 'client' WHEN p_resource='agency_sheet' THEN 'agency' ELSE '' END)) FOR SHARE;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO g FROM appointment_system.google_resource_grants WHERE id=p_id AND revision=p_revision
  AND refresh_revision=p_revision AND refresh_lease=p_lease AND refresh_lease_until>clock_timestamp() AND revoked_at IS NULL FOR UPDATE;
 IF NOT FOUND OR g.owner_email<>target.owner_email OR NOT p_resource=ANY(g.resources) OR NOT g.client_id=ANY(target.retained_clients) THEN RETURN false; END IF;
 IF p_error IS NOT NULL THEN
  IF p_error NOT IN ('google_reconnect_required','google_request_failed','google_account_mismatch','google_permissions_mismatch','google_token_invalid','google_saved_grant_invalid') THEN RETURN false; END IF;
  UPDATE appointment_system.google_resource_grants SET refresh_lease=NULL,refresh_lease_until=NULL,refresh_revision=NULL,last_error_code=p_error WHERE id=p_id;
  RETURN true;
 END IF;
 IF p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768
  OR NOT coalesce(appointment_system.resource_scopes_valid(g.resources,p_scopes),false)
  OR (SELECT array_agg(CASE WHEN s#>>'{}'='email' THEN 'https://www.googleapis.com/auth/userinfo.email' ELSE s#>>'{}' END ORDER BY CASE WHEN s#>>'{}'='email' THEN 'https://www.googleapis.com/auth/userinfo.email' ELSE s#>>'{}' END) FROM jsonb_array_elements(g.scopes)s)
     IS DISTINCT FROM (SELECT array_agg(s#>>'{}' ORDER BY s#>>'{}') FROM jsonb_array_elements(p_scopes)s)
  OR (p_expires IS NOT NULL AND (NOT isfinite(p_expires) OR p_expires<=clock_timestamp())) THEN RETURN false; END IF;
 UPDATE appointment_system.google_resource_grants SET encrypted_grant=p_encrypted,grant_format='v1',scopes=p_scopes,
  grant_expires_at=p_expires,revision=revision+1,refresh_lease=NULL,refresh_lease_until=NULL,refresh_revision=NULL,last_error_code=NULL WHERE id=p_id;
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.finish_google_workbook(p_role text, p_lease uuid, p_file text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker','staff','company']); IF p_role='agency' AND EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user AND purpose='staff') THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource access denied'; END IF; RETURN appointment_system.entry_finish_google_workbook(p_role, p_lease, p_file); END $$;

CREATE FUNCTION appointment_system.finish_mail_attempt(p_kind text, p_job uuid, p_lease uuid, p_provider uuid, p_hash text, p_error text, p_attention boolean, p_delay integer, p_rejected boolean) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_mail_attempt(p_kind, p_job, p_lease, p_provider, p_hash, p_error, p_attention, p_delay, p_rejected); END $$;

CREATE FUNCTION appointment_system.finish_payment_event(p_account text, p_mode text, p_event text, p_lease uuid, p_done boolean, p_delay integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_payment_event(p_account, p_mode, p_event, p_lease, p_done, p_delay, p_error); END $$;

CREATE FUNCTION appointment_system.finish_payment_recovery(p_booking uuid, p_lease uuid, p_delay integer, p_cursor integer, p_skip integer, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_finish_payment_recovery(p_booking, p_lease, p_delay, p_cursor, p_skip, p_error); END $$;

CREATE FUNCTION appointment_system.finish_recovery_run(p_run uuid, p_release text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE instant timestamptz:=clock_timestamp();current_generation uuid;items jsonb;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT restore_generation INTO current_generation FROM appointment_system.control_product_state WHERE singleton FOR SHARE;
 PERFORM 1 FROM appointment_system.worker_release r JOIN appointment_system.worker_runs w ON w.id=p_run
  WHERE r.singleton AND r.release_digest=p_release AND r.active_run=p_run AND r.active_until>instant
   AND w.generation=current_generation AND w.release_digest=p_release FOR UPDATE OF r;
 IF NOT FOUND THEN RETURN jsonb_build_object('completed',false); END IF;
 WITH work AS MATERIALIZED (SELECT * FROM appointment_system.recovery_due_work WHERE due IS NOT NULL)
 SELECT jsonb_object_agg(lane,jsonb_build_object('remaining_due',remaining_due,'next_due_at',next_due_at)) INTO items
 FROM (SELECT t.lane,least(10000,count(w.due) FILTER(WHERE w.due<=instant))::integer remaining_due,
  floor(extract(epoch FROM min(w.due))*1000)::bigint next_due_at
 FROM appointment_system.worker_lane_turns t LEFT JOIN work w USING(lane) GROUP BY t.lane) lane_work;
 result:=jsonb_build_object('completed',true,'generation',current_generation,'release_digest',p_release,'run_id',p_run,
  'evaluated_at',floor(extract(epoch FROM instant)*1000)::bigint,'lanes',items,'attention',appointment_system.recovery_attention());
 UPDATE appointment_system.worker_runs SET finished_at=instant,final_summary=result WHERE id=p_run;
 UPDATE appointment_system.worker_release SET active_run=NULL,active_until=NULL WHERE singleton AND active_run=p_run;
 RETURN result;
END $$;

CREATE FUNCTION appointment_system.finish_resource_consent(p_authority text, p_parent text, p_csrf text, p_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_resource_attempts%ROWTYPE;parent_revision bigint;installed boolean;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE id=p_id AND authority=p_authority AND parent_digest=p_parent;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','consent_unavailable'); END IF;
 parent_revision:=appointment_system.resource_parent(p_authority,p_parent,p_csrf,a.signin_client,a.resource,true);
 IF a.result='saved' THEN RETURN jsonb_build_object('code','saved','resource',a.resource); END IF;
 IF a.result IS DISTINCT FROM 'pending' OR NOT appointment_system.resource_consent_current(a) THEN RETURN jsonb_build_object('code','consent_changed'); END IF;
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE id=p_id FOR UPDATE;
 IF a.result='saved' THEN RETURN jsonb_build_object('code','saved','resource',a.resource); END IF;
 installed:=appointment_system.install_resource_grant(a.resource,a.resource_revision,a.grant_id,a.subject,a.owner_email,
  a.client_id,ARRAY[a.resource],a.scopes,a.encrypted_grant,a.grant_expires_at,'v1');
 UPDATE appointment_system.google_resource_attempts SET result=CASE WHEN installed THEN 'saved' ELSE 'changed' END,
  finished_at=clock_timestamp(),encrypted_grant=NULL WHERE id=p_id;
 RETURN jsonb_build_object('code',CASE WHEN installed THEN 'saved' ELSE 'consent_changed' END,'resource',a.resource);
END $$;

CREATE FUNCTION appointment_system.freeze_booking_code_message() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF OLD.first_attempt_at IS NOT NULL AND (
  ROW(NEW.first_attempt_at,NEW.mail_account_id,NEW.mail_event_account_id,NEW.mail_credential_version,NEW.mail_format,NEW.mail_idempotency_key,NEW.message_digest)
   IS DISTINCT FROM ROW(OLD.first_attempt_at,OLD.mail_account_id,OLD.mail_event_account_id,OLD.mail_credential_version,OLD.mail_format,OLD.mail_idempotency_key,OLD.message_digest)
  OR (NEW.message_ciphertext IS NOT NULL AND NEW.message_ciphertext IS DISTINCT FROM OLD.message_ciphertext))
 THEN RAISE EXCEPTION 'A booking code send cannot change after its first attempt'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.freeze_mail_binding() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF OLD.first_attempt_at IS NOT NULL AND ROW(NEW.mail_event_account_id,NEW.mail_account_id,NEW.mail_credential_version,NEW.mail_format,NEW.mail_idempotency_key)
  IS DISTINCT FROM ROW(OLD.mail_event_account_id,OLD.mail_account_id,OLD.mail_credential_version,OLD.mail_format,OLD.mail_idempotency_key)
 THEN RAISE EXCEPTION 'A saved mail attempt identity cannot change'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.install_resource_grant(p_resource text, p_expected bigint, p_id uuid, p_subject text, p_email text, p_client text, p_resources text[], p_scopes jsonb, p_encrypted text, p_expires timestamp with time zone, p_format text) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE target appointment_system.google_resources%ROWTYPE;candidate record;connection_role text;
BEGIN
 IF p_resource IS NULL OR p_expected IS NULL OR p_id IS NULL OR p_id='00000000-0000-0000-0000-000000000000'
  OR p_subject IS NULL OR length(p_subject) NOT BETWEEN 1 AND 255 OR p_subject ~ '[[:cntrl:]]'
  OR p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768
  OR p_format IS NULL OR p_format !~ '^[a-z0-9][a-z0-9-]{0,63}$'
  OR (p_expires IS NOT NULL AND (NOT isfinite(p_expires) OR p_expires<=clock_timestamp()))
  OR NOT coalesce(appointment_system.resource_scopes_valid(p_resources,p_scopes),false)
  OR NOT p_resource=ANY(p_resources) THEN RETURN false; END IF;
 PERFORM 1 FROM appointment_system.google_resources WHERE resource=ANY(p_resources) ORDER BY resource FOR UPDATE;
 SELECT * INTO target FROM appointment_system.google_resources WHERE resource=p_resource;
 IF NOT FOUND OR target.revision<>p_expected OR target.owner_email IS DISTINCT FROM p_email OR NOT p_client=ANY(target.retained_clients)
  OR (SELECT count(*) FROM appointment_system.google_resources WHERE resource=ANY(p_resources))<>cardinality(p_resources)
  OR EXISTS(SELECT 1 FROM appointment_system.google_resources WHERE resource=ANY(p_resources)
   AND (owner_email<>p_email OR NOT p_client=ANY(retained_clients) OR resource<>p_resource AND revision<>0))
 THEN RETURN false; END IF;
 connection_role:=CASE WHEN p_resource='agency_sheet' THEN 'agency' ELSE 'client' END;
 INSERT INTO appointment_system.google_resource_grants(id,owner_role,owner_email,subject,client_id,resources,scopes,encrypted_grant,grant_format,grant_expires_at)
 VALUES(p_id,connection_role,p_email,p_subject,p_client,p_resources,p_scopes,p_encrypted,p_format,p_expires);
 UPDATE appointment_system.google_resources SET grant_id=p_id,revision=revision+1,updated_at=clock_timestamp() WHERE resource=ANY(p_resources);

 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.installation_value(p_path text) RETURNS text
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT CASE WHEN p_path='sender.formatted'
  THEN (specification#>>'{sender,name}')||' <'||(specification#>>'{sender,email}')||'>'
  ELSE specification#>>string_to_array(p_path,'.') END
 FROM appointment_system.installation WHERE singleton
$$;

CREATE FUNCTION appointment_system.is_email_job(k text, r text) RETURNS boolean
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$ SELECT (k='booking_ack' AND r IN ('customer','client'))
 OR(k='booking_details' AND r='customer') OR(k='booking_cancelled' AND r IN ('customer','client'))
 OR(k='payment_review' AND r='client') $$;

CREATE FUNCTION appointment_system.issue_resource_owner_link(p_parent text, p_csrf text, p_id uuid, p_resource text, p_reference uuid, p_reason text, p_access text, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE old appointment_system.google_resource_owner_links%ROWTYPE;g appointment_system.google_resources%ROWTYPE;owner_role text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.resource_parent('company',p_parent,p_csrf,'',p_resource,true);
 owner_role:=CASE WHEN p_resource='agency_sheet' THEN 'agency' ELSE 'client' END;
 IF p_id IS NULL OR p_id='00000000-0000-0000-0000-000000000000' OR p_reference IS NULL
  OR p_resource NOT IN ('calendar','client_sheet','agency_sheet') OR p_access IS NULL OR p_access!~'^[a-f0-9]{64}$'
  OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$' OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 5 AND 300
 THEN RETURN NULL; END IF;
 SELECT * INTO g FROM appointment_system.google_resources WHERE resource=p_resource FOR UPDATE;
 IF NOT FOUND OR NOT appointment_system.control_repair_obligation(p_reference,owner_role,CASE WHEN p_resource='calendar' THEN 'calendar' ELSE 'records' END)
 THEN RETURN NULL; END IF;
 SELECT * INTO old FROM appointment_system.google_resource_owner_links WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
  IF old.parent_digest<>p_parent OR old.body_hash<>p_hash OR old.access_digest<>p_access
  THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='owner link changed'; END IF;
  RETURN jsonb_build_object('id',old.id,'expires_at',old.expires_at);
 END IF;
 INSERT INTO appointment_system.google_resource_owner_links(id,parent_digest,resource,resource_revision,reference,reason,access_digest,body_hash)
 VALUES(p_id,p_parent,p_resource,g.revision,p_reference,btrim(p_reason),p_access,p_hash) RETURNING * INTO old;
 RETURN jsonb_build_object('id',old.id,'expires_at',old.expires_at);
END $_$;

CREATE FUNCTION appointment_system.lock_booking_verification_context(p_context uuid) RETURNS jsonb
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE ctx appointment_system.checkout_contexts%ROWTYPE;settings appointment_system.intake_settings%ROWTYPE;spec jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO settings FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND OR ctx.expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','context_expired'); END IF;
 PERFORM appointment_system.control_admission(ctx.activation_epoch);
 SELECT specification INTO spec FROM appointment_system.booking_policies WHERE version=settings.policy_version;
 IF spec#>'{booking_verification,email}' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('code','verification_not_required'); END IF;
 RETURN jsonb_build_object('code','ok','policy_digest',appointment_system.verification_policy(spec),'context',to_jsonb(ctx));
END $$;

CREATE FUNCTION appointment_system.lock_capacity_window(p_start timestamp with time zone, p_end timestamp with time zone, p_other_start timestamp with time zone DEFAULT NULL::timestamp with time zone, p_other_end timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE day date;
BEGIN
 IF p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end)
  OR p_end<=p_start OR p_end-p_start>interval '366 days'
  OR (p_other_start IS NULL)<>(p_other_end IS NULL)
  OR (p_other_start IS NOT NULL AND (NOT isfinite(p_other_start) OR NOT isfinite(p_other_end)
    OR p_other_end<=p_other_start OR p_other_end-p_other_start>interval '366 days')) THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid capacity interval'; END IF;
 FOR day IN SELECT DISTINCT value FROM (
  SELECT (p_start AT TIME ZONE 'UTC')::date+n AS value
  FROM generate_series(0,((p_end-interval '1 microsecond') AT TIME ZONE 'UTC')::date-(p_start AT TIME ZONE 'UTC')::date) n
  UNION ALL
  SELECT (p_other_start AT TIME ZONE 'UTC')::date+n
  FROM generate_series(0,((p_other_end-interval '1 microsecond') AT TIME ZONE 'UTC')::date-(p_other_start AT TIME ZONE 'UTC')::date) n
  WHERE p_other_start IS NOT NULL) dates ORDER BY value LOOP
  PERFORM pg_advisory_xact_lock(82178,day-date '1970-01-01');
 END LOOP;
END $$;

CREATE FUNCTION appointment_system.lock_contact_intake() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE opened boolean;
BEGIN
 SELECT public_open INTO opened FROM appointment_system.contact_intake WHERE id=true FOR SHARE;
 RETURN coalesce(opened,false);
END $$;

CREATE FUNCTION appointment_system.lock_move_capacity(p_booking uuid, p_start timestamp with time zone, p_end timestamp with time zone) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE identifiers uuid[]; instant timestamptz:=clock_timestamp();
BEGIN
 SELECT array_agg(id ORDER BY id) INTO identifiers FROM (
  (SELECT b.id FROM appointment_system.bookings b WHERE b.state='held' AND b.hold_expires_at<=instant
   AND EXISTS(SELECT 1 FROM appointment_system.slot_claims c WHERE c.booking_id=b.id AND c.released_at IS NULL
    AND tstzrange(c.starts_at,c.ends_at,'[)')&&tstzrange(p_start,p_end,'[)')) ORDER BY b.id LIMIT 25)
  UNION SELECT p_booking) candidates;
 PERFORM 1 FROM appointment_system.bookings WHERE id=ANY(identifiers) ORDER BY id FOR UPDATE;
 RETURN appointment_system.expire_locked(identifiers,instant);
END $$;

CREATE FUNCTION appointment_system.mail_tags(p_job uuid, p_version integer) RETURNS jsonb
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT jsonb_build_array(jsonb_build_object('name','project','value',appointment_system.installation_value('project_id')),
  jsonb_build_object('name','installation','value',appointment_system.installation_value('installation_id')),
  jsonb_build_object('name','environment','value',appointment_system.installation_value('environment')),
  jsonb_build_object('name','job_id','value',p_job::text),jsonb_build_object('name','message_version','value',p_version::text))
$$;

CREATE FUNCTION appointment_system.mapped_google_row(p_role text, p_job uuid, p_kind text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_mapped_google_row(p_role, p_job, p_kind); END $$;

CREATE FUNCTION appointment_system.observe_financial_resource(p_booking uuid, p_merchant text, p_mode text, p_version text, p_fact jsonb, p_provenance text, p_hash text, p_parent jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_observe_financial_resource(p_booking, p_merchant, p_mode, p_version, p_fact, p_provenance, p_hash, p_parent); END $$;

CREATE FUNCTION appointment_system.observe_payment(p_context uuid, p_booking uuid, p_merchant text, p_mode text, p_version text, p_payment text, p_order text, p_hash text, p_status text, p_amount bigint, p_currency text, p_refunded bigint, p_captured boolean) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_observe_payment(p_context, p_booking, p_merchant, p_mode, p_version, p_payment, p_order, p_hash, p_status, p_amount, p_currency, p_refunded, p_captured); END $$;

CREATE FUNCTION appointment_system.owner_resource_link_context(p_id uuid, p_access text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE link appointment_system.google_resource_owner_links%ROWTYPE;g appointment_system.google_resources%ROWTYPE;role_name text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO link FROM appointment_system.google_resource_owner_links WHERE id=p_id AND access_digest=p_access;
 IF NOT FOUND OR link.expires_at<=clock_timestamp() OR link.attempt_id IS NOT NULL THEN RETURN NULL; END IF;
 PERFORM appointment_system.resource_parent('company',link.parent_digest,NULL,'',link.resource,true);
 SELECT * INTO g FROM appointment_system.google_resources WHERE resource=link.resource AND revision=link.resource_revision FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 role_name:=CASE WHEN link.resource='agency_sheet' THEN 'agency' ELSE 'client' END;
 IF NOT appointment_system.control_repair_obligation(link.reference,role_name,CASE WHEN link.resource='calendar' THEN 'calendar' ELSE 'records' END)
 THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('resource',g.resource,'client_id',g.active_client,'owner_email',g.owner_email);
END $$;

CREATE FUNCTION appointment_system.pending_resource_consents(p_parent text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.resource_parent('company',p_parent,NULL,'','calendar',false);
 RETURN (SELECT coalesce(jsonb_agg(jsonb_build_object('attempt_id',id,'resource',resource,'expires_at',expires_at) ORDER BY created_at),'[]'::jsonb)
  FROM appointment_system.google_resource_attempts WHERE authority='company' AND parent_digest=p_parent AND result='pending' AND expires_at>clock_timestamp());
END $$;

CREATE FUNCTION appointment_system.privacy_finish_replay(p_operation uuid, p_generation uuid, p_sequence bigint, p_head_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_privacy_replay_progress%ROWTYPE;current jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 PERFORM pg_advisory_xact_lock(83124,4);PERFORM pg_advisory_xact_lock(83125,4);
 current:=appointment_system.control_snapshot();
 IF p_sequence IS NULL OR p_sequence<appointment_system.privacy_required_sequence() OR p_head_hash IS NULL OR p_head_hash!~'^[a-f0-9]{64}$'
  OR current->>'restore_generation' IS DISTINCT FROM p_generation::text OR current->'enabled' IS DISTINCT FROM 'false'::jsonb
  OR NOT EXISTS(SELECT 1 FROM appointment_system.control_restore_operations WHERE id=p_operation AND result_snapshot=current)
  OR EXISTS(SELECT 1 FROM appointment_system.control_privacy_intents i LEFT JOIN appointment_system.control_privacy_completions c ON c.intent_id=i.id WHERE c.intent_id IS NULL)
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy replay incomplete'; END IF;
 SELECT * INTO saved FROM appointment_system.control_privacy_replay_progress WHERE restore_operation=p_operation;
 IF FOUND AND (saved.sequence IS DISTINCT FROM p_sequence OR saved.head_hash IS DISTINCT FROM p_head_hash)
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy replay changed'; END IF;
 INSERT INTO appointment_system.control_privacy_replay_progress(restore_operation,sequence,head_hash) VALUES(p_operation,p_sequence,p_head_hash) ON CONFLICT DO NOTHING;
 RETURN jsonb_build_object('project',appointment_system.installation_value('project_id'),'environment',appointment_system.installation_value('environment'),
  'restore_generation',p_generation,'sequence',p_sequence,'head_hash',p_head_hash,'unresolved',0);
END $_$;

CREATE FUNCTION appointment_system.privacy_freeze(p_operation uuid, p_document jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE intent appointment_system.control_privacy_intents%ROWTYPE;policy appointment_system.control_privacy_policies%ROWTYPE;saved jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 PERFORM pg_advisory_xact_lock(83125,4);
 SELECT * INTO intent FROM appointment_system.control_privacy_intents WHERE id=p_operation;
 SELECT * INTO policy FROM appointment_system.control_privacy_policies WHERE id=intent.policy_id;
 IF intent.id IS NULL OR p_document IS NULL OR jsonb_typeof(p_document) IS DISTINCT FROM 'object'
  OR octet_length(p_document::text)>8192 OR (SELECT count(*) FROM jsonb_object_keys(p_document))<>8
  OR p_document->>'operation_id' IS DISTINCT FROM intent.id::text OR p_document->>'policy_id' IS DISTINCT FROM intent.policy_id
  OR p_document->>'target_id' IS DISTINCT FROM intent.target_id::text OR p_document->>'target_hash' IS DISTINCT FROM intent.target_hash
  OR p_document->'policy_version' IS DISTINCT FROM to_jsonb(policy.version)
  OR p_document->'minimum_days' IS DISTINCT FROM to_jsonb(policy.minimum_days)
  OR jsonb_typeof(p_document->'approval_reference') IS DISTINCT FROM 'string'
  OR coalesce(p_document->>'approval_reference','')!~'^[a-f0-9]{64}$'
  OR p_document->>'intent_created_at' IS DISTINCT FROM to_char(intent.created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='privacy document rejected'; END IF;
 INSERT INTO appointment_system.control_privacy_documents(intent_id,body) VALUES(p_operation,p_document) ON CONFLICT DO NOTHING;
 SELECT body INTO saved FROM appointment_system.control_privacy_documents WHERE intent_id=p_operation;
 IF saved IS DISTINCT FROM p_document THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy document changed'; END IF;
 RETURN saved;
END $_$;

CREATE FUNCTION appointment_system.privacy_required_sequence() RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 RETURN greatest(coalesce((SELECT max(sequence) FROM appointment_system.control_privacy_exports),0),
  coalesce((SELECT max(sequence) FROM appointment_system.control_privacy_replay_progress),0),
  coalesce((SELECT max(base_sequence) FROM appointment_system.control_privacy_intents),0));
END $$;

CREATE FUNCTION appointment_system.privacy_restore_intent(p_document jsonb, p_sequence bigint, p_entry_hash text, p_head_hash text, p_file text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_privacy_intents%ROWTYPE;policy appointment_system.control_privacy_policies%ROWTYPE;operation uuid;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);PERFORM pg_advisory_xact_lock(83125,4);
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_restore_operations r JOIN appointment_system.control_product_state s ON s.singleton
  WHERE r.result_snapshot=appointment_system.control_snapshot() AND NOT s.enabled AND NOT s.requested_enabled)
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='isolated restored generation required'; END IF;
 IF p_document IS NULL OR jsonb_typeof(p_document) IS DISTINCT FROM 'object' OR octet_length(p_document::text)>8192
  OR (SELECT count(*) FROM jsonb_object_keys(p_document))<>8
  OR coalesce(p_document->>'operation_id','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
  OR coalesce(p_document->>'target_id','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
  OR coalesce(p_document->>'target_hash','')!~'^[a-f0-9]{64}$' OR coalesce(p_document->>'approval_reference','')!~'^[a-f0-9]{64}$'
  OR coalesce(p_document->>'intent_created_at','')!~'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
 THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='privacy recovery document rejected'; END IF;
 operation:=(p_document->>'operation_id')::uuid;
 SELECT * INTO policy FROM appointment_system.control_privacy_policies WHERE id=p_document->>'policy_id';
 IF policy.id IS NULL OR p_document->'policy_version' IS DISTINCT FROM to_jsonb(policy.version)
  OR p_document->'minimum_days' IS DISTINCT FROM to_jsonb(policy.minimum_days)
  OR (p_document->>'intent_created_at')::timestamptz>clock_timestamp() OR operation='00000000-0000-0000-0000-000000000000'
 THEN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='privacy recovery policy rejected'; END IF;
 INSERT INTO appointment_system.control_privacy_policy_approvals(policy_id,approved_by)
  VALUES(policy.id,'verified-independent-privacy-ledger') ON CONFLICT DO NOTHING;
 INSERT INTO appointment_system.control_privacy_intents(id,policy_id,target_id,target_hash,base_sequence,created_at)
  VALUES(operation,policy.id,(p_document->>'target_id')::uuid,p_document->>'target_hash',0,(p_document->>'intent_created_at')::timestamptz) ON CONFLICT DO NOTHING;
 SELECT * INTO saved FROM appointment_system.control_privacy_intents WHERE id=operation;
 IF saved.policy_id IS DISTINCT FROM policy.id OR saved.target_id::text IS DISTINCT FROM p_document->>'target_id'
  OR saved.target_hash IS DISTINCT FROM p_document->>'target_hash'
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy recovery intent changed'; END IF;
 PERFORM appointment_system.privacy_freeze(operation,p_document);
 PERFORM appointment_system.control_privacy_attach_export(operation,p_sequence,p_entry_hash,p_head_hash,p_file);
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.privacy_saved_intent(p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE saved jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 SELECT jsonb_build_object('intent',to_jsonb(i),'policy',to_jsonb(p),'approval',to_jsonb(a),'export',to_jsonb(e),'completion',to_jsonb(c),'document',d.body)
 INTO saved FROM appointment_system.control_privacy_intents i JOIN appointment_system.control_privacy_policies p ON p.id=i.policy_id
 JOIN appointment_system.control_privacy_policy_approvals a ON a.policy_id=p.id
 LEFT JOIN appointment_system.control_privacy_exports e ON e.intent_id=i.id
 LEFT JOIN appointment_system.control_privacy_completions c ON c.intent_id=i.id
 LEFT JOIN appointment_system.control_privacy_documents d ON d.intent_id=i.id WHERE i.id=p_operation;
 RETURN saved;
END $$;

CREATE FUNCTION appointment_system.protect_email_snapshot() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF appointment_system.is_email_job(OLD.kind,OLD.recipient_role) AND OLD.message_snapshot IS NOT NULL AND
   ((OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at AND NOT(NEW.first_attempt_at IS NULL AND NOT OLD.prior_send_uncertain AND NOT NEW.send_uncertain AND NEW.last_error_code IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) OR NEW.message_snapshot IS DISTINCT FROM OLD.message_snapshot
    OR NEW.template_version IS DISTINCT FROM OLD.template_version OR NEW.message_hash IS DISTINCT FROM OLD.message_hash OR NEW.destination IS DISTINCT FROM OLD.destination
    OR NEW.booking_id IS DISTINCT FROM OLD.booking_id OR NEW.booking_revision IS DISTINCT FROM OLD.booking_revision
    OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.recipient_role IS DISTINCT FROM OLD.recipient_role
    OR NEW.event_key IS DISTINCT FROM OLD.event_key OR NEW.send_deadline_at IS DISTINCT FROM OLD.send_deadline_at) THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Attempted email identity is immutable';
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.protect_enquiry_delivery() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.request_id IS DISTINCT FROM OLD.request_id
  OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.generation IS DISTINCT FROM OLD.generation
  OR NEW.deadline_at IS DISTINCT FROM OLD.deadline_at OR NEW.created_at IS DISTINCT FROM OLD.created_at
  OR (OLD.provider_id IS NOT NULL AND NEW.provider_id IS DISTINCT FROM OLD.provider_id)
  OR (OLD.message_ciphertext IS NOT NULL AND ((OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at AND NOT(NEW.first_attempt_at IS NULL AND NOT OLD.prior_send_uncertain AND NOT NEW.send_uncertain AND NEW.last_error_code IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited')))
   OR NEW.destination IS DISTINCT FROM OLD.destination OR NEW.message_digest IS DISTINCT FROM OLD.message_digest
   OR NEW.template_version IS DISTINCT FROM OLD.template_version
   OR (NEW.message_ciphertext IS DISTINCT FROM OLD.message_ciphertext AND NEW.message_ciphertext IS NOT NULL))) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Enquiry delivery identity is immutable'; END IF;
 IF NEW.state IN ('accepted','done','suppressed','expired','attention') THEN NEW.message_ciphertext:=NULL; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.protect_enquiry_identity() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE erasing boolean:=false;
BEGIN
 IF NEW.payload IS DISTINCT FROM OLD.payload THEN
  IF current_user='appointment_system_owner'
   AND OLD.verified_at IS NULL AND NEW.payload='{}'::jsonb AND NEW.code_digest IS NULL AND NEW.code_ciphertext IS NULL THEN
   SELECT EXISTS(SELECT 1 FROM appointment_system.control_privacy_intents i
    JOIN appointment_system.control_privacy_policies p ON p.id=i.policy_id
    JOIN appointment_system.control_privacy_policy_approvals a ON a.policy_id=p.id
    JOIN appointment_system.control_privacy_exports e ON e.intent_id=i.id
    JOIN appointment_system.control_privacy_documents d ON d.intent_id=i.id
    WHERE i.target_id=OLD.request_id AND p.kind='abandoned_enquiry') INTO erasing;
  END IF;
 END IF;
 IF NEW.request_id IS DISTINCT FROM OLD.request_id OR NEW.receipt_digest IS DISTINCT FROM OLD.receipt_digest
  OR NEW.email_key IS DISTINCT FROM OLD.email_key OR (NEW.payload IS DISTINCT FROM OLD.payload AND NOT erasing)
  OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR NEW.created_at IS DISTINCT FROM OLD.created_at
  OR NEW.receipt_expires_at IS DISTINCT FROM OLD.receipt_expires_at
  OR (OLD.verified_at IS NOT NULL AND NEW.verified_at IS DISTINCT FROM OLD.verified_at)
  OR NEW.generation<OLD.generation OR NEW.generation>OLD.generation+1
  OR (NEW.generation=OLD.generation AND NEW.code_digest IS NOT NULL AND
    (NEW.code_digest IS DISTINCT FROM OLD.code_digest OR NEW.code_ciphertext IS DISTINCT FROM OLD.code_ciphertext)) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Enquiry identity is immutable';
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.protect_workbook_volume() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.role,NEW.volume_number,NEW.generation,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.created_at,NEW.grant_id)
  IS DISTINCT FROM ROW(OLD.role,OLD.volume_number,OLD.generation,OLD.layout_version,OLD.intent,OLD.subject,OLD.client_id,OLD.created_at,OLD.grant_id)
  OR (OLD.spreadsheet_id IS NOT NULL AND NEW.spreadsheet_id IS DISTINCT FROM OLD.spreadsheet_id)
  OR (OLD.state='retired' AND NEW.state<>'retired')
  OR (OLD.state='ready' AND NEW.state NOT IN ('ready','retired')) THEN
  RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='immutable workbook identity';
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.provision_company_password(p_username text, p_hash text) RETURNS text
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE identifier text; audience text; previous appointment_system.company_credentials%ROWTYPE;
BEGIN
 IF coalesce(p_username,'') !~ '^[a-z0-9][a-z0-9_.-]{2,63}$'
  OR coalesce(p_hash,'') !~ '^\$argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$'
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='invalid company credential'; END IF;
 PERFORM pg_advisory_xact_lock(83124,4);
 SELECT * INTO previous FROM appointment_system.company_credentials WHERE username=p_username FOR UPDATE;
 identifier:=coalesce(previous.subject,'local:'||gen_random_uuid()::text);
 audience:='installation:'||(SELECT installation_id::text FROM appointment_system.installation WHERE singleton);
 IF audience IS NULL THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='installation is not configured'; END IF;
 INSERT INTO appointment_system.control_company_identities(subject,email,audience,capabilities)
 VALUES(identifier,appointment_system.installation_value('owners.agency_email'),audience,
  ARRAY['service_controller','obligation_handler']) ON CONFLICT(subject) DO NOTHING;
 INSERT INTO appointment_system.company_credentials(subject,username,password_hash)
 VALUES(identifier,p_username,p_hash) ON CONFLICT(username) DO UPDATE SET
  password_hash=excluded.password_hash,credential_revision=appointment_system.company_credentials.credential_revision+1,
  changed_at=clock_timestamp(),enabled=true;
 UPDATE appointment_system.control_company_sessions SET revoked_at=clock_timestamp()
 WHERE subject=identifier AND revoked_at IS NULL;
 RETURN identifier;
END $_$;

CREATE FUNCTION appointment_system.provision_login(p_login text, p_purpose text) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE config jsonb; identifier uuid; stage text; existing record;
BEGIN
 IF p_purpose NOT IN ('web','staff','worker','company','backup','maintenance')
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

CREATE FUNCTION appointment_system.public_policy() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_public_policy(); END $$;

CREATE FUNCTION appointment_system.read_operation_incidents(p_session text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_read_operation_incidents(p_session); END $$;

CREATE FUNCTION appointment_system.reconcile_booking_code_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record;j appointment_system.booking_verification_mail%ROWTYPE;e appointment_system.provider_inbox%ROWTYPE;
 provider uuid;occurred timestamptz;fault text;context uuid;challenge uuid;acceptance text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 FOR candidate IN SELECT p.account_id,p.event_id,p.payload,d.id AS job_id,d.context_id,d.challenge_id FROM appointment_system.provider_inbox p
  JOIN appointment_system.booking_verification_mail d ON d.id::text=p.payload->>'job_id'
  WHERE p.provider='resend' AND p.environment='live' AND p.account_id=d.mail_event_account_id
   AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp() ORDER BY p.next_attempt_at,p.received_at,p.event_id LIMIT 20 LOOP
  PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=candidate.context_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  PERFORM 1 FROM appointment_system.booking_verification_challenges WHERE id=candidate.challenge_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.booking_verification_mail WHERE id=candidate.job_id FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO e FROM appointment_system.provider_inbox WHERE provider='resend' AND environment='live' AND account_id=candidate.account_id AND event_id=candidate.event_id
   AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  fault:=NULL;provider:=NULL;occurred:=NULL;
  BEGIN provider:=(e.payload->>'email_id')::uuid;occurred:=(e.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN fault:='email_event_invalid';END;
  IF provider IS NULL OR occurred IS NULL OR NOT isfinite(occurred) OR occurred>clock_timestamp()+interval '5 minutes'
   OR e.payload->>'event' IS NULL OR e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed')
   OR j.first_attempt_at IS NULL OR j.message_digest IS NULL
   OR e.payload->>'binding_version' IS DISTINCT FROM '2'
   OR e.payload->>'mail_format' IS DISTINCT FROM j.mail_format
   OR e.payload->>'recipient_hash' IS DISTINCT FROM encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex')
   OR e.payload->>'message_version' IS DISTINCT FROM j.template_version::text
  THEN fault:='email_event_job_unmatched';END IF;
  IF fault IS NULL THEN
   acceptance:=appointment_system.append_mail_acceptance('verification',j.id,j.message_digest,provider);
   IF acceptance IS DISTINCT FROM 'accepted' THEN fault:='email_event_provider_conflict';END IF;
  END IF;
  IF fault IS NOT NULL THEN
   UPDATE appointment_system.provider_inbox SET attempts=attempts+1,last_error_code=fault,next_attempt_at=clock_timestamp()+interval '1 hour'
    WHERE provider=e.provider AND environment=e.environment AND account_id=e.account_id AND event_id=e.event_id;RETURN false;
  END IF;
  INSERT INTO appointment_system.booking_verification_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
   VALUES(e.event_id,j.id,provider,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE appointment_system.booking_verification_mail SET provider_id=provider,state=CASE WHEN state IN ('suppressed','needs_review') THEN state ELSE 'completed' END
   WHERE id=j.id AND(lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE appointment_system.provider_inbox SET attempts=attempts+1,processed_at=clock_timestamp(),last_error_code=NULL
   WHERE provider=e.provider AND environment=e.environment AND account_id=e.account_id AND event_id=e.event_id;RETURN true;
 END LOOP;RETURN false;
END $$;

CREATE FUNCTION appointment_system.reconcile_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_reconcile_email_event(); END $$;

CREATE FUNCTION appointment_system.reconcile_enquiry_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['worker']); RETURN appointment_system.entry_reconcile_enquiry_email_event(); END $$;

CREATE FUNCTION appointment_system.record_operation_incident(p_reference uuid, p_operation text, p_stage text, p_code text, p_elapsed integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','staff','worker','company']); RETURN appointment_system.entry_record_operation_incident(p_reference, p_operation, p_stage, p_code, p_elapsed); END $$;

CREATE FUNCTION appointment_system.record_order_creation(p_context uuid, p_booking uuid, p_merchant text, p_mode text, p_version text, p_order text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_record_order_creation(p_context, p_booking, p_merchant, p_mode, p_version, p_order); END $$;

CREATE FUNCTION appointment_system.recovery_attention() RETURNS boolean
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE resolved_at IS NULL)
 OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE state IN ('needs_review','needs_review'))
 OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE state IN ('needs_review','needs_review'))
 OR EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail WHERE state='needs_review')
 OR EXISTS(SELECT 1 FROM appointment_system.recovery_due_work WHERE due<statement_timestamp()-interval '5 minutes');
$$;

CREATE FUNCTION appointment_system.redeem_receipt_recovery(p_reference uuid, p_code text, p_receipt text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_redeem_receipt_recovery(p_reference, p_code, p_receipt); END $$;

CREATE FUNCTION appointment_system.reopen_calendar(p_operation uuid, p_claim uuid, p_actor text, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE old appointment_system.staff_calendar_actions%ROWTYPE; claim appointment_system.slot_claims%ROWTYPE;
BEGIN
    IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('staff-calendar-operation:'||p_operation::text,0));
    SELECT * INTO old FROM appointment_system.staff_calendar_actions WHERE operation_id=p_operation;
    IF FOUND THEN
        IF old.action <> 'reopen' OR old.claim_id IS DISTINCT FROM p_claim
           OR old.actor IS DISTINCT FROM p_actor OR old.reason IS DISTINCT FROM p_reason THEN
            RETURN jsonb_build_object('code','request_conflict');
        END IF;
        RETURN jsonb_build_object('code','existing','claim_id',old.claim_id);
    END IF;
    IF coalesce(length(btrim(p_actor)),0) NOT BETWEEN 1 AND 200
       OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 1 AND 500 THEN
        RETURN jsonb_build_object('code','invalid_closure');
    END IF;
    SELECT * INTO claim FROM appointment_system.slot_claims WHERE id=p_claim FOR UPDATE;
    IF NOT FOUND OR claim.booking_id IS NOT NULL THEN RETURN jsonb_build_object('code','closure_not_found'); END IF;
    IF claim.released_at IS NOT NULL THEN RETURN jsonb_build_object('code','already_open'); END IF;
    UPDATE appointment_system.slot_claims SET released_at=clock_timestamp() WHERE id=p_claim;
    INSERT INTO appointment_system.staff_calendar_actions(operation_id,claim_id,action,actor,reason,starts_at,ends_at)
      VALUES(p_operation,p_claim,'reopen',p_actor,p_reason,claim.starts_at,claim.ends_at);
    RETURN jsonb_build_object('code','reopened','claim_id',p_claim);
END
$$;

CREATE FUNCTION appointment_system.require_job_claim(p_kind text, p_id uuid, p_lease uuid, p_attempt integer, p_installation uuid, p_generation uuid, p_release text, p_contract integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE data jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker','web']);
 IF p_kind='booking' THEN SELECT to_jsonb(j) INTO data FROM appointment_system.delivery_jobs j WHERE id=p_id;
 ELSIF p_kind='contact' THEN SELECT to_jsonb(j) INTO data FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_id;
 ELSIF p_kind='booking_code' THEN SELECT to_jsonb(j) INTO data FROM appointment_system.booking_verification_mail j WHERE id=p_id;
 END IF;
 IF data IS NULL OR data->>'state' IS DISTINCT FROM 'processing' OR p_lease IS NULL OR (data->>'lease_token')::uuid IS DISTINCT FROM p_lease
  OR (data->>'lease_expires_at')::timestamptz<=clock_timestamp() OR (data->>'attempts')::integer IS DISTINCT FROM p_attempt
  OR (data->>'claim_installation')::uuid IS DISTINCT FROM p_installation OR (data->>'claim_generation')::uuid IS DISTINCT FROM p_generation
  OR data->>'claim_release' IS DISTINCT FROM p_release OR (data->>'claim_contract')::integer IS DISTINCT FROM p_contract
  OR NOT appointment_system.transport_claim_current(data)
 THEN RAISE EXCEPTION USING ERRCODE='P0489',MESSAGE='job claim changed'; END IF;
END $$;

CREATE FUNCTION appointment_system.require_registered_caller(p_purposes text[]) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
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
  AND EXISTS(SELECT 1 FROM appointment_system.control_restore_operations r JOIN appointment_system.control_product_state s ON s.singleton
   WHERE r.result_snapshot->>'restore_generation'=s.restore_generation::text
    AND NOT EXISTS(SELECT 1 FROM appointment_system.control_restore_completions c WHERE c.restore_generation=s.restore_generation))
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='isolated recovery completion required'; END IF;
END $$;

CREATE FUNCTION appointment_system.require_worker_turn(p_run uuid, p_lane text, p_generation uuid, p_release text, p_lease uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 PERFORM 1 FROM appointment_system.control_product_state WHERE singleton AND restore_generation=p_generation FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='worker generation changed'; END IF;
 PERFORM 1 FROM appointment_system.worker_release WHERE singleton AND release_digest=p_release
  AND active_run=p_run AND active_until>clock_timestamp() FOR SHARE;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM appointment_system.worker_runs WHERE id=p_run AND generation=p_generation
  AND release_digest=p_release AND expires_at>clock_timestamp())
 THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='worker run changed'; END IF;
 PERFORM 1 FROM appointment_system.worker_lane_evaluations WHERE run_id=p_run AND lane=p_lane AND lease_token=p_lease
  AND completed_at IS NULL FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='worker turn changed'; END IF;
END $$;

CREATE FUNCTION appointment_system.resend_booking_verification(p_context uuid, p_operation uuid, p_challenge uuid, p_email text, p_generation integer, p_digest text, p_cipher text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;a appointment_system.booking_verification_actions%ROWTYPE;
 fingerprint text;instant timestamptz:=clock_timestamp();job uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 locked:=appointment_system.lock_booking_verification_context(p_context);IF locked->>'code'<>'ok' THEN RETURN locked; END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','resend','context',p_context,'challenge',p_challenge,'email',p_email,'generation',p_generation));
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_generation IS NULL OR p_generation NOT BETWEEN 1 AND 3
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 OR p_key IS NULL OR p_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'resend' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;RETURN a.result;
 END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=p_challenge AND context_id=p_context AND email=p_email FOR UPDATE;
 IF NOT FOUND OR (locked#>>'{context,verification_id}') IS DISTINCT FROM c.id::text OR c.policy_digest IS DISTINCT FROM locked->>'policy_digest' OR c.generation<>p_generation OR c.verified_at IS NOT NULL
 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF c.generation>=3 OR c.attempts>=5 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF c.last_code_at>instant-interval '60 seconds' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-recipient:'||c.recipient_hash,0));
 IF (SELECT count(*) FROM appointment_system.booking_verification_mail m JOIN appointment_system.booking_verification_challenges x ON x.id=m.challenge_id
  WHERE x.recipient_hash=c.recipient_hash AND m.created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 UPDATE appointment_system.booking_verification_mail SET state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,code_ciphertext=NULL,message_ciphertext=NULL,
  lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_replaced' WHERE challenge_id=c.id;
 UPDATE appointment_system.booking_verification_challenges SET generation=generation+1,attempts=0,code_digest=p_digest,code_ciphertext=p_cipher,digest_key_id=p_key,
  expires_at=instant+interval '5 minutes',last_code_at=instant WHERE id=c.id RETURNING * INTO c;
 INSERT INTO appointment_system.booking_verification_mail(challenge_id,context_id,generation,destination,code_ciphertext) VALUES(c.id,p_context,c.generation,p_email,p_cipher) RETURNING id INTO job;
 result:=jsonb_build_object('code','ok','challenge_id',c.id,'generation',c.generation,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'resend',fingerprint,result);
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.resend_enquiry(p_id uuid, p_receipt text, p_operation uuid, p_generation integer, p_digest text, p_cipher text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_resend_enquiry(p_id, p_receipt, p_operation, p_generation, p_digest, p_cipher); END $$;

CREATE FUNCTION appointment_system.reserve_configured_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text, p_input jsonb, p_expected jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_reserve_configured_checkout(p_context, p_request, p_receipt, p_fingerprint, p_input, p_expected); END $$;

CREATE FUNCTION appointment_system.reserve_delivery_budget(p_class text, p_job uuid) RETURNS text
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE p_booking uuid;p_enquiry uuid;p_code uuid;p_verification boolean;instant timestamptz:=clock_timestamp();day_start timestamptz;budget jsonb;c appointment_system.mail_connection%ROWTYPE;
 daily integer;rolling integer;vd integer;vr integer;dc bigint;rc bigint;vc bigint;vrc bigint;
BEGIN
 IF p_class IS NULL OR p_class NOT IN ('booking_notification','enquiry_notification','enquiry_code','booking_code') OR p_job IS NULL THEN RETURN 'email_budget_invalid'; END IF;
 p_booking:=CASE WHEN p_class='booking_notification' THEN p_job END;
 p_enquiry:=CASE WHEN p_class IN ('enquiry_notification','enquiry_code') THEN p_job END;
 p_code:=CASE WHEN p_class='booking_code' THEN p_job END;
 p_verification:=p_class IN ('enquiry_code','booking_code');
 PERFORM pg_advisory_xact_lock(4004003);
 SELECT * INTO c FROM appointment_system.mail_connection WHERE singleton;
 IF NOT FOUND THEN RETURN 'email_budget_unconfigured'; END IF;
 SELECT p.specification->'email_budget' INTO budget FROM appointment_system.intake_settings s JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton;
 daily:=least((budget->>'daily')::integer,c.daily_allowance);rolling:=least((budget->>'rolling')::integer,c.rolling_allowance);
 vd:=least((budget->>'verification_daily')::integer,daily);vr:=least((budget->>'verification_rolling')::integer,rolling);
 IF daily IS NULL OR rolling IS NULL OR daily<=0 OR rolling<=0 THEN RETURN 'email_budget_unconfigured'; END IF;
 -- A job reserves once. Known rejection does not free a provider quota reservation.
 IF EXISTS(SELECT 1 FROM appointment_system.email_reservations WHERE job_id=p_booking OR enquiry_job_id=p_enquiry OR verification_job_id=p_code) THEN RETURN NULL; END IF;
 day_start:=date_trunc('day',instant AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
 SELECT count(*) FILTER(WHERE reserved_at>=day_start),count(*),count(*) FILTER(WHERE verification AND reserved_at>=day_start),count(*) FILTER(WHERE verification)
 INTO dc,rc,vc,vrc FROM appointment_system.email_reservations WHERE reserved_at>=instant-interval '31 days';
 IF dc>=daily OR rc>=rolling OR (p_verification AND (vc>=vd OR vrc>=vr))
  OR (NOT p_verification AND (dc-vc>=daily-vd OR rc-vrc>=rolling-vr)) THEN RETURN 'email_budget_exhausted'; END IF;
 INSERT INTO appointment_system.email_reservations(job_id,enquiry_job_id,verification_job_id,verification) VALUES(p_booking,p_enquiry,p_code,p_verification);
 RETURN NULL;
END $$;

CREATE FUNCTION appointment_system.reserve_mail_budget(p_booking uuid, p_enquiry uuid, p_verification boolean) RETURNS text
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF (p_booking IS NULL)=(p_enquiry IS NULL) OR p_verification IS NULL OR(p_booking IS NOT NULL AND p_verification) THEN RETURN 'email_budget_invalid'; END IF;
 RETURN appointment_system.reserve_delivery_budget(CASE WHEN p_booking IS NOT NULL THEN 'booking_notification' WHEN p_verification THEN 'enquiry_code' ELSE 'enquiry_notification' END,coalesce(p_booking,p_enquiry));
END $$;

CREATE FUNCTION appointment_system.resource_connection_status(p_authority text, p_parent text, p_signin_client text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 PERFORM appointment_system.resource_parent(p_authority,p_parent,NULL,p_signin_client,'client_sheet',false);
 RETURN (SELECT coalesce(jsonb_agg(jsonb_build_object('resource',r.resource,'connected',g.id IS NOT NULL AND g.revoked_at IS NULL,
  'reconnect_required',coalesce(g.last_error_code='google_reconnect_required' OR g.revoked_at IS NOT NULL OR g.grant_expires_at<=clock_timestamp(),false),
  'spreadsheet_id',CASE WHEN w.subject=g.subject AND w.client_id=g.client_id AND w.state='ready' THEN w.spreadsheet_id ELSE NULL END)
  ORDER BY r.resource),'[]'::jsonb) FROM appointment_system.google_resources r
  LEFT JOIN appointment_system.google_resource_grants g ON g.id=r.grant_id
  LEFT JOIN appointment_system.google_workbooks w ON w.role=CASE WHEN r.resource='agency_sheet' THEN 'agency' WHEN r.resource='client_sheet' THEN 'client' ELSE '' END
  WHERE p_authority='company' OR r.resource IN ('calendar','client_sheet'));
END $$;

CREATE TABLE appointment_system.google_resource_attempts (
    id uuid NOT NULL,
    authority text NOT NULL,
    parent_digest text NOT NULL,
    parent_revision bigint,
    signin_client text NOT NULL,
    resource text NOT NULL,
    resource_revision bigint NOT NULL,
    client_id text NOT NULL,
    owner_email text NOT NULL,
    previous_subject text,
    restore_generation uuid NOT NULL,
    state_digest text NOT NULL,
    browser_digest text NOT NULL,
    encrypted_attempt text NOT NULL,
    grant_id uuid NOT NULL,
    encrypted_grant text,
    subject text,
    scopes jsonb,
    grant_expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '00:10:00'::interval) NOT NULL,
    consumed_at timestamp with time zone,
    finished_at timestamp with time zone,
    result text,
    CONSTRAINT google_resource_attempts_authority_check CHECK ((authority = ANY (ARRAY['company'::text, 'staff'::text]))),
    CONSTRAINT google_resource_attempts_browser_digest_check CHECK ((browser_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT google_resource_attempts_check CHECK ((((authority = 'company'::text) AND (parent_revision IS NOT NULL)) OR ((authority = 'staff'::text) AND (parent_revision IS NULL)))),
    CONSTRAINT google_resource_attempts_encrypted_attempt_check CHECK (((length(encrypted_attempt) >= 100) AND (length(encrypted_attempt) <= 32768))),
    CONSTRAINT google_resource_attempts_parent_digest_check CHECK ((parent_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT google_resource_attempts_result_check CHECK ((result = ANY (ARRAY['pending'::text, 'saved'::text, 'failed'::text, 'changed'::text]))),
    CONSTRAINT google_resource_attempts_state_digest_check CHECK ((state_digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE FUNCTION appointment_system.resource_consent_current(p_attempt appointment_system.google_resource_attempts) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE current_revision bigint;current_generation uuid;resource_revision bigint;
BEGIN
 IF EXISTS(SELECT 1 FROM appointment_system.google_resource_owner_links l WHERE l.attempt_id=p_attempt.id AND (l.expires_at<=clock_timestamp() OR NOT appointment_system.control_repair_obligation(l.reference,CASE WHEN l.resource='agency_sheet' THEN 'agency' ELSE 'client' END,CASE WHEN l.resource='calendar' THEN 'calendar' ELSE 'records' END))) THEN RETURN false; END IF;
 IF p_attempt.expires_at<=clock_timestamp() OR p_attempt.finished_at IS NOT NULL THEN RETURN false; END IF;
 current_revision:=appointment_system.resource_parent(p_attempt.authority,p_attempt.parent_digest,NULL,p_attempt.signin_client,p_attempt.resource,true);
 SELECT restore_generation INTO current_generation FROM appointment_system.control_product_state WHERE singleton;
 SELECT revision INTO resource_revision FROM appointment_system.google_resources WHERE resource=p_attempt.resource FOR UPDATE;
 RETURN current_revision IS NOT DISTINCT FROM p_attempt.parent_revision AND current_generation=p_attempt.restore_generation
  AND resource_revision=p_attempt.resource_revision;
END $$;

CREATE FUNCTION appointment_system.resource_parent(p_authority text, p_parent text, p_csrf text, p_signin_client text, p_resource text, p_fresh boolean) RETURNS bigint
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor jsonb;parent_revision bigint;
BEGIN
 IF p_parent IS NULL OR p_parent!~'^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='resource parent rejected'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('google-resource-parent:'||p_parent,0));
 IF p_authority='company' THEN
  PERFORM appointment_system.require_registered_caller(ARRAY['company']);
  PERFORM appointment_system.control_authorize(p_parent,'service_controller',p_csrf,p_fresh);
  SELECT credential_revision INTO parent_revision FROM appointment_system.control_company_sessions WHERE token_hash=p_parent;
 ELSIF p_authority='staff' AND p_resource IN ('calendar','client_sheet') THEN
  PERFORM appointment_system.require_registered_caller(ARRAY['staff']);
  PERFORM appointment_system.control_admission(NULL);
  actor:=appointment_system.studio_session(p_parent,p_signin_client,appointment_system.installation_value('origin'));
  IF actor IS NULL OR actor->>'role'<>'client' THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='resource parent rejected'; END IF;
 ELSE RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='resource authority denied'; END IF;
 RETURN parent_revision;
END $_$;

CREATE FUNCTION appointment_system.resource_scopes_valid(p_resources text[], p_scopes jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE normalized text[];cal text[]:=ARRAY['https://www.googleapis.com/auth/calendar.events.owned','https://www.googleapis.com/auth/userinfo.email','openid'];
 sheet text[]:=ARRAY['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/userinfo.email','openid'];
 combo text[]:=ARRAY['https://www.googleapis.com/auth/calendar.events.owned','https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/userinfo.email','openid'];
 wide_sheet text[]:=ARRAY['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/userinfo.email','openid'];
 desktop_sheet text[]:=ARRAY['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/spreadsheets'];
 readonly_cal text[]:=ARRAY['https://www.googleapis.com/auth/calendar.calendars.readonly','https://www.googleapis.com/auth/calendar.events.owned','https://www.googleapis.com/auth/userinfo.email','openid'];
BEGIN
 IF jsonb_typeof(p_scopes) IS DISTINCT FROM 'array' OR jsonb_array_length(p_scopes) NOT BETWEEN 1 AND 8
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_scopes) a WHERE jsonb_typeof(a)<>'string') THEN RETURN false; END IF;
 SELECT array_agg(s ORDER BY s) INTO normalized FROM (SELECT CASE WHEN a#>>'{}'='email' THEN 'https://www.googleapis.com/auth/userinfo.email' ELSE a#>>'{}' END s FROM jsonb_array_elements(p_scopes) a)q;
 IF cardinality(normalized)<>(SELECT count(DISTINCT x) FROM unnest(normalized)x) THEN RETURN false; END IF;
 RETURN CASE WHEN p_resources=ARRAY['calendar'] THEN normalized IN (cal,readonly_cal,combo)
  WHEN p_resources=ARRAY['client_sheet'] THEN normalized IN (sheet,wide_sheet,desktop_sheet,combo)
  WHEN p_resources=ARRAY['agency_sheet'] THEN normalized IN (sheet,wide_sheet,desktop_sheet)
  WHEN p_resources=ARRAY['calendar','client_sheet'] THEN normalized=combo ELSE false END;
END $$;

CREATE FUNCTION appointment_system.restore_claim_probe() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE job appointment_system.control_publications%ROWTYPE; product appointment_system.control_product_state%ROWTYPE;
BEGIN
 PERFORM appointment_system.restore_publication_allowed();
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO product FROM appointment_system.control_product_state WHERE singleton FOR SHARE;
 SELECT p.* INTO job FROM appointment_system.control_publications p
 JOIN appointment_system.control_command_progress c USING(operation_id)
 WHERE p.operation_id=product.winning_operation AND p.state='published' AND c.state='published'
 AND p.snapshot=appointment_system.control_snapshot() AND p.next_attempt_at<=clock_timestamp()
 AND (p.lease_until IS NULL OR p.lease_until<=clock_timestamp())
 FOR UPDATE OF p SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE appointment_system.control_publications SET lease_token=gen_random_uuid(),
  lease_until=clock_timestamp()+interval '90 seconds' WHERE operation_id=job.operation_id RETURNING * INTO job;
 RETURN jsonb_build_object('operation_id',job.operation_id,'lease_token',job.lease_token,'snapshot',job.snapshot);
END $$;

CREATE FUNCTION appointment_system.restore_claim_publication() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.restore_publication_allowed();RETURN appointment_system.entry_control_claim_publication();END $$;

CREATE FUNCTION appointment_system.restore_current() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);RETURN appointment_system.control_snapshot();END $$;

CREATE FUNCTION appointment_system.restore_finish_publication(p_operation uuid, p_lease uuid, p_ack jsonb, p_error text DEFAULT NULL::text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.restore_publication_allowed(p_operation);RETURN appointment_system.entry_control_finish_publication(p_operation,p_lease,p_ack,p_error);END $$;

CREATE FUNCTION appointment_system.restore_probe_retry(p_operation uuid, p_lease uuid, p_error text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
BEGIN
 PERFORM appointment_system.restore_publication_allowed(p_operation);
 IF p_error IS NULL OR p_error !~ '^[a-z0-9_]{1,80}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid probe result'; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 UPDATE appointment_system.control_publications SET lease_token=NULL,lease_until=NULL,
  next_attempt_at=clock_timestamp()+interval '15 seconds',last_error=p_error
 WHERE operation_id=p_operation AND lease_token=p_lease AND state='published'
 AND operation_id=(SELECT winning_operation FROM appointment_system.control_product_state WHERE singleton);
 RETURN FOUND;
END $_$;

CREATE FUNCTION appointment_system.restore_publication_allowed(p_operation uuid DEFAULT NULL::uuid) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE operation uuid;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT r.id INTO operation FROM appointment_system.control_restore_operations r JOIN appointment_system.control_product_state s ON s.singleton
  WHERE r.result_snapshot=appointment_system.control_snapshot() AND r.id=s.winning_operation AND NOT s.enabled AND NOT s.requested_enabled
   AND (p_operation IS NULL OR r.id=p_operation);
 IF operation IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='restore publication rejected'; END IF;RETURN operation;
END $$;

CREATE FUNCTION appointment_system.restore_record_probe(p_operation uuid, p_observed jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.restore_publication_allowed(p_operation);RETURN appointment_system.entry_control_record_probe(p_operation,p_observed);END $$;

CREATE FUNCTION appointment_system.restore_saved(p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE saved jsonb;
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['maintenance']);
 SELECT jsonb_build_object('operation_id',id,'external_snapshot',external_snapshot,'snapshot',result_snapshot) INTO saved
 FROM appointment_system.control_restore_operations WHERE id=p_operation;RETURN saved;
END $$;

CREATE FUNCTION appointment_system.schedule_starts(p_spec jsonb, p_duration integer, p_day date, p_now timestamp with time zone, p_deadline timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS TABLE(starts_at timestamp with time zone, ends_at timestamp with time zone, occupied_start timestamp with time zone, occupied_end timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 WITH windows AS (
  SELECT p_day+(w->>'start')::time opening,p_day+(w->>'end')::time closing
  FROM jsonb_array_elements(p_spec->'weekly_windows') w
  WHERE (w->>'weekday')::integer=extract(isodow FROM p_day)::integer-1
 ), local_starts AS (
  SELECT opening+make_interval(mins=>n*(p_spec->>'slot_step_minutes')::integer) local_start,closing
  FROM windows CROSS JOIN LATERAL generate_series(0,
   floor(extract(epoch FROM closing-opening)/60-p_duration)::integer /
    (p_spec->>'slot_step_minutes')::integer) n
  WHERE closing-opening>=make_interval(mins=>p_duration)
 ), converted AS (
  SELECT local_start,closing,local_start AT TIME ZONE(p_spec->>'timezone') utc_start
  FROM local_starts
 ), fits AS (
  SELECT utc_start,utc_start+make_interval(mins=>p_duration) utc_end,local_start,closing FROM converted
 )
 SELECT utc_start,utc_end,utc_start-make_interval(mins=>(p_spec->>'buffer_before_minutes')::integer),
  utc_end+make_interval(mins=>(p_spec->>'buffer_after_minutes')::integer)
 FROM fits
 WHERE p_duration BETWEEN 5 AND 480 AND p_duration%5=0
  AND p_day>=(p_now AT TIME ZONE(p_spec->>'timezone'))::date
  AND (p_deadline IS NOT NULL OR p_day<=(p_now AT TIME ZONE(p_spec->>'timezone'))::date+(p_spec->>'horizon_days')::integer)
  AND utc_start>=p_now+make_interval(mins=>(p_spec->>'notice_minutes')::integer)
  AND (p_deadline IS NULL OR utc_start<=p_deadline)
  AND utc_start AT TIME ZONE(p_spec->>'timezone')=local_start
  AND utc_end AT TIME ZONE(p_spec->>'timezone')=local_start+make_interval(mins=>p_duration)
  AND utc_end AT TIME ZONE(p_spec->>'timezone')<=closing
 ORDER BY utc_start
$$;

CREATE FUNCTION appointment_system.seed_workbook_volume() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,spreadsheet_id,state,grant_id)
 VALUES(NEW.role,NEW.volume_number,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.spreadsheet_id,NEW.state,(SELECT grant_id FROM appointment_system.google_resources WHERE resource=CASE WHEN NEW.role='client' THEN 'client_sheet' ELSE 'agency_sheet' END));
 IF NEW.layout_version=1 AND NEW.state='creating' THEN
  UPDATE appointment_system.google_workbooks SET creation_attempt_at=clock_timestamp() WHERE role=NEW.role;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.service_quote(p_spec jsonb, p_service text, p_questions integer) RETURNS jsonb
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE service jsonb; amount bigint;
BEGIN
 SELECT item INTO service FROM jsonb_array_elements(p_spec->'services') item
 WHERE item->>'id'=p_service AND item->'enabled'='true'::jsonb;
 IF service IS NULL OR p_questions IS NULL OR p_questions<1
  OR p_questions>(service#>>'{pricing,maximum_questions}')::integer
  OR (service#>>'{pricing,kind}'='fixed' AND p_questions<>1) THEN RETURN NULL; END IF;
 amount:=(service#>>'{pricing,amount_paise}')::bigint *
  CASE WHEN service#>>'{pricing,kind}'='per_question' THEN p_questions ELSE 1 END;
 RETURN service||jsonb_build_object('amount_paise',amount,'questions',p_questions,'currency','INR',
  'meeting',p_spec->>'meeting','meeting_platform',CASE WHEN p_spec->>'meeting'='google_meet' THEN 'Google Meet' ELSE 'Arrange directly' END);
END $$;

CREATE FUNCTION appointment_system.settings_digest(p_value jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT encode(sha256(convert_to(appointment_system.canonical_json(p_value),'UTF8')),'hex')
$$;

CREATE FUNCTION appointment_system.staff_actor(p_session text, p_client text, p_origin text) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT appointment_system.staff_actor(p_session,p_client,p_origin,'booking');
$$;

CREATE FUNCTION appointment_system.staff_actor(p_session text, p_client text, p_origin text, p_capability text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE s appointment_system.studio_sessions%ROWTYPE;principal text;
BEGIN
 IF p_capability IS NULL OR p_capability NOT IN ('booking','enquiry') THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_origin=(appointment_system.installation_value('origin')||'/company/booking-support') THEN
  principal:=appointment_system.control_obligation_actor(p_session,p_client,p_origin);
  IF principal IS NULL THEN RETURN NULL; END IF;
  RETURN jsonb_build_object('role','client','actor',principal);
 END IF;
 SELECT * INTO s FROM appointment_system.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
  OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
  OR NOT EXISTS(SELECT 1 FROM appointment_system.studio_identities i WHERE i.role=s.role AND i.subject=s.subject) THEN RETURN NULL; END IF;
 IF s.role<>'client' AND p_capability='enquiry' THEN RETURN NULL; END IF;
 IF s.role='client' AND p_capability='booking' THEN PERFORM appointment_system.control_admission(NULL); END IF;
 RETURN jsonb_build_object('role',s.role,'actor',s.role||':'||encode(sha256(convert_to(s.subject,'UTF8')),'hex'));
END $$;

CREATE FUNCTION appointment_system.staff_items(p_role text) RETURNS TABLE(item_key text, category text, state text, created_at timestamp with time zone, reference text, subject text, reason text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT 'enquiry:'||e.request_id,'enquiry','received',e.verified_at,e.request_id::text,e.payload->>'subject',NULL::text
 FROM appointment_system.enquiries e WHERE p_role='client' AND e.verified_at IS NOT NULL
 UNION ALL
 SELECT 'payment:'||c.id,'payment','needs_review',c.next_check_at,b.request_id::text,b.service_snapshot->>'name',c.reason
 FROM appointment_system.payment_cases c JOIN appointment_system.bookings b ON b.id=c.booking_id
 WHERE p_role='client' AND c.resolved_at IS NULL
 UNION ALL
 SELECT 'delivery:'||j.id,CASE WHEN j.recipient_role='agency_sheet' THEN 'agency_records'
  WHEN j.recipient_role='client_sheet' THEN 'client_records' WHEN j.recipient_role='calendar' THEN 'meeting' ELSE 'booking_email' END,
  CASE WHEN EXISTS(SELECT 1 FROM appointment_system.email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM appointment_system.email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))) THEN 'delivery_problem' ELSE j.state END,
  coalesce(j.first_attempt_at,j.next_attempt_at),CASE WHEN p_role='client' THEN b.request_id::text END,
  CASE WHEN p_role='client' THEN b.service_snapshot->>'name' END,j.last_error_code
 FROM appointment_system.delivery_jobs j JOIN appointment_system.bookings b ON b.id=j.booking_id
 WHERE (j.booking_revision=b.revision OR j.kind IN ('sheet_booking','booking_calendar') OR (j.kind='booking_cancelled' AND j.recipient_role='calendar'))
 AND (p_role='client' OR (p_role='agency' AND j.recipient_role='agency_sheet')) AND
  (j.state IN ('needs_review','retry_wait','delivery_unknown') OR
   (j.state IN ('pending','processing') AND j.next_attempt_at<statement_timestamp()-interval '5 minutes'
    AND (j.lease_expires_at IS NULL OR j.lease_expires_at<statement_timestamp())) OR
   EXISTS(SELECT 1 FROM appointment_system.email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM appointment_system.email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))))
 UNION ALL
 SELECT 'enquiry-delivery:'||j.id,CASE WHEN j.kind='agency_sheet' THEN 'agency_records'
  WHEN j.kind='client_sheet' THEN 'client_records' ELSE 'enquiry_email' END,
  CASE WHEN EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))) THEN 'delivery_problem' ELSE j.state END,
  j.created_at,CASE WHEN p_role='client' THEN j.request_id::text END,NULL::text,j.last_error_code
 FROM appointment_system.enquiry_delivery_jobs j JOIN appointment_system.enquiries e USING(request_id)
 WHERE j.kind<>'verification' AND e.verified_at IS NOT NULL
  AND (p_role='client' OR (p_role='agency' AND j.kind='agency_sheet')) AND
  (j.state IN ('needs_review','retry_wait','delivery_unknown') OR
   (j.state IN ('pending','processing') AND j.next_attempt_at<statement_timestamp()-interval '5 minutes'
    AND (j.lease_expires_at IS NULL OR j.lease_expires_at<statement_timestamp())) OR
   EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))))
$$;

CREATE FUNCTION appointment_system.staff_signin_consume(p_state text, p_browser text, p_purpose text, p_client text, p_origin text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_attempts%ROWTYPE;result jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['staff']);
 IF p_purpose IS DISTINCT FROM 'signin' OR p_origin IS DISTINCT FROM appointment_system.installation_value('origin') THEN RETURN NULL; END IF;
 SELECT * INTO a FROM appointment_system.google_attempts WHERE state_digest=p_state FOR UPDATE;
 IF NOT FOUND OR a.role<>'client' OR a.purpose<>'signin' THEN RETURN NULL; END IF;
 IF a.portal='booking' THEN
  IF NOT coalesce((SELECT enabled FROM appointment_system.control_product_state WHERE singleton),false) THEN RETURN NULL; END IF;
  PERFORM appointment_system.control_admission(NULL);
 END IF;
 result:=appointment_system.entry_consume_google_attempt(p_state,p_browser,p_purpose,p_client,p_origin);
 IF result IS NULL THEN RETURN NULL; END IF;
 RETURN result||jsonb_build_object('portal',a.portal);
END $$;

CREATE FUNCTION appointment_system.staff_signin_finish(p_state text, p_subject text, p_session text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE a appointment_system.google_attempts%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['staff']);
 SELECT * INTO a FROM appointment_system.google_attempts WHERE state_digest=p_state;
 IF NOT FOUND OR a.role<>'client' OR a.purpose<>'signin' OR p_session IS NULL OR p_session!~'^[a-f0-9]{64}$' THEN RETURN false; END IF;
 IF a.portal='booking' THEN
  IF NOT coalesce((SELECT enabled FROM appointment_system.control_product_state WHERE singleton),false) THEN RETURN false; END IF;
  PERFORM appointment_system.control_admission(NULL);
 END IF;
 RETURN appointment_system.entry_finish_google_signin(p_state,p_subject,p_session);
END $_$;

CREATE FUNCTION appointment_system.staff_signin_start(p_state text, p_browser text, p_purpose text, p_role text, p_encrypted text, p_session text, p_client text, p_origin text, p_portal text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['staff']);
 IF p_purpose IS DISTINCT FROM 'signin' OR p_role IS DISTINCT FROM 'client' OR p_session IS NOT NULL
  OR p_portal IS NULL OR p_portal NOT IN ('booking','enquiry') OR p_origin IS DISTINCT FROM appointment_system.installation_value('origin')
  OR p_state IS NULL OR p_state!~'^[a-f0-9]{64}$' OR p_browser IS NULL OR p_browser!~'^[a-f0-9]{64}$'
  OR p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 128 AND 8192
  OR p_client IS NULL OR length(p_client) NOT BETWEEN 20 AND 250 THEN RETURN false; END IF;
 IF p_portal='booking' THEN PERFORM appointment_system.control_admission(NULL); END IF;
 IF NOT appointment_system.entry_start_google_attempt(p_state,p_browser,p_purpose,p_role,p_encrypted,p_session,p_client,p_origin) THEN RETURN false; END IF;
 UPDATE appointment_system.google_attempts SET portal=p_portal WHERE state_digest=p_state;
 RETURN true;
END $_$;

CREATE FUNCTION appointment_system.stage_resource_consent(p_authority text, p_id uuid, p_state text, p_subject text, p_email text, p_encrypted text, p_scopes jsonb, p_expires timestamp with time zone) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a appointment_system.google_resource_attempts%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE id=p_id AND authority=p_authority AND state_digest=p_state;
 IF NOT FOUND OR a.consumed_at IS NULL OR a.result IS NOT NULL OR NOT appointment_system.resource_consent_current(a) THEN RETURN false; END IF;
 SELECT * INTO a FROM appointment_system.google_resource_attempts WHERE id=p_id AND result IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 IF p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768 OR p_email IS DISTINCT FROM a.owner_email
  OR p_subject IS NULL OR length(p_subject) NOT BETWEEN 1 AND 255 OR p_subject~'[[:cntrl:]]'
  OR a.previous_subject IS NOT NULL AND p_subject<>a.previous_subject
  OR NOT coalesce(appointment_system.resource_scopes_valid(ARRAY[a.resource],p_scopes),false)
  OR (p_expires IS NOT NULL AND (NOT isfinite(p_expires) OR p_expires<=clock_timestamp()))
 THEN UPDATE appointment_system.google_resource_attempts SET result='failed',finished_at=clock_timestamp() WHERE id=p_id;
  RETURN false; END IF;
 UPDATE appointment_system.google_resource_attempts SET encrypted_grant=p_encrypted,subject=p_subject,scopes=p_scopes,
  grant_expires_at=p_expires,result='pending' WHERE id=p_id;
 RETURN true;
END $$;

CREATE FUNCTION appointment_system.stamp_transport_claim() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE facts appointment_system.installation%ROWTYPE; generation uuid; release text;
BEGIN
 IF NEW.state='processing' AND NEW.lease_token IS NOT NULL
  AND (TG_OP='INSERT' OR OLD.state IS DISTINCT FROM 'processing' OR NEW.lease_token IS DISTINCT FROM OLD.lease_token) THEN
  SELECT * INTO STRICT facts FROM appointment_system.installation WHERE singleton;
  SELECT restore_generation INTO STRICT generation FROM appointment_system.control_product_state WHERE singleton;
  SELECT release_digest INTO release FROM appointment_system.worker_release WHERE singleton;
  IF release IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='installed writer release required'; END IF;
  NEW.claim_installation:=facts.installation_id;NEW.claim_generation:=generation;
  NEW.claim_release:=release;NEW.claim_contract:=facts.writer_contract;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION appointment_system.start_booking_verification(p_context uuid, p_operation uuid, p_email text, p_digest text, p_cipher text, p_recipient text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;ctx jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;
 a appointment_system.booking_verification_actions%ROWTYPE;fingerprint text;instant timestamptz:=clock_timestamp();job uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 locked:=appointment_system.lock_booking_verification_context(p_context);
 IF locked->>'code'<>'ok' THEN RETURN locked; END IF;ctx:=locked->'context';
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_email IS NULL OR length(p_email) NOT BETWEEN 3 AND 254
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_recipient IS NULL OR p_recipient !~ '^[a-f0-9]{64}$'
  OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 OR p_key IS NULL OR p_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','start','context',p_context,'email',p_email));
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'start' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN a.result;
 END IF;
 IF ctx->>'unresolved_booking_id' IS NOT NULL THEN RETURN jsonb_build_object('code','request_unresolved'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-recipient:'||p_recipient,0));
 IF (SELECT count(*) FROM appointment_system.booking_verification_mail m JOIN appointment_system.booking_verification_challenges x ON x.id=m.challenge_id
   WHERE x.recipient_hash=p_recipient AND m.created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=(ctx->>'verification_id')::uuid FOR UPDATE;
 IF FOUND AND c.verified_at IS NULL AND c.email=p_email AND c.policy_digest=locked->>'policy_digest' AND c.expires_at>instant AND c.attempts<5 THEN
  SELECT id INTO job FROM appointment_system.booking_verification_mail WHERE challenge_id=c.id AND generation=c.generation;
  result:=jsonb_build_object('code','ok','challenge_id',c.id,'generation',c.generation,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 ELSE
  UPDATE appointment_system.booking_verification_grants SET revoked_at=instant WHERE context_id=p_context AND consumed_request IS NULL AND revoked_at IS NULL;
  IF c.id IS NOT NULL THEN
   UPDATE appointment_system.booking_verification_mail SET state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,code_ciphertext=NULL,message_ciphertext=NULL,
    lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_replaced' WHERE challenge_id=c.id;
   UPDATE appointment_system.booking_verification_challenges SET code_ciphertext=NULL WHERE id=c.id;
  END IF;
  INSERT INTO appointment_system.booking_verification_challenges(id,context_id,email,recipient_hash,policy_digest,activation_epoch,code_digest,code_ciphertext,digest_key_id,expires_at)
   VALUES(p_operation,p_context,p_email,p_recipient,locked->>'policy_digest',(ctx->>'activation_epoch')::uuid,p_digest,p_cipher,p_key,instant+interval '5 minutes') RETURNING * INTO c;
  INSERT INTO appointment_system.booking_verification_mail(challenge_id,context_id,generation,destination,code_ciphertext)
   VALUES(c.id,p_context,1,p_email,p_cipher) RETURNING id INTO job;
  UPDATE appointment_system.checkout_contexts SET verification_id=c.id WHERE id=p_context;
  result:=jsonb_build_object('code','ok','challenge_id',c.id,'generation',1,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 END IF;
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'start',fingerprint,result);
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.start_enquiry(p_id uuid, p_receipt text, p_fingerprint text, p_payload jsonb, p_digest text, p_cipher text, p_email_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_start_enquiry(p_id, p_receipt, p_fingerprint, p_payload, p_digest, p_cipher, p_email_key); END $$;

CREATE FUNCTION appointment_system.start_order_creation(p_context uuid, p_booking uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web','worker']); RETURN appointment_system.entry_start_order_creation(p_context, p_booking); END $$;

CREATE FUNCTION appointment_system.start_owner_resource_consent(p_link uuid, p_access text, p_id uuid, p_state text, p_browser text, p_attempt text, p_grant uuid, p_client text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE context jsonb;link appointment_system.google_resource_owner_links%ROWTYPE;saved jsonb;
BEGIN
 context:=appointment_system.owner_resource_link_context(p_link,p_access);
 IF context IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO link FROM appointment_system.google_resource_owner_links WHERE id=p_link AND attempt_id IS NULL FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 saved:=appointment_system.start_resource_consent('company',link.parent_digest,NULL,'',p_id,link.resource,p_state,p_browser,p_attempt,p_grant,p_client);
 IF saved IS NULL THEN RETURN NULL; END IF;
 UPDATE appointment_system.google_resource_owner_links SET attempt_id=p_id WHERE id=p_link;
 RETURN saved;
END $$;

CREATE FUNCTION appointment_system.start_resource_consent(p_authority text, p_parent text, p_csrf text, p_signin_client text, p_id uuid, p_resource text, p_state text, p_browser text, p_attempt text, p_grant uuid, p_client text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE current_revision bigint;g appointment_system.google_resources%ROWTYPE;generation uuid;previous_subject text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 current_revision:=appointment_system.resource_parent(p_authority,p_parent,p_csrf,p_signin_client,p_resource,true);
 IF p_id IS NULL OR p_id='00000000-0000-0000-0000-000000000000' OR p_grant IS NULL OR p_grant='00000000-0000-0000-0000-000000000000'
  OR p_state IS NULL OR p_state!~'^[a-f0-9]{64}$' OR p_browser IS NULL OR p_browser!~'^[a-f0-9]{64}$'
  OR p_attempt IS NULL OR length(p_attempt) NOT BETWEEN 100 AND 32768 THEN RETURN NULL; END IF;
 SELECT * INTO g FROM appointment_system.google_resources WHERE resource=p_resource AND active_client=p_client FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF (SELECT count(*) FROM appointment_system.google_resource_attempts WHERE authority=p_authority AND parent_digest=p_parent
  AND created_at>clock_timestamp()-interval '1 hour')>=5 THEN RAISE EXCEPTION USING ERRCODE='P0429',MESSAGE='resource consent limit'; END IF;
 SELECT restore_generation INTO generation FROM appointment_system.control_product_state WHERE singleton;
 SELECT subject INTO previous_subject FROM appointment_system.google_resource_grants WHERE id=g.grant_id;
 INSERT INTO appointment_system.google_resource_attempts(id,authority,parent_digest,parent_revision,signin_client,resource,
  resource_revision,client_id,owner_email,previous_subject,restore_generation,state_digest,browser_digest,encrypted_attempt,grant_id)
 VALUES(p_id,p_authority,p_parent,current_revision,p_signin_client,p_resource,g.revision,p_client,g.owner_email,previous_subject,generation,p_state,p_browser,p_attempt,p_grant);
 RETURN jsonb_build_object('id',p_id,'owner_email',g.owner_email,'client_id',p_client,'resource',p_resource,'expires_at',clock_timestamp()+interval '10 minutes');
END $_$;

CREATE FUNCTION appointment_system.studio_action_result(p_session text, p_client text, p_origin text, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_action_result(p_session, p_client, p_origin, p_operation); END $$;

CREATE FUNCTION appointment_system.studio_appointment_cancel(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_appointment_cancel(p_session, p_client, p_origin, p_operation, p_claim, p_revision, p_reason); END $$;

CREATE FUNCTION appointment_system.studio_appointment_detail(p_session text, p_client text, p_origin text, p_claim uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_appointment_detail(p_session, p_client, p_origin, p_claim); END $$;

CREATE FUNCTION appointment_system.studio_appointment_reschedule(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text, p_start timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_appointment_reschedule(p_session, p_client, p_origin, p_operation, p_claim, p_revision, p_reason, p_start); END $$;

CREATE FUNCTION appointment_system.studio_booking_lookup(p_session text, p_client text, p_origin text, p_reference uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_booking_lookup(p_session, p_client, p_origin, p_reference); END $$;

CREATE FUNCTION appointment_system.studio_calendar_actor(p_session text, p_client text, p_origin text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE s appointment_system.studio_sessions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_origin=(appointment_system.installation_value('origin')||'/company/booking-support') THEN
  RETURN appointment_system.control_obligation_actor(p_session,p_client,p_origin);
 END IF;
 PERFORM appointment_system.control_admission(NULL);
 SELECT * INTO s FROM appointment_system.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.role<>'client' OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
  OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
  OR NOT EXISTS(SELECT 1 FROM appointment_system.studio_identities i WHERE i.role=s.role AND i.subject=s.subject) THEN RETURN NULL; END IF;
 RETURN 'client:'||encode(sha256(convert_to(s.subject,'UTF8')),'hex');
END $$;

CREATE FUNCTION appointment_system.studio_calendar_close(p_session text, p_client text, p_origin text, p_operation uuid, p_reason text, p_start timestamp with time zone, p_end timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_calendar_close(p_session, p_client, p_origin, p_operation, p_reason, p_start, p_end); END $$;

CREATE FUNCTION appointment_system.studio_calendar_list(p_session text, p_client text, p_origin text, p_day date, p_after uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_calendar_list(p_session, p_client, p_origin, p_day, p_after); END $$;

CREATE FUNCTION appointment_system.studio_calendar_month(p_session text, p_client text, p_origin text, p_month date) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE zone text; first_day date;last_day date;actor text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']);
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 zone:=appointment_system.current_business()->>'timezone';
 IF p_month IS NULL OR NOT isfinite(p_month) OR p_month<(clock_timestamp() AT TIME ZONE zone)::date-interval '2 months'
 OR p_month>(clock_timestamp() AT TIME ZONE zone)::date+interval '13 months' THEN RETURN jsonb_build_object('code','invalid_calendar_date'); END IF;
 first_day:=date_trunc('month',p_month)::date;last_day:=(first_day+interval '1 month')::date;
 RETURN jsonb_build_object('code','ok','month',first_day,'timezone',zone,'days',coalesce((
  SELECT jsonb_agg(jsonb_build_object('date',day,'appointments',appointments,'closures',closures) ORDER BY day)
  FROM (SELECT day::date AS day,
   (SELECT count(*) FROM appointment_system.bookings b JOIN appointment_system.slot_claims c ON c.booking_id=b.id
    WHERE c.released_at IS NULL AND b.state='confirmed' AND b.starts_at>=day::timestamp AT TIME ZONE zone
    AND b.starts_at<(day+interval '1 day')::timestamp AT TIME ZONE zone) AS appointments,
   (SELECT count(*) FROM appointment_system.slot_claims c WHERE c.booking_id IS NULL AND c.released_at IS NULL
    AND c.starts_at<(day+interval '1 day')::timestamp AT TIME ZONE zone AND c.ends_at>day::timestamp AT TIME ZONE zone) AS closures
   FROM generate_series(first_day,last_day-1,interval '1 day') days(day)) totals),'[]'::jsonb));
END $$;

CREATE FUNCTION appointment_system.studio_calendar_reopen(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_calendar_reopen(p_session, p_client, p_origin, p_operation, p_claim, p_reason); END $$;

CREATE FUNCTION appointment_system.studio_inbox_detail(p_session text, p_client text, p_origin text, p_item text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_detail(p_session, p_client, p_origin, p_item); END $$;

CREATE FUNCTION appointment_system.studio_inbox_detail_before_resources(p_session text, p_client text, p_origin text, p_item text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE a jsonb;item record;result jsonb;
BEGIN
 a:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_item LIKE 'enquiry:%' OR p_item LIKE 'enquiry-delivery:%' THEN 'enquiry' ELSE 'booking' END);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO item FROM appointment_system.staff_items(a->>'role') WHERE item_key=p_item;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','item_unavailable'); END IF;
 result:=to_jsonb(item)||jsonb_build_object('review_revision',coalesce((SELECT max(revision) FROM appointment_system.staff_reviews WHERE item_key=p_item),0),
  'reviews',coalesce((SELECT jsonb_agg(x ORDER BY x.revision DESC) FROM
    (SELECT revision,split_part(actor,':',1) role,note,created_at FROM appointment_system.staff_reviews WHERE item_key=p_item ORDER BY revision DESC LIMIT 20) x),'[]'::jsonb));
 IF item.category='enquiry' THEN
  result:=result||jsonb_build_object('enquiry',(SELECT payload FROM appointment_system.enquiries WHERE request_id=item.reference::uuid AND verified_at IS NOT NULL));
 END IF;
 RETURN jsonb_build_object('code','ok','item',result);
END $$;

CREATE FUNCTION appointment_system.studio_inbox_list(p_session text, p_client text, p_origin text, p_view text, p_after text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_list(p_session, p_client, p_origin, p_view, p_after); END $$;

CREATE FUNCTION appointment_system.studio_inbox_refund_verified(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_refund_verified(p_session, p_client, p_origin, p_operation, p_item, p_revision, p_note); END $$;

CREATE FUNCTION appointment_system.studio_inbox_resource_reviewed(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_resource_reviewed(p_session, p_client, p_origin, p_operation, p_item, p_revision, p_note); END $$;

CREATE FUNCTION appointment_system.studio_inbox_retry(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_retry(p_session, p_client, p_origin, p_operation, p_item, p_revision, p_note); END $$;

CREATE FUNCTION appointment_system.studio_inbox_review(p_session text, p_client text, p_origin text, p_operation uuid, p_item text, p_revision integer, p_note text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_inbox_review(p_session, p_client, p_origin, p_operation, p_item, p_revision, p_note); END $$;

CREATE FUNCTION appointment_system.studio_logout(p_digest text, p_client text, p_origin text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_logout(p_digest, p_client, p_origin); END $$;

CREATE FUNCTION appointment_system.studio_session(p_digest text, p_client text, p_origin text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_session(p_digest, p_client, p_origin); END $$;

CREATE FUNCTION appointment_system.studio_support_change(p_session text, p_client text, p_origin text, p_operation uuid, p_reference uuid, p_revision integer, p_action text, p_reason text, p_payment text, p_email text, p_phone text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']); RETURN appointment_system.entry_studio_support_change(p_session, p_client, p_origin, p_operation, p_reference, p_revision, p_action, p_reason, p_payment, p_email, p_phone, p_digest); END $$;

CREATE FUNCTION appointment_system.transport_claim_current(p_job jsonb) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.installation i JOIN appointment_system.control_product_state s ON s.singleton
  JOIN appointment_system.worker_release r ON r.singleton WHERE i.singleton
  AND p_job->>'claim_installation'=i.installation_id::text AND p_job->>'claim_generation'=s.restore_generation::text
  AND p_job->>'claim_release'=r.release_digest AND p_job->>'claim_contract'=i.writer_contract::text);
$$;

CREATE FUNCTION appointment_system.transport_job_resolved(p_kind text, p_job uuid, p_lock boolean DEFAULT false) RETURNS boolean
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE document jsonb;
BEGIN
 IF p_kind='booking' THEN
  IF p_lock THEN PERFORM 1 FROM appointment_system.delivery_jobs WHERE id=p_job FOR SHARE; END IF;
  SELECT to_jsonb(j) INTO document FROM appointment_system.delivery_jobs j WHERE id=p_job;
 ELSIF p_kind='contact' THEN
  IF p_lock THEN PERFORM 1 FROM appointment_system.enquiry_delivery_jobs WHERE id=p_job FOR SHARE; END IF;
  SELECT to_jsonb(j) INTO document FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_job;
 ELSIF p_kind='booking_code' THEN
  IF p_lock THEN PERFORM 1 FROM appointment_system.booking_verification_mail WHERE id=p_job FOR SHARE; END IF;
  SELECT to_jsonb(j) INTO document FROM appointment_system.booking_verification_mail j WHERE id=p_job;
 ELSE RETURN false;
 END IF;
 RETURN document IS NULL OR (document->>'state' IN('completed','suppressed','failed')
  AND (document->>'lease_token') IS NULL AND NOT coalesce((document->>'send_uncertain')::boolean,false)
  AND NOT coalesce((document->>'prior_send_uncertain')::boolean,false));
END $$;

CREATE FUNCTION appointment_system.valid_mail_binding(p_binding jsonb, p_saved jsonb) RETURNS boolean
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE c appointment_system.mail_connection%ROWTYPE;
BEGIN
 SELECT * INTO c FROM appointment_system.mail_connection WHERE singleton;
 IF NOT FOUND OR NOT appointment_system.exact_keys(p_binding,ARRAY['account_id','event_account_id','credential_version','format','idempotency_key'])
  OR EXISTS(SELECT 1 FROM jsonb_each(p_binding) a WHERE jsonb_typeof(a.value)<>'string')
  OR p_binding->>'account_id' IS DISTINCT FROM c.account_id
  OR NOT coalesce(p_binding->>'credential_version'=ANY(c.retained_keys),false)
  OR p_binding->>'format' NOT IN ('resend-v1','resend-legacy-job-v1','resend-legacy-verification-v1')
  OR length(p_binding->>'idempotency_key') NOT BETWEEN 1 AND 256 OR p_binding->>'idempotency_key' ~ '[^!-~]'
 THEN RETURN false; END IF;
 IF p_saved->>'mail_account_id' IS NOT NULL THEN
  RETURN p_binding=jsonb_build_object('account_id',p_saved->>'mail_account_id','event_account_id',p_saved->>'mail_event_account_id','credential_version',p_saved->>'mail_credential_version',
   'format',p_saved->>'mail_format','idempotency_key',p_saved->>'mail_idempotency_key');
 END IF;
 RETURN p_saved->>'first_attempt_at' IS NULL AND p_saved->>'mail_format'='resend-v1'
  AND p_binding->>'event_account_id'=c.account_id AND p_binding->>'format'='resend-v1' AND p_binding->>'credential_version'=c.active_key_id
  AND p_binding->>'idempotency_key'='abs/'||appointment_system.installation_value('installation_id')||'/'||(p_saved->>'id')||'/v'||(p_saved->>'template_version');
END $$;

CREATE FUNCTION appointment_system.validate_business(p_spec jsonb) RETURNS boolean
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE item jsonb; other jsonb; windows jsonb; ids text[]:=ARRAY[]::text[];
 quantity integer; opening time; closing time;
BEGIN
 IF octet_length(p_spec::text)>131072 OR NOT appointment_system.exact_keys(p_spec,ARRAY[
  'version','timezone','services','weekly_windows','slot_step_minutes','notice_minutes',
  'horizon_days','buffer_before_minutes','buffer_after_minutes','booking_verification',
  'required_contacts','meeting','email_budget']) THEN RETURN false; END IF;
 IF p_spec->'version' IS DISTINCT FROM '1'::jsonb
  OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=p_spec->>'timezone')
  OR NOT appointment_system.bounded_integer(p_spec->'slot_step_minutes',5,120)
  OR (p_spec->>'slot_step_minutes')::integer%5<>0
  OR NOT appointment_system.bounded_integer(p_spec->'notice_minutes',0,10080)
  OR NOT appointment_system.bounded_integer(p_spec->'horizon_days',1,365)
  OR NOT appointment_system.bounded_integer(p_spec->'buffer_before_minutes',0,120)
  OR NOT appointment_system.bounded_integer(p_spec->'buffer_after_minutes',0,120)
  OR jsonb_typeof(p_spec->'meeting') IS DISTINCT FROM 'string'
  OR p_spec->>'meeting' NOT IN ('internal','google_meet')
  OR NOT appointment_system.exact_keys(p_spec->'booking_verification',ARRAY['email','sms'])
  OR jsonb_typeof(p_spec#>'{booking_verification,email}') IS DISTINCT FROM 'boolean'
  OR p_spec#>'{booking_verification,sms}' IS DISTINCT FROM 'false'::jsonb
  OR p_spec->'required_contacts' NOT IN ('["email"]'::jsonb,'["email","phone"]'::jsonb,'["phone","email"]'::jsonb)
  OR jsonb_typeof(p_spec->'services') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'services') NOT BETWEEN 1 AND 100
  OR jsonb_typeof(p_spec->'weekly_windows') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'weekly_windows') NOT BETWEEN 1 AND 28
 THEN RETURN false; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_spec->'services') LOOP
  IF NOT appointment_system.exact_keys(item,ARRAY['id','name','enabled','duration_minutes','pricing','required_preparation'])
   OR jsonb_typeof(item->'id') IS DISTINCT FROM 'string'
   OR jsonb_typeof(item->'name') IS DISTINCT FROM 'string'
   OR coalesce(item->>'id','') !~ '^[a-z0-9][a-z0-9-]{0,79}$'
   OR item->>'id'=ANY(ids)
   OR coalesce(length(btrim(item->>'name')),0) NOT BETWEEN 1 AND 150
   OR item->>'name' ~ '[[:cntrl:]]'
   OR jsonb_typeof(item->'enabled') IS DISTINCT FROM 'boolean'
   OR NOT appointment_system.bounded_integer(item->'duration_minutes',5,480)
   OR (item->>'duration_minutes')::integer%5<>0
   OR NOT appointment_system.exact_keys(item->'pricing',ARRAY['kind','amount_paise','maximum_questions'])
   OR coalesce(item#>>'{pricing,kind}','') NOT IN ('fixed','per_question')
   OR NOT appointment_system.bounded_integer(item#>'{pricing,amount_paise}',1,2147483647)
   OR NOT appointment_system.bounded_integer(item#>'{pricing,maximum_questions}',1,10)
   OR ((item#>>'{pricing,amount_paise}')::bigint*(item#>>'{pricing,maximum_questions}')::bigint)>2147483647
   OR (item#>>'{pricing,kind}'='fixed' AND item#>'{pricing,maximum_questions}'<>'1'::jsonb)
   OR jsonb_typeof(item->'required_preparation') IS DISTINCT FROM 'array'
  THEN RETURN false; END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(item->'required_preparation') a
   WHERE jsonb_typeof(a) IS DISTINCT FROM 'string'
    OR a#>>'{}' NOT IN ('birth_date','birth_time','birth_place','notes'))
   OR (SELECT count(*) FROM jsonb_array_elements(item->'required_preparation')) <>
      (SELECT count(DISTINCT a) FROM jsonb_array_elements(item->'required_preparation') a)
  THEN RETURN false; END IF;
  ids:=array_append(ids,item->>'id');
 END LOOP;
 FOR item IN SELECT value FROM jsonb_array_elements(p_spec->'weekly_windows') LOOP
  IF NOT appointment_system.exact_keys(item,ARRAY['weekday','start','end'])
   OR NOT appointment_system.bounded_integer(item->'weekday',0,6)
   OR coalesce(item->>'start','') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
   OR coalesce(item->>'end','') !~ '^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$'
  THEN RETURN false; END IF;
  opening:=(item->>'start')::time; closing:=(item->>'end')::time;
  IF opening>=closing THEN RETURN false; END IF;
  FOR other IN SELECT value FROM jsonb_array_elements(p_spec->'weekly_windows') LOOP
   IF item<>other AND item->'weekday'=other->'weekday'
    AND (other->>'start') ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
    AND (other->>'end') ~ '^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$'
    AND opening<(other->>'end')::time AND (other->>'start')::time<closing
   THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 IF (SELECT count(*) FROM jsonb_array_elements(p_spec->'weekly_windows')) <>
    (SELECT count(DISTINCT w) FROM jsonb_array_elements(p_spec->'weekly_windows') w)
 THEN RETURN false; END IF;
 IF NOT appointment_system.exact_keys(p_spec->'email_budget',
  ARRAY['daily','rolling','verification_daily','verification_rolling'])
 THEN RETURN false; END IF;
 FOR item IN SELECT value FROM jsonb_each(p_spec->'email_budget') LOOP
  IF NOT appointment_system.bounded_integer(item,0,100000) THEN RETURN false; END IF;
 END LOOP;
 IF (p_spec#>>'{email_budget,daily}')::integer>(p_spec#>>'{email_budget,rolling}')::integer
  OR (p_spec#>>'{email_budget,verification_daily}')::integer>(p_spec#>>'{email_budget,daily}')::integer
  OR (p_spec#>>'{email_budget,verification_rolling}')::integer>(p_spec#>>'{email_budget,rolling}')::integer
  OR (p_spec#>>'{email_budget,verification_daily}')::integer>(p_spec#>>'{email_budget,verification_rolling}')::integer
 THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END $_$;

CREATE FUNCTION appointment_system.validate_caller(p_installation uuid, p_environment text, p_purpose text, p_contract integer) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.caller_logins c JOIN appointment_system.installation i ON i.singleton
  JOIN pg_roles r ON r.rolname=c.login_role
  WHERE c.login_role=session_user AND c.enabled AND c.purpose=p_purpose AND c.environment=p_environment
   AND c.installation_id=p_installation AND i.installation_id=p_installation AND i.environment=p_environment
   AND c.writer_contract=p_contract AND i.writer_contract=p_contract AND r.rolcanlogin AND NOT r.rolsuper
   AND NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolbypassrls
   AND i.specification#>>ARRAY['database_targets',c.purpose,'role']=session_user
   AND i.specification#>>ARRAY['database_targets',c.purpose,'database']=current_database()
   AND pg_has_role(session_user,'appointment_system_'||c.purpose||'_access','MEMBER')
   AND NOT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles other ON other.oid=m.roleid
    WHERE m.member=r.oid AND other.rolname<>'appointment_system_'||c.purpose||'_access'));
$$;

CREATE FUNCTION appointment_system.verification_policy(p_spec jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT appointment_system.settings_digest(jsonb_build_object('purpose','booking',
  'verification',p_spec->'booking_verification','required_contacts',p_spec->'required_contacts'))
$$;

CREATE FUNCTION appointment_system.verify_booking_code(p_context uuid, p_operation uuid, p_challenge uuid, p_email text, p_generation integer, p_digest text, p_grant text, p_cipher text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;a appointment_system.booking_verification_actions%ROWTYPE;
 fingerprint text;instant timestamptz:=clock_timestamp();expiry timestamptz;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);locked:=appointment_system.lock_booking_verification_context(p_context);
 IF locked->>'code'<>'ok' THEN RETURN locked; END IF;
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_generation IS NULL OR p_generation NOT BETWEEN 1 AND 3
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_grant IS NULL OR p_grant !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','verify','context',p_context,'challenge',p_challenge,'email',p_email,'generation',p_generation,'code_digest',p_digest));
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'verify' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;RETURN a.result;
 END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=p_challenge AND context_id=p_context AND email=p_email FOR UPDATE;
 IF NOT FOUND OR c.id::text IS DISTINCT FROM locked#>>'{context,verification_id}' OR c.policy_digest IS DISTINCT FROM locked->>'policy_digest' OR c.generation<>p_generation OR c.verified_at IS NOT NULL
 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF c.expires_at<=instant THEN result:=jsonb_build_object('code','verification_expired');
 ELSIF c.attempts>=5 THEN result:=jsonb_build_object('code','verification_locked');
 ELSIF c.code_digest IS DISTINCT FROM p_digest THEN
  UPDATE appointment_system.booking_verification_challenges SET attempts=attempts+1 WHERE id=c.id;
  result:=jsonb_build_object('code','verification_incorrect');
 ELSE
  expiry:=least((locked#>>'{context,expires_at}')::timestamptz,instant+interval '30 minutes');
  INSERT INTO appointment_system.booking_verification_grants(digest,context_id,email,purpose,policy_digest,expires_at) VALUES(p_grant,p_context,p_email,'booking',c.policy_digest,expiry);
  UPDATE appointment_system.booking_verification_challenges SET verified_at=instant,grant_digest=p_grant,code_ciphertext=NULL WHERE id=c.id;
  UPDATE appointment_system.booking_verification_mail SET code_ciphertext=NULL,message_ciphertext=NULL,state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,
   lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_completed' WHERE challenge_id=c.id;
  result:=jsonb_build_object('code','ok','state','verified','grant_ciphertext',p_cipher,'expires_at',expiry);
 END IF;
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'verify',fingerprint,result);
 RETURN result;
END $_$;

CREATE FUNCTION appointment_system.verify_enquiry(p_id uuid, p_receipt text, p_generation integer, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']); RETURN appointment_system.entry_verify_enquiry(p_id, p_receipt, p_generation, p_digest); END $$;

CREATE TABLE appointment_system.accepted_payments (
    booking_id uuid NOT NULL,
    observation_id uuid NOT NULL,
    merchant_id text NOT NULL,
    mode text NOT NULL,
    payment_id text NOT NULL,
    CONSTRAINT accepted_payments_mode_check CHECK ((mode = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT canonical_accepted_merchant CHECK ((merchant_id ~ '^[A-Za-z0-9]{1,64}$'::text))
);

CREATE TABLE appointment_system.booking_policies (
    version text NOT NULL,
    specification jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT booking_policies_specification_check CHECK ((jsonb_typeof(specification) = 'object'::text)),
    CONSTRAINT booking_policies_version_check CHECK ((version ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.booking_verification_actions (
    operation_id uuid NOT NULL,
    context_id uuid NOT NULL,
    action text NOT NULL,
    input_digest text NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT booking_verification_actions_action_check CHECK ((action = ANY (ARRAY['start'::text, 'resend'::text, 'verify'::text]))),
    CONSTRAINT booking_verification_actions_input_digest_check CHECK ((input_digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.booking_verification_challenges (
    id uuid NOT NULL,
    context_id uuid NOT NULL,
    email text NOT NULL,
    recipient_hash text NOT NULL,
    policy_digest text NOT NULL,
    activation_epoch uuid NOT NULL,
    generation integer DEFAULT 1 NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    code_digest text NOT NULL,
    code_ciphertext text,
    digest_key_id text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    grant_digest text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    last_code_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT booking_verification_challenges_attempts_check CHECK (((attempts >= 0) AND (attempts <= 5))),
    CONSTRAINT booking_verification_challenges_code_digest_check CHECK ((code_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT booking_verification_challenges_digest_key_id_check CHECK ((digest_key_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$'::text)),
    CONSTRAINT booking_verification_challenges_email_check CHECK (((length(email) >= 3) AND (length(email) <= 254))),
    CONSTRAINT booking_verification_challenges_generation_check CHECK (((generation >= 1) AND (generation <= 3))),
    CONSTRAINT booking_verification_challenges_policy_digest_check CHECK ((policy_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT booking_verification_challenges_recipient_hash_check CHECK ((recipient_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.booking_verification_email_observations (
    event_id text NOT NULL,
    job_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

CREATE TABLE appointment_system.booking_verification_grants (
    digest text NOT NULL,
    context_id uuid NOT NULL,
    email text NOT NULL,
    purpose text NOT NULL,
    policy_digest text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_request uuid,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT booking_verification_grants_digest_check CHECK ((digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT booking_verification_grants_policy_digest_check CHECK ((policy_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT booking_verification_grants_purpose_check CHECK ((purpose = 'booking'::text))
);

CREATE TABLE appointment_system.booking_verification_mail (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    challenge_id uuid NOT NULL,
    context_id uuid NOT NULL,
    generation integer NOT NULL,
    destination text NOT NULL,
    code_ciphertext text,
    message_ciphertext text,
    message_digest text,
    template_version integer DEFAULT 1 NOT NULL,
    mail_account_id text,
    mail_event_account_id text,
    mail_credential_version text,
    mail_format text DEFAULT 'resend-v1'::text NOT NULL,
    mail_idempotency_key text,
    state text DEFAULT 'pending'::text NOT NULL,
    provider_id uuid,
    first_attempt_at timestamp with time zone,
    last_error_code text,
    attempts integer DEFAULT 0 NOT NULL,
    lease_token uuid,
    lease_expires_at timestamp with time zone,
    next_attempt_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    claim_installation uuid,
    claim_generation uuid,
    claim_release text,
    claim_contract integer,
    CONSTRAINT booking_verification_mail_attempts_check CHECK (((attempts >= 0) AND (attempts <= 20))),
    CONSTRAINT booking_verification_mail_check CHECK (((state <> 'processing'::text) OR ((lease_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (claim_installation IS NOT NULL) AND (claim_generation IS NOT NULL) AND (claim_release IS NOT NULL) AND (claim_release ~ '^[a-f0-9]{64}$'::text) AND (claim_contract IS NOT NULL) AND (claim_contract = 1)))),
    CONSTRAINT booking_verification_mail_generation_check CHECK (((generation >= 1) AND (generation <= 3))),
    CONSTRAINT booking_verification_mail_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'suppressed'::text, 'retry_wait'::text, 'delivery_unknown'::text, 'needs_review'::text, 'failed'::text])))
);

CREATE TABLE appointment_system.bookings (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    context_id uuid NOT NULL,
    state text NOT NULL,
    service_id text NOT NULL,
    policy_version text NOT NULL,
    service_snapshot jsonb NOT NULL,
    amount_paise bigint NOT NULL,
    currency text NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    practice_timezone text NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text,
    preparation jsonb DEFAULT '{}'::jsonb NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    hold_expires_at timestamp with time zone NOT NULL,
    receipt_expires_at timestamp with time zone NOT NULL,
    receipt_revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    reschedule_deadline_at timestamp with time zone,
    activation_epoch uuid NOT NULL,
    original_starts_at timestamp with time zone,
    receipt_format text DEFAULT 'v1'::text NOT NULL,
    receipt_key_id text,
    cancelled_at timestamp with time zone,
    provider_receipt_format text DEFAULT 'provider-receipt-v1'::text NOT NULL,
    calendar_protocol text DEFAULT 'v1'::text NOT NULL,
    CONSTRAINT bookings_amount_paise_check CHECK ((amount_paise > 0)),
    CONSTRAINT bookings_calendar_protocol_check CHECK ((calendar_protocol = ANY (ARRAY['v1'::text, 'legacy-sarsa004'::text, 'legacy-astro003'::text, 'legacy-astro003-unversioned'::text]))),
    CONSTRAINT bookings_check CHECK ((ends_at > starts_at)),
    CONSTRAINT bookings_check1 CHECK (((hold_expires_at > created_at) AND (hold_expires_at <= starts_at))),
    CONSTRAINT bookings_check2 CHECK ((receipt_expires_at >= ends_at)),
    CONSTRAINT bookings_currency_check CHECK ((currency = 'INR'::text)),
    CONSTRAINT bookings_email_check CHECK (((length(btrim(email)) >= 3) AND (length(btrim(email)) <= 254))),
    CONSTRAINT bookings_full_name_check CHECK (((length(btrim(full_name)) >= 2) AND (length(btrim(full_name)) <= 100))),
    CONSTRAINT bookings_phone_check CHECK (((phone IS NULL) OR (phone = ''::text) OR (phone ~ '^\+[1-9][0-9]{6,14}$'::text))),
    CONSTRAINT bookings_policy_version_check CHECK ((policy_version ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT bookings_practice_timezone_check CHECK ((length(practice_timezone) > 0)),
    CONSTRAINT bookings_preparation_check CHECK ((jsonb_typeof(preparation) = 'object'::text)),
    CONSTRAINT bookings_provider_receipt_format_check CHECK ((provider_receipt_format = ANY (ARRAY['provider-receipt-v1'::text, 'astro-order-receipt-v1'::text, 'sarsa-order-receipt-v1'::text]))),
    CONSTRAINT bookings_receipt_format_check CHECK ((receipt_format ~ '^[a-z0-9][a-z0-9-]{0,63}$'::text)),
    CONSTRAINT bookings_receipt_key_id_check CHECK (((receipt_key_id IS NULL) OR (receipt_key_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$'::text))),
    CONSTRAINT bookings_revision_check CHECK ((revision > 0)),
    CONSTRAINT bookings_service_id_check CHECK (((length(service_id) >= 1) AND (length(service_id) <= 80))),
    CONSTRAINT bookings_service_snapshot_check CHECK ((jsonb_typeof(service_snapshot) = 'object'::text)),
    CONSTRAINT bookings_state_check CHECK ((state = ANY (ARRAY['held'::text, 'confirmed'::text, 'expired'::text, 'cancelled'::text, 'payment_review'::text])))
);

CREATE TABLE appointment_system.caller_logins (
    login_role name NOT NULL,
    purpose text NOT NULL,
    installation_id uuid NOT NULL,
    environment text NOT NULL,
    writer_contract integer NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    CONSTRAINT caller_logins_purpose_check CHECK ((purpose = ANY (ARRAY['web'::text, 'staff'::text, 'worker'::text, 'company'::text, 'backup'::text, 'maintenance'::text]))),
    CONSTRAINT caller_logins_writer_contract_check CHECK ((writer_contract = 1))
);

CREATE TABLE appointment_system.checkout_admissions (
    request_id uuid NOT NULL,
    context_id uuid NOT NULL,
    receipt_digest text NOT NULL,
    request_fingerprint text NOT NULL,
    outcome text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    activation_epoch uuid NOT NULL,
    CONSTRAINT checkout_admissions_outcome_check CHECK ((outcome = ANY (ARRAY['pending'::text, 'rejected'::text, 'committed'::text]))),
    CONSTRAINT checkout_admissions_receipt_digest_check CHECK ((receipt_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT checkout_admissions_request_fingerprint_check CHECK ((request_fingerprint ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.checkout_contexts (
    id uuid NOT NULL,
    credential_digest text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    active_checkout_id uuid,
    activation_epoch uuid NOT NULL,
    credential_format text DEFAULT 'v1'::text NOT NULL,
    credential_key_id text,
    verification_id uuid,
    CONSTRAINT checkout_contexts_check CHECK ((expires_at > created_at)),
    CONSTRAINT checkout_contexts_credential_digest_check CHECK ((credential_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT checkout_contexts_credential_format_check CHECK ((credential_format ~ '^[a-z0-9][a-z0-9-]{0,63}$'::text)),
    CONSTRAINT checkout_contexts_credential_key_id_check CHECK (((credential_key_id IS NULL) OR (credential_key_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$'::text)))
);

CREATE TABLE appointment_system.company_configuration_actions (
    operation_id uuid NOT NULL,
    actor text NOT NULL,
    expected_revision bigint NOT NULL,
    configuration_revision bigint NOT NULL,
    settings_digest text NOT NULL,
    specification jsonb NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    result jsonb NOT NULL,
    CONSTRAINT company_configuration_actions_configuration_revision_check CHECK ((configuration_revision > 0)),
    CONSTRAINT company_configuration_actions_expected_revision_check CHECK ((expected_revision > 0)),
    CONSTRAINT company_configuration_actions_reason_check CHECK (((length(reason) >= 5) AND (length(reason) <= 300))),
    CONSTRAINT company_configuration_actions_settings_digest_check CHECK ((settings_digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.company_credentials (
    subject text NOT NULL,
    username text NOT NULL,
    password_hash text NOT NULL,
    credential_revision bigint DEFAULT 1 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    changed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT company_credentials_credential_revision_check CHECK ((credential_revision > 0)),
    CONSTRAINT company_credentials_password_hash_check CHECK (((length(password_hash) >= 90) AND (length(password_hash) <= 200))),
    CONSTRAINT company_credentials_username_check CHECK ((username ~ '^[a-z0-9][a-z0-9_.-]{2,63}$'::text))
);

CREATE TABLE appointment_system.company_login_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subject text,
    credential_revision bigint,
    risk_digest text NOT NULL,
    username_digest text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '00:01:00'::interval) NOT NULL,
    consumed_at timestamp with time zone,
    success boolean DEFAULT false NOT NULL,
    purpose text DEFAULT 'login'::text NOT NULL,
    bound_token text,
    CONSTRAINT company_login_attempts_check CHECK ((((purpose = 'login'::text) AND (bound_token IS NULL)) OR ((purpose <> 'login'::text) AND (bound_token ~ '^[a-f0-9]{64}$'::text)))),
    CONSTRAINT company_login_attempts_purpose_check CHECK ((purpose = ANY (ARRAY['login'::text, 'reauthenticate'::text, 'password'::text]))),
    CONSTRAINT company_login_attempts_risk_digest_check CHECK ((risk_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT company_login_attempts_username_digest_check CHECK ((username_digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.company_security_events (
    attempt_id uuid NOT NULL,
    subject text,
    purpose text NOT NULL,
    success boolean NOT NULL,
    credential_revision bigint,
    happened_at timestamp with time zone NOT NULL
);

CREATE TABLE appointment_system.contact_intake (
    id boolean DEFAULT true NOT NULL,
    public_open boolean DEFAULT false NOT NULL,
    CONSTRAINT contact_intake_id_check CHECK (id)
);

CREATE TABLE appointment_system.control_command_progress (
    operation_id uuid NOT NULL,
    state text NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    probed_at timestamp with time zone,
    error_code text,
    CONSTRAINT control_command_progress_error_code_check CHECK ((error_code ~ '^[a-z0-9_]{1,80}$'::text)),
    CONSTRAINT control_command_progress_state_check CHECK ((state = ANY (ARRAY['accepted'::text, 'publishing'::text, 'published'::text, 'effective'::text, 'superseded'::text, 'needs_review'::text])))
);

CREATE TABLE appointment_system.control_company_enrolment_evidence (
    id uuid NOT NULL,
    subject text NOT NULL,
    audience text NOT NULL,
    source_project text NOT NULL,
    source_hash text NOT NULL,
    purpose text NOT NULL,
    provisioned_by text NOT NULL,
    at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_company_enrolment_evidence_purpose_check CHECK ((purpose = 'verified-company-identity'::text)),
    CONSTRAINT control_company_enrolment_evidence_source_hash_check CHECK ((source_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_company_enrolment_evidence_source_project_check CHECK ((source_project = ANY (ARRAY['003'::text, '004'::text])))
);

CREATE TABLE appointment_system.control_company_identities (
    subject text NOT NULL,
    email text NOT NULL,
    audience text NOT NULL,
    capabilities text[] NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    enrolled_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_company_identities_audience_check CHECK (((length(audience) >= 20) AND (length(audience) <= 255))),
    CONSTRAINT control_company_identities_capabilities_check CHECK ((((cardinality(capabilities) >= 1) AND (cardinality(capabilities) <= 2)) AND (capabilities <@ ARRAY['service_controller'::text, 'obligation_handler'::text]))),
    CONSTRAINT control_company_identities_email_check CHECK ((email = appointment_system.installation_value('owners.agency_email'::text))),
    CONSTRAINT control_company_identities_subject_check CHECK (((length(subject) >= 1) AND (length(subject) <= 255)))
);

CREATE TABLE appointment_system.control_company_sessions (
    token_hash text NOT NULL,
    subject text NOT NULL,
    csrf_hash text NOT NULL,
    restore_generation uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    fresh_until timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    credential_revision bigint,
    last_used_at timestamp with time zone,
    CONSTRAINT control_company_sessions_check CHECK (((created_at < fresh_until) AND (fresh_until <= expires_at))),
    CONSTRAINT control_company_sessions_csrf_hash_check CHECK ((csrf_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_company_sessions_token_hash_check CHECK ((token_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.control_grant_repairs (
    id uuid NOT NULL,
    issuer text NOT NULL,
    body_hash text NOT NULL,
    reference uuid NOT NULL,
    owner_role text NOT NULL,
    lane text NOT NULL,
    owner_subject text NOT NULL,
    owner_email text NOT NULL,
    audience text NOT NULL,
    restore_generation uuid NOT NULL,
    expected_revision bigint NOT NULL,
    reason text NOT NULL,
    link_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '00:10:00'::interval) NOT NULL,
    state_hash text,
    browser_hash text,
    encrypted_attempt text,
    consumed_at timestamp with time zone,
    finished_at timestamp with time zone,
    result text,
    CONSTRAINT control_grant_repairs_body_hash_check CHECK ((body_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_grant_repairs_browser_hash_check CHECK ((browser_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_grant_repairs_check CHECK ((((state_hash IS NULL) AND (browser_hash IS NULL) AND (encrypted_attempt IS NULL)) OR ((state_hash IS NOT NULL) AND (browser_hash IS NOT NULL) AND ((length(encrypted_attempt) >= 100) AND (length(encrypted_attempt) <= 32768))))),
    CONSTRAINT control_grant_repairs_check1 CHECK (((finished_at IS NULL) = (result IS NULL))),
    CONSTRAINT control_grant_repairs_expected_revision_check CHECK ((expected_revision >= 0)),
    CONSTRAINT control_grant_repairs_lane_check CHECK ((lane = ANY (ARRAY['calendar'::text, 'records'::text]))),
    CONSTRAINT control_grant_repairs_link_hash_check CHECK ((link_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_grant_repairs_owner_role_check CHECK ((owner_role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT control_grant_repairs_owner_subject_check CHECK (((length(owner_subject) >= 1) AND (length(owner_subject) <= 255))),
    CONSTRAINT control_grant_repairs_reason_check CHECK (((length(btrim(reason)) >= 5) AND (length(btrim(reason)) <= 300))),
    CONSTRAINT control_grant_repairs_result_check CHECK ((result = ANY (ARRAY['saved'::text, 'denied'::text, 'failed'::text, 'changed'::text]))),
    CONSTRAINT control_grant_repairs_state_hash_check CHECK ((state_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.control_login_challenges (
    state_hash text NOT NULL,
    browser_hash text NOT NULL,
    audience text NOT NULL,
    nonce_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT control_login_challenges_browser_hash_check CHECK ((browser_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_login_challenges_nonce_hash_check CHECK ((nonce_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_login_challenges_state_hash_check CHECK ((state_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.control_login_limits (
    key_hash text NOT NULL,
    window_start timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempts integer NOT NULL,
    CONSTRAINT control_login_limits_attempts_check CHECK ((attempts > 0)),
    CONSTRAINT control_login_limits_key_hash_check CHECK ((key_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.control_maintenance_control_actions (
    operation_id uuid NOT NULL,
    company_subject text NOT NULL,
    provisioned_by text NOT NULL,
    purpose text NOT NULL,
    body_hash text NOT NULL,
    at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_maintenance_control_actions_body_hash_check CHECK ((body_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_maintenance_control_actions_purpose_check CHECK ((purpose = 'protected-emergency-control'::text))
);

CREATE TABLE appointment_system.control_operations (
    id uuid NOT NULL,
    actor_subject text NOT NULL,
    body_hash text NOT NULL,
    expected_generation uuid NOT NULL,
    expected_revision bigint NOT NULL,
    target_enabled boolean NOT NULL,
    reason text NOT NULL,
    result_snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_operations_body_hash_check CHECK ((body_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_operations_reason_check CHECK (((length(btrim(reason)) >= 5) AND (length(btrim(reason)) <= 300))),
    CONSTRAINT control_operations_result_snapshot_check CHECK ((jsonb_typeof(result_snapshot) = 'object'::text))
);

CREATE TABLE appointment_system.control_privacy_completions (
    intent_id uuid NOT NULL,
    outcome text NOT NULL,
    reason text NOT NULL,
    completed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_completions_outcome_check CHECK ((outcome = ANY (ARRAY['applied'::text, 'cancelled'::text]))),
    CONSTRAINT control_privacy_completions_reason_check CHECK ((reason = ANY (ARRAY['content_erased'::text, 'eligibility_changed'::text])))
);

CREATE TABLE appointment_system.control_privacy_documents (
    intent_id uuid NOT NULL,
    body jsonb NOT NULL,
    CONSTRAINT control_privacy_documents_body_check CHECK (((jsonb_typeof(body) = 'object'::text) AND (octet_length((body)::text) <= 8192)))
);

CREATE TABLE appointment_system.control_privacy_exports (
    intent_id uuid NOT NULL,
    sequence bigint NOT NULL,
    entry_hash text NOT NULL,
    head_hash text NOT NULL,
    file_id text NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_exports_entry_hash_check CHECK ((entry_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_privacy_exports_file_id_check CHECK ((file_id ~ '^[A-Za-z0-9_-]{10,180}$'::text)),
    CONSTRAINT control_privacy_exports_head_hash_check CHECK ((head_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_privacy_exports_sequence_check CHECK ((sequence > 0))
);

CREATE TABLE appointment_system.control_privacy_intents (
    id uuid NOT NULL,
    policy_id text NOT NULL,
    target_id uuid NOT NULL,
    target_hash text NOT NULL,
    base_sequence bigint NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_intents_base_sequence_check CHECK ((base_sequence >= 0)),
    CONSTRAINT control_privacy_intents_target_hash_check CHECK ((target_hash ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.control_privacy_policies (
    id text NOT NULL,
    kind text NOT NULL,
    version integer NOT NULL,
    minimum_days integer NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_policies_kind_check CHECK ((kind = ANY (ARRAY['abandoned_enquiry'::text, 'routine_incident'::text, 'resolved_transport'::text]))),
    CONSTRAINT control_privacy_policies_minimum_days_check CHECK (((minimum_days >= 7) AND (minimum_days <= 3650))),
    CONSTRAINT control_privacy_policies_version_check CHECK ((version = 1))
);

CREATE TABLE appointment_system.control_privacy_policy_approvals (
    policy_id text NOT NULL,
    approved_by text NOT NULL,
    approved_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_policy_approvals_approved_by_check CHECK (((length(btrim(approved_by)) >= 3) AND (length(btrim(approved_by)) <= 180)))
);

CREATE TABLE appointment_system.control_privacy_replay_progress (
    restore_operation uuid NOT NULL,
    sequence bigint NOT NULL,
    head_hash text NOT NULL,
    completed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_privacy_replay_progress_head_hash_check CHECK ((head_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_privacy_replay_progress_sequence_check CHECK ((sequence >= 0))
);

CREATE TABLE appointment_system.control_product_state (
    singleton boolean DEFAULT true NOT NULL,
    project text NOT NULL,
    environment text NOT NULL,
    origin text NOT NULL,
    enabled boolean NOT NULL,
    restore_generation uuid NOT NULL,
    generation_sequence bigint NOT NULL,
    revision bigint NOT NULL,
    activation_epoch uuid NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    provenance text NOT NULL,
    requested_enabled boolean DEFAULT false NOT NULL,
    winning_operation uuid,
    CONSTRAINT control_product_state_environment_check CHECK ((environment = ANY (ARRAY['development'::text, 'test'::text, 'production'::text]))),
    CONSTRAINT control_product_state_generation_sequence_check CHECK ((generation_sequence > 0)),
    CONSTRAINT control_product_state_origin_check CHECK ((origin ~ '^https?://[^/]+$'::text)),
    CONSTRAINT control_product_state_project_check CHECK ((project ~ '^[a-z0-9][a-z0-9-]{0,79}$'::text)),
    CONSTRAINT control_product_state_provenance_check CHECK ((provenance = ANY (ARRAY['existing_service'::text, 'company_command'::text, 'restore_reconciliation'::text]))),
    CONSTRAINT control_product_state_revision_check CHECK ((revision > 0)),
    CONSTRAINT control_product_state_singleton_check CHECK (singleton)
);

CREATE TABLE appointment_system.control_publications (
    operation_id uuid NOT NULL,
    snapshot jsonb NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    lease_token uuid,
    lease_until timestamp with time zone,
    published_at timestamp with time zone,
    last_error text,
    CONSTRAINT control_publications_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT control_publications_check CHECK (((lease_token IS NULL) = (lease_until IS NULL))),
    CONSTRAINT control_publications_check1 CHECK (((state = 'published'::text) = (published_at IS NOT NULL))),
    CONSTRAINT control_publications_last_error_check CHECK ((last_error ~ '^[a-z0-9_]{1,80}$'::text)),
    CONSTRAINT control_publications_snapshot_check CHECK ((jsonb_typeof(snapshot) = 'object'::text)),
    CONSTRAINT control_publications_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'published'::text, 'superseded'::text, 'attention'::text])))
);

CREATE TABLE appointment_system.control_restore_completions (
    operation_id uuid NOT NULL,
    restore_generation uuid NOT NULL,
    projection_snapshot jsonb NOT NULL,
    privacy_sequence bigint NOT NULL,
    privacy_head_hash text NOT NULL,
    completed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT control_restore_completions_privacy_head_hash_check CHECK ((privacy_head_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT control_restore_completions_privacy_sequence_check CHECK ((privacy_sequence >= 0))
);

CREATE TABLE appointment_system.control_restore_operations (
    id uuid NOT NULL,
    external_snapshot jsonb NOT NULL,
    archived_snapshot jsonb NOT NULL,
    result_snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

CREATE TABLE appointment_system.delivery_jobs (
    id uuid NOT NULL,
    booking_id uuid NOT NULL,
    kind text NOT NULL,
    recipient_role text NOT NULL,
    booking_revision integer NOT NULL,
    event_key text DEFAULT ''::text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_token uuid,
    lease_expires_at timestamp with time zone,
    first_attempt_at timestamp with time zone,
    provider_id text,
    destination text,
    payload jsonb,
    last_error_code text,
    message_snapshot jsonb,
    template_version integer DEFAULT 1 NOT NULL,
    message_hash text,
    send_deadline_at timestamp with time zone,
    ever_uncertain boolean DEFAULT false NOT NULL,
    accepted_at timestamp with time zone,
    send_uncertain boolean DEFAULT false NOT NULL,
    prior_send_uncertain boolean DEFAULT false NOT NULL,
    mail_account_id text,
    mail_credential_version text,
    mail_format text DEFAULT 'resend-v1'::text NOT NULL,
    mail_idempotency_key text,
    mail_key_kind text,
    mail_key_role text,
    mail_event_account_id text,
    claim_installation uuid,
    claim_generation uuid,
    claim_release text,
    claim_contract integer,
    CONSTRAINT delivery_jobs_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT delivery_jobs_booking_revision_check CHECK ((booking_revision > 0)),
    CONSTRAINT delivery_jobs_check CHECK (((lease_token IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT delivery_jobs_check1 CHECK (((state <> 'processing'::text) OR ((lease_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (claim_installation IS NOT NULL) AND (claim_generation IS NOT NULL) AND (claim_release IS NOT NULL) AND (claim_release ~ '^[a-f0-9]{64}$'::text) AND (claim_contract IS NOT NULL) AND (claim_contract = 1)))),
    CONSTRAINT delivery_jobs_destination_check CHECK ((((kind = 'payment_review'::text) AND (recipient_role = 'client'::text) AND (length(event_key) > 0)) OR ((event_key = ''::text) AND (((kind = 'booking_ack'::text) AND (recipient_role = ANY (ARRAY['customer'::text, 'client'::text]))) OR ((kind = 'booking_calendar'::text) AND (recipient_role = 'calendar'::text)) OR ((kind = 'booking_details'::text) AND (recipient_role = 'customer'::text)) OR ((kind = 'booking_cancelled'::text) AND (recipient_role = ANY (ARRAY['customer'::text, 'client'::text, 'calendar'::text]))) OR ((kind = 'sheet_booking'::text) AND (recipient_role = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text]))))) OR ((event_key = 'meeting-ready'::text) AND (kind = 'sheet_booking'::text) AND (recipient_role = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text]))))),
    CONSTRAINT delivery_jobs_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'suppressed'::text, 'retry_wait'::text, 'delivery_unknown'::text, 'needs_review'::text, 'failed'::text]))),
    CONSTRAINT delivery_jobs_template_version_check CHECK ((template_version > 0))
);

CREATE TABLE appointment_system.email_observations (
    event_id text NOT NULL,
    job_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT email_observations_event_type_check CHECK ((event_type = ANY (ARRAY['email.sent'::text, 'email.delivered'::text, 'email.delivery_delayed'::text, 'email.bounced'::text, 'email.complained'::text, 'email.failed'::text, 'email.suppressed'::text])))
);

CREATE TABLE appointment_system.email_policy (
    id boolean DEFAULT true NOT NULL,
    daily_limit integer DEFAULT 0 NOT NULL,
    monthly_limit integer DEFAULT 0 NOT NULL,
    contact_daily_limit integer DEFAULT 0 NOT NULL,
    contact_monthly_limit integer DEFAULT 0 NOT NULL,
    CONSTRAINT email_policy_check CHECK (((contact_daily_limit <= daily_limit) AND (contact_monthly_limit <= monthly_limit))),
    CONSTRAINT email_policy_contact_daily_limit_check CHECK ((contact_daily_limit >= 0)),
    CONSTRAINT email_policy_contact_monthly_limit_check CHECK ((contact_monthly_limit >= 0)),
    CONSTRAINT email_policy_daily_limit_check CHECK (((daily_limit >= 0) AND (daily_limit <= 100))),
    CONSTRAINT email_policy_id_check CHECK (id),
    CONSTRAINT email_policy_monthly_limit_check CHECK (((monthly_limit >= 0) AND (monthly_limit <= 3000)))
);

CREATE TABLE appointment_system.email_reservations (
    job_id uuid,
    reserved_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    enquiry_job_id uuid,
    verification boolean DEFAULT false NOT NULL,
    verification_job_id uuid,
    CONSTRAINT email_reservations_check CHECK ((num_nonnulls(job_id, enquiry_job_id, verification_job_id) = 1))
);

CREATE TABLE appointment_system.enquiry_email_observations (
    event_id text NOT NULL,
    job_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT enquiry_email_observations_event_type_check CHECK ((event_type = ANY (ARRAY['email.sent'::text, 'email.delivered'::text, 'email.delivery_delayed'::text, 'email.bounced'::text, 'email.complained'::text, 'email.failed'::text, 'email.suppressed'::text])))
);

CREATE TABLE appointment_system.enquiry_resends (
    operation_id uuid NOT NULL,
    request_id uuid NOT NULL,
    generation integer NOT NULL,
    CONSTRAINT enquiry_resends_generation_check CHECK (((generation >= 2) AND (generation <= 3)))
);

CREATE TABLE appointment_system.enquiry_sheet_rows (
    role text NOT NULL,
    job_id uuid NOT NULL,
    row_number integer NOT NULL,
    values_json jsonb NOT NULL,
    volume_number bigint DEFAULT 1 NOT NULL,
    CONSTRAINT enquiry_sheet_rows_row_number_check CHECK (((row_number >= 2) AND (row_number <= 10000))),
    CONSTRAINT enquiry_sheet_rows_values_json_check CHECK (((jsonb_typeof(values_json) = 'array'::text) AND (jsonb_array_length(values_json) = ANY (ARRAY[10, 12, 15]))))
);

CREATE TABLE appointment_system.financial_resource_facts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    booking_id uuid NOT NULL,
    merchant_id text NOT NULL,
    mode text NOT NULL,
    credential_version text NOT NULL,
    resource_id text NOT NULL,
    provenance text NOT NULL,
    evidence_hash text NOT NULL,
    fact jsonb NOT NULL,
    observed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT financial_resource_facts_evidence_hash_check CHECK ((evidence_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT financial_resource_facts_fact_check CHECK (((jsonb_typeof(fact) = 'object'::text) AND (octet_length((fact)::text) <= 4096))),
    CONSTRAINT financial_resource_facts_mode_check CHECK ((mode = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT financial_resource_facts_provenance_check CHECK ((provenance = ANY (ARRAY['signed_webhook'::text, 'provider_fetch'::text]))),
    CONSTRAINT financial_resource_facts_resource_id_check CHECK ((resource_id ~ '^(rfnd|disp)_[A-Za-z0-9]{1,64}$'::text))
);

CREATE TABLE appointment_system.financial_resource_states (
    merchant_id text NOT NULL,
    mode text NOT NULL,
    resource_id text NOT NULL,
    booking_id uuid NOT NULL,
    payment_id text NOT NULL,
    order_id text NOT NULL,
    kind text NOT NULL,
    status text NOT NULL,
    outcome text,
    amount_paise bigint NOT NULL,
    currency text NOT NULL,
    fact jsonb NOT NULL,
    verified boolean NOT NULL,
    attention_reason text,
    latest_fact_id uuid NOT NULL,
    observed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT financial_resource_states_amount_paise_check CHECK ((amount_paise > 0)),
    CONSTRAINT financial_resource_states_currency_check CHECK ((currency = 'INR'::text)),
    CONSTRAINT financial_resource_states_kind_check CHECK ((kind = ANY (ARRAY['refund'::text, 'dispute'::text]))),
    CONSTRAINT financial_resource_states_mode_check CHECK ((mode = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT financial_resource_states_outcome_check CHECK ((outcome = ANY (ARRAY['won'::text, 'lost'::text])))
);

CREATE TABLE appointment_system.google_attempts (
    state_digest text NOT NULL,
    browser_digest text NOT NULL,
    purpose text NOT NULL,
    role text NOT NULL,
    encrypted_attempt text NOT NULL,
    session_digest text,
    expected_revision bigint DEFAULT 0 NOT NULL,
    client_id text NOT NULL,
    origin text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    finished_at timestamp with time zone,
    portal text DEFAULT 'booking'::text NOT NULL,
    CONSTRAINT google_attempts_browser_digest_check CHECK ((browser_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT google_attempts_check CHECK ((((purpose = 'signin'::text) AND (session_digest IS NULL)) OR ((purpose = 'connect'::text) AND (session_digest IS NOT NULL)))),
    CONSTRAINT google_attempts_encrypted_attempt_check CHECK (((length(encrypted_attempt) >= 100) AND (length(encrypted_attempt) <= 32768))),
    CONSTRAINT google_attempts_expected_revision_check CHECK ((expected_revision >= 0)),
    CONSTRAINT google_attempts_portal_check CHECK ((portal = ANY (ARRAY['booking'::text, 'enquiry'::text]))),
    CONSTRAINT google_attempts_purpose_check CHECK ((purpose = ANY (ARRAY['signin'::text, 'connect'::text]))),
    CONSTRAINT google_attempts_role_check CHECK ((role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT google_attempts_state_digest_check CHECK ((state_digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.google_connections (
    role text NOT NULL,
    subject text NOT NULL,
    client_id text NOT NULL,
    revision bigint NOT NULL,
    encrypted_grant text NOT NULL,
    connected_at timestamp with time zone NOT NULL,
    grant_expires_at timestamp with time zone,
    refresh_lease uuid,
    refresh_lease_until timestamp with time zone,
    refresh_revision bigint,
    grant_format text DEFAULT 'v1'::text NOT NULL,
    CONSTRAINT google_connections_encrypted_grant_check CHECK (((length(encrypted_grant) >= 100) AND (length(encrypted_grant) <= 32768))),
    CONSTRAINT google_connections_grant_format_check CHECK ((grant_format ~ '^[a-z0-9][a-z0-9-]{0,63}$'::text)),
    CONSTRAINT google_connections_revision_check CHECK ((revision > 0)),
    CONSTRAINT google_refresh_lease_complete CHECK ((((refresh_lease IS NULL) AND (refresh_lease_until IS NULL) AND (refresh_revision IS NULL)) OR ((refresh_lease IS NOT NULL) AND (refresh_lease_until IS NOT NULL) AND (refresh_revision IS NOT NULL) AND (refresh_revision > 0))))
);

CREATE TABLE appointment_system.google_resource_grants (
    id uuid NOT NULL,
    owner_role text NOT NULL,
    owner_email text NOT NULL,
    subject text NOT NULL,
    client_id text NOT NULL,
    resources text[] NOT NULL,
    scopes jsonb NOT NULL,
    encrypted_grant text NOT NULL,
    grant_format text NOT NULL,
    revision bigint DEFAULT 1 NOT NULL,
    grant_expires_at timestamp with time zone,
    connected_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_at timestamp with time zone,
    refresh_lease uuid,
    refresh_lease_until timestamp with time zone,
    refresh_revision bigint,
    last_error_code text,
    CONSTRAINT google_resource_grant_scopes CHECK (appointment_system.resource_scopes_valid(resources, scopes)),
    CONSTRAINT google_resource_grants_check CHECK ((((refresh_lease IS NULL) AND (refresh_lease_until IS NULL) AND (refresh_revision IS NULL)) OR ((refresh_lease IS NOT NULL) AND (refresh_lease_until IS NOT NULL) AND (refresh_revision > 0)))),
    CONSTRAINT google_resource_grants_client_id_check CHECK ((client_id ~ '^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$'::text)),
    CONSTRAINT google_resource_grants_encrypted_grant_check CHECK (((length(encrypted_grant) >= 100) AND (length(encrypted_grant) <= 32768))),
    CONSTRAINT google_resource_grants_grant_format_check CHECK ((grant_format ~ '^[a-z0-9][a-z0-9-]{0,63}$'::text)),
    CONSTRAINT google_resource_grants_owner_role_check CHECK ((owner_role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT google_resource_grants_revision_check CHECK ((revision > 0)),
    CONSTRAINT google_resource_grants_subject_check CHECK (((length(subject) >= 1) AND (length(subject) <= 255)))
);

CREATE TABLE appointment_system.google_resource_owner_links (
    id uuid NOT NULL,
    parent_digest text NOT NULL,
    resource text NOT NULL,
    resource_revision bigint NOT NULL,
    reference uuid NOT NULL,
    reason text NOT NULL,
    access_digest text NOT NULL,
    body_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '00:10:00'::interval) NOT NULL,
    attempt_id uuid,
    CONSTRAINT google_resource_owner_links_access_digest_check CHECK ((access_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT google_resource_owner_links_body_hash_check CHECK ((body_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT google_resource_owner_links_reason_check CHECK (((length(btrim(reason)) >= 5) AND (length(btrim(reason)) <= 300)))
);

CREATE TABLE appointment_system.google_resources (
    resource text NOT NULL,
    owner_email text NOT NULL,
    active_client text NOT NULL,
    retained_clients text[] NOT NULL,
    grant_id uuid,
    revision bigint DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT google_resources_resource_check CHECK ((resource = ANY (ARRAY['calendar'::text, 'client_sheet'::text, 'agency_sheet'::text]))),
    CONSTRAINT google_resources_revision_check CHECK ((revision >= 0))
);

CREATE VIEW appointment_system.google_sheet_connections AS
 SELECT
        CASE
            WHEN (r.resource = 'client_sheet'::text) THEN 'client'::text
            ELSE 'agency'::text
        END AS role,
    g.subject,
    g.client_id,
    r.revision,
    g.encrypted_grant,
    g.connected_at,
    g.grant_expires_at,
    g.refresh_lease,
    g.refresh_lease_until,
    g.refresh_revision,
    g.grant_format
   FROM (appointment_system.google_resources r
     JOIN appointment_system.google_resource_grants g ON ((g.id = r.grant_id)))
  WHERE ((r.resource = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text])) AND (g.revoked_at IS NULL));

CREATE TABLE appointment_system.google_workbook_volumes (
    role text NOT NULL,
    volume_number bigint NOT NULL,
    generation uuid DEFAULT gen_random_uuid() NOT NULL,
    layout_version integer NOT NULL,
    intent uuid NOT NULL,
    subject text NOT NULL,
    client_id text NOT NULL,
    spreadsheet_id text,
    state text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    grant_id uuid,
    CONSTRAINT google_workbook_volumes_check CHECK (((state = 'creating'::text) OR (spreadsheet_id IS NOT NULL))),
    CONSTRAINT google_workbook_volumes_layout_version_check CHECK ((layout_version = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT google_workbook_volumes_role_check CHECK ((role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT google_workbook_volumes_state_check CHECK ((state = ANY (ARRAY['creating'::text, 'ready'::text, 'retired'::text]))),
    CONSTRAINT google_workbook_volumes_volume_number_check CHECK ((volume_number > 0))
);

CREATE TABLE appointment_system.google_workbooks (
    role text NOT NULL,
    intent uuid DEFAULT gen_random_uuid() NOT NULL,
    subject text NOT NULL,
    client_id text NOT NULL,
    spreadsheet_id text,
    state text NOT NULL,
    lease uuid,
    lease_until timestamp with time zone,
    connection_revision bigint NOT NULL,
    next_row integer DEFAULT 2 NOT NULL,
    next_enquiry_row integer DEFAULT 2 NOT NULL,
    volume_number bigint DEFAULT 1 NOT NULL,
    layout_version integer DEFAULT 1 NOT NULL,
    creation_attempt_at timestamp with time zone,
    CONSTRAINT google_workbooks_check CHECK (((lease IS NULL) = (lease_until IS NULL))),
    CONSTRAINT google_workbooks_check1 CHECK (((state <> 'ready'::text) OR (spreadsheet_id IS NOT NULL))),
    CONSTRAINT google_workbooks_layout_version_check CHECK ((layout_version = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT google_workbooks_next_enquiry_row_check CHECK (((next_enquiry_row >= 2) AND (next_enquiry_row <= 10001))),
    CONSTRAINT google_workbooks_next_row_check CHECK (((next_row >= 2) AND (next_row <= 10001))),
    CONSTRAINT google_workbooks_role_check CHECK ((role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT google_workbooks_state_check CHECK ((state = ANY (ARRAY['creating'::text, 'ready'::text])))
);

CREATE TABLE appointment_system.installation (
    singleton boolean DEFAULT true NOT NULL,
    installation_id uuid NOT NULL,
    project_id text NOT NULL,
    environment text NOT NULL,
    specification jsonb NOT NULL,
    writer_contract integer DEFAULT 1 NOT NULL,
    installed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT installation_environment_check CHECK ((environment = ANY (ARRAY['development'::text, 'test'::text, 'production'::text]))),
    CONSTRAINT installation_provider_tag CHECK ((project_id ~ '^[a-z0-9][a-z0-9-]{0,74}$'::text)),
    CONSTRAINT installation_singleton_check CHECK (singleton),
    CONSTRAINT installation_specification_check CHECK ((jsonb_typeof(specification) = 'object'::text)),
    CONSTRAINT installation_writer_contract_check CHECK ((writer_contract = 1))
);

CREATE TABLE appointment_system.intake_settings (
    singleton boolean DEFAULT true NOT NULL,
    policy_version text NOT NULL,
    public_open boolean DEFAULT false NOT NULL,
    merchant_id text,
    payment_mode text,
    credential_version text,
    schedule_browsing_open boolean DEFAULT true NOT NULL,
    configuration_revision bigint DEFAULT 1 NOT NULL,
    CONSTRAINT canonical_intake_merchant CHECK (((merchant_id IS NULL) OR (merchant_id ~ '^[A-Za-z0-9]{1,64}$'::text))),
    CONSTRAINT intake_settings_check CHECK (((NOT public_open) OR ((length(btrim(merchant_id)) > 0) AND (payment_mode = 'live'::text) AND (length(btrim(credential_version)) > 0) AND (merchant_id IS NOT NULL) AND (credential_version IS NOT NULL)))),
    CONSTRAINT intake_settings_configuration_revision_check CHECK ((configuration_revision > 0)),
    CONSTRAINT intake_settings_payment_mode_check CHECK ((payment_mode = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT intake_settings_singleton_check CHECK (singleton)
);

CREATE TABLE appointment_system.mail_acceptance_claims (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind text NOT NULL,
    job_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    message_hash text NOT NULL,
    result text NOT NULL,
    observed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT mail_acceptance_claims_kind_check CHECK ((kind = ANY (ARRAY['booking'::text, 'contact'::text, 'verification'::text]))),
    CONSTRAINT mail_acceptance_claims_message_hash_check CHECK ((message_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT mail_acceptance_claims_result_check CHECK ((result = ANY (ARRAY['accepted'::text, 'conflict'::text])))
);

CREATE TABLE appointment_system.mail_connection (
    singleton boolean DEFAULT true NOT NULL,
    account_id text NOT NULL,
    active_key_id text NOT NULL,
    retained_keys text[] NOT NULL,
    legacy_identities jsonb NOT NULL,
    daily_allowance integer NOT NULL,
    rolling_allowance integer NOT NULL,
    CONSTRAINT mail_connection_account_id_check CHECK ((account_id ~ '^[A-Za-z0-9_-]{1,80}$'::text)),
    CONSTRAINT mail_connection_active_key_id_check CHECK ((active_key_id ~ '^[A-Za-z0-9_-]{1,80}$'::text)),
    CONSTRAINT mail_connection_daily_allowance_check CHECK (((daily_allowance >= 0) AND (daily_allowance <= 100))),
    CONSTRAINT mail_connection_legacy_identities_check CHECK ((jsonb_typeof(legacy_identities) = 'array'::text)),
    CONSTRAINT mail_connection_retained_keys_check CHECK (((cardinality(retained_keys) >= 1) AND (cardinality(retained_keys) <= 8))),
    CONSTRAINT mail_connection_rolling_allowance_check CHECK (((rolling_allowance >= 0) AND (rolling_allowance <= 3000))),
    CONSTRAINT mail_connection_singleton_check CHECK (singleton)
);

CREATE TABLE appointment_system.meeting_events (
    booking_id uuid NOT NULL,
    booking_revision integer NOT NULL,
    event_id text NOT NULL,
    state text NOT NULL,
    meet_url text,
    CONSTRAINT meeting_events_check CHECK ((((state = 'ready'::text) AND (meet_url IS NOT NULL) AND (meet_url ~ '^https://meet[.]google[.]com/[a-z]{3}-[a-z]{4}-[a-z]{3}$'::text)) OR ((state <> 'ready'::text) AND (meet_url IS NULL)))),
    CONSTRAINT meeting_events_state_check CHECK ((state = ANY (ARRAY['waiting'::text, 'ready'::text, 'cancelled'::text])))
);

CREATE TABLE appointment_system.operational_incidents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    project text NOT NULL,
    operation text NOT NULL,
    stage text NOT NULL,
    code text NOT NULL,
    first_seen_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    first_reference uuid NOT NULL,
    last_reference uuid NOT NULL,
    occurrences integer NOT NULL,
    elapsed_ms integer NOT NULL,
    CONSTRAINT operational_incidents_code_check CHECK ((code = ANY (ARRAY['service_unavailable'::text, 'storage_unavailable'::text, 'time_budget'::text, 'unexpected_failure'::text, 'provider_rejected'::text, 'result_invalid'::text]))),
    CONSTRAINT operational_incidents_elapsed_ms_check CHECK (((elapsed_ms >= 0) AND (elapsed_ms <= 60000))),
    CONSTRAINT operational_incidents_occurrences_check CHECK ((occurrences > 0)),
    CONSTRAINT operational_incidents_operation_check CHECK ((operation = ANY (ARRAY['control'::text, 'provider_event'::text, 'recovery'::text, 'verification'::text, 'enquiry'::text, 'staff'::text, 'checkout'::text, 'booking'::text, 'availability'::text, 'site'::text]))),
    CONSTRAINT operational_incidents_project_check CHECK ((project ~ '^[a-z0-9][a-z0-9-]{0,79}$'::text)),
    CONSTRAINT operational_incidents_stage_check CHECK ((stage = ANY (ARRAY['request'::text, 'provider'::text, 'storage'::text, 'recovery'::text, 'diagnostic'::text]))),
    CONSTRAINT operational_incidents_version_check CHECK ((version = 1))
);

CREATE TABLE appointment_system.payment_cases (
    id uuid NOT NULL,
    booking_id uuid NOT NULL,
    event_key text NOT NULL,
    reason text NOT NULL,
    next_check_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    resolution_actor text,
    resolution_note text,
    financial_first_seen timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    financial_lease_token uuid,
    financial_lease_until timestamp with time zone,
    financial_attempts integer DEFAULT 0 NOT NULL,
    financial_error text,
    CONSTRAINT paired_financial_lease CHECK (((financial_lease_token IS NULL) = (financial_lease_until IS NULL))),
    CONSTRAINT payment_cases_check CHECK (((resolved_at IS NULL) OR ((resolution_actor IS NOT NULL) AND (resolution_note IS NOT NULL)))),
    CONSTRAINT payment_cases_event_key_check CHECK ((length(event_key) > 0)),
    CONSTRAINT payment_cases_financial_attempts_check CHECK ((financial_attempts >= 0))
);

CREATE TABLE appointment_system.payment_observations (
    id uuid NOT NULL,
    booking_id uuid NOT NULL,
    merchant_id text NOT NULL,
    mode text NOT NULL,
    payment_id text NOT NULL,
    provider_order_id text NOT NULL,
    evidence_hash text NOT NULL,
    status text NOT NULL,
    amount_paise bigint NOT NULL,
    currency text NOT NULL,
    refunded_paise bigint DEFAULT 0 NOT NULL,
    observed_at timestamp with time zone DEFAULT now() NOT NULL,
    captured boolean DEFAULT false NOT NULL,
    CONSTRAINT canonical_observation_merchant CHECK ((merchant_id ~ '^[A-Za-z0-9]{1,64}$'::text)),
    CONSTRAINT payment_observations_amount_paise_check CHECK ((amount_paise >= 0)),
    CONSTRAINT payment_observations_check CHECK (((refunded_paise >= 0) AND (refunded_paise <= amount_paise))),
    CONSTRAINT payment_observations_evidence_hash_check CHECK ((evidence_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT payment_observations_mode_check CHECK ((mode = ANY (ARRAY['test'::text, 'live'::text])))
);

CREATE TABLE appointment_system.payment_orders (
    booking_id uuid NOT NULL,
    merchant_id text NOT NULL,
    mode text NOT NULL,
    credential_version text NOT NULL,
    provider_order_id text,
    state text DEFAULT 'not_attempted'::text NOT NULL,
    attempted_at timestamp with time zone,
    resolution text,
    resolved_at timestamp with time zone,
    resolution_actor text,
    resolution_note text,
    next_check_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_token uuid,
    recovery_followup boolean DEFAULT false NOT NULL,
    last_recovery_error text,
    recovery_cursor integer DEFAULT 0 NOT NULL,
    order_search_skip integer DEFAULT 0 NOT NULL,
    lease_expires_at timestamp with time zone,
    resume_started_at timestamp with time zone,
    order_search_match text,
    order_search_conflict boolean DEFAULT false NOT NULL,
    order_search_from timestamp with time zone,
    order_search_until timestamp with time zone,
    CONSTRAINT canonical_order_merchant CHECK ((merchant_id ~ '^[A-Za-z0-9]{1,64}$'::text)),
    CONSTRAINT complete_search_window CHECK ((((order_search_from IS NULL) = (order_search_until IS NULL)) AND ((order_search_until IS NULL) OR (order_search_until >= order_search_from)))),
    CONSTRAINT order_lease_pair CHECK (((lease_token IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT payment_orders_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT payment_orders_check CHECK (((state = 'not_attempted'::text) = (attempted_at IS NULL))),
    CONSTRAINT payment_orders_check1 CHECK (((state <> 'ready'::text) OR (provider_order_id IS NOT NULL))),
    CONSTRAINT payment_orders_check2 CHECK (((resolution IS NULL) = (resolved_at IS NULL))),
    CONSTRAINT payment_orders_check3 CHECK (((resolution <> 'never_attempted_abandoned'::text) OR (state = 'not_attempted'::text))),
    CONSTRAINT payment_orders_check4 CHECK (((resolution <> 'creation_definitely_rejected'::text) OR ((state = 'failed'::text) AND (provider_order_id IS NULL)))),
    CONSTRAINT payment_orders_check5 CHECK (((resolution <> 'studio_reviewed'::text) OR ((resolution_actor IS NOT NULL) AND (length(btrim(resolution_actor)) > 0) AND (resolution_note IS NOT NULL) AND (length(btrim(resolution_note)) > 0)))),
    CONSTRAINT payment_orders_credential_version_check CHECK ((length(credential_version) > 0)),
    CONSTRAINT payment_orders_merchant_id_check CHECK ((length(merchant_id) > 0)),
    CONSTRAINT payment_orders_mode_check CHECK ((mode = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT payment_orders_order_search_match_check CHECK ((order_search_match ~ '^order_[A-Za-z0-9]{1,64}$'::text)),
    CONSTRAINT payment_orders_order_search_skip_check CHECK ((order_search_skip >= 0)),
    CONSTRAINT payment_orders_recovery_cursor_check CHECK ((recovery_cursor >= 0)),
    CONSTRAINT payment_orders_resolution_check CHECK ((resolution = ANY (ARRAY['never_attempted_abandoned'::text, 'creation_definitely_rejected'::text, 'provider_terminal'::text, 'studio_reviewed'::text, 'confirmed'::text]))),
    CONSTRAINT payment_orders_state_check CHECK ((state = ANY (ARRAY['not_attempted'::text, 'creating'::text, 'creation_unknown'::text, 'ready'::text, 'failed'::text])))
);

CREATE TABLE appointment_system.provider_inbox (
    provider text NOT NULL,
    account_id text NOT NULL,
    environment text NOT NULL,
    event_id text NOT NULL,
    body_hash text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_token uuid,
    lease_expires_at timestamp with time zone,
    last_error_code text,
    CONSTRAINT canonical_inbox_merchant CHECK (((provider <> 'razorpay'::text) OR (account_id ~ '^[A-Za-z0-9]{1,64}$'::text))),
    CONSTRAINT inbox_lease_pair CHECK (((lease_token IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT provider_inbox_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT provider_inbox_body_hash_check CHECK ((body_hash ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT provider_inbox_environment_check CHECK ((environment = ANY (ARRAY['test'::text, 'live'::text]))),
    CONSTRAINT provider_inbox_provider_check CHECK ((provider = ANY (ARRAY['razorpay'::text, 'resend'::text])))
);

CREATE TABLE appointment_system.receipt_recoveries (
    operation_id uuid NOT NULL,
    request_id uuid NOT NULL,
    action text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    verified_payment_id text NOT NULL,
    verification_method text DEFAULT 'existing_phone_callback'::text NOT NULL,
    previous_revision integer NOT NULL,
    revision integer NOT NULL,
    previous_email text,
    previous_phone text,
    new_email text,
    new_phone text,
    code_digest text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone DEFAULT (clock_timestamp() + '00:15:00'::interval) NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    superseded_at timestamp with time zone,
    redeemed_at timestamp with time zone,
    redeemed_digest text,
    CONSTRAINT receipt_recoveries_action_check CHECK ((action = ANY (ARRAY['receipt_recovery'::text, 'contact_correction'::text]))),
    CONSTRAINT receipt_recoveries_attempts_check CHECK (((attempts >= 0) AND (attempts <= 5))),
    CONSTRAINT receipt_recoveries_check CHECK (((redeemed_at IS NULL) = (redeemed_digest IS NULL))),
    CONSTRAINT receipt_recoveries_code_digest_check CHECK ((code_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT receipt_recoveries_reason_check CHECK (((length(btrim(reason)) >= 2) AND (length(btrim(reason)) <= 500))),
    CONSTRAINT receipt_recoveries_redeemed_digest_check CHECK ((redeemed_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT receipt_recoveries_verification_method_check CHECK ((verification_method = 'existing_phone_callback'::text))
);

CREATE TABLE appointment_system.request_limits (
    scope text NOT NULL,
    key_digest text NOT NULL,
    window_start timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempts integer NOT NULL,
    CONSTRAINT request_limits_attempts_check CHECK ((attempts > 0)),
    CONSTRAINT request_limits_key_digest_check CHECK ((key_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT request_limits_scope_check CHECK ((scope = ANY (ARRAY['context'::text, 'availability'::text, 'receipt'::text, 'checkout'::text, 'studio'::text, 'studio_status'::text, 'contact_start'::text, 'contact_email'::text, 'contact_read'::text, 'contact_verify'::text])))
);

CREATE TABLE appointment_system.studio_sessions (
    digest text NOT NULL,
    role text NOT NULL,
    subject text NOT NULL,
    client_id text NOT NULL,
    origin text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT studio_sessions_digest_check CHECK ((digest ~ '^[a-f0-9]{64}$'::text))
);

CREATE VIEW appointment_system.recovery_due_work AS
 SELECT
        CASE
            WHEN appointment_system.is_email_job(delivery_jobs.kind, delivery_jobs.recipient_role) THEN 'notification_email'::text
            ELSE 'booking_records'::text
        END AS lane,
        CASE
            WHEN appointment_system.is_email_job(delivery_jobs.kind, delivery_jobs.recipient_role) THEN 'booking'::text
            WHEN ((delivery_jobs.recipient_role = 'calendar'::text) OR (delivery_jobs.kind = 'booking_calendar'::text)) THEN 'calendar'::text
            WHEN (delivery_jobs.kind = 'sheet_booking'::text) THEN delivery_jobs.recipient_role
            ELSE 'calendar'::text
        END AS resource,
    GREATEST(delivery_jobs.next_attempt_at, COALESCE(delivery_jobs.lease_expires_at, delivery_jobs.next_attempt_at)) AS due
   FROM appointment_system.delivery_jobs
  WHERE ((delivery_jobs.state = ANY (ARRAY['pending'::text, 'processing'::text, 'retry_wait'::text, 'delivery_unknown'::text])) AND (appointment_system.is_email_job(delivery_jobs.kind, delivery_jobs.recipient_role) OR (delivery_jobs.kind = ANY (ARRAY['booking_calendar'::text, 'sheet_booking'::text])) OR ((delivery_jobs.kind = 'booking_cancelled'::text) AND (delivery_jobs.recipient_role = 'calendar'::text))))
UNION ALL
 SELECT
        CASE
            WHEN (enquiry_delivery_jobs.kind = 'verification'::text) THEN 'verification_email'::text
            WHEN (enquiry_delivery_jobs.kind = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text])) THEN 'enquiry_records'::text
            ELSE 'notification_email'::text
        END AS lane,
        CASE
            WHEN (enquiry_delivery_jobs.kind = 'verification'::text) THEN 'enquiry_code'::text
            WHEN (enquiry_delivery_jobs.kind = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text])) THEN enquiry_delivery_jobs.kind
            ELSE 'enquiry'::text
        END AS resource,
    GREATEST(enquiry_delivery_jobs.next_attempt_at, COALESCE(enquiry_delivery_jobs.lease_expires_at, enquiry_delivery_jobs.next_attempt_at)) AS due
   FROM appointment_system.enquiry_delivery_jobs
  WHERE (enquiry_delivery_jobs.state = ANY (ARRAY['pending'::text, 'processing'::text, 'retry_wait'::text, 'delivery_unknown'::text]))
UNION ALL
 SELECT 'verification_email'::text AS lane,
    'booking_code'::text AS resource,
    GREATEST(booking_verification_mail.next_attempt_at, COALESCE(booking_verification_mail.lease_expires_at, booking_verification_mail.next_attempt_at)) AS due
   FROM appointment_system.booking_verification_mail
  WHERE (booking_verification_mail.state = ANY (ARRAY['pending'::text, 'processing'::text, 'retry_wait'::text, 'delivery_unknown'::text]))
UNION ALL
 SELECT
        CASE
            WHEN (p.provider = 'resend'::text) THEN 'email_events'::text
            ELSE 'payment_events'::text
        END AS lane,
        CASE
            WHEN (p.provider <> 'resend'::text) THEN 'inbox'::text
            WHEN (EXISTS ( SELECT 1
               FROM appointment_system.enquiry_delivery_jobs c
              WHERE ((c.id)::text = (p.payload ->> 'job_id'::text)))) THEN 'enquiry'::text
            WHEN (EXISTS ( SELECT 1
               FROM appointment_system.booking_verification_mail c
              WHERE ((c.id)::text = (p.payload ->> 'job_id'::text)))) THEN 'verification'::text
            ELSE 'booking'::text
        END AS resource,
    GREATEST(p.next_attempt_at, COALESCE(p.lease_expires_at, p.next_attempt_at)) AS due
   FROM appointment_system.provider_inbox p
  WHERE (p.processed_at IS NULL)
UNION ALL
 SELECT 'payment_events'::text AS lane,
    'resource'::text AS resource,
    GREATEST(c.next_check_at, COALESCE(c.financial_lease_until, c.next_check_at)) AS due
   FROM (appointment_system.payment_cases c
     JOIN appointment_system.financial_resource_states f ON (((f.booking_id = c.booking_id) AND (f.resource_id = split_part(c.event_key, ':'::text, 2)))))
  WHERE ((c.resolved_at IS NULL) AND ((NOT f.verified) OR (f.attention_reason IS NOT NULL) OR (f.status = ANY (ARRAY['pending'::text, 'open'::text, 'under_review'::text]))))
UNION ALL
 SELECT 'payment'::text AS lane,
    'order'::text AS resource,
    GREATEST(payment_orders.next_check_at, COALESCE(payment_orders.lease_expires_at, payment_orders.next_check_at),
        CASE
            WHEN (payment_orders.state = 'creating'::text) THEN (payment_orders.attempted_at + '00:00:30'::interval)
            ELSE payment_orders.next_check_at
        END) AS due
   FROM appointment_system.payment_orders
  WHERE ((payment_orders.resolved_at IS NULL) OR (payment_orders.recovery_followup AND (payment_orders.resolution = 'confirmed'::text)))
UNION ALL
 SELECT 'control_publication'::text AS lane,
    'display'::text AS resource,
    (statement_timestamp() + make_interval(secs => (((publication.h ->> 'due'::text))::integer)::double precision)) AS due
   FROM ( SELECT appointment_system.control_publication_schedule() AS h) publication
  WHERE ((publication.h ->> 'due'::text) IS NOT NULL)
UNION ALL
 SELECT 'maintenance'::text AS lane,
    'temporary'::text AS resource,
    (min(google_attempts.expires_at) + '24:00:00'::interval) AS due
   FROM appointment_system.google_attempts
UNION ALL
 SELECT 'maintenance'::text AS lane,
    'temporary'::text AS resource,
    (min(s.expires_at) + '24:00:00'::interval) AS due
   FROM appointment_system.studio_sessions s
  WHERE (NOT (EXISTS ( SELECT 1
           FROM appointment_system.google_attempts a
          WHERE (a.session_digest = s.digest))))
UNION ALL
 SELECT 'maintenance'::text AS lane,
    'temporary'::text AS resource,
    (min(request_limits.expires_at) + '24:00:00'::interval) AS due
   FROM appointment_system.request_limits
UNION ALL
 SELECT 'maintenance'::text AS lane,
    'temporary'::text AS resource,
    min(enquiries.code_expires_at) AS due
   FROM appointment_system.enquiries
  WHERE (enquiries.code_ciphertext IS NOT NULL);

CREATE TABLE appointment_system.recovery_lane_incidents (
    lane text NOT NULL,
    code text NOT NULL,
    first_seen_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    occurrences integer NOT NULL,
    CONSTRAINT recovery_lane_incidents_code_check CHECK ((code = ANY (ARRAY['execution_failed'::text, 'result_invalid'::text, 'result_stale'::text]))),
    CONSTRAINT recovery_lane_incidents_occurrences_check CHECK ((occurrences > 0))
);

CREATE TABLE appointment_system.recovery_lanes (
    lane text NOT NULL,
    latest_run uuid,
    last_attempt_at timestamp with time zone,
    last_completed_at timestamp with time zone,
    active_until timestamp with time zone,
    outcome text DEFAULT 'unchecked'::text NOT NULL,
    processed integer DEFAULT 0 NOT NULL,
    CONSTRAINT recovery_lanes_lane_check CHECK ((lane = ANY (ARRAY['email'::text, 'email_events'::text, 'google'::text, 'payment'::text, 'payment_events'::text, 'contact_email'::text, 'contact_google'::text, 'maintenance'::text, 'control_publication'::text]))),
    CONSTRAINT recovery_lanes_outcome_check CHECK ((outcome = ANY (ARRAY['unchecked'::text, 'attempted'::text, 'completed'::text, 'failed'::text]))),
    CONSTRAINT recovery_lanes_processed_check CHECK (((processed >= 0) AND (processed <= 2)))
);

CREATE TABLE appointment_system.schema_migrations (
    version text NOT NULL,
    sha256 text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT schema_migrations_sha256_check CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))
);

CREATE TABLE appointment_system.sheet_rows (
    role text NOT NULL,
    job_id uuid NOT NULL,
    row_number integer NOT NULL,
    values_json jsonb NOT NULL,
    volume_number bigint DEFAULT 1 NOT NULL,
    CONSTRAINT sheet_rows_row_number_check CHECK (((row_number >= 2) AND (row_number <= 10000))),
    CONSTRAINT sheet_rows_values_json_check CHECK (((jsonb_typeof(values_json) = 'array'::text) AND (jsonb_array_length(values_json) = ANY (ARRAY[12, 33]))))
);

CREATE TABLE appointment_system.slot_claims (
    id uuid NOT NULL,
    booking_id uuid,
    closure_reason text,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    released_at timestamp with time zone,
    CONSTRAINT slot_claims_check CHECK (((booking_id IS NULL) <> (closure_reason IS NULL))),
    CONSTRAINT slot_claims_check1 CHECK ((ends_at > starts_at))
);

CREATE TABLE appointment_system.staff_appointment_actions (
    operation_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    booking_id uuid NOT NULL,
    action text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    previous_revision integer NOT NULL,
    revision integer NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    notice_seconds bigint NOT NULL,
    policy_guidance text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    new_starts_at timestamp with time zone,
    new_ends_at timestamp with time zone,
    late_exception boolean DEFAULT false NOT NULL,
    CONSTRAINT staff_appointment_actions_action_check CHECK ((action = ANY (ARRAY['cancel'::text, 'reschedule'::text]))),
    CONSTRAINT staff_appointment_actions_check CHECK ((revision = (previous_revision + 1))),
    CONSTRAINT staff_appointment_actions_check1 CHECK ((((action = 'cancel'::text) AND (new_starts_at IS NULL) AND (new_ends_at IS NULL) AND (NOT late_exception)) OR ((action = 'reschedule'::text) AND (new_starts_at IS NOT NULL) AND (new_ends_at IS NOT NULL) AND (new_ends_at > new_starts_at)))),
    CONSTRAINT staff_appointment_actions_reason_check CHECK (((length(btrim(reason)) >= 2) AND (length(btrim(reason)) <= 500)))
);

CREATE TABLE appointment_system.staff_calendar_actions (
    operation_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    action text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT staff_calendar_actions_action_check CHECK ((action = ANY (ARRAY['close'::text, 'reopen'::text]))),
    CONSTRAINT staff_calendar_actions_actor_check CHECK (((length(btrim(actor)) >= 1) AND (length(btrim(actor)) <= 200))),
    CONSTRAINT staff_calendar_actions_reason_check CHECK (((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500)))
);

CREATE TABLE appointment_system.staff_reviews (
    operation_id uuid NOT NULL,
    item_key text NOT NULL,
    revision integer NOT NULL,
    actor text NOT NULL,
    note text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    action text DEFAULT 'note'::text NOT NULL,
    evidence_id uuid,
    resource_evidence_id uuid,
    CONSTRAINT recorded_resource_review CHECK (((action = 'resource_reviewed'::text) = (resource_evidence_id IS NOT NULL))),
    CONSTRAINT staff_reviews_action_check CHECK ((action = ANY (ARRAY['note'::text, 'retry'::text, 'verified_refund'::text, 'resource_reviewed'::text]))),
    CONSTRAINT staff_reviews_check CHECK (((action = 'verified_refund'::text) = (evidence_id IS NOT NULL))),
    CONSTRAINT staff_reviews_item_key_check CHECK ((item_key ~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'::text)),
    CONSTRAINT staff_reviews_note_check CHECK (((length(btrim(note)) >= 2) AND (length(btrim(note)) <= 1000))),
    CONSTRAINT staff_reviews_revision_check CHECK ((revision > 0))
);

CREATE TABLE appointment_system.studio_audit (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    role text NOT NULL,
    action text NOT NULL,
    CONSTRAINT studio_audit_action_check CHECK ((action = ANY (ARRAY['signin'::text, 'connect'::text, 'logout'::text]))),
    CONSTRAINT studio_audit_role_check CHECK ((role = ANY (ARRAY['client'::text, 'agency'::text])))
);

CREATE TABLE appointment_system.studio_identities (
    role text NOT NULL,
    subject text NOT NULL,
    CONSTRAINT studio_identities_role_check CHECK ((role = ANY (ARRAY['client'::text, 'agency'::text]))),
    CONSTRAINT studio_identities_subject_check CHECK (((length(subject) >= 1) AND (length(subject) <= 255)))
);

CREATE TABLE appointment_system.transport_attempt_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    installation_id uuid NOT NULL,
    job_kind text NOT NULL,
    job_id uuid NOT NULL,
    attempt integer NOT NULL,
    lease_token uuid NOT NULL,
    generation uuid NOT NULL,
    release_digest text NOT NULL,
    contract integer NOT NULL,
    phase text NOT NULL,
    state text NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    error_code text,
    CONSTRAINT transport_attempt_events_attempt_check CHECK (((attempt >= 1) AND (attempt <= 10000))),
    CONSTRAINT transport_attempt_events_contract_check CHECK ((contract = 1)),
    CONSTRAINT transport_attempt_events_error_code_check CHECK (((error_code IS NULL) OR (error_code ~ '^[a-z0-9_]{1,80}$'::text))),
    CONSTRAINT transport_attempt_events_job_kind_check CHECK ((job_kind = ANY (ARRAY['booking'::text, 'contact'::text, 'booking_code'::text]))),
    CONSTRAINT transport_attempt_events_phase_check CHECK ((phase = ANY (ARRAY['claimed'::text, 'result'::text]))),
    CONSTRAINT transport_attempt_events_release_digest_check CHECK ((release_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT transport_attempt_events_state_check CHECK ((state = ANY (ARRAY['processing'::text, 'completed'::text, 'suppressed'::text, 'retry_wait'::text, 'delivery_unknown'::text, 'needs_review'::text, 'failed'::text, 'pending'::text])))
);

CREATE TABLE appointment_system.worker_lane_evaluations (
    run_id uuid NOT NULL,
    lane text NOT NULL,
    lease_token uuid NOT NULL,
    resource text NOT NULL,
    started_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    completed_at timestamp with time zone,
    result jsonb
);

CREATE TABLE appointment_system.worker_lane_turns (
    lane text NOT NULL,
    next_resource integer DEFAULT 0 NOT NULL
);

CREATE TABLE appointment_system.worker_release (
    singleton boolean DEFAULT true NOT NULL,
    release_digest text NOT NULL,
    next_cursor integer DEFAULT 0 NOT NULL,
    active_run uuid,
    active_until timestamp with time zone,
    CONSTRAINT worker_release_next_cursor_check CHECK (((next_cursor >= 0) AND (next_cursor <= 8))),
    CONSTRAINT worker_release_release_digest_check CHECK ((release_digest ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT worker_release_singleton_check CHECK (singleton)
);

CREATE TABLE appointment_system.worker_runs (
    id uuid NOT NULL,
    generation uuid NOT NULL,
    release_digest text NOT NULL,
    scheduled_at timestamp with time zone NOT NULL,
    evaluated_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    plan jsonb NOT NULL,
    finished_at timestamp with time zone,
    final_summary jsonb
);

ALTER TABLE ONLY appointment_system.accepted_payments
    ADD CONSTRAINT accepted_payments_merchant_id_mode_payment_id_key UNIQUE (merchant_id, mode, payment_id);

ALTER TABLE ONLY appointment_system.accepted_payments
    ADD CONSTRAINT accepted_payments_observation_id_key UNIQUE (observation_id);

ALTER TABLE ONLY appointment_system.accepted_payments
    ADD CONSTRAINT accepted_payments_pkey PRIMARY KEY (booking_id);

ALTER TABLE ONLY appointment_system.booking_policies
    ADD CONSTRAINT booking_policies_pkey PRIMARY KEY (version);

ALTER TABLE ONLY appointment_system.booking_verification_actions
    ADD CONSTRAINT booking_verification_actions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.booking_verification_challenges
    ADD CONSTRAINT booking_verification_challenges_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.booking_verification_email_observations
    ADD CONSTRAINT booking_verification_email_observations_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY appointment_system.booking_verification_grants
    ADD CONSTRAINT booking_verification_grants_pkey PRIMARY KEY (digest);

ALTER TABLE ONLY appointment_system.booking_verification_mail
    ADD CONSTRAINT booking_verification_mail_challenge_id_generation_key UNIQUE (challenge_id, generation);

ALTER TABLE ONLY appointment_system.booking_verification_mail
    ADD CONSTRAINT booking_verification_mail_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.booking_verification_mail
    ADD CONSTRAINT booking_verification_mail_provider_id_key UNIQUE (provider_id);

ALTER TABLE ONLY appointment_system.bookings
    ADD CONSTRAINT bookings_id_context_id_key UNIQUE (id, context_id);

ALTER TABLE ONLY appointment_system.bookings
    ADD CONSTRAINT bookings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.bookings
    ADD CONSTRAINT bookings_request_id_key UNIQUE (request_id);

ALTER TABLE ONLY appointment_system.caller_logins
    ADD CONSTRAINT caller_logins_pkey PRIMARY KEY (login_role);

ALTER TABLE ONLY appointment_system.checkout_admissions
    ADD CONSTRAINT checkout_admissions_pkey PRIMARY KEY (request_id);

ALTER TABLE ONLY appointment_system.checkout_admissions
    ADD CONSTRAINT checkout_admissions_request_id_context_id_key UNIQUE (request_id, context_id);

ALTER TABLE ONLY appointment_system.checkout_contexts
    ADD CONSTRAINT checkout_contexts_credential_digest_key UNIQUE (credential_digest);

ALTER TABLE ONLY appointment_system.checkout_contexts
    ADD CONSTRAINT checkout_contexts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.company_configuration_actions
    ADD CONSTRAINT company_configuration_actions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.company_credentials
    ADD CONSTRAINT company_credentials_pkey PRIMARY KEY (subject);

ALTER TABLE ONLY appointment_system.company_credentials
    ADD CONSTRAINT company_credentials_username_key UNIQUE (username);

ALTER TABLE ONLY appointment_system.company_login_attempts
    ADD CONSTRAINT company_login_attempts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.company_security_events
    ADD CONSTRAINT company_security_events_pkey PRIMARY KEY (attempt_id);

ALTER TABLE ONLY appointment_system.contact_intake
    ADD CONSTRAINT contact_intake_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_command_progress
    ADD CONSTRAINT control_command_progress_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.control_company_enrolment_evidence
    ADD CONSTRAINT control_company_enrolment_evidence_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_company_identities
    ADD CONSTRAINT control_company_identities_pkey PRIMARY KEY (subject);

ALTER TABLE ONLY appointment_system.control_company_sessions
    ADD CONSTRAINT control_company_sessions_pkey PRIMARY KEY (token_hash);

ALTER TABLE ONLY appointment_system.control_grant_repairs
    ADD CONSTRAINT control_grant_repairs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_grant_repairs
    ADD CONSTRAINT control_grant_repairs_state_hash_key UNIQUE (state_hash);

ALTER TABLE ONLY appointment_system.control_login_challenges
    ADD CONSTRAINT control_login_challenges_pkey PRIMARY KEY (state_hash);

ALTER TABLE ONLY appointment_system.control_login_limits
    ADD CONSTRAINT control_login_limits_pkey PRIMARY KEY (key_hash, window_start);

ALTER TABLE ONLY appointment_system.control_maintenance_control_actions
    ADD CONSTRAINT control_maintenance_control_actions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.control_operations
    ADD CONSTRAINT control_operations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_privacy_completions
    ADD CONSTRAINT control_privacy_completions_pkey PRIMARY KEY (intent_id);

ALTER TABLE ONLY appointment_system.control_privacy_documents
    ADD CONSTRAINT control_privacy_documents_pkey PRIMARY KEY (intent_id);

ALTER TABLE ONLY appointment_system.control_privacy_exports
    ADD CONSTRAINT control_privacy_exports_pkey PRIMARY KEY (intent_id);

ALTER TABLE ONLY appointment_system.control_privacy_intents
    ADD CONSTRAINT control_privacy_intents_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_privacy_policies
    ADD CONSTRAINT control_privacy_policies_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.control_privacy_policy_approvals
    ADD CONSTRAINT control_privacy_policy_approvals_pkey PRIMARY KEY (policy_id);

ALTER TABLE ONLY appointment_system.control_privacy_replay_progress
    ADD CONSTRAINT control_privacy_replay_progress_pkey PRIMARY KEY (restore_operation);

ALTER TABLE ONLY appointment_system.control_product_state
    ADD CONSTRAINT control_product_state_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY appointment_system.control_publications
    ADD CONSTRAINT control_publications_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.control_restore_completions
    ADD CONSTRAINT control_restore_completions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.control_restore_completions
    ADD CONSTRAINT control_restore_completions_restore_generation_key UNIQUE (restore_generation);

ALTER TABLE ONLY appointment_system.control_restore_operations
    ADD CONSTRAINT control_restore_operations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.delivery_jobs
    ADD CONSTRAINT delivery_jobs_kind_booking_id_recipient_role_booking_revisi_key UNIQUE (kind, booking_id, recipient_role, booking_revision, event_key);

ALTER TABLE ONLY appointment_system.delivery_jobs
    ADD CONSTRAINT delivery_jobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.email_observations
    ADD CONSTRAINT email_observations_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY appointment_system.email_policy
    ADD CONSTRAINT email_policy_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_enquiry_job_id_key UNIQUE (enquiry_job_id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_job_id_key UNIQUE (job_id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_verification_job_id_key UNIQUE (verification_job_id);

ALTER TABLE ONLY appointment_system.enquiries
    ADD CONSTRAINT enquiries_pkey PRIMARY KEY (request_id);

ALTER TABLE ONLY appointment_system.enquiry_delivery_jobs
    ADD CONSTRAINT enquiry_delivery_jobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.enquiry_delivery_jobs
    ADD CONSTRAINT enquiry_delivery_jobs_request_id_kind_generation_key UNIQUE (request_id, kind, generation);

ALTER TABLE ONLY appointment_system.enquiry_email_observations
    ADD CONSTRAINT enquiry_email_observations_pkey PRIMARY KEY (event_id);

ALTER TABLE ONLY appointment_system.enquiry_resends
    ADD CONSTRAINT enquiry_resends_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.enquiry_sheet_rows
    ADD CONSTRAINT enquiry_sheet_rows_pkey PRIMARY KEY (role, job_id);

ALTER TABLE ONLY appointment_system.enquiry_sheet_rows
    ADD CONSTRAINT enquiry_sheet_rows_role_volume_number_row_number_key UNIQUE (role, volume_number, row_number);

ALTER TABLE ONLY appointment_system.financial_resource_facts
    ADD CONSTRAINT financial_resource_facts_merchant_id_mode_resource_id_prove_key UNIQUE (merchant_id, mode, resource_id, provenance, evidence_hash);

ALTER TABLE ONLY appointment_system.financial_resource_facts
    ADD CONSTRAINT financial_resource_facts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.financial_resource_states
    ADD CONSTRAINT financial_resource_states_pkey PRIMARY KEY (merchant_id, mode, resource_id);

ALTER TABLE ONLY appointment_system.google_attempts
    ADD CONSTRAINT google_attempts_pkey PRIMARY KEY (state_digest);

ALTER TABLE ONLY appointment_system.google_connections
    ADD CONSTRAINT google_connections_pkey PRIMARY KEY (role);

ALTER TABLE ONLY appointment_system.google_resource_attempts
    ADD CONSTRAINT google_resource_attempts_grant_id_key UNIQUE (grant_id);

ALTER TABLE ONLY appointment_system.google_resource_attempts
    ADD CONSTRAINT google_resource_attempts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.google_resource_attempts
    ADD CONSTRAINT google_resource_attempts_state_digest_key UNIQUE (state_digest);

ALTER TABLE ONLY appointment_system.google_resource_grants
    ADD CONSTRAINT google_resource_grants_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.google_resource_owner_links
    ADD CONSTRAINT google_resource_owner_links_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.google_resources
    ADD CONSTRAINT google_resources_pkey PRIMARY KEY (resource);

ALTER TABLE ONLY appointment_system.google_workbook_volumes
    ADD CONSTRAINT google_workbook_volumes_intent_key UNIQUE (intent);

ALTER TABLE ONLY appointment_system.google_workbook_volumes
    ADD CONSTRAINT google_workbook_volumes_pkey PRIMARY KEY (role, volume_number);

ALTER TABLE ONLY appointment_system.google_workbook_volumes
    ADD CONSTRAINT google_workbook_volumes_spreadsheet_id_key UNIQUE (spreadsheet_id);

ALTER TABLE ONLY appointment_system.google_workbooks
    ADD CONSTRAINT google_workbooks_intent_key UNIQUE (intent);

ALTER TABLE ONLY appointment_system.google_workbooks
    ADD CONSTRAINT google_workbooks_pkey PRIMARY KEY (role);

ALTER TABLE ONLY appointment_system.google_workbooks
    ADD CONSTRAINT google_workbooks_spreadsheet_id_key UNIQUE (spreadsheet_id);

ALTER TABLE ONLY appointment_system.installation
    ADD CONSTRAINT installation_installation_id_key UNIQUE (installation_id);

ALTER TABLE ONLY appointment_system.installation
    ADD CONSTRAINT installation_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY appointment_system.intake_settings
    ADD CONSTRAINT intake_settings_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY appointment_system.mail_acceptance_claims
    ADD CONSTRAINT mail_acceptance_claims_kind_job_id_provider_id_message_hash_key UNIQUE (kind, job_id, provider_id, message_hash, result);

ALTER TABLE ONLY appointment_system.mail_acceptance_claims
    ADD CONSTRAINT mail_acceptance_claims_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.mail_connection
    ADD CONSTRAINT mail_connection_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY appointment_system.meeting_events
    ADD CONSTRAINT meeting_events_event_id_key UNIQUE (event_id);

ALTER TABLE ONLY appointment_system.meeting_events
    ADD CONSTRAINT meeting_events_pkey PRIMARY KEY (booking_id, booking_revision);

ALTER TABLE ONLY appointment_system.operational_incidents
    ADD CONSTRAINT operational_incidents_operation_stage_code_key UNIQUE (operation, stage, code);

ALTER TABLE ONLY appointment_system.operational_incidents
    ADD CONSTRAINT operational_incidents_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.payment_cases
    ADD CONSTRAINT payment_cases_booking_id_event_key_key UNIQUE (booking_id, event_key);

ALTER TABLE ONLY appointment_system.payment_cases
    ADD CONSTRAINT payment_cases_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.payment_observations
    ADD CONSTRAINT payment_observations_id_booking_id_merchant_id_mode_payment_key UNIQUE (id, booking_id, merchant_id, mode, payment_id);

ALTER TABLE ONLY appointment_system.payment_observations
    ADD CONSTRAINT payment_observations_merchant_id_mode_payment_id_evidence_h_key UNIQUE (merchant_id, mode, payment_id, evidence_hash);

ALTER TABLE ONLY appointment_system.payment_observations
    ADD CONSTRAINT payment_observations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.payment_orders
    ADD CONSTRAINT payment_orders_merchant_id_mode_provider_order_id_key UNIQUE (merchant_id, mode, provider_order_id);

ALTER TABLE ONLY appointment_system.payment_orders
    ADD CONSTRAINT payment_orders_pkey PRIMARY KEY (booking_id);

ALTER TABLE ONLY appointment_system.provider_inbox
    ADD CONSTRAINT provider_inbox_pkey PRIMARY KEY (provider, account_id, environment, event_id);

ALTER TABLE ONLY appointment_system.receipt_recoveries
    ADD CONSTRAINT receipt_recoveries_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.recovery_lane_incidents
    ADD CONSTRAINT recovery_lane_incidents_pkey PRIMARY KEY (lane, code);

ALTER TABLE ONLY appointment_system.recovery_lanes
    ADD CONSTRAINT recovery_lanes_pkey PRIMARY KEY (lane);

ALTER TABLE ONLY appointment_system.request_limits
    ADD CONSTRAINT request_limits_pkey PRIMARY KEY (scope, key_digest, window_start);

ALTER TABLE ONLY appointment_system.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);

ALTER TABLE ONLY appointment_system.sheet_rows
    ADD CONSTRAINT sheet_rows_pkey PRIMARY KEY (role, job_id);

ALTER TABLE ONLY appointment_system.sheet_rows
    ADD CONSTRAINT sheet_rows_role_volume_number_row_number_key UNIQUE (role, volume_number, row_number);

ALTER TABLE ONLY appointment_system.slot_claims
    ADD CONSTRAINT slot_claims_booking_id_key UNIQUE (booking_id);

ALTER TABLE ONLY appointment_system.slot_claims
    ADD CONSTRAINT slot_claims_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.slot_claims
    ADD CONSTRAINT slot_claims_tstzrange_excl EXCLUDE USING gist (tstzrange(starts_at, ends_at, '[)'::text) WITH &&) WHERE ((released_at IS NULL));

ALTER TABLE ONLY appointment_system.staff_appointment_actions
    ADD CONSTRAINT staff_appointment_actions_booking_id_revision_key UNIQUE (booking_id, revision);

ALTER TABLE ONLY appointment_system.staff_appointment_actions
    ADD CONSTRAINT staff_appointment_actions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.staff_calendar_actions
    ADD CONSTRAINT staff_calendar_actions_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.staff_reviews
    ADD CONSTRAINT staff_reviews_item_key_revision_key UNIQUE (item_key, revision);

ALTER TABLE ONLY appointment_system.staff_reviews
    ADD CONSTRAINT staff_reviews_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY appointment_system.studio_audit
    ADD CONSTRAINT studio_audit_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.studio_identities
    ADD CONSTRAINT studio_identities_pkey PRIMARY KEY (role);

ALTER TABLE ONLY appointment_system.studio_identities
    ADD CONSTRAINT studio_identities_subject_key UNIQUE (subject);

ALTER TABLE ONLY appointment_system.studio_sessions
    ADD CONSTRAINT studio_sessions_pkey PRIMARY KEY (digest);

ALTER TABLE ONLY appointment_system.transport_attempt_events
    ADD CONSTRAINT transport_attempt_events_job_kind_job_id_lease_token_phase_key UNIQUE (job_kind, job_id, lease_token, phase);

ALTER TABLE ONLY appointment_system.transport_attempt_events
    ADD CONSTRAINT transport_attempt_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY appointment_system.worker_lane_evaluations
    ADD CONSTRAINT worker_lane_evaluations_pkey PRIMARY KEY (run_id, lane);

ALTER TABLE ONLY appointment_system.worker_lane_turns
    ADD CONSTRAINT worker_lane_turns_pkey PRIMARY KEY (lane);

ALTER TABLE ONLY appointment_system.worker_release
    ADD CONSTRAINT worker_release_pkey PRIMARY KEY (singleton);

ALTER TABLE ONLY appointment_system.worker_runs
    ADD CONSTRAINT worker_runs_pkey PRIMARY KEY (id);

CREATE INDEX admissions_context_time ON appointment_system.checkout_admissions USING btree (context_id, created_at);

CREATE INDEX booking_code_mail_due ON appointment_system.booking_verification_mail USING btree (next_attempt_at, id) WHERE (state = ANY (ARRAY['pending'::text, 'processing'::text, 'retry_wait'::text, 'delivery_unknown'::text]));

CREATE INDEX company_login_risk_time ON appointment_system.company_login_attempts USING btree (risk_digest, created_at);

CREATE INDEX company_login_username_time ON appointment_system.company_login_attempts USING btree (username_digest, created_at);

CREATE INDEX company_sessions_expiry ON appointment_system.control_company_sessions USING btree (expires_at);

CREATE INDEX contact_expiry ON appointment_system.enquiries USING btree (code_expires_at) WHERE (code_ciphertext IS NOT NULL);

CREATE INDEX delivery_jobs_due ON appointment_system.delivery_jobs USING btree (next_attempt_at, id) WHERE (state = ANY (ARRAY['pending'::text, 'failed'::text, 'uncertain'::text]));

CREATE INDEX delivery_staff_page ON appointment_system.delivery_jobs USING btree (id) WHERE (state = ANY (ARRAY['pending'::text, 'processing'::text, 'failed'::text, 'uncertain'::text, 'attention'::text, 'accepted'::text, 'delivered'::text]));

CREATE INDEX email_observation_job ON appointment_system.email_observations USING btree (job_id, event_type);

CREATE UNIQUE INDEX email_provider_identity ON appointment_system.delivery_jobs USING btree (provider_id) WHERE ((recipient_role = ANY (ARRAY['customer'::text, 'client'::text])) AND (provider_id IS NOT NULL));

CREATE INDEX email_reservation_time ON appointment_system.email_reservations USING btree (reserved_at);

CREATE INDEX enquiries_verified_page ON appointment_system.enquiries USING btree (request_id) WHERE (verified_at IS NOT NULL);

CREATE INDEX enquiry_delivery_due ON appointment_system.enquiry_delivery_jobs USING btree (next_attempt_at, id) WHERE (state = ANY (ARRAY['pending'::text, 'processing'::text, 'uncertain'::text, 'failed'::text]));

CREATE INDEX enquiry_delivery_staff_page ON appointment_system.enquiry_delivery_jobs USING btree (id) WHERE (kind <> 'verification'::text);

CREATE UNIQUE INDEX enquiry_email_provider ON appointment_system.enquiry_delivery_jobs USING btree (provider_id) WHERE ((provider_id IS NOT NULL) AND (kind = ANY (ARRAY['verification'::text, 'acknowledgement'::text, 'practice_notice'::text])));

CREATE INDEX enquiry_mail_observation_job ON appointment_system.enquiry_email_observations USING btree (job_id, event_type);

CREATE INDEX financial_cases_due ON appointment_system.payment_cases USING btree (next_check_at, id) WHERE (resolved_at IS NULL);

CREATE INDEX financial_facts_by_booking ON appointment_system.financial_resource_facts USING btree (booking_id, observed_at, id);

CREATE INDEX google_attempts_expiry ON appointment_system.google_attempts USING btree (expires_at);

CREATE INDEX google_attempts_session ON appointment_system.google_attempts USING btree (session_digest) WHERE (session_digest IS NOT NULL);

CREATE INDEX google_resource_attempts_expiry ON appointment_system.google_resource_attempts USING btree (expires_at);

CREATE INDEX google_resource_grants_expiry ON appointment_system.google_resource_grants USING btree (grant_expires_at);

CREATE INDEX google_resource_owner_links_expiry ON appointment_system.google_resource_owner_links USING btree (expires_at);

CREATE INDEX google_resources_grant ON appointment_system.google_resources USING btree (grant_id);

CREATE INDEX grant_repairs_expiry ON appointment_system.control_grant_repairs USING btree (expires_at);

CREATE INDEX mail_acceptance_lookup ON appointment_system.mail_acceptance_claims USING btree (kind, job_id, result);

CREATE UNIQUE INDEX mail_accepted_owner ON appointment_system.mail_acceptance_claims USING btree (provider_id) WHERE (result = 'accepted'::text);

CREATE UNIQUE INDEX one_held_booking_per_context ON appointment_system.bookings USING btree (context_id) WHERE (state = 'held'::text);

CREATE INDEX payment_cases_due ON appointment_system.payment_cases USING btree (next_check_at, id) WHERE (resolved_at IS NULL);

CREATE INDEX payment_followup_due ON appointment_system.payment_orders USING btree (next_check_at, booking_id) WHERE (recovery_followup AND (resolution = 'confirmed'::text));

CREATE INDEX product_publications_due ON appointment_system.control_publications USING btree (next_attempt_at, operation_id) WHERE (state = 'pending'::text);

CREATE INDEX provider_inbox_due ON appointment_system.provider_inbox USING btree (next_attempt_at, received_at) WHERE (processed_at IS NULL);

CREATE INDEX receipt_recoveries_booking ON appointment_system.receipt_recoveries USING btree (request_id, created_at DESC);

CREATE INDEX request_limits_expiry ON appointment_system.request_limits USING btree (expires_at);

CREATE INDEX slot_claims_studio_page ON appointment_system.slot_claims USING btree (id) WHERE (released_at IS NULL);

CREATE INDEX studio_sessions_expiry ON appointment_system.studio_sessions USING btree (expires_at);

CREATE INDEX transport_attempt_job_history ON appointment_system.transport_attempt_events USING btree (job_kind, job_id, occurred_at, id);

CREATE INDEX unresolved_orders_due ON appointment_system.payment_orders USING btree (next_check_at, booking_id) WHERE (resolved_at IS NULL);

CREATE INDEX verification_recipient_time ON appointment_system.booking_verification_challenges USING btree (recipient_hash, created_at);

CREATE INDEX worker_runs_retention ON appointment_system.worker_runs USING btree (evaluated_at);

CREATE CONSTRAINT TRIGGER audit_company_credentials AFTER UPDATE ON appointment_system.company_login_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION appointment_system.audit_credential_attempt();

CREATE TRIGGER booking_context_admission BEFORE INSERT ON appointment_system.checkout_contexts FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_context();

CREATE TRIGGER booking_order_admission BEFORE INSERT OR UPDATE ON appointment_system.payment_orders FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_order_attempt();

CREATE TRIGGER booking_request_admission BEFORE INSERT ON appointment_system.checkout_admissions FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_checkout_admission();

CREATE TRIGGER booking_row_admission BEFORE INSERT ON appointment_system.bookings FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_booking();

CREATE TRIGGER company_enrolment_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_company_enrolment_evidence FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_maintenance_evidence();

CREATE TRIGGER email_snapshot_immutable BEFORE UPDATE ON appointment_system.delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.protect_email_snapshot();

CREATE TRIGGER enquiry_delivery_identity BEFORE UPDATE ON appointment_system.enquiry_delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.protect_enquiry_delivery();

CREATE TRIGGER enquiry_identity BEFORE UPDATE ON appointment_system.enquiries FOR EACH ROW EXECUTE FUNCTION appointment_system.protect_enquiry_identity();

CREATE TRIGGER erased_enquiry_guard BEFORE DELETE OR UPDATE ON appointment_system.enquiries FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_erased_enquiry();

CREATE TRIGGER freeze_booking_code_message BEFORE UPDATE ON appointment_system.booking_verification_mail FOR EACH ROW EXECUTE FUNCTION appointment_system.freeze_booking_code_message();

CREATE TRIGGER freeze_enquiry_mail_binding BEFORE UPDATE ON appointment_system.enquiry_delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.freeze_mail_binding();

CREATE TRIGGER freeze_mail_binding BEFORE UPDATE ON appointment_system.delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.freeze_mail_binding();

CREATE TRIGGER maintenance_control_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_maintenance_control_actions FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_maintenance_evidence();

CREATE TRIGGER privacy_approval_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_policy_approvals FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_completion_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_completions FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_document_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_documents FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_export_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_exports FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_intent_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_intents FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_policy_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_policies FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER privacy_replay_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_privacy_replay_progress FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER restore_completion_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_restore_completions FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER restore_history_immutable BEFORE DELETE OR UPDATE ON appointment_system.control_restore_operations FOR EACH ROW EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE TRIGGER restored_activation_guard BEFORE INSERT OR UPDATE ON appointment_system.control_product_state FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_restored_activation();

CREATE TRIGGER saved_order_search_window BEFORE INSERT OR UPDATE ON appointment_system.payment_orders FOR EACH ROW EXECUTE FUNCTION appointment_system.bind_order_search_window();

CREATE TRIGGER stamp_transport_claim BEFORE INSERT OR UPDATE ON appointment_system.booking_verification_mail FOR EACH ROW EXECUTE FUNCTION appointment_system.stamp_transport_claim();

CREATE TRIGGER stamp_transport_claim BEFORE INSERT OR UPDATE ON appointment_system.delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.stamp_transport_claim();

CREATE TRIGGER stamp_transport_claim BEFORE INSERT OR UPDATE ON appointment_system.enquiry_delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.stamp_transport_claim();

CREATE TRIGGER transport_attempt_history AFTER INSERT OR UPDATE ON appointment_system.booking_verification_mail FOR EACH ROW EXECUTE FUNCTION appointment_system.append_transport_attempt('booking_code');

CREATE TRIGGER transport_attempt_history AFTER INSERT OR UPDATE ON appointment_system.delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.append_transport_attempt('booking');

CREATE TRIGGER transport_attempt_history AFTER INSERT OR UPDATE ON appointment_system.enquiry_delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.append_transport_attempt('contact');

CREATE TRIGGER verified_privacy_completion BEFORE INSERT ON appointment_system.control_restore_completions FOR EACH ROW EXECUTE FUNCTION appointment_system.control_guard_privacy_completion();

CREATE TRIGGER workbook_volume_identity BEFORE DELETE OR UPDATE ON appointment_system.google_workbook_volumes FOR EACH ROW EXECUTE FUNCTION appointment_system.protect_workbook_volume();

CREATE TRIGGER workbook_volume_seed AFTER INSERT ON appointment_system.google_workbooks FOR EACH ROW EXECUTE FUNCTION appointment_system.seed_workbook_volume();

ALTER TABLE ONLY appointment_system.accepted_payments
    ADD CONSTRAINT accepted_payments_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.accepted_payments
    ADD CONSTRAINT accepted_payments_observation_id_booking_id_merchant_id_mo_fkey FOREIGN KEY (observation_id, booking_id, merchant_id, mode, payment_id) REFERENCES appointment_system.payment_observations(id, booking_id, merchant_id, mode, payment_id);

ALTER TABLE ONLY appointment_system.booking_verification_actions
    ADD CONSTRAINT booking_verification_actions_context_id_fkey FOREIGN KEY (context_id) REFERENCES appointment_system.checkout_contexts(id) ON DELETE CASCADE;

ALTER TABLE ONLY appointment_system.booking_verification_challenges
    ADD CONSTRAINT booking_verification_challenges_context_id_fkey FOREIGN KEY (context_id) REFERENCES appointment_system.checkout_contexts(id) ON DELETE CASCADE;

ALTER TABLE ONLY appointment_system.booking_verification_email_observations
    ADD CONSTRAINT booking_verification_email_observations_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.booking_verification_mail(id);

ALTER TABLE ONLY appointment_system.booking_verification_grants
    ADD CONSTRAINT booking_verification_grants_context_id_fkey FOREIGN KEY (context_id) REFERENCES appointment_system.checkout_contexts(id);

ALTER TABLE ONLY appointment_system.booking_verification_mail
    ADD CONSTRAINT booking_verification_mail_challenge_id_fkey FOREIGN KEY (challenge_id) REFERENCES appointment_system.booking_verification_challenges(id);

ALTER TABLE ONLY appointment_system.booking_verification_mail
    ADD CONSTRAINT booking_verification_mail_context_id_fkey FOREIGN KEY (context_id) REFERENCES appointment_system.checkout_contexts(id) ON DELETE CASCADE;

ALTER TABLE ONLY appointment_system.bookings
    ADD CONSTRAINT bookings_request_id_context_id_fkey FOREIGN KEY (request_id, context_id) REFERENCES appointment_system.checkout_admissions(request_id, context_id);

ALTER TABLE ONLY appointment_system.checkout_admissions
    ADD CONSTRAINT checkout_admissions_context_id_fkey FOREIGN KEY (context_id) REFERENCES appointment_system.checkout_contexts(id);

ALTER TABLE ONLY appointment_system.checkout_contexts
    ADD CONSTRAINT checkout_contexts_verification_id_fkey FOREIGN KEY (verification_id) REFERENCES appointment_system.booking_verification_challenges(id) ON DELETE SET NULL;

ALTER TABLE ONLY appointment_system.company_credentials
    ADD CONSTRAINT company_credentials_subject_fkey FOREIGN KEY (subject) REFERENCES appointment_system.control_company_identities(subject);

ALTER TABLE ONLY appointment_system.company_login_attempts
    ADD CONSTRAINT company_login_attempts_subject_fkey FOREIGN KEY (subject) REFERENCES appointment_system.company_credentials(subject);

ALTER TABLE ONLY appointment_system.control_command_progress
    ADD CONSTRAINT control_command_progress_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES appointment_system.control_operations(id);

ALTER TABLE ONLY appointment_system.control_company_sessions
    ADD CONSTRAINT control_company_sessions_subject_fkey FOREIGN KEY (subject) REFERENCES appointment_system.control_company_identities(subject);

ALTER TABLE ONLY appointment_system.control_grant_repairs
    ADD CONSTRAINT control_grant_repairs_issuer_fkey FOREIGN KEY (issuer) REFERENCES appointment_system.control_company_identities(subject);

ALTER TABLE ONLY appointment_system.control_maintenance_control_actions
    ADD CONSTRAINT control_maintenance_control_actions_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES appointment_system.control_operations(id);

ALTER TABLE ONLY appointment_system.control_privacy_completions
    ADD CONSTRAINT control_privacy_completions_intent_id_fkey FOREIGN KEY (intent_id) REFERENCES appointment_system.control_privacy_intents(id);

ALTER TABLE ONLY appointment_system.control_privacy_documents
    ADD CONSTRAINT control_privacy_documents_intent_id_fkey FOREIGN KEY (intent_id) REFERENCES appointment_system.control_privacy_intents(id);

ALTER TABLE ONLY appointment_system.control_privacy_exports
    ADD CONSTRAINT control_privacy_exports_intent_id_fkey FOREIGN KEY (intent_id) REFERENCES appointment_system.control_privacy_intents(id);

ALTER TABLE ONLY appointment_system.control_privacy_intents
    ADD CONSTRAINT control_privacy_intents_policy_id_fkey FOREIGN KEY (policy_id) REFERENCES appointment_system.control_privacy_policies(id);

ALTER TABLE ONLY appointment_system.control_privacy_policy_approvals
    ADD CONSTRAINT control_privacy_policy_approvals_policy_id_fkey FOREIGN KEY (policy_id) REFERENCES appointment_system.control_privacy_policies(id);

ALTER TABLE ONLY appointment_system.control_privacy_replay_progress
    ADD CONSTRAINT control_privacy_replay_progress_restore_operation_fkey FOREIGN KEY (restore_operation) REFERENCES appointment_system.control_restore_operations(id);

ALTER TABLE ONLY appointment_system.control_product_state
    ADD CONSTRAINT control_product_state_winning_operation_fkey FOREIGN KEY (winning_operation) REFERENCES appointment_system.control_operations(id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY appointment_system.control_publications
    ADD CONSTRAINT control_publications_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES appointment_system.control_operations(id);

ALTER TABLE ONLY appointment_system.control_restore_completions
    ADD CONSTRAINT control_restore_completions_operation_id_fkey FOREIGN KEY (operation_id) REFERENCES appointment_system.control_restore_operations(id);

ALTER TABLE ONLY appointment_system.delivery_jobs
    ADD CONSTRAINT delivery_jobs_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.email_observations
    ADD CONSTRAINT email_observations_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.delivery_jobs(id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_enquiry_job_id_fkey FOREIGN KEY (enquiry_job_id) REFERENCES appointment_system.enquiry_delivery_jobs(id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.delivery_jobs(id);

ALTER TABLE ONLY appointment_system.email_reservations
    ADD CONSTRAINT email_reservations_verification_job_id_fkey FOREIGN KEY (verification_job_id) REFERENCES appointment_system.booking_verification_mail(id);

ALTER TABLE ONLY appointment_system.enquiry_delivery_jobs
    ADD CONSTRAINT enquiry_delivery_jobs_request_id_fkey FOREIGN KEY (request_id) REFERENCES appointment_system.enquiries(request_id);

ALTER TABLE ONLY appointment_system.enquiry_email_observations
    ADD CONSTRAINT enquiry_email_observations_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.enquiry_delivery_jobs(id);

ALTER TABLE ONLY appointment_system.enquiry_resends
    ADD CONSTRAINT enquiry_resends_request_id_fkey FOREIGN KEY (request_id) REFERENCES appointment_system.enquiries(request_id);

ALTER TABLE ONLY appointment_system.enquiry_sheet_rows
    ADD CONSTRAINT enquiry_sheet_rows_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.enquiry_delivery_jobs(id);

ALTER TABLE ONLY appointment_system.enquiry_sheet_rows
    ADD CONSTRAINT enquiry_sheet_rows_role_fkey FOREIGN KEY (role) REFERENCES appointment_system.google_workbooks(role);

ALTER TABLE ONLY appointment_system.enquiry_sheet_rows
    ADD CONSTRAINT enquiry_sheet_rows_role_volume_number_fkey FOREIGN KEY (role, volume_number) REFERENCES appointment_system.google_workbook_volumes(role, volume_number);

ALTER TABLE ONLY appointment_system.financial_resource_facts
    ADD CONSTRAINT financial_resource_facts_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.financial_resource_states
    ADD CONSTRAINT financial_resource_states_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.financial_resource_states
    ADD CONSTRAINT financial_resource_states_latest_fact_id_fkey FOREIGN KEY (latest_fact_id) REFERENCES appointment_system.financial_resource_facts(id);

ALTER TABLE ONLY appointment_system.google_attempts
    ADD CONSTRAINT google_attempts_session_digest_fkey FOREIGN KEY (session_digest) REFERENCES appointment_system.studio_sessions(digest);

ALTER TABLE ONLY appointment_system.google_connections
    ADD CONSTRAINT google_connections_role_fkey FOREIGN KEY (role) REFERENCES appointment_system.studio_identities(role);

ALTER TABLE ONLY appointment_system.google_resource_attempts
    ADD CONSTRAINT google_resource_attempts_resource_fkey FOREIGN KEY (resource) REFERENCES appointment_system.google_resources(resource);

ALTER TABLE ONLY appointment_system.google_resource_owner_links
    ADD CONSTRAINT google_resource_owner_links_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES appointment_system.google_resource_attempts(id);

ALTER TABLE ONLY appointment_system.google_resource_owner_links
    ADD CONSTRAINT google_resource_owner_links_resource_fkey FOREIGN KEY (resource) REFERENCES appointment_system.google_resources(resource);

ALTER TABLE ONLY appointment_system.google_resources
    ADD CONSTRAINT google_resources_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES appointment_system.google_resource_grants(id);

ALTER TABLE ONLY appointment_system.google_workbook_volumes
    ADD CONSTRAINT google_workbook_volumes_grant_id_fkey FOREIGN KEY (grant_id) REFERENCES appointment_system.google_resource_grants(id);

ALTER TABLE ONLY appointment_system.intake_settings
    ADD CONSTRAINT intake_settings_policy_version_fkey FOREIGN KEY (policy_version) REFERENCES appointment_system.booking_policies(version);

ALTER TABLE ONLY appointment_system.meeting_events
    ADD CONSTRAINT meeting_events_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.payment_cases
    ADD CONSTRAINT payment_cases_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.payment_observations
    ADD CONSTRAINT payment_observations_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.payment_orders
    ADD CONSTRAINT payment_orders_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.receipt_recoveries
    ADD CONSTRAINT receipt_recoveries_request_id_fkey FOREIGN KEY (request_id) REFERENCES appointment_system.bookings(request_id);

ALTER TABLE ONLY appointment_system.recovery_lane_incidents
    ADD CONSTRAINT recovery_lane_incidents_lane_fkey FOREIGN KEY (lane) REFERENCES appointment_system.recovery_lanes(lane);

ALTER TABLE ONLY appointment_system.checkout_contexts
    ADD CONSTRAINT same_context_checkout FOREIGN KEY (active_checkout_id, id) REFERENCES appointment_system.bookings(id, context_id);

ALTER TABLE ONLY appointment_system.sheet_rows
    ADD CONSTRAINT sheet_rows_job_id_fkey FOREIGN KEY (job_id) REFERENCES appointment_system.delivery_jobs(id);

ALTER TABLE ONLY appointment_system.sheet_rows
    ADD CONSTRAINT sheet_rows_role_fkey FOREIGN KEY (role) REFERENCES appointment_system.google_workbooks(role);

ALTER TABLE ONLY appointment_system.sheet_rows
    ADD CONSTRAINT sheet_rows_role_volume_number_fkey FOREIGN KEY (role, volume_number) REFERENCES appointment_system.google_workbook_volumes(role, volume_number);

ALTER TABLE ONLY appointment_system.slot_claims
    ADD CONSTRAINT slot_claims_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.staff_appointment_actions
    ADD CONSTRAINT staff_appointment_actions_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES appointment_system.bookings(id);

ALTER TABLE ONLY appointment_system.staff_appointment_actions
    ADD CONSTRAINT staff_appointment_actions_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES appointment_system.slot_claims(id);

ALTER TABLE ONLY appointment_system.staff_calendar_actions
    ADD CONSTRAINT staff_calendar_actions_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES appointment_system.slot_claims(id);

ALTER TABLE ONLY appointment_system.staff_reviews
    ADD CONSTRAINT staff_reviews_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES appointment_system.payment_observations(id);

ALTER TABLE ONLY appointment_system.staff_reviews
    ADD CONSTRAINT staff_reviews_resource_evidence_id_fkey FOREIGN KEY (resource_evidence_id) REFERENCES appointment_system.financial_resource_facts(id);

ALTER TABLE ONLY appointment_system.studio_sessions
    ADD CONSTRAINT studio_sessions_role_fkey FOREIGN KEY (role) REFERENCES appointment_system.studio_identities(role);

ALTER TABLE ONLY appointment_system.worker_lane_evaluations
    ADD CONSTRAINT worker_lane_evaluations_lane_fkey FOREIGN KEY (lane) REFERENCES appointment_system.worker_lane_turns(lane);

ALTER TABLE ONLY appointment_system.worker_lane_evaluations
    ADD CONSTRAINT worker_lane_evaluations_run_id_fkey FOREIGN KEY (run_id) REFERENCES appointment_system.worker_runs(id);


-- General enquiries are independent and open; mail allocation requires explicit connection provisioning.
INSERT INTO appointment_system.contact_intake(id,public_open) VALUES(true,true);
INSERT INTO appointment_system.email_policy DEFAULT VALUES;
INSERT INTO appointment_system.worker_lane_turns(lane,next_resource) SELECT lane,0 FROM unnest(ARRAY['verification_email','payment_events','payment','booking_records','email_events','notification_email','enquiry_records','maintenance','control_publication'])lane;
INSERT INTO appointment_system.control_privacy_policies(id,kind,version,minimum_days) VALUES ('abandoned-enquiry-v1','abandoned_enquiry',1,7),('routine-incidents-v1','routine_incident',1,30),('resolved-transport-v1','resolved_transport',1,90);
REVOKE ALL ON SCHEMA appointment_system FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA appointment_system FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA appointment_system FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA appointment_system FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA appointment_system REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_web_access;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_staff_access;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_worker_access;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_company_access;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_backup_access;
GRANT USAGE ON SCHEMA appointment_system TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.abandon_unattempted(uuid,uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.admit_checkout(uuid,uuid,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.adopt_mail_acceptance(text,uuid,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.advance_order_search(uuid,uuid,integer,text[],boolean) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_checkout_launchable(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_consume_limit(text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_context_snapshot(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_create_context(uuid,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_create_context(uuid,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_enquiry_protection(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_enquiry_verification_context(uuid,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_find_order(text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_find_order(text,text,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_order_intent(uuid,uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_order_intent(uuid,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_payment_intake() TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_receipt_snapshot(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_receipt_snapshot(uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_resend_enquiry(uuid,text,uuid,integer,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_save_provider_event(text,text,text,text,text,jsonb) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_save_provider_event(text,text,text,text,text,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_scheduling_snapshot(timestamp with time zone,timestamp with time zone) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_start_enquiry(uuid,text,text,jsonb,text,text,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_wake_payment_recovery(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.api_wake_payment_recovery(uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.assign_enquiry_row(text,uuid,uuid,integer,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.assign_sheet_row(text,uuid,uuid,integer,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.authorize_resource_operation(text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.available_times(text,date,integer) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_booking_code(uuid,uuid,text,text,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_contact_send(uuid,uuid,text,text,bigint,uuid,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_email_send(uuid,uuid,jsonb,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_enquiry_send(uuid,uuid,text,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_google_workbook_create(text,uuid,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_google_workbook_create(text,uuid,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_google_workbook_create(text,uuid,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_recovery_run(uuid,text,bigint) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_scoped_contact_mail(uuid,uuid,text,text,jsonb,bigint,uuid,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.begin_scoped_mail(text,uuid,uuid,jsonb,text,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.booking_verification_metadata(uuid,uuid,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_booking_code(uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_checkout_resume(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_email_delivery() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_enquiry_delivery(text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_financial_resources(text,text,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_delivery() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource(text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_resource_refresh(text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_workbook_v2(text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_workbook_v2(text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_google_workbook_v2(text,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_payment_events(integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_payment_recovery(integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.claim_recovery_turn(uuid,text,uuid,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.cleanup_temporary_records() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_business_settings(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_credential_begin(text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_credential_finish(text,text,uuid,bigint,boolean,text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_login_begin(text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_login_finish(uuid,bigint,boolean,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_save_business_settings(text,text,uuid,bigint,jsonb,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.company_session_touch(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.complete_recovery_turn(uuid,text,uuid,uuid,text,integer,boolean,boolean) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.consume_request_limit(text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.consume_request_limit(text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.consume_resource_consent(text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.consume_resource_consent(text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_admission(uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_admission(uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_admission(uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_claim_probe() TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_claim_probe() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_claim_publication() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_claim_publication() TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_command(text,text,uuid,uuid,bigint,boolean,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_command_result(text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_confirm_restore(uuid,jsonb,bigint,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_control_status(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_finish_publication(uuid,uuid,jsonb,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_finish_publication(uuid,uuid,jsonb,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_obligation_action(text,text,text,text,jsonb) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_obligation_summary(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_privacy_apply(uuid) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_privacy_attach_export(uuid,bigint,text,text,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_privacy_candidates(text,integer,uuid,uuid) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_privacy_record_intent(uuid,text,uuid,text,bigint) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_privacy_replay_apply(uuid,uuid) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_probe_retry(uuid,uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_probe_retry(uuid,uuid,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_publication_schedule() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_publication_schedule() TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_record_probe(uuid,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_record_probe(uuid,jsonb) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_restore_barrier(uuid,jsonb) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.control_session_end(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.enquiry_view(uuid,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.expire_enquiry_codes() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.expire_holds() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_booking_code(uuid,uuid,uuid,text,boolean,integer,boolean) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_enquiry_delivery(uuid,uuid,text,text,boolean,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_financial_resource(uuid,uuid,integer,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_delivery(uuid,uuid,text,text,text,text,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_resource_refresh(text,uuid,bigint,bigint,uuid,text,timestamp with time zone,jsonb,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_resource_refresh(text,uuid,bigint,bigint,uuid,text,timestamp with time zone,jsonb,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_resource_refresh(text,uuid,bigint,bigint,uuid,text,timestamp with time zone,jsonb,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_workbook(text,uuid,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_workbook(text,uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_google_workbook(text,uuid,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_mail_attempt(text,uuid,uuid,uuid,text,text,boolean,integer,boolean) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_payment_event(text,text,text,uuid,boolean,integer,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_payment_recovery(uuid,uuid,integer,integer,integer,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_recovery_run(uuid,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_resource_consent(text,text,text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.finish_resource_consent(text,text,text,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.issue_resource_owner_link(text,text,uuid,text,uuid,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.mapped_google_row(text,uuid,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.observe_financial_resource(uuid,text,text,text,jsonb,text,text,jsonb) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.observe_payment(uuid,uuid,text,text,text,text,text,text,text,bigint,text,bigint,boolean) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.observe_payment(uuid,uuid,text,text,text,text,text,text,text,bigint,text,bigint,boolean) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.owner_resource_link_context(uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.pending_resource_consents(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.privacy_finish_replay(uuid,uuid,bigint,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.privacy_freeze(uuid,jsonb) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.privacy_required_sequence() TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.privacy_restore_intent(jsonb,bigint,text,text,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.privacy_saved_intent(uuid) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.public_policy() TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.read_operation_incidents(text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.reconcile_booking_code_email_event() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.reconcile_email_event() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.reconcile_enquiry_email_event() TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_operation_incident(uuid,text,text,text,integer) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_operation_incident(uuid,text,text,text,integer) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_operation_incident(uuid,text,text,text,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_operation_incident(uuid,text,text,text,integer) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_order_creation(uuid,uuid,text,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.record_order_creation(uuid,uuid,text,text,text,text) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.require_job_claim(text,uuid,uuid,integer,uuid,uuid,text,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.require_job_claim(text,uuid,uuid,integer,uuid,uuid,text,integer) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.require_worker_turn(uuid,text,uuid,text,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.resend_booking_verification(uuid,uuid,uuid,text,integer,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.resend_enquiry(uuid,text,uuid,integer,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.resource_connection_status(text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.resource_connection_status(text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_claim_probe() TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_claim_publication() TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_current() TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_finish_publication(uuid,uuid,jsonb,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_probe_retry(uuid,uuid,text) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_record_probe(uuid,jsonb) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.restore_saved(uuid) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.staff_signin_consume(text,text,text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.staff_signin_finish(text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.staff_signin_start(text,text,text,text,text,text,text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.stage_resource_consent(text,uuid,text,text,text,text,jsonb,timestamp with time zone) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.stage_resource_consent(text,uuid,text,text,text,text,jsonb,timestamp with time zone) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_booking_verification(uuid,uuid,text,text,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_enquiry(uuid,text,text,jsonb,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_order_creation(uuid,uuid) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_order_creation(uuid,uuid) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_owner_resource_consent(uuid,text,uuid,text,text,text,uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_resource_consent(text,text,text,text,uuid,text,text,text,text,uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.start_resource_consent(text,text,text,text,uuid,text,text,text,text,uuid,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_action_result(text,text,text,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_action_result(text,text,text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_cancel(text,text,text,uuid,uuid,integer,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_cancel(text,text,text,uuid,uuid,integer,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_detail(text,text,text,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_detail(text,text,text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_reschedule(text,text,text,uuid,uuid,integer,text,timestamp with time zone) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_appointment_reschedule(text,text,text,uuid,uuid,integer,text,timestamp with time zone) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_booking_lookup(text,text,text,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_booking_lookup(text,text,text,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_close(text,text,text,uuid,text,timestamp with time zone,timestamp with time zone) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_close(text,text,text,uuid,text,timestamp with time zone,timestamp with time zone) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_list(text,text,text,date,uuid) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_list(text,text,text,date,uuid) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_month(text,text,text,date) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_month(text,text,text,date) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_reopen(text,text,text,uuid,uuid,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_calendar_reopen(text,text,text,uuid,uuid,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_detail(text,text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_detail(text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_list(text,text,text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_list(text,text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_refund_verified(text,text,text,uuid,text,integer,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_refund_verified(text,text,text,uuid,text,integer,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_resource_reviewed(text,text,text,uuid,text,integer,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_resource_reviewed(text,text,text,uuid,text,integer,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_retry(text,text,text,uuid,text,integer,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_retry(text,text,text,uuid,text,integer,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_review(text,text,text,uuid,text,integer,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_inbox_review(text,text,text,uuid,text,integer,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_logout(text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_logout(text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_session(text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_session(text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_staff_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_worker_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_backup_access;
GRANT EXECUTE ON FUNCTION appointment_system.validate_caller(uuid,text,text,integer) TO appointment_system_maintenance_access;
GRANT EXECUTE ON FUNCTION appointment_system.verify_booking_code(uuid,uuid,uuid,text,integer,text,text,text) TO appointment_system_web_access;
GRANT EXECUTE ON FUNCTION appointment_system.verify_enquiry(uuid,text,integer,text) TO appointment_system_web_access;
GRANT SELECT ON TABLE appointment_system.accepted_payments TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_policies TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_verification_actions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_verification_challenges TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_verification_email_observations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_verification_grants TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.booking_verification_mail TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.bookings TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.caller_logins TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.checkout_admissions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.checkout_contexts TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.company_configuration_actions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.company_credentials TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.company_login_attempts TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.company_security_events TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.contact_intake TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_command_progress TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_company_enrolment_evidence TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_company_identities TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_company_sessions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_grant_repairs TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_login_challenges TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_login_limits TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_maintenance_control_actions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_operations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_completions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_documents TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_exports TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_intents TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_policies TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_policy_approvals TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_privacy_replay_progress TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_product_state TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_publications TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_restore_completions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.control_restore_operations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.delivery_jobs TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.email_observations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.email_policy TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.email_reservations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.enquiries TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.enquiry_delivery_jobs TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.enquiry_email_observations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.enquiry_resends TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.enquiry_sheet_rows TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.financial_resource_facts TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.financial_resource_states TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_attempts TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_connections TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_resource_attempts TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_resource_grants TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_resource_owner_links TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_resources TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_sheet_connections TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_workbook_volumes TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.google_workbooks TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.installation TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.intake_settings TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.mail_acceptance_claims TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.mail_connection TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.meeting_events TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.operational_incidents TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.payment_cases TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.payment_observations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.payment_orders TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.provider_inbox TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.receipt_recoveries TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.recovery_due_work TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.recovery_lane_incidents TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.recovery_lanes TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.request_limits TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.schema_migrations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.sheet_rows TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.slot_claims TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.staff_appointment_actions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.staff_calendar_actions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.staff_reviews TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.studio_audit TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.studio_identities TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.studio_sessions TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.transport_attempt_events TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.worker_lane_evaluations TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.worker_lane_turns TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.worker_release TO appointment_system_backup_access;
GRANT SELECT ON TABLE appointment_system.worker_runs TO appointment_system_backup_access;
GRANT SELECT ON ALL TABLES IN SCHEMA appointment_system TO appointment_system_backup_access;
RESET ROLE;
