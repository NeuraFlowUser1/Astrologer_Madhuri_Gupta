-- Current-record addresses are independent of immutable history rows. A daily
-- readback remains due even after success: SQL leases cannot fence remote IO.
SET LOCAL ROLE appointment_system_owner;
CREATE TABLE appointment_system.sheet_current_records (
 role text NOT NULL CHECK(role IN ('client','agency')),
 record_kind text NOT NULL CHECK(record_kind IN ('booking','enquiry')),
 record_id uuid NOT NULL,
 booking_id uuid REFERENCES appointment_system.bookings(id) ON DELETE CASCADE,
 enquiry_id uuid REFERENCES appointment_system.enquiries(request_id) ON DELETE CASCADE,
 volume_number bigint NOT NULL,
 row_number integer NOT NULL CHECK(row_number BETWEEN 2 AND 8999),
 sequence bigint NOT NULL DEFAULT 1 CHECK(sequence>0),
 due_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease uuid,lease_until timestamptz,lease_sequence bigint,
 claim_generation uuid,claim_release text,
 snapshot jsonb,approved_digest text,
 last_error_code text,attention boolean NOT NULL DEFAULT false,
 failures integer NOT NULL DEFAULT 0 CHECK(failures BETWEEN 0 AND 10000),
 verified_at timestamptz,
 PRIMARY KEY(role,record_kind,record_id),
 UNIQUE(role,record_kind,volume_number,row_number),
 FOREIGN KEY(role,volume_number) REFERENCES appointment_system.google_workbook_volumes(role,volume_number),
 CHECK((record_kind='booking' AND booking_id IS NOT NULL AND booking_id=record_id AND enquiry_id IS NULL)
    OR(record_kind='enquiry' AND enquiry_id IS NOT NULL AND enquiry_id=record_id AND booking_id IS NULL)),
 CHECK((lease IS NULL)=(lease_until IS NULL)),
 CHECK(last_error_code IS NULL OR last_error_code ~ '^[a-z][a-z0-9_]{0,100}$')
);
CREATE TABLE appointment_system.sheet_current_digests (
 role text NOT NULL,record_kind text NOT NULL,record_id uuid NOT NULL,
 digest text NOT NULL CHECK(digest ~ '^[a-f0-9]{64}$'),
 attempted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(role,record_kind,record_id,digest),
 FOREIGN KEY(role,record_kind,record_id) REFERENCES appointment_system.sheet_current_records(role,record_kind,record_id) ON DELETE CASCADE
);
CREATE TABLE appointment_system.sheet_projection_turns (
 role text NOT NULL CHECK(role IN ('client','agency')),
 record_kind text NOT NULL CHECK(record_kind IN ('booking','enquiry')),
 last_was_current boolean NOT NULL DEFAULT false,
 PRIMARY KEY(role,record_kind)
);
INSERT INTO appointment_system.sheet_projection_turns(role,record_kind)
 SELECT r,k FROM unnest(ARRAY['client','agency'])r CROSS JOIN unnest(ARRAY['booking','enquiry'])k;
REVOKE ALL ON appointment_system.sheet_current_records,appointment_system.sheet_current_digests,
 appointment_system.sheet_projection_turns FROM PUBLIC;
GRANT SELECT ON appointment_system.sheet_current_records,appointment_system.sheet_current_digests,
 appointment_system.sheet_projection_turns TO appointment_system_backup_access;
CREATE INDEX sheet_current_due ON appointment_system.sheet_current_records(record_kind,role,due_at) WHERE NOT attention;

CREATE FUNCTION appointment_system.protect_current_sheet_address() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
BEGIN
 IF ROW(NEW.role,NEW.record_kind,NEW.record_id,NEW.booking_id,NEW.enquiry_id,NEW.volume_number,NEW.row_number)
  IS DISTINCT FROM ROW(OLD.role,OLD.record_kind,OLD.record_id,OLD.booking_id,OLD.enquiry_id,OLD.volume_number,OLD.row_number)
  OR NEW.sequence<OLD.sequence THEN RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='immutable current row address';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER protect_current_sheet_address BEFORE UPDATE ON appointment_system.sheet_current_records
 FOR EACH ROW EXECUTE FUNCTION appointment_system.protect_current_sheet_address();
