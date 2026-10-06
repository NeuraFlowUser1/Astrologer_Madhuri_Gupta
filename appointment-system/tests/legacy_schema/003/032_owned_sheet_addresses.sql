-- Existing fixed destinations retain their legacy layout. New volumes carry
-- an exact owner/intent/generation and may only be created by that owner.
CREATE TABLE public.sheet_volumes(
 role text NOT NULL CHECK(role IN ('client_sheet','agency_sheet')),number integer NOT NULL CHECK(number>0),
 generation uuid NOT NULL DEFAULT gen_random_uuid(),intent uuid NOT NULL DEFAULT gen_random_uuid(),
 owner_email text NOT NULL,writer_email text NOT NULL,spreadsheet_id text UNIQUE,
 layout_version integer NOT NULL CHECK(layout_version IN(1,2)),
 state text NOT NULL CHECK(state IN ('scanning','ready','creation_required','creating','retired','attention')),
 creation_started_at timestamptz,creation_lease uuid,creation_lease_until timestamptz,
 error_code text,created_at timestamptz NOT NULL,headers_json jsonb,PRIMARY KEY(role,number),UNIQUE(intent),UNIQUE(generation),
 CHECK(owner_email=CASE WHEN role='client_sheet' THEN 'astroadvicebyks@gmail.com' ELSE 'neuraflowindia@gmail.com' END)
);
CREATE UNIQUE INDEX sheet_active_volume ON public.sheet_volumes(role) WHERE state IN ('scanning','ready','creation_required','creating');
CREATE TABLE public.sheet_tab_counters(
 role text NOT NULL,volume integer NOT NULL,tab text NOT NULL CHECK(tab IN ('Appointments','Inquiries','Appointment history','Enquiry context')),
 scan_cursor integer NOT NULL DEFAULT 2 CHECK(scan_cursor>=2),scan_limit integer NOT NULL CHECK(scan_limit BETWEEN 1 AND 1000000),
 scan_complete boolean NOT NULL DEFAULT false,next_row integer NOT NULL DEFAULT 2 CHECK(next_row>=2),
 scan_lease uuid,scan_lease_until timestamptz,PRIMARY KEY(role,volume,tab),
 FOREIGN KEY(role,volume) REFERENCES public.sheet_volumes(role,number)
);
CREATE TABLE public.sheet_record_rows(
 role text NOT NULL,record_kind text NOT NULL CHECK(record_kind IN ('booking','inquiry')),record_id uuid NOT NULL,
 volume integer NOT NULL,tab text NOT NULL,row_number integer NOT NULL CHECK(row_number>=2),
 applied_hash text CHECK(applied_hash ~ '^[a-f0-9]{64}$'),applied_revision integer NOT NULL DEFAULT 0,
 sync_lease uuid,sync_lease_until timestamptz,pending_hash text CHECK(pending_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(role,record_kind,record_id),UNIQUE(role,volume,tab,row_number),
 FOREIGN KEY(role,volume) REFERENCES public.sheet_volumes(role,number)
);
CREATE TABLE public.sheet_history_rows(
 role text NOT NULL,job_id uuid NOT NULL REFERENCES public.delivery_jobs(id),volume integer NOT NULL,tab text NOT NULL,
 row_number integer NOT NULL CHECK(row_number>=2),values_json jsonb NOT NULL CHECK(jsonb_typeof(values_json)='array'),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[a-f0-9]{64}$'),observed_at timestamptz NOT NULL,
 PRIMARY KEY(role,job_id),UNIQUE(role,volume,tab,row_number),FOREIGN KEY(role,volume) REFERENCES public.sheet_volumes(role,number)
);
CREATE TABLE public.sheet_job_snapshots(
 job_id uuid PRIMARY KEY REFERENCES public.delivery_jobs(id),record_kind text NOT NULL,revision integer NOT NULL,
 values_json jsonb NOT NULL CHECK(jsonb_typeof(values_json)='array'),payload_hash text NOT NULL,created_at timestamptz NOT NULL
);
CREATE FUNCTION public.protect_sheet_address() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 IF ROW(NEW.role,NEW.number,NEW.generation,NEW.intent,NEW.owner_email,NEW.writer_email,NEW.layout_version,NEW.created_at)
  IS DISTINCT FROM ROW(OLD.role,OLD.number,OLD.generation,OLD.intent,OLD.owner_email,OLD.writer_email,OLD.layout_version,OLD.created_at)
  OR (OLD.spreadsheet_id IS NOT NULL AND NEW.spreadsheet_id IS DISTINCT FROM OLD.spreadsheet_id)
  OR (OLD.headers_json IS NOT NULL AND NEW.headers_json IS DISTINCT FROM OLD.headers_json)
  OR (OLD.state='retired' AND NEW.state<>'retired') THEN
  RAISE EXCEPTION USING ERRCODE='P0432',MESSAGE='immutable sheet ownership';
 END IF; RETURN NEW;
END $body$;
CREATE TRIGGER sheet_volume_identity BEFORE UPDATE ON public.sheet_volumes FOR EACH ROW EXECUTE FUNCTION public.protect_sheet_address();
CREATE FUNCTION public.protect_sheet_row() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 IF ROW(NEW.role,NEW.record_kind,NEW.record_id,NEW.volume,NEW.tab,NEW.row_number)
  IS DISTINCT FROM ROW(OLD.role,OLD.record_kind,OLD.record_id,OLD.volume,OLD.tab,OLD.row_number) THEN
  RAISE EXCEPTION USING ERRCODE='P0432',MESSAGE='immutable sheet row address';
 END IF;RETURN NEW;
END $body$;
CREATE TRIGGER sheet_row_identity BEFORE UPDATE ON public.sheet_record_rows FOR EACH ROW EXECUTE FUNCTION public.protect_sheet_row();
CREATE TRIGGER sheet_history_identity BEFORE UPDATE OR DELETE ON public.sheet_history_rows FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
CREATE TRIGGER sheet_snapshot_identity BEFORE UPDATE OR DELETE ON public.sheet_job_snapshots FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
REVOKE ALL ON public.sheet_volumes,public.sheet_tab_counters,public.sheet_record_rows,public.sheet_history_rows,public.sheet_job_snapshots FROM PUBLIC;
REVOKE ALL ON FUNCTION public.protect_sheet_address(),public.protect_sheet_row() FROM PUBLIC;

CREATE TABLE public.sheet_owner_grants(
 role text PRIMARY KEY CHECK(role IN ('client_sheet','agency_sheet')),owner_email text NOT NULL,
 subject text NOT NULL,client_id text NOT NULL,scopes text NOT NULL,
 client_secret_encrypted text NOT NULL,refresh_encrypted text NOT NULL,
 revision integer NOT NULL DEFAULT 1,refresh_lease uuid,refresh_lease_until timestamptz,
 access_encrypted text,access_expires_at timestamptz,last_error_code text,connected_at timestamptz NOT NULL,
 CHECK(owner_email=CASE WHEN role='client_sheet' THEN 'astroadvicebyks@gmail.com' ELSE 'neuraflowindia@gmail.com' END)
);
REVOKE ALL ON public.sheet_owner_grants FROM PUBLIC;
-- The runtime can refresh an existing grant, but cannot install another owner,
-- audience, scope or secret. Owner consent is installed by the protected helper.
