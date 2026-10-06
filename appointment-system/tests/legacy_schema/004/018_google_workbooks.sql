CREATE TABLE sarsa_booking.google_workbooks (
    role text PRIMARY KEY REFERENCES sarsa_booking.studio_identities(role),
    intent uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    subject text NOT NULL,
    client_id text NOT NULL,
    spreadsheet_id text UNIQUE,
    state text NOT NULL CHECK(state IN ('creating','ready')),
    lease uuid,
    lease_until timestamptz,
    connection_revision bigint NOT NULL,
    next_row integer NOT NULL DEFAULT 2 CHECK(next_row BETWEEN 2 AND 10001),
    CHECK((lease IS NULL)=(lease_until IS NULL)),
    CHECK(state<>'ready' OR spreadsheet_id IS NOT NULL)
);
CREATE TABLE sarsa_booking.sheet_rows (
    role text NOT NULL REFERENCES sarsa_booking.google_workbooks(role),
    job_id uuid NOT NULL REFERENCES sarsa_booking.delivery_jobs(id),
    row_number integer NOT NULL CHECK(row_number BETWEEN 2 AND 10000),
    values_json jsonb NOT NULL CHECK(jsonb_typeof(values_json)='array' AND jsonb_array_length(values_json)=12),
    PRIMARY KEY(role,job_id), UNIQUE(role,row_number)
);
REVOKE ALL ON sarsa_booking.google_workbooks,sarsa_booking.sheet_rows FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON sarsa_booking.google_workbooks TO sarsa_booking_runtime;
GRANT SELECT,INSERT ON sarsa_booking.sheet_rows TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.claim_google_workbook(p_role text,p_client text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE g sarsa_booking.google_connections%ROWTYPE; w sarsa_booking.google_workbooks%ROWTYPE; token uuid; action text;
BEGIN
    IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_client IS NULL THEN RETURN NULL; END IF;
    PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
    SELECT * INTO g FROM sarsa_booking.google_connections WHERE role=p_role AND client_id=p_client;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role FOR UPDATE;
    token:=gen_random_uuid();
    IF NOT FOUND THEN
      INSERT INTO sarsa_booking.google_workbooks(role,subject,client_id,state,lease,lease_until,connection_revision)
        VALUES(p_role,g.subject,p_client,'creating',token,clock_timestamp()+interval '180 seconds',g.revision) RETURNING * INTO w;
      action:='create';
    ELSE
      IF w.subject<>g.subject OR w.client_id<>p_client THEN RETURN NULL; END IF;
      IF w.state='ready' THEN action:='ready';
      ELSE
        IF w.lease_until>clock_timestamp() AND w.connection_revision=g.revision THEN RETURN NULL; END IF;
        UPDATE sarsa_booking.google_workbooks SET lease=token,lease_until=clock_timestamp()+interval '180 seconds',
          connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
        -- A previous creation might have succeeded remotely. Never issue a
        -- second POST, even if Drive's search index has not caught up yet.
        action:='discover';
      END IF;
    END IF;
    RETURN to_jsonb(w)||jsonb_build_object('action',action);
END
$body$;
CREATE FUNCTION sarsa_booking.finish_google_workbook(p_role text,p_lease uuid,p_file text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_file IS NULL OR p_file !~ '^[A-Za-z0-9_-]{1,200}$' THEN RETURN false; END IF;
    UPDATE sarsa_booking.google_workbooks w SET spreadsheet_id=p_file,state='ready',lease=NULL,lease_until=NULL
      WHERE role=p_role AND lease=p_lease AND lease_until>clock_timestamp() AND state='creating'
      AND EXISTS(SELECT 1 FROM sarsa_booking.google_connections g WHERE g.role=w.role AND g.subject=w.subject
        AND g.client_id=w.client_id AND g.revision=w.connection_revision);
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;
CREATE FUNCTION sarsa_booking.assign_sheet_row(p_role text,p_job uuid,p_values jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE w sarsa_booking.google_workbooks%ROWTYPE; old sarsa_booking.sheet_rows%ROWTYPE;
BEGIN
    IF p_values IS NULL OR jsonb_typeof(p_values)<>'array' OR jsonb_array_length(p_values)<>12
       OR p_values->>0 IS DISTINCT FROM '004-sarsa-jyotish-sansthan' OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
    SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF NOT EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs j WHERE j.id=p_job AND j.kind='sheet_booking'
       AND j.recipient_role=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
       AND j.booking_id::text=p_values->>2 AND j.booking_revision::text=p_values->>3) THEN RETURN NULL; END IF;
    SELECT * INTO old FROM sarsa_booking.sheet_rows WHERE role=p_role AND job_id=p_job;
    IF FOUND THEN
      IF old.values_json IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
      RETURN jsonb_build_object('row',old.row_number,'spreadsheet_id',w.spreadsheet_id,'intent',w.intent,'values',old.values_json);
    END IF;
    IF w.next_row>10000 THEN RETURN NULL; END IF;
    INSERT INTO sarsa_booking.sheet_rows(role,job_id,row_number,values_json) VALUES(p_role,p_job,w.next_row,p_values);
    UPDATE sarsa_booking.google_workbooks SET next_row=next_row+1 WHERE role=p_role;
    RETURN jsonb_build_object('row',w.next_row,'spreadsheet_id',w.spreadsheet_id,'intent',w.intent,'values',p_values);
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_google_workbook(text,text),sarsa_booking.finish_google_workbook(text,uuid,text),
    sarsa_booking.assign_sheet_row(text,uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_google_workbook(text,text),sarsa_booking.finish_google_workbook(text,uuid,text),
    sarsa_booking.assign_sheet_row(text,uuid,jsonb) TO sarsa_booking_runtime;