REVOKE ALL ON FUNCTION appointment_system.protect_current_sheet_address() FROM PUBLIC;

CREATE FUNCTION appointment_system.seed_current_sheet_record() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE kind text;identity uuid;
BEGIN
 -- Historical handover has its own explicit mapping proof. It must not queue
 -- writes to a remote workbook merely by copying an old history row.
 IF EXISTS(SELECT 1 FROM appointment_system.conversion_handover WHERE phase='fenced') THEN RETURN NEW;END IF;
 IF TG_TABLE_NAME='sheet_rows' THEN
  kind:='booking';SELECT booking_id INTO identity FROM appointment_system.delivery_jobs WHERE id=NEW.job_id;
 ELSE
  kind:='enquiry';SELECT request_id INTO identity FROM appointment_system.enquiry_delivery_jobs WHERE id=NEW.job_id;
 END IF;
 INSERT INTO appointment_system.sheet_current_records(role,record_kind,record_id,booking_id,enquiry_id,volume_number,row_number)
 VALUES(NEW.role,kind,identity,CASE WHEN kind='booking' THEN identity END,CASE WHEN kind='enquiry' THEN identity END,NEW.volume_number,NEW.row_number)
 ON CONFLICT(role,record_kind,record_id) DO UPDATE SET sequence=sheet_current_records.sequence+1,due_at=clock_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER seed_current_booking AFTER INSERT ON appointment_system.sheet_rows FOR EACH ROW EXECUTE FUNCTION appointment_system.seed_current_sheet_record();
CREATE TRIGGER seed_current_enquiry AFTER INSERT ON appointment_system.enquiry_sheet_rows FOR EACH ROW EXECUTE FUNCTION appointment_system.seed_current_sheet_record();

CREATE FUNCTION appointment_system.dirty_current_sheet_record() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
BEGIN
 IF TG_TABLE_NAME='bookings' THEN
  IF ROW(NEW.state,NEW.revision) IS DISTINCT FROM ROW(OLD.state,OLD.revision) THEN
   UPDATE appointment_system.sheet_current_records SET sequence=sequence+1,due_at=clock_timestamp() WHERE booking_id=NEW.id;
  END IF;
 ELSIF TG_TABLE_NAME='delivery_jobs' THEN
  IF NEW.kind='sheet_booking' THEN
   UPDATE appointment_system.sheet_current_records SET sequence=sequence+1,due_at=clock_timestamp()
    WHERE booking_id=NEW.booking_id AND role=replace(NEW.recipient_role,'_sheet','');
  END IF;
 ELSE
  IF NEW.payload IS DISTINCT FROM OLD.payload THEN
   UPDATE appointment_system.sheet_current_records SET sequence=sequence+1,due_at=clock_timestamp() WHERE enquiry_id=NEW.request_id;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER dirty_current_booking AFTER UPDATE ON appointment_system.bookings FOR EACH ROW EXECUTE FUNCTION appointment_system.dirty_current_sheet_record();
CREATE TRIGGER dirty_current_booking_output AFTER INSERT ON appointment_system.delivery_jobs FOR EACH ROW EXECUTE FUNCTION appointment_system.dirty_current_sheet_record();
CREATE TRIGGER dirty_current_enquiry AFTER UPDATE ON appointment_system.enquiries FOR EACH ROW EXECUTE FUNCTION appointment_system.dirty_current_sheet_record();

