-- Protected recovery evidence is independent of normal commercial ON/OFF.
-- Only owner maintenance may attest a recovered instance; no command enables it.
CREATE TABLE booking_control.restore_completions(
 operation_id uuid PRIMARY KEY REFERENCES booking_control.restore_operations(id),
 restore_generation uuid NOT NULL UNIQUE,
 projection_snapshot jsonb NOT NULL,
 privacy_sequence bigint NOT NULL CHECK(privacy_sequence>=0),
 privacy_head_hash text NOT NULL CHECK(privacy_head_hash~'^[a-f0-9]{64}$'),
 completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON booking_control.restore_completions FROM PUBLIC;
CREATE TRIGGER restore_completion_immutable BEFORE UPDATE OR DELETE ON booking_control.restore_completions
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE FUNCTION booking_control.confirm_restore(p_operation uuid,p_projection jsonb,p_sequence bigint,p_head_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE saved booking_control.restore_operations%ROWTYPE;completed booking_control.restore_completions%ROWTYPE;
 current jsonb;
BEGIN
 IF p_operation IS NULL OR p_sequence IS NULL OR p_sequence<0 OR p_head_hash IS NULL OR p_head_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid recovery completion'; END IF;
 PERFORM pg_advisory_xact_lock(83124,3);
 SELECT * INTO saved FROM booking_control.restore_operations WHERE id=p_operation;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery operation unavailable'; END IF;
 current:=booking_control.snapshot();
 IF current IS DISTINCT FROM saved.result_snapshot OR p_projection IS DISTINCT FROM current OR
   current->'enabled' IS DISTINCT FROM 'false'::jsonb OR current->>'revision' IS DISTINCT FROM '1' THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery state changed'; END IF;
 SELECT * INTO completed FROM booking_control.restore_completions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF completed.projection_snapshot IS DISTINCT FROM p_projection OR completed.privacy_sequence IS DISTINCT FROM p_sequence OR
     completed.privacy_head_hash IS DISTINCT FROM p_head_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='recovery proof changed'; END IF;
  RETURN jsonb_build_object('operation_id',p_operation,'verified',true,'replayed',true);
 END IF;
 INSERT INTO booking_control.restore_completions(operation_id,restore_generation,projection_snapshot,privacy_sequence,privacy_head_hash)
 VALUES(p_operation,(current->>'restore_generation')::uuid,p_projection,p_sequence,p_head_hash);
 RETURN jsonb_build_object('operation_id',p_operation,'verified',true,'replayed',false);
END $body$;
REVOKE ALL ON FUNCTION booking_control.confirm_restore(uuid,jsonb,bigint,text) FROM PUBLIC;
CREATE FUNCTION booking_control.guard_restored_activation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 IF NEW.enabled AND EXISTS(SELECT 1 FROM booking_control.restore_operations WHERE result_snapshot->>'restore_generation'=NEW.restore_generation::text)
  AND NOT EXISTS(SELECT 1 FROM booking_control.restore_completions WHERE restore_generation=NEW.restore_generation) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='recovery completion required'; END IF;
 RETURN NEW;
END $body$;
REVOKE ALL ON FUNCTION booking_control.guard_restored_activation() FROM PUBLIC;
CREATE TRIGGER restored_activation_guard BEFORE INSERT OR UPDATE ON booking_control.product_state
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_restored_activation();
