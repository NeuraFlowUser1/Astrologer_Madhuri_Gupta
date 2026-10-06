-- Protected retention is separate from OFF and payment resolution. No policy
-- is approved by this migration; normal serving/control roles get no authority.
CREATE TABLE booking_control.privacy_policies(
 id text PRIMARY KEY,kind text NOT NULL CHECK(kind IN('abandoned_enquiry','routine_incident','resolved_transport')),
 version integer NOT NULL CHECK(version=1),minimum_days integer NOT NULL CHECK(minimum_days BETWEEN 7 AND 3650),
 project text NOT NULL CHECK(project='003'),created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO booking_control.privacy_policies(id,kind,version,minimum_days,project) VALUES
 ('abandoned-enquiry-v1','abandoned_enquiry',1,7,'003'),
 ('routine-incidents-v1','routine_incident',1,30,'003'),
 ('resolved-transport-v1','resolved_transport',1,90,'003');
CREATE TABLE booking_control.privacy_policy_approvals(
 policy_id text PRIMARY KEY REFERENCES booking_control.privacy_policies(id),
 approved_by text NOT NULL CHECK(length(btrim(approved_by)) BETWEEN 3 AND 180),
 approved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.privacy_intents(
 id uuid PRIMARY KEY,policy_id text NOT NULL REFERENCES booking_control.privacy_policies(id),target_id uuid NOT NULL,
 target_hash text NOT NULL CHECK(target_hash~'^[a-f0-9]{64}$'),base_sequence bigint NOT NULL CHECK(base_sequence>=0),created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.privacy_documents(intent_id uuid PRIMARY KEY REFERENCES booking_control.privacy_intents(id),body jsonb NOT NULL CHECK(jsonb_typeof(body)='object' AND octet_length(body::text)<=8192));
CREATE TRIGGER privacy_document_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_documents FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
REVOKE ALL ON booking_control.privacy_documents FROM PUBLIC;
CREATE TABLE booking_control.privacy_exports(
 intent_id uuid PRIMARY KEY REFERENCES booking_control.privacy_intents(id),
 sequence bigint NOT NULL CHECK(sequence>0),entry_hash text NOT NULL CHECK(entry_hash~'^[a-f0-9]{64}$'),
 head_hash text NOT NULL CHECK(head_hash~'^[a-f0-9]{64}$'),file_id text NOT NULL CHECK(file_id~'^[A-Za-z0-9_-]{10,180}$'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.privacy_completions(
 intent_id uuid PRIMARY KEY REFERENCES booking_control.privacy_intents(id),outcome text NOT NULL CHECK(outcome IN('applied','cancelled')),
 reason text NOT NULL CHECK(reason IN('content_erased','eligibility_changed')),
 completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.privacy_replay_progress(
 restore_operation uuid PRIMARY KEY REFERENCES booking_control.restore_operations(id),
 sequence bigint NOT NULL CHECK(sequence>=0),head_hash text NOT NULL CHECK(head_hash~'^[a-f0-9]{64}$'),
 completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON booking_control.privacy_policies,booking_control.privacy_policy_approvals,booking_control.privacy_intents,
 booking_control.privacy_exports,booking_control.privacy_completions,booking_control.privacy_replay_progress FROM PUBLIC;
CREATE TRIGGER privacy_policy_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_policies
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE TRIGGER privacy_approval_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_policy_approvals
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE TRIGGER privacy_intent_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_intents
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE TRIGGER privacy_export_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_exports
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE TRIGGER privacy_completion_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_completions
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE TRIGGER privacy_replay_immutable BEFORE UPDATE OR DELETE ON booking_control.privacy_replay_progress
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_restore_history();
CREATE FUNCTION booking_control.privacy_candidates(p_policy text,p_limit integer DEFAULT 100,p_after uuid DEFAULT NULL,p_exact uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp SET TimeZone='UTC' AS $body$
DECLARE policy booking_control.privacy_policies%ROWTYPE;records jsonb;
BEGIN
 IF p_policy IS NULL OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention inspection'; END IF;
 SELECT * INTO policy FROM booking_control.privacy_policies WHERE id=p_policy;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='unknown retention policy'; END IF;
 IF policy.kind='routine_incident' THEN
  SELECT coalesce(jsonb_agg(x ORDER BY x.id),'[]'::jsonb) INTO records FROM
   (SELECT id,encode(sha256(convert_to(to_jsonb(i)::text,'UTF8')),'hex') AS target_hash
    FROM public.operational_incidents i WHERE last_seen_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
      AND (p_after IS NULL OR id>p_after) AND (p_exact IS NULL OR id=p_exact) ORDER BY id LIMIT p_limit) x;
 ELSIF policy.kind='abandoned_enquiry' THEN
  -- 003 stores no unverified enquiry body; verified inquiries are protected.
  records:='[]'::jsonb;
 ELSE
  -- These implementations retain no separate resolved personal transport log.
  -- Payment/provider/audit history is not such a log and is never selected.
  records:='[]'::jsonb;
 END IF;
 RETURN jsonb_build_object('project','003','environment','production','policy_id',policy.id,'version',policy.version,
  'approved',EXISTS(SELECT 1 FROM booking_control.privacy_policy_approvals WHERE policy_id=policy.id),'targets',records);
END $body$;
CREATE FUNCTION booking_control.privacy_record_intent(p_operation uuid,p_policy text,p_target uuid,p_hash text,p_base bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp SET TimeZone='UTC' AS $body$
DECLARE saved booking_control.privacy_intents%ROWTYPE;candidate jsonb;
BEGIN
 IF p_operation IS NULL OR p_target IS NULL OR p_base IS NULL OR p_base<0 OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention intent'; END IF;
 PERFORM pg_advisory_xact_lock(83125,3);
 SELECT * INTO saved FROM booking_control.privacy_intents WHERE id=p_operation;
 IF FOUND THEN
  IF saved.policy_id IS DISTINCT FROM p_policy OR saved.target_id IS DISTINCT FROM p_target OR saved.target_hash IS DISTINCT FROM p_hash THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retention intent changed'; END IF;
  RETURN to_jsonb(saved)||jsonb_build_object('replayed',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM booking_control.privacy_policy_approvals WHERE policy_id=p_policy) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='owner retention approval required'; END IF;
 SELECT x INTO candidate FROM jsonb_array_elements(booking_control.privacy_candidates(p_policy,1,NULL,p_target)->'targets') x
  WHERE x->>'id'=p_target::text AND x->>'target_hash'=p_hash;
 IF candidate IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retention target changed'; END IF;
 INSERT INTO booking_control.privacy_intents(id,policy_id,target_id,target_hash,base_sequence) VALUES(p_operation,p_policy,p_target,p_hash,p_base) RETURNING * INTO saved;
 RETURN to_jsonb(saved)||jsonb_build_object('replayed',false);
END $body$;
CREATE FUNCTION booking_control.privacy_attach_export(p_operation uuid,p_sequence bigint,p_entry_hash text,p_head_hash text,p_file text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE saved booking_control.privacy_exports%ROWTYPE;
BEGIN
 IF p_operation IS NULL OR p_sequence IS NULL OR p_sequence<1 OR p_entry_hash IS NULL OR p_entry_hash!~'^[a-f0-9]{64}$'
  OR p_head_hash IS NULL OR p_head_hash!~'^[a-f0-9]{64}$' OR p_file IS NULL OR p_file!~'^[A-Za-z0-9_-]{10,180}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid independent retention proof'; END IF;
 PERFORM pg_advisory_xact_lock(83125,3);
 SELECT * INTO saved FROM booking_control.privacy_exports WHERE intent_id=p_operation;
 IF FOUND THEN
  IF saved.sequence IS DISTINCT FROM p_sequence OR saved.entry_hash IS DISTINCT FROM p_entry_hash OR saved.head_hash IS DISTINCT FROM p_head_hash OR saved.file_id IS DISTINCT FROM p_file THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='independent retention proof changed'; END IF;
  RETURN true;
 END IF;
 INSERT INTO booking_control.privacy_exports(intent_id,sequence,entry_hash,head_hash,file_id) VALUES(p_operation,p_sequence,p_entry_hash,p_head_hash,p_file);
 RETURN true;
END $body$;
CREATE FUNCTION booking_control.privacy_apply(p_operation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp SET TimeZone='UTC' AS $body$
DECLARE intent booking_control.privacy_intents%ROWTYPE;completed booking_control.privacy_completions%ROWTYPE;
 policy booking_control.privacy_policies%ROWTYPE;target record;eligible boolean:=false;
BEGIN
 IF p_operation IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid retention operation'; END IF;
 PERFORM pg_advisory_xact_lock(83125,3);
 SELECT * INTO intent FROM booking_control.privacy_intents WHERE id=p_operation;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM booking_control.privacy_exports WHERE intent_id=p_operation) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='independent retention intent required'; END IF;
 SELECT * INTO completed FROM booking_control.privacy_completions WHERE intent_id=p_operation;
 IF FOUND THEN RETURN to_jsonb(completed)||jsonb_build_object('replayed',true); END IF;
 IF NOT EXISTS(SELECT 1 FROM booking_control.privacy_policy_approvals WHERE policy_id=intent.policy_id) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='owner retention approval required'; END IF;
 SELECT * INTO policy FROM booking_control.privacy_policies WHERE id=intent.policy_id;
 IF policy.kind='routine_incident' THEN
  SELECT * INTO target FROM public.operational_incidents WHERE id=intent.target_id FOR UPDATE;
  eligible:=FOUND AND target.last_seen_at<clock_timestamp()-make_interval(days=>policy.minimum_days)
    AND encode(sha256(convert_to(to_jsonb(target)::text,'UTF8')),'hex')=intent.target_hash;
  IF eligible THEN DELETE FROM public.operational_incidents WHERE id=intent.target_id; END IF;
 ELSIF policy.kind='abandoned_enquiry' THEN
  eligible:=false;
 END IF;
 INSERT INTO booking_control.privacy_completions(intent_id,outcome,reason)
 VALUES(p_operation,CASE WHEN eligible THEN 'applied' ELSE 'cancelled' END,CASE WHEN eligible THEN 'content_erased' ELSE 'eligibility_changed' END) RETURNING * INTO completed;
 RETURN to_jsonb(completed)||jsonb_build_object('replayed',false);
END $body$;
REVOKE ALL ON FUNCTION booking_control.privacy_candidates(text,integer,uuid,uuid),booking_control.privacy_record_intent(uuid,text,uuid,text,bigint),
 booking_control.privacy_attach_export(uuid,bigint,text,text,text),booking_control.privacy_apply(uuid) FROM PUBLIC;

-- Recovery of an older archive is deliberately different from live cleanup.
-- Only the verified external terminal history authorizes this owner-only path.
-- Its signed intent time protects any newer activity in the recovered target.
CREATE FUNCTION booking_control.privacy_replay_apply(p_restore uuid,p_operation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp SET TimeZone='UTC' AS $body$
DECLARE intent booking_control.privacy_intents%ROWTYPE;completed booking_control.privacy_completions%ROWTYPE;
 policy booking_control.privacy_policies%ROWTYPE;document jsonb;current_state jsonb;restore_state jsonb;
 target record;intent_time timestamptz;cutoff timestamptz;
BEGIN
 IF p_restore IS NULL OR p_operation IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='invalid privacy recovery operation'; END IF;
 PERFORM pg_advisory_xact_lock(83124,3);
 PERFORM pg_advisory_xact_lock(83125,3);
 SELECT booking_control.snapshot() INTO current_state;
 SELECT result_snapshot INTO restore_state FROM booking_control.restore_operations WHERE id=p_restore;
 IF restore_state IS NULL OR current_state IS DISTINCT FROM restore_state OR current_state->'enabled'<>'false'::jsonb THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='isolated restored generation required'; END IF;
 SELECT * INTO intent FROM booking_control.privacy_intents WHERE id=p_operation;
 SELECT body INTO document FROM booking_control.privacy_documents WHERE intent_id=p_operation;
 IF intent.id IS NULL OR document IS NULL OR NOT EXISTS(SELECT 1 FROM booking_control.privacy_exports WHERE intent_id=p_operation) THEN
  RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='verified independent privacy intent required'; END IF;
 SELECT * INTO completed FROM booking_control.privacy_completions WHERE intent_id=p_operation;
 IF FOUND THEN
  IF completed.outcome<>'applied' THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='privacy recovery outcome changed'; END IF;
  RETURN to_jsonb(completed)||jsonb_build_object('replayed',true);
 END IF;
 SELECT * INTO policy FROM booking_control.privacy_policies WHERE id=intent.policy_id;
 IF NOT EXISTS(SELECT 1 FROM booking_control.privacy_policy_approvals WHERE policy_id=intent.policy_id)
  OR document->>'operation_id' IS DISTINCT FROM intent.id::text OR document->>'policy_id' IS DISTINCT FROM intent.policy_id
  OR document->>'target_id' IS DISTINCT FROM intent.target_id::text OR document->>'target_hash' IS DISTINCT FROM intent.target_hash
  OR document->>'policy_version' IS DISTINCT FROM policy.version::text OR document->>'minimum_days' IS DISTINCT FROM policy.minimum_days::text
  OR document->>'intent_created_at' IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0403',MESSAGE='privacy recovery authorization changed'; END IF;
 intent_time:=(document->>'intent_created_at')::timestamptz;
 IF intent_time>clock_timestamp() THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='future privacy intent rejected'; END IF;
 cutoff:=intent_time-make_interval(days=>policy.minimum_days);
 IF policy.kind='routine_incident' THEN
  SELECT * INTO target FROM public.operational_incidents WHERE id=intent.target_id FOR UPDATE;
  IF FOUND THEN
   IF target.last_seen_at>=cutoff THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='newer activity requires privacy review'; END IF;
   DELETE FROM public.operational_incidents WHERE id=intent.target_id;
  END IF;

 ELSE RAISE EXCEPTION USING ERRCODE='P0422',MESSAGE='unsupported privacy recovery policy';
 END IF;
 INSERT INTO booking_control.privacy_completions(intent_id,outcome,reason) VALUES(p_operation,'applied','content_erased') RETURNING * INTO completed;
 RETURN to_jsonb(completed)||jsonb_build_object('replayed',false);
END $body$;
REVOKE ALL ON FUNCTION booking_control.privacy_replay_apply(uuid,uuid) FROM PUBLIC;

-- An opaque helper result alone cannot certify restored privacy. The protected
-- replay stage records the exact current ledger proof in this recovered target.
CREATE FUNCTION booking_control.guard_privacy_completion() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM booking_control.privacy_replay_progress
   WHERE restore_operation=NEW.operation_id AND sequence=NEW.privacy_sequence AND head_hash=NEW.privacy_head_hash) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='verified privacy replay required'; END IF;
 RETURN NEW;
END $body$;
REVOKE ALL ON FUNCTION booking_control.guard_privacy_completion() FROM PUBLIC;
CREATE TRIGGER verified_privacy_completion BEFORE INSERT ON booking_control.restore_completions
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_privacy_completion();