CREATE FUNCTION appointment_system.claim_sheet_projection(p_kind text,p_role text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE chosen appointment_system.sheet_current_records%ROWTYPE;last_current boolean;has_history boolean;payload jsonb;volume jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT last_was_current INTO last_current FROM appointment_system.sheet_projection_turns WHERE role=p_role AND record_kind=p_kind FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL;END IF;
 has_history:=CASE WHEN p_kind='booking' THEN EXISTS(SELECT 1 FROM appointment_system.delivery_jobs
  WHERE kind='sheet_booking' AND recipient_role=p_role||'_sheet' AND state IN('pending','processing','retry_wait','delivery_unknown')
   AND next_attempt_at<=clock_timestamp() AND coalesce(lease_expires_at,clock_timestamp())<=clock_timestamp())
 ELSE EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE kind=p_role||'_sheet'
  AND state IN('pending','processing','retry_wait','delivery_unknown') AND next_attempt_at<=clock_timestamp()
  AND coalesce(lease_expires_at,clock_timestamp())<=clock_timestamp()) END;
 IF last_current AND has_history THEN
  UPDATE appointment_system.sheet_projection_turns SET last_was_current=false WHERE role=p_role AND record_kind=p_kind;RETURN NULL;
 END IF;
 SELECT * INTO chosen FROM appointment_system.sheet_current_records WHERE role=p_role AND record_kind=p_kind
  AND NOT attention AND due_at<=clock_timestamp() AND coalesce(lease_until,clock_timestamp())<=clock_timestamp()
  ORDER BY due_at,record_id LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL;END IF;
 IF p_kind='booking' THEN payload:=appointment_system.booking_snapshot(chosen.record_id);
 ELSE SELECT jsonb_build_object('request_id',e.request_id,'verified_at',e.verified_at,'payload',e.payload) INTO payload
  FROM appointment_system.enquiries e WHERE request_id=chosen.record_id AND verified_at IS NOT NULL;END IF;
 SELECT to_jsonb(v) INTO volume FROM appointment_system.google_workbook_volumes v
  WHERE role=p_role AND volume_number=chosen.volume_number AND state IN('ready','retired');
 IF payload IS NULL OR volume IS NULL THEN RETURN NULL;END IF;
 UPDATE appointment_system.sheet_current_records SET lease=gen_random_uuid(),lease_until=clock_timestamp()+interval '90 seconds',
  lease_sequence=sequence,snapshot=payload,approved_digest=NULL,
  claim_generation=(SELECT restore_generation FROM appointment_system.control_product_state WHERE singleton),
  claim_release=(SELECT release_digest FROM appointment_system.worker_release WHERE singleton)
  WHERE role=p_role AND record_kind=p_kind AND record_id=chosen.record_id RETURNING * INTO chosen;
 UPDATE appointment_system.sheet_projection_turns SET last_was_current=true WHERE role=p_role AND record_kind=p_kind;
 RETURN volume||to_jsonb(chosen);
END $$;

