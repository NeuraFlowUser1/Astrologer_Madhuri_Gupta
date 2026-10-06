-- Maintenance-only restore barrier. A saved archive never becomes live authority.
CREATE TABLE booking_control.restore_operations(
 id uuid PRIMARY KEY,external_snapshot jsonb NOT NULL,archived_snapshot jsonb NOT NULL,
 result_snapshot jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON booking_control.restore_operations FROM PUBLIC;
CREATE FUNCTION booking_control.protect_restore_history() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='restore history is immutable'; END $body$;
CREATE TRIGGER restore_history_immutable BEFORE UPDATE OR DELETE ON booking_control.restore_operations
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
REVOKE ALL ON FUNCTION booking_control.protect_restore_history() FROM PUBLIC;
CREATE FUNCTION booking_control.restore_barrier(p_operation uuid,p_external jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp AS $body$
DECLARE previous booking_control.restore_operations%ROWTYPE;current booking_control.product_state%ROWTYPE;
 external_sequence bigint;result jsonb;archived jsonb;
BEGIN
 IF p_operation IS NULL OR p_external IS NULL OR jsonb_typeof(p_external) IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery state'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_external))<>9 OR
   p_external->>'project' IS DISTINCT FROM '003' OR p_external->>'environment' IS DISTINCT FROM 'production' OR
   p_external->>'origin' IS DISTINCT FROM 'https://astroadvicebykundansingh.com' OR p_external->>'version' IS DISTINCT FROM '1' OR
   jsonb_typeof(p_external->'version') IS DISTINCT FROM 'number' OR
   jsonb_typeof(p_external->'enabled') IS DISTINCT FROM 'boolean' OR
   jsonb_typeof(p_external->'generation_sequence') IS DISTINCT FROM 'string' OR
   jsonb_typeof(p_external->'revision') IS DISTINCT FROM 'string' OR
   coalesce(p_external->>'generation_sequence','')!~'^[1-9][0-9]{0,18}$' OR
   coalesce(p_external->>'revision','')!~'^[1-9][0-9]{0,18}$' OR
   coalesce(p_external->>'restore_generation','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' OR
   coalesce(p_external->>'activation_epoch','')!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery state'; END IF;
 IF (p_external->>'generation_sequence')::numeric>=9223372036854775807 OR
    (p_external->>'revision')::numeric>9223372036854775807 THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery sequence exhausted'; END IF;
 PERFORM pg_advisory_xact_lock(83124,3);
 SELECT * INTO previous FROM booking_control.restore_operations WHERE id=p_operation;
 IF FOUND THEN
  IF previous.external_snapshot IS DISTINCT FROM p_external OR previous.result_snapshot IS DISTINCT FROM booking_control.snapshot() THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery operation changed'; END IF;
  RETURN jsonb_build_object('operation_id',p_operation,'snapshot',previous.result_snapshot,'replayed',true);
 END IF;
 SELECT * INTO current FROM booking_control.product_state WHERE singleton FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery state unavailable'; END IF;
 external_sequence:=(p_external->>'generation_sequence')::bigint;
 IF external_sequence<current.generation_sequence OR
   (external_sequence=current.generation_sequence AND p_external->>'restore_generation' IS DISTINCT FROM current.restore_generation::text) THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='external recovery generation is inconsistent'; END IF;
 archived:=booking_control.snapshot();
 UPDATE booking_control.product_state SET enabled=false,restore_generation=gen_random_uuid(),
   generation_sequence=external_sequence+1,revision=1,activation_epoch=gen_random_uuid(),
   updated_at=clock_timestamp(),provenance='restore_reconciliation' WHERE singleton;
 result:=booking_control.snapshot();
 UPDATE booking_control.company_sessions SET revoked_at=clock_timestamp() WHERE revoked_at IS NULL;
 DELETE FROM booking_control.login_challenges;
 DELETE FROM public.admin_sessions; DELETE FROM public.admin_login_challenges;
 UPDATE booking_control.publications SET state='superseded',lease_token=NULL,lease_until=NULL
  WHERE state IN('pending','attention');
 UPDATE public.recovery_lanes SET latest_run=NULL,last_attempt_at=NULL,last_completed_at=NULL,active_until=NULL,outcome='unchecked',processed=0;
 INSERT INTO booking_control.restore_operations(id,external_snapshot,archived_snapshot,result_snapshot)
  VALUES(p_operation,p_external,archived,result);
 INSERT INTO booking_control.operations(id,actor_subject,body_hash,expected_generation,expected_revision,target_enabled,reason,result_snapshot)
  VALUES(p_operation,'recovery-maintenance',encode(sha256(convert_to(p_external::text,'UTF8')),'hex'),
    current.restore_generation,current.revision,false,'Restore reconciliation; fresh company sign-in required',result);
 INSERT INTO booking_control.publications(operation_id,snapshot) VALUES(p_operation,result);
 RETURN jsonb_build_object('operation_id',p_operation,'snapshot',result,'replayed',false);
END $body$;
REVOKE ALL ON FUNCTION booking_control.restore_barrier(uuid,jsonb) FROM PUBLIC;
