-- Protected provisioning evidence and emergency commands share normal history.
CREATE TABLE booking_control.company_enrolment_evidence (
 id uuid PRIMARY KEY, subject text NOT NULL, audience text NOT NULL,
 source_project text NOT NULL CHECK(source_project IN ('003','004')),
 source_hash text NOT NULL CHECK(source_hash~'^[a-f0-9]{64}$'),
 purpose text NOT NULL CHECK(purpose='verified-company-identity'),
 provisioned_by text NOT NULL, at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.maintenance_control_actions (
 operation_id uuid PRIMARY KEY REFERENCES booking_control.operations(id),
 company_subject text NOT NULL, provisioned_by text NOT NULL,
 purpose text NOT NULL CHECK(purpose='protected-emergency-control'),
 body_hash text NOT NULL CHECK(body_hash~'^[a-f0-9]{64}$'),
 at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON booking_control.company_enrolment_evidence,booking_control.maintenance_control_actions FROM PUBLIC;
CREATE FUNCTION booking_control.protect_maintenance_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='company maintenance evidence is immutable'; END $$;
REVOKE ALL ON FUNCTION booking_control.protect_maintenance_evidence() FROM PUBLIC;
CREATE TRIGGER company_enrolment_immutable BEFORE UPDATE OR DELETE ON booking_control.company_enrolment_evidence
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_maintenance_evidence();
CREATE TRIGGER maintenance_control_immutable BEFORE UPDATE OR DELETE ON booking_control.maintenance_control_actions
 FOR EACH ROW EXECUTE FUNCTION booking_control.protect_maintenance_evidence();

CREATE FUNCTION booking_control.maintenance_command(p_subject text,p_operation uuid,p_generation uuid,
 p_revision bigint,p_enabled boolean,p_reason text,p_hash text) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog,booking_control,pg_temp AS $$
DECLARE token text; csrf text; audience text; response jsonb; prior booking_control.maintenance_control_actions%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND(rolsuper OR rolname='neondb_owner'))
  OR current_database() NOT IN ('neondb','sarsa_booking_test')
  OR NOT EXISTS(SELECT 1 FROM booking_control.product_state WHERE singleton AND project='004'
   AND environment='production' AND origin='https://www.sarsajyotishsansthan.com') THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='protected control owner required'; END IF;
 SELECT * INTO prior FROM booking_control.maintenance_control_actions WHERE operation_id=p_operation;
 IF FOUND AND(prior.company_subject IS DISTINCT FROM p_subject OR prior.body_hash IS DISTINCT FROM p_hash) THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='protected command changed'; END IF;
 SELECT i.audience INTO audience FROM booking_control.company_identities i WHERE subject=p_subject AND enabled
  AND 'service_controller'=ANY(capabilities);
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='enrolled controller required'; END IF;
 token:=encode(sha256(convert_to(gen_random_uuid()::text||gen_random_uuid()::text,'UTF8')),'hex');
 csrf:=encode(sha256(convert_to(gen_random_uuid()::text||gen_random_uuid()::text,'UTF8')),'hex');
 PERFORM booking_control.session_start(token,p_subject,'neuraflowindia@gmail.com',audience,csrf);
 response:=booking_control.command(token,csrf,p_operation,p_generation,p_revision,p_enabled,p_reason,p_hash);
 PERFORM booking_control.session_end(token);
 INSERT INTO booking_control.maintenance_control_actions(operation_id,company_subject,provisioned_by,purpose,body_hash)
  VALUES(p_operation,p_subject,current_user,'protected-emergency-control',p_hash) ON CONFLICT(operation_id) DO NOTHING;
 RETURN response;
END $$;
REVOKE ALL ON FUNCTION booking_control.maintenance_command(text,uuid,uuid,bigint,boolean,text,text) FROM PUBLIC;
