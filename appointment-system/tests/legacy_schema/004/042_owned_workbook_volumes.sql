-- Keep old mapped rows in their original owner-verified file. New allocations
-- use a new once-only creation intent before either tab reaches its boundary.
CREATE TABLE sarsa_booking.google_workbook_volumes (
 role text NOT NULL REFERENCES sarsa_booking.studio_identities(role),
 volume_number bigint NOT NULL CHECK(volume_number>0),
 generation uuid NOT NULL DEFAULT gen_random_uuid(),
 layout_version integer NOT NULL CHECK(layout_version IN (1,2)),
 intent uuid NOT NULL UNIQUE, subject text NOT NULL, client_id text NOT NULL,
 spreadsheet_id text UNIQUE,
 state text NOT NULL CHECK(state IN ('creating','ready','retired')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(role,volume_number),
 CHECK(state='creating' OR spreadsheet_id IS NOT NULL)
);
ALTER TABLE sarsa_booking.google_workbooks ADD COLUMN volume_number bigint NOT NULL DEFAULT 1,
 ADD COLUMN layout_version integer NOT NULL DEFAULT 1 CHECK(layout_version IN (1,2)),
 ADD COLUMN creation_attempt_at timestamptz;
UPDATE sarsa_booking.google_workbooks SET creation_attempt_at=clock_timestamp() WHERE state='creating';
INSERT INTO sarsa_booking.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,spreadsheet_id,state)
 SELECT role,1,1,intent,subject,client_id,spreadsheet_id,state FROM sarsa_booking.google_workbooks;
ALTER TABLE sarsa_booking.sheet_rows ADD COLUMN volume_number bigint NOT NULL DEFAULT 1;
ALTER TABLE sarsa_booking.enquiry_sheet_rows ADD COLUMN volume_number bigint NOT NULL DEFAULT 1;
ALTER TABLE sarsa_booking.sheet_rows DROP CONSTRAINT sheet_rows_role_row_number_key;
ALTER TABLE sarsa_booking.enquiry_sheet_rows DROP CONSTRAINT enquiry_sheet_rows_role_row_number_key;
ALTER TABLE sarsa_booking.sheet_rows ADD UNIQUE(role,volume_number,row_number),
 ADD FOREIGN KEY(role,volume_number) REFERENCES sarsa_booking.google_workbook_volumes(role,volume_number);
ALTER TABLE sarsa_booking.enquiry_sheet_rows ADD UNIQUE(role,volume_number,row_number),
 ADD FOREIGN KEY(role,volume_number) REFERENCES sarsa_booking.google_workbook_volumes(role,volume_number);

CREATE FUNCTION sarsa_booking.protect_workbook_volume() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.role,NEW.volume_number,NEW.generation,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.created_at)
  IS DISTINCT FROM ROW(OLD.role,OLD.volume_number,OLD.generation,OLD.layout_version,OLD.intent,OLD.subject,OLD.client_id,OLD.created_at)
  OR (OLD.spreadsheet_id IS NOT NULL AND NEW.spreadsheet_id IS DISTINCT FROM OLD.spreadsheet_id)
  OR (OLD.state='retired' AND NEW.state<>'retired')
  OR (OLD.state='ready' AND NEW.state NOT IN ('ready','retired')) THEN
  RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='immutable workbook identity';
 END IF;
 RETURN NEW;
END $body$;
CREATE TRIGGER workbook_volume_identity BEFORE UPDATE OR DELETE ON sarsa_booking.google_workbook_volumes
 FOR EACH ROW EXECUTE FUNCTION sarsa_booking.protect_workbook_volume();
REVOKE ALL ON sarsa_booking.google_workbook_volumes FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON sarsa_booking.google_workbook_volumes TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.seed_workbook_volume() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 INSERT INTO sarsa_booking.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,spreadsheet_id,state)
 VALUES(NEW.role,NEW.volume_number,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.spreadsheet_id,NEW.state);
 IF NEW.layout_version=1 AND NEW.state='creating' THEN
  UPDATE sarsa_booking.google_workbooks SET creation_attempt_at=clock_timestamp() WHERE role=NEW.role;
 END IF;
 RETURN NEW;
END $body$;
CREATE TRIGGER workbook_volume_seed AFTER INSERT ON sarsa_booking.google_workbooks
 FOR EACH ROW EXECUTE FUNCTION sarsa_booking.seed_workbook_volume();