CREATE FUNCTION appointment_system.approve_sheet_projection(p_role text,p_kind text,p_record uuid,p_lease uuid,p_sequence bigint,p_values jsonb,p_digest text,p_observed text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE chosen appointment_system.sheet_current_records%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT * INTO chosen FROM appointment_system.sheet_current_records WHERE role=p_role AND record_kind=p_kind AND record_id=p_record
  AND lease=p_lease AND lease_until>clock_timestamp() AND sequence=p_sequence AND lease_sequence=p_sequence
  AND claim_generation=(SELECT restore_generation FROM appointment_system.control_product_state WHERE singleton)
  AND claim_release=(SELECT release_digest FROM appointment_system.worker_release WHERE singleton) FOR UPDATE;
 IF NOT FOUND THEN RETURN 'changed';END IF;
 IF p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_values) IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_values)<>(CASE WHEN p_kind='booking' THEN 21 ELSE 14 END)
  OR p_values->>0 IS DISTINCT FROM chosen.snapshot->>'request_id'
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_values)v WHERE jsonb_typeof(v)<>'string' OR length(v#>>'{}')>4000)
  OR (p_kind='booking' AND p_values->>20 IS DISTINCT FROM chosen.snapshot->>'revision') THEN RETURN 'invalid';END IF;
 IF p_digest IS DISTINCT FROM encode(sha256(convert_to('['||(SELECT string_agg(v::text,',' ORDER BY n)
  FROM jsonb_array_elements(p_values) WITH ORDINALITY x(v,n))||']','UTF8')),'hex') THEN RETURN 'invalid';END IF;
 IF chosen.approved_digest IS NOT NULL AND chosen.approved_digest<>p_digest THEN RETURN 'invalid';END IF;
 -- Check occupied content against an earlier *committed* attempted digest,
 -- before recording today's intention. Foreign occupied cells are not ours.
 IF p_observed IS NOT NULL AND NOT EXISTS(SELECT 1 FROM appointment_system.sheet_current_digests
  WHERE role=p_role AND record_kind=p_kind AND record_id=p_record AND digest=p_observed) THEN RETURN 'conflict';END IF;
 INSERT INTO appointment_system.sheet_current_digests(role,record_kind,record_id,digest)
  VALUES(p_role,p_kind,p_record,p_digest) ON CONFLICT DO NOTHING;
 UPDATE appointment_system.sheet_current_records SET approved_digest=p_digest WHERE role=p_role AND record_kind=p_kind AND record_id=p_record;
 RETURN 'ok';
END $$;

CREATE FUNCTION appointment_system.finish_sheet_projection(p_role text,p_kind text,p_record uuid,p_lease uuid,p_sequence bigint,p_digest text,p_error text,p_attention boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE chosen appointment_system.sheet_current_records%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['worker']);
 SELECT * INTO chosen FROM appointment_system.sheet_current_records WHERE role=p_role AND record_kind=p_kind AND record_id=p_record
  AND lease=p_lease AND lease_until>clock_timestamp() AND lease_sequence=p_sequence
  AND claim_generation=(SELECT restore_generation FROM appointment_system.control_product_state WHERE singleton)
  AND claim_release=(SELECT release_digest FROM appointment_system.worker_release WHERE singleton) FOR UPDATE;
 IF NOT FOUND OR p_attention IS NULL OR (p_error IS NOT NULL AND p_error !~ '^[a-z][a-z0-9_]{0,100}$') THEN RETURN false;END IF;
 IF p_error IS NULL AND (p_digest IS NULL OR p_digest IS DISTINCT FROM chosen.approved_digest OR p_attention) THEN RETURN false;END IF;
 IF p_error IS NOT NULL AND p_digest IS NOT NULL THEN RETURN false;END IF;
 UPDATE appointment_system.sheet_current_records SET lease=NULL,lease_until=NULL,
  due_at=CASE WHEN sequence<>p_sequence THEN clock_timestamp() WHEN p_error IS NULL THEN clock_timestamp()+interval '1 day'
   ELSE clock_timestamp()+make_interval(secs=>least(86400,900*power(2,least(failures,7)))::double precision) END,
  failures=CASE WHEN sequence<>p_sequence THEN failures WHEN p_error IS NULL THEN 0 ELSE least(10000,failures+1) END,
  last_error_code=p_error,attention=p_attention,
  verified_at=CASE WHEN p_error IS NULL AND sequence=p_sequence THEN clock_timestamp() ELSE verified_at END
  WHERE role=p_role AND record_kind=p_kind AND record_id=p_record;
 RETURN true;
END $$;

REVOKE ALL ON FUNCTION appointment_system.seed_current_sheet_record(),appointment_system.dirty_current_sheet_record(),
 appointment_system.claim_sheet_projection(text,text),appointment_system.approve_sheet_projection(text,text,uuid,uuid,bigint,jsonb,text,text),
 appointment_system.finish_sheet_projection(text,text,uuid,uuid,bigint,text,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.claim_sheet_projection(text,text),
 appointment_system.approve_sheet_projection(text,text,uuid,uuid,bigint,jsonb,text,text),
 appointment_system.finish_sheet_projection(text,text,uuid,uuid,bigint,text,text,boolean) TO appointment_system_worker_access;
CREATE OR REPLACE VIEW appointment_system.recovery_due_work AS
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
  WHERE (enquiries.code_ciphertext IS NOT NULL)
UNION ALL SELECT CASE WHEN record_kind='booking' THEN 'booking_records' ELSE 'enquiry_records' END,role||'_sheet',greatest(due_at,coalesce(lease_until,due_at)) FROM appointment_system.sheet_current_records WHERE NOT attention;

CREATE OR REPLACE FUNCTION appointment_system.recovery_attention() RETURNS boolean
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
 SELECT EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE resolved_at IS NULL)
 OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE state IN ('needs_review','needs_review'))
 OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE state IN ('needs_review','needs_review'))
 OR EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail WHERE state='needs_review')
 OR EXISTS(SELECT 1 FROM appointment_system.sheet_current_records WHERE attention)
 OR EXISTS(SELECT 1 FROM appointment_system.recovery_due_work WHERE due<statement_timestamp()-interval '5 minutes');
