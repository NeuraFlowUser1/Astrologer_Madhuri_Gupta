-- Exclusive control writers must take the barrier before caller validation.
-- The handover guard takes a shared barrier; upgrading it concurrently deadlocks.
-- Keep all caller/session/revision/restore checks and grants unchanged.


CREATE OR REPLACE FUNCTION appointment_system.control_command(p_token text, p_csrf text, p_operation uuid, p_generation uuid, p_revision bigint, p_enabled boolean, p_reason text, p_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM pg_advisory_xact_lock(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['company']); RETURN appointment_system.entry_control_command(p_token, p_csrf, p_operation, p_generation, p_revision, p_enabled, p_reason, p_hash); END $$;

CREATE OR REPLACE FUNCTION appointment_system.control_finish_publication(p_operation uuid, p_lease uuid, p_ack jsonb, p_error text DEFAULT NULL::text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN PERFORM pg_advisory_xact_lock(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker','company']); RETURN appointment_system.entry_control_finish_publication(p_operation, p_lease, p_ack, p_error); END $$;

CREATE OR REPLACE FUNCTION appointment_system.control_confirm_restore(p_operation uuid, p_projection jsonb, p_sequence bigint, p_head_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_restore_operations%ROWTYPE;completed appointment_system.control_restore_completions%ROWTYPE;
 current jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(83124,4);
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

CREATE OR REPLACE FUNCTION appointment_system.control_privacy_replay_apply(p_restore uuid, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    SET "TimeZone" TO 'UTC'
    AS $$
DECLARE intent appointment_system.control_privacy_intents%ROWTYPE;completed appointment_system.control_privacy_completions%ROWTYPE;
 policy appointment_system.control_privacy_policies%ROWTYPE;document jsonb;current_state jsonb;restore_state jsonb;
 target record;intent_time timestamptz;cutoff timestamptz;
BEGIN
 PERFORM pg_advisory_xact_lock(83124,4);
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

CREATE OR REPLACE FUNCTION appointment_system.control_restore_barrier(p_operation uuid, p_external jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE previous appointment_system.control_restore_operations%ROWTYPE;current appointment_system.control_product_state%ROWTYPE;
 external_sequence bigint;result jsonb;archived jsonb;instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM pg_advisory_xact_lock(83124,4);
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

CREATE OR REPLACE FUNCTION appointment_system.privacy_finish_replay(p_operation uuid, p_generation uuid, p_sequence bigint, p_head_hash text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE saved appointment_system.control_privacy_replay_progress%ROWTYPE;current jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(83124,4);
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

CREATE OR REPLACE FUNCTION appointment_system.require_worker_turn(p_run uuid, p_lane text, p_generation uuid, p_release text, p_lease uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 -- Publication can change admission state after validating this turn.
 -- Take its write barrier before any shared state/authority locks.
 IF p_lane='control_publication' THEN
  PERFORM pg_advisory_xact_lock(83124,4);
 ELSE
  PERFORM pg_advisory_xact_lock_shared(83124,4);
 END IF;
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