REVOKE ALL ON FUNCTION sarsa_booking.seed_workbook_volume() FROM PUBLIC;

CREATE FUNCTION sarsa_booking.claim_google_workbook_v2(p_role text,p_client text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE g sarsa_booking.google_connections%ROWTYPE; w sarsa_booking.google_workbooks%ROWTYPE;
 v sarsa_booking.google_workbook_volumes%ROWTYPE; token uuid; action text;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_client IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 SELECT * INTO g FROM sarsa_booking.google_connections WHERE role=p_role AND client_id=p_client;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role FOR UPDATE;
 token:=gen_random_uuid();
 IF NOT FOUND THEN
  INSERT INTO sarsa_booking.google_workbooks(role,subject,client_id,layout_version,state,lease,lease_until,connection_revision)
   VALUES(p_role,g.subject,p_client,2,'creating',token,clock_timestamp()+interval '180 seconds',g.revision) RETURNING * INTO w;
  action:='create';
 ELSE
  IF w.subject<>g.subject OR w.client_id<>p_client THEN RETURN NULL; END IF;
  IF w.state='ready' AND greatest(w.next_row,w.next_enquiry_row)>=9000 THEN
   UPDATE sarsa_booking.google_workbook_volumes SET state='retired' WHERE role=p_role AND volume_number=w.volume_number;
   UPDATE sarsa_booking.google_workbooks SET volume_number=volume_number+1,intent=gen_random_uuid(),spreadsheet_id=NULL,
    state='creating',layout_version=2,creation_attempt_at=NULL,next_row=2,next_enquiry_row=2,lease=token,lease_until=clock_timestamp()+interval '180 seconds',
    connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
   INSERT INTO sarsa_booking.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,state)
    VALUES(p_role,w.volume_number,2,w.intent,w.subject,w.client_id,'creating');
   action:='create';
  ELSIF w.state='ready' THEN action:='ready';
  ELSE
   IF w.lease_until>clock_timestamp() AND w.connection_revision=g.revision THEN RETURN NULL; END IF;
   UPDATE sarsa_booking.google_workbooks SET lease=token,lease_until=clock_timestamp()+interval '180 seconds',
    connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
   action:=CASE WHEN w.creation_attempt_at IS NULL THEN 'create' ELSE 'discover' END;
  END IF;
 END IF;
 SELECT * INTO v FROM sarsa_booking.google_workbook_volumes WHERE role=p_role AND volume_number=w.volume_number;
 RETURN to_jsonb(w)||jsonb_build_object('action',action,'generation',v.generation,'layout_version',v.layout_version);
END $body$;

