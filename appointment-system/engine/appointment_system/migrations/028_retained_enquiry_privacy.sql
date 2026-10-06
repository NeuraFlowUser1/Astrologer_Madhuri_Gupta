-- A comparison copy does not create an exception to approved personal-data
-- erasure. Only the offline handover owner can register a retained source.
SET ROLE appointment_system_owner;
CREATE TABLE appointment_system.conversion_retained_enquiries (
 handover_id uuid NOT NULL REFERENCES appointment_system.conversion_handover(id),
 request_id uuid NOT NULL REFERENCES appointment_system.enquiries(request_id),
 source_schema text NOT NULL CHECK(source_schema ~ '^[a-z][a-z0-9_]{0,62}$' AND source_schema<>'appointment_system'),
 enquiry_hash text NOT NULL CHECK(enquiry_hash ~ '^[a-f0-9]{64}$'),
 job_hashes jsonb NOT NULL CHECK(jsonb_typeof(job_hashes)='object'),
 PRIMARY KEY(source_schema,request_id)
);
CREATE INDEX retained_enquiry_target ON appointment_system.conversion_retained_enquiries(request_id);
REVOKE ALL ON appointment_system.conversion_retained_enquiries FROM PUBLIC;
GRANT SELECT ON appointment_system.conversion_retained_enquiries TO appointment_system_backup_access;
CREATE TRIGGER retained_enquiry_mapping_immutable BEFORE UPDATE OR DELETE
 ON appointment_system.conversion_retained_enquiries FOR EACH ROW
 EXECUTE FUNCTION appointment_system.control_protect_restore_history();

CREATE FUNCTION appointment_system.retained_enquiry_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE permitted text[];
BEGIN
 IF TG_OP<>'UPDATE' OR current_user<>'appointment_system_owner' THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='retained source is read only';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.conversion_retained_enquiries r
  JOIN appointment_system.conversion_handover h ON h.id=r.handover_id
  JOIN appointment_system.control_privacy_intents i ON i.target_id=r.request_id
  JOIN appointment_system.control_privacy_policies p ON p.id=i.policy_id
  JOIN appointment_system.control_privacy_completions c ON c.intent_id=i.id
  WHERE r.source_schema=TG_TABLE_SCHEMA AND r.request_id=OLD.request_id
   AND h.phase='complete' AND p.kind='abandoned_enquiry' AND c.outcome='applied') THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='approved retained erasure required';
 END IF;
 IF TG_TABLE_NAME='enquiries' THEN
  permitted:=ARRAY['payload','code_digest','code_ciphertext'];
  IF NEW.verified_at IS NOT NULL OR NEW.payload<>'{}'::jsonb
   OR NEW.code_digest IS NOT NULL OR NEW.code_ciphertext IS NOT NULL THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='retained enquiry erase only';
  END IF;
 ELSIF TG_TABLE_NAME='enquiry_delivery_jobs' THEN
  permitted:=ARRAY['destination','message_ciphertext','state','lease_token','lease_expires_at'];
  IF NEW.kind<>'verification' OR NEW.destination IS NOT NULL OR NEW.message_ciphertext IS NOT NULL
   OR NEW.state<>'expired' OR NEW.lease_token IS NOT NULL OR NEW.lease_expires_at IS NOT NULL THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='retained delivery erase only';
  END IF;
 ELSE RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='unknown retained relation';
 END IF;
 IF (to_jsonb(NEW)-permitted) IS DISTINCT FROM (to_jsonb(OLD)-permitted) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='retained evidence is immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION appointment_system.retained_enquiry_guard() FROM PUBLIC;

CREATE FUNCTION appointment_system.erase_retained_enquiry() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp SET TimeZone='UTC' AS $$
DECLARE intent appointment_system.control_privacy_intents%ROWTYPE; mapping record;
 actual_hash text; actual_jobs jsonb; source_row jsonb; source_jobs jsonb;
 enquiry_relation regclass; jobs_relation regclass;
BEGIN
 IF NEW.outcome<>'applied' THEN RETURN NEW; END IF;
 SELECT * INTO intent FROM appointment_system.control_privacy_intents WHERE id=NEW.intent_id;
 IF NOT EXISTS(SELECT 1 FROM appointment_system.control_privacy_policies WHERE id=intent.policy_id AND kind='abandoned_enquiry')
 THEN RETURN NEW; END IF;
 FOR mapping IN SELECT r.*,h.phase,h.completed_at FROM appointment_system.conversion_retained_enquiries r
  JOIN appointment_system.conversion_handover h ON h.id=r.handover_id WHERE r.request_id=intent.target_id
  ORDER BY r.source_schema LOOP
  IF mapping.phase<>'complete' THEN RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retained handover incomplete'; END IF;
  enquiry_relation:=to_regclass(format('%I.enquiries',mapping.source_schema));
  jobs_relation:=to_regclass(format('%I.enquiry_delivery_jobs',mapping.source_schema));
  -- New archives contain only the canonical schema. Neither old relation is
  -- present after that restore; an incomplete old copy must instead be reviewed.
  IF enquiry_relation IS NULL AND jobs_relation IS NULL THEN
   IF EXISTS(SELECT 1 FROM appointment_system.control_restore_operations r
    JOIN appointment_system.control_product_state s ON s.singleton
    WHERE r.result_snapshot->>'restore_generation'=s.restore_generation::text
     AND r.created_at>=mapping.completed_at) THEN CONTINUE; END IF;
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retained source absence requires restored generation';
  END IF;
  IF enquiry_relation IS NULL OR jobs_relation IS NULL THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retained source incomplete'; END IF;
  EXECUTE format('SELECT to_jsonb(e),encode(sha256(convert_to(to_jsonb(e)::text,''UTF8'')),''hex'') FROM %I.enquiries e WHERE request_id=$1 FOR UPDATE',mapping.source_schema)
   INTO source_row,actual_hash USING intent.target_id;
  EXECUTE format('SELECT coalesce(jsonb_object_agg(j.id,encode(sha256(convert_to(to_jsonb(j)::text,''UTF8'')),''hex'')),''{}''::jsonb),coalesce(jsonb_agg(to_jsonb(j)),''[]''::jsonb) FROM (SELECT * FROM %I.enquiry_delivery_jobs WHERE request_id=$1 ORDER BY id FOR UPDATE) j',mapping.source_schema)
   INTO actual_jobs,source_jobs USING intent.target_id;
  IF actual_hash IS DISTINCT FROM mapping.enquiry_hash OR actual_jobs IS DISTINCT FROM mapping.job_hashes
   OR source_row->'verified_at' IS DISTINCT FROM 'null'::jsonb
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(source_jobs) j WHERE j->>'kind'<>'verification') THEN
   RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='retained source changed'; END IF;
  EXECUTE format('UPDATE %I.enquiries SET payload=''{}''::jsonb,code_digest=NULL,code_ciphertext=NULL WHERE request_id=$1',mapping.source_schema) USING intent.target_id;
  EXECUTE format('UPDATE %I.enquiry_delivery_jobs SET destination=NULL,message_ciphertext=NULL,state=''expired'',lease_token=NULL,lease_expires_at=NULL WHERE request_id=$1',mapping.source_schema) USING intent.target_id;
 END LOOP;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION appointment_system.erase_retained_enquiry() FROM PUBLIC;
CREATE TRIGGER erase_retained_enquiry AFTER INSERT ON appointment_system.control_privacy_completions
 FOR EACH ROW EXECUTE FUNCTION appointment_system.erase_retained_enquiry();
RESET ROLE;