$$;
-- New workbooks use the canonical four-tab layout. Existing ready volumes
-- retain their exact layout until ordinary capacity or credential rollover.
ALTER TABLE appointment_system.google_workbooks DROP CONSTRAINT google_workbooks_layout_version_check,
 ADD CONSTRAINT google_workbooks_layout_version_check CHECK(layout_version IN(1,2,3,4));
ALTER TABLE appointment_system.google_workbook_volumes DROP CONSTRAINT google_workbook_volumes_layout_version_check,
 ADD CONSTRAINT google_workbook_volumes_layout_version_check CHECK(layout_version IN(1,2,3,4));
ALTER TABLE appointment_system.sheet_rows DROP CONSTRAINT sheet_rows_values_json_check,
 ADD CONSTRAINT sheet_rows_values_json_check CHECK(jsonb_typeof(values_json)='array' AND jsonb_array_length(values_json) IN(12,33,36));
ALTER TABLE appointment_system.enquiry_sheet_rows DROP CONSTRAINT enquiry_sheet_rows_values_json_check,
 ADD CONSTRAINT enquiry_sheet_rows_values_json_check CHECK(jsonb_typeof(values_json)='array' AND jsonb_array_length(values_json) IN(10,12,15,17));
CREATE OR REPLACE FUNCTION appointment_system.entry_claim_google_workbook_v2(p_role text, p_client text) RETURNS jsonb
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
   VALUES(p_role,g.subject,p_client,4,'creating',token,clock_timestamp()+interval '180 seconds',g.revision) RETURNING * INTO w;
  action:='create';
 ELSE
  IF w.state='creating' AND (w.client_id<>p_client OR w.subject<>g.subject) THEN RETURN jsonb_build_object('action','review','code','google_workbook_client_changed_unresolved'); END IF;
  IF w.state='ready' AND (greatest(w.next_row,w.next_enquiry_row)>=9000 OR w.client_id<>p_client OR w.subject<>g.subject) THEN
   UPDATE appointment_system.google_workbook_volumes SET state='retired' WHERE role=p_role AND volume_number=w.volume_number;
   UPDATE appointment_system.google_workbooks SET volume_number=volume_number+1,intent=gen_random_uuid(),spreadsheet_id=NULL,
    state='creating',layout_version=4,client_id=p_client,subject=g.subject,creation_attempt_at=NULL,next_row=2,next_enquiry_row=2,lease=token,lease_until=clock_timestamp()+interval '180 seconds',
    connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;
   INSERT INTO appointment_system.google_workbook_volumes(role,volume_number,layout_version,intent,subject,client_id,state,grant_id)
    VALUES(p_role,w.volume_number,4,w.intent,w.subject,w.client_id,'creating',(SELECT grant_id FROM appointment_system.google_resources WHERE resource=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END));
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
 RETURN to_jsonb(w)||to_jsonb(v)||jsonb_build_object('action',action);