CREATE FUNCTION sarsa_booking.begin_google_workbook_create(p_role text,p_lease uuid,p_intent uuid)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
 UPDATE sarsa_booking.google_workbooks w SET creation_attempt_at=clock_timestamp()
 WHERE role=p_role AND lease=p_lease AND intent=p_intent AND state='creating' AND creation_attempt_at IS NULL
  AND lease_until>clock_timestamp() AND EXISTS(SELECT 1 FROM sarsa_booking.google_connections g WHERE g.role=w.role
   AND g.subject=w.subject AND g.client_id=w.client_id AND g.revision=w.connection_revision);
 GET DIAGNOSTICS changed=ROW_COUNT;
 RETURN changed=1;
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.begin_google_workbook_create(text,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.begin_google_workbook_create(text,uuid,uuid) TO sarsa_booking_runtime;

CREATE OR REPLACE FUNCTION sarsa_booking.finish_google_workbook(p_role text,p_lease uuid,p_file text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE w sarsa_booking.google_workbooks%ROWTYPE;
BEGIN
 IF p_file IS NULL OR p_file !~ '^[A-Za-z0-9_-]{1,200}$' THEN RETURN false; END IF;
 UPDATE sarsa_booking.google_workbooks x SET spreadsheet_id=p_file,state='ready',lease=NULL,lease_until=NULL
 WHERE role=p_role AND lease=p_lease AND lease_until>clock_timestamp() AND state='creating'
 AND EXISTS(SELECT 1 FROM sarsa_booking.google_connections g WHERE g.role=x.role AND g.subject=x.subject
  AND g.client_id=x.client_id AND g.revision=x.connection_revision) RETURNING * INTO w;
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE sarsa_booking.google_workbook_volumes SET spreadsheet_id=p_file,state='ready'
  WHERE role=p_role AND volume_number=w.volume_number AND intent=w.intent AND state='creating';
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='missing workbook identity'; END IF;
 RETURN true;
END $body$;

CREATE FUNCTION sarsa_booking.mapped_google_row(p_role text,p_job uuid,p_kind text) RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE result jsonb;
BEGIN
 IF p_role NOT IN ('client','agency') OR p_role IS NULL THEN RETURN NULL; END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(v)||jsonb_build_object('row',r.row_number,'values',r.values_json,'action','mapped') INTO result
   FROM sarsa_booking.sheet_rows r JOIN sarsa_booking.google_workbook_volumes v USING(role,volume_number)
   WHERE r.role=p_role AND r.job_id=p_job AND v.state IN ('ready','retired');
 ELSIF p_kind='enquiry' THEN
  SELECT to_jsonb(v)||jsonb_build_object('row',r.row_number,'values',r.values_json,'action','mapped') INTO result
   FROM sarsa_booking.enquiry_sheet_rows r JOIN sarsa_booking.google_workbook_volumes v USING(role,volume_number)
   WHERE r.role=p_role AND r.job_id=p_job AND v.state IN ('ready','retired');
 END IF;
 RETURN result;
END $body$;

CREATE OR REPLACE FUNCTION sarsa_booking.assign_sheet_row(p_role text,p_job uuid,p_values jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE w sarsa_booking.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values)<>12 OR p_values->>0 IS DISTINCT FROM '004-sarsa-jyotish-sansthan'
  OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs j WHERE j.id=p_job AND j.kind='sheet_booking'
  AND j.recipient_role=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
  AND j.booking_id::text=p_values->>2 AND j.booking_revision::text=p_values->>3) THEN RETURN NULL; END IF;
 old:=sarsa_booking.mapped_google_row(p_role,p_job,'booking');
 IF old IS NOT NULL THEN
  IF old->'values' IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN old;
 END IF;
 SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 INSERT INTO sarsa_booking.sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_row,p_values,w.volume_number);
 UPDATE sarsa_booking.google_workbooks SET next_row=next_row+1 WHERE role=p_role;
 RETURN sarsa_booking.mapped_google_row(p_role,p_job,'booking');
END $body$;

CREATE OR REPLACE FUNCTION sarsa_booking.assign_enquiry_row(p_role text,p_job uuid,p_values jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE w sarsa_booking.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (10,12) OR p_values->>0 IS DISTINCT FROM '004-sarsa-jyotish-sansthan'
  OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs j JOIN sarsa_booking.enquiries e USING(request_id)
  WHERE j.id=p_job AND j.kind=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
  AND j.request_id::text=p_values->>2 AND e.verified_at IS NOT NULL
  AND (p_values->>3)::timestamptz=e.verified_at AND p_values->>4=e.payload->>'name'
  AND p_values->>5=e.payload->>'email' AND p_values->>6=e.payload->>'phone'
  AND p_values->>7=e.payload->>'subject' AND p_values->>8=e.payload->>'message' AND p_values->>9='received'
  AND (jsonb_array_length(p_values)=10 OR (p_values->>10=coalesce(e.payload->>'source','unknown')
   AND p_values->>11=coalesce(e.payload->>'service_interest','')))) THEN RETURN NULL; END IF;
 old:=sarsa_booking.mapped_google_row(p_role,p_job,'enquiry');
 IF old IS NOT NULL THEN
  IF old->'values' IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN old;
 END IF;
 SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF w.layout_version=1 AND jsonb_array_length(p_values)<>10 THEN RETURN NULL; END IF;
 INSERT INTO sarsa_booking.enquiry_sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_enquiry_row,p_values,w.volume_number);
 UPDATE sarsa_booking.google_workbooks SET next_enquiry_row=next_enquiry_row+1 WHERE role=p_role;
 RETURN sarsa_booking.mapped_google_row(p_role,p_job,'enquiry');
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.mapped_google_row(text,uuid,text),sarsa_booking.protect_workbook_volume() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.mapped_google_row(text,uuid,text) TO sarsa_booking_runtime;

REVOKE ALL ON FUNCTION sarsa_booking.claim_google_workbook_v2(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_google_workbook_v2(text,text) TO sarsa_booking_runtime;
