-- Historical file/row identities are exact external protocols. New files
-- use v1 and installation-bound layout 3 markers.
ALTER TABLE appointment_system.google_workbook_volumes ADD COLUMN workbook_protocol text NOT NULL DEFAULT 'v1',
 ADD CONSTRAINT workbook_protocol_supported CHECK(workbook_protocol IN('v1','legacy-sarsa-workbook-v1','legacy-sarsa-workbook-v2')),
 ADD CONSTRAINT workbook_protocol_layout CHECK(workbook_protocol='v1' OR
  (workbook_protocol='legacy-sarsa-workbook-v1' AND layout_version=1) OR
  (workbook_protocol='legacy-sarsa-workbook-v2' AND layout_version=2));
CREATE OR REPLACE FUNCTION appointment_system.protect_workbook_volume() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.role,NEW.volume_number,NEW.generation,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.created_at,NEW.grant_id,NEW.workbook_protocol)
  IS DISTINCT FROM ROW(OLD.role,OLD.volume_number,OLD.generation,OLD.layout_version,OLD.intent,OLD.subject,OLD.client_id,OLD.created_at,OLD.grant_id,OLD.workbook_protocol)
  OR (OLD.spreadsheet_id IS NOT NULL AND NEW.spreadsheet_id IS DISTINCT FROM OLD.spreadsheet_id)
  OR (OLD.state='retired' AND NEW.state<>'retired')
  OR (OLD.state='ready' AND NEW.state NOT IN ('ready','retired')) THEN
  RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='immutable workbook identity';
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION appointment_system.seed_workbook_volume() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE prior appointment_system.google_workbook_volumes%ROWTYPE;pinned_grant uuid;
BEGIN
 pinned_grant:=(SELECT grant_id FROM appointment_system.google_resources WHERE resource=CASE WHEN NEW.role='client' THEN 'client_sheet' ELSE 'agency_sheet' END);
 SELECT * INTO prior FROM appointment_system.google_workbook_volumes WHERE role=NEW.role AND volume_number=NEW.volume_number;
 IF FOUND THEN
  IF NOT EXISTS(SELECT 1 FROM appointment_system.conversion_handover WHERE phase='fenced')
   OR ROW(prior.layout_version,prior.intent,prior.subject,prior.client_id,prior.spreadsheet_id,prior.state,prior.grant_id)
   IS DISTINCT FROM ROW(NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.spreadsheet_id,NEW.state,pinned_grant) THEN
   RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='existing workbook identity differs';
  END IF;
  RETURN NEW;
 END IF;
 INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,spreadsheet_id,state,grant_id)
 VALUES(NEW.role,NEW.volume_number,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.spreadsheet_id,NEW.state,pinned_grant);
 IF NEW.layout_version=1 AND NEW.state='creating' THEN
  UPDATE appointment_system.google_workbooks SET creation_attempt_at=clock_timestamp() WHERE role=NEW.role;
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION appointment_system.entry_assign_sheet_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE w appointment_system.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (12,33)
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
 IF p_values->>0 IS DISTINCT FROM appointment_system.installation_value('project_id') THEN RETURN NULL; END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF (w.layout_version IN (1,2) AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>33) THEN RETURN NULL; END IF;
 INSERT INTO appointment_system.sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_row,p_values,w.volume_number);
 UPDATE appointment_system.google_workbooks SET next_row=next_row+1 WHERE role=p_role;
 RETURN appointment_system.mapped_google_row(p_role,p_job,'booking');
END $$;
CREATE OR REPLACE FUNCTION appointment_system.entry_assign_enquiry_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE w appointment_system.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (10,12,15)
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
 IF p_values->>0 IS DISTINCT FROM appointment_system.installation_value('project_id') THEN RETURN NULL; END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF (w.layout_version=1 AND jsonb_array_length(p_values)<>10) OR (w.layout_version=2 AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>15) THEN RETURN NULL; END IF;
 INSERT INTO appointment_system.enquiry_sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_enquiry_row,p_values,w.volume_number);
 UPDATE appointment_system.google_workbooks SET next_enquiry_row=next_enquiry_row+1 WHERE role=p_role;
 RETURN appointment_system.mapped_google_row(p_role,p_job,'enquiry');
END $$;

-- Same external identity as the frozen source calendar protocol.
CREATE OR REPLACE FUNCTION appointment_system.calendar_event_identity(p_booking uuid, p_revision integer, p_protocol text) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF p_booking IS NULL OR p_revision IS NULL OR p_revision<1 THEN RETURN NULL; END IF;
 IF p_protocol='v1' THEN RETURN 'ab'||encode(sha256(convert_to(appointment_system.installation_value('installation_id')||':'||p_booking::text||':'||p_revision::text,'UTF8')),'hex');
 ELSIF p_protocol='legacy-sarsa004' THEN RETURN 'sarsa'||encode(sha256(convert_to('004-sarsa-jyotish-sansthan:'||p_booking::text||':'||p_revision::text,'UTF8')),'hex');
 ELSIF p_protocol IN ('legacy-astro003','legacy-astro003-unversioned') THEN RETURN 'astro'||replace(p_booking::text,'-','')||CASE WHEN p_revision=1 THEN '' ELSE 'r'||to_hex(p_revision) END;
 ELSE RETURN NULL; END IF;
END $$;