END $$;
CREATE OR REPLACE FUNCTION appointment_system.entry_assign_sheet_row(p_role text, p_job uuid, p_values jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE w appointment_system.google_workbooks%ROWTYPE; old jsonb;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array'
  OR jsonb_array_length(p_values) NOT IN (12,33,36)
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
 IF p_values->>0 IS DISTINCT FROM (SELECT CASE WHEN v.workbook_protocol IN('legacy-sarsa-workbook-v1','legacy-sarsa-workbook-v2')
  THEN '004-sarsa-jyotish-sansthan' ELSE appointment_system.installation_value('project_id') END
  FROM appointment_system.google_workbook_volumes v WHERE v.role=p_role AND v.volume_number=w.volume_number) THEN RETURN NULL;END IF;
 IF (w.layout_version IN (1,2) AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>33) OR (w.layout_version=4 AND jsonb_array_length(p_values)<>36) THEN RETURN NULL; END IF;
 IF w.layout_version=4 AND p_values->>35 IS DISTINCT FROM encode(sha256(convert_to('['||(
  SELECT string_agg(v::text,',' ORDER BY n) FROM jsonb_array_elements(p_values) WITH ORDINALITY x(v,n)
  WHERE n<jsonb_array_length(p_values))||']','UTF8')),'hex') THEN RETURN NULL;END IF;
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
  OR jsonb_array_length(p_values) NOT IN (10,12,15,17)
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
 IF jsonb_array_length(p_values)>=15 AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiries e JOIN appointment_system.enquiry_delivery_jobs j USING(request_id) WHERE j.id=p_job AND p_values->>12=coalesce(e.payload->>'kind','contact') AND p_values->>13=coalesce(e.payload->>'dob','') AND p_values->>14=coalesce(e.payload->>'location','')) THEN RETURN NULL; END IF;
 old:=appointment_system.mapped_google_row(p_role,p_job,'enquiry');
 IF old IS NOT NULL THEN
  IF old->'values' IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN old;
 END IF;
 SELECT * INTO w FROM appointment_system.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND OR greatest(w.next_row,w.next_enquiry_row)>=9000 THEN RETURN NULL; END IF;
 IF p_values->>0 IS DISTINCT FROM (SELECT CASE WHEN v.workbook_protocol IN('legacy-sarsa-workbook-v1','legacy-sarsa-workbook-v2')
  THEN '004-sarsa-jyotish-sansthan' ELSE appointment_system.installation_value('project_id') END
  FROM appointment_system.google_workbook_volumes v WHERE v.role=p_role AND v.volume_number=w.volume_number) THEN RETURN NULL;END IF;
 IF (w.layout_version=1 AND jsonb_array_length(p_values)<>10) OR (w.layout_version=2 AND jsonb_array_length(p_values)<>12) OR (w.layout_version=3 AND jsonb_array_length(p_values)<>15) OR (w.layout_version=4 AND jsonb_array_length(p_values)<>17) THEN RETURN NULL; END IF;
 IF w.layout_version=4 AND p_values->>16 IS DISTINCT FROM encode(sha256(convert_to('['||(
  SELECT string_agg(v::text,',' ORDER BY n) FROM jsonb_array_elements(p_values) WITH ORDINALITY x(v,n)
  WHERE n<jsonb_array_length(p_values))||']','UTF8')),'hex') THEN RETURN NULL;END IF;
 INSERT INTO appointment_system.enquiry_sheet_rows(role,job_id,row_number,values_json,volume_number)
  VALUES(p_role,p_job,w.next_enquiry_row,p_values,w.volume_number);
 UPDATE appointment_system.google_workbooks SET next_enquiry_row=next_enquiry_row+1 WHERE role=p_role;
 RETURN appointment_system.mapped_google_row(p_role,p_job,'enquiry');
END $$;
CREATE TABLE appointment_system.company_sheet_reviews (
 operation_id uuid PRIMARY KEY,role text NOT NULL,record_kind text NOT NULL,record_id uuid NOT NULL,
 sequence bigint NOT NULL,actor text NOT NULL,reason text NOT NULL CHECK(length(reason) BETWEEN 5 AND 300),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(role,record_kind,record_id) REFERENCES appointment_system.sheet_current_records(role,record_kind,record_id) ON DELETE CASCADE
);
REVOKE ALL ON appointment_system.company_sheet_reviews FROM PUBLIC;
GRANT SELECT ON appointment_system.company_sheet_reviews TO appointment_system_backup_access;
CREATE FUNCTION appointment_system.company_sheet_status(p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE result jsonb;total bigint;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.control_authorize(p_session,'service_controller');
 SELECT count(*) INTO total FROM appointment_system.sheet_current_records
 WHERE attention OR last_error_code IS NOT NULL OR due_at<clock_timestamp()-interval '30 minutes';
 SELECT coalesce(jsonb_agg(row),'[]'::jsonb) INTO result FROM (
  SELECT r.role,r.record_kind,r.record_id,r.sequence::text,coalesce(b.request_id,e.request_id)::text reference,
   r.last_error_code,r.attention,r.verified_at,r.due_at,r.lease_until>clock_timestamp() busy
  FROM appointment_system.sheet_current_records r
  LEFT JOIN appointment_system.bookings b ON b.id=r.booking_id LEFT JOIN appointment_system.enquiries e ON e.request_id=r.enquiry_id
  WHERE r.attention OR r.last_error_code IS NOT NULL OR r.due_at<clock_timestamp()-interval '30 minutes'
  ORDER BY r.attention DESC,r.due_at,r.role,r.record_kind,r.record_id LIMIT 50)row;
 RETURN jsonb_build_object('records',result,'total',total,'limited',total>50);
END $$;
CREATE FUNCTION appointment_system.company_sheet_recheck(p_session text,p_csrf text,p_operation uuid,p_role text,p_kind text,p_record uuid,p_sequence bigint,p_reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE actor text;prior appointment_system.company_sheet_reviews%ROWTYPE;row appointment_system.sheet_current_records%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 actor:=appointment_system.control_authorize(p_session,'service_controller',p_csrf);
 IF p_csrf IS NULL OR p_operation IS NULL OR p_record IS NULL OR p_sequence IS NULL OR p_sequence<1
  OR p_role IS NULL OR p_role NOT IN('client','agency') OR p_kind IS NULL OR p_kind NOT IN('booking','enquiry')
  OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 5 AND 300 OR p_reason ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 SELECT * INTO row FROM appointment_system.sheet_current_records WHERE role=p_role AND record_kind=p_kind AND record_id=p_record FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','record_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.company_sheet_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF ROW(prior.role,prior.record_kind,prior.record_id,prior.sequence,prior.actor,prior.reason) IS DISTINCT FROM ROW(p_role,p_kind,p_record,p_sequence,actor,p_reason)
   THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','check_queued');
 END IF;
 IF row.sequence<>p_sequence THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF row.lease_until>clock_timestamp() THEN RETURN jsonb_build_object('code','check_running');END IF;
 INSERT INTO appointment_system.company_sheet_reviews(operation_id,role,record_kind,record_id,sequence,actor,reason)
 VALUES(p_operation,p_role,p_kind,p_record,p_sequence,actor,p_reason);
 UPDATE appointment_system.sheet_current_records SET attention=false,due_at=clock_timestamp(),last_error_code=NULL,failures=0
 WHERE role=p_role AND record_kind=p_kind AND record_id=p_record;
 RETURN jsonb_build_object('code','check_queued');
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $$;
REVOKE ALL ON FUNCTION appointment_system.company_sheet_status(text),appointment_system.company_sheet_recheck(text,text,uuid,text,text,uuid,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.company_sheet_status(text),appointment_system.company_sheet_recheck(text,text,uuid,text,text,uuid,bigint,text) TO appointment_system_company_access;
RESET ROLE;
