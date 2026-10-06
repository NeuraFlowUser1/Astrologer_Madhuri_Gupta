-- Staff commands retain original money and capacity; no provider calls here.
ALTER TABLE bookings ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK(revision>0);
ALTER TABLE bookings ADD COLUMN original_starts_at timestamptz;
ALTER TABLE bookings ADD COLUMN original_timing_provenance text NOT NULL DEFAULT 'legacy_baseline' CHECK(original_timing_provenance IN('legacy_baseline','booking_created'));
ALTER TABLE bookings ADD COLUMN late_reschedule_used boolean NOT NULL DEFAULT false;
ALTER TABLE bookings ADD COLUMN late_reschedule_deadline timestamptz;
UPDATE bookings SET original_starts_at=starts_at;
ALTER TABLE bookings ALTER COLUMN original_starts_at SET NOT NULL;
CREATE FUNCTION bind_original_booking_time() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN NEW.original_starts_at:=NEW.starts_at;NEW.original_timing_provenance:='booking_created';
 ELSIF NEW.original_starts_at IS DISTINCT FROM OLD.original_starts_at OR NEW.original_timing_provenance IS DISTINCT FROM OLD.original_timing_provenance
  OR(OLD.late_reschedule_used AND NOT NEW.late_reschedule_used)
  OR(OLD.late_reschedule_deadline IS NOT NULL AND NEW.late_reschedule_deadline IS DISTINCT FROM OLD.late_reschedule_deadline)
  THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Original timing and late allowance are immutable';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER booking_original_time BEFORE INSERT OR UPDATE ON bookings FOR EACH ROW EXECUTE FUNCTION bind_original_booking_time();
REVOKE ALL ON FUNCTION bind_original_booking_time() FROM PUBLIC;

CREATE TABLE staff_operations (
 operation_id uuid PRIMARY KEY,booking_id uuid NOT NULL REFERENCES bookings(id),
 action text NOT NULL CHECK(action IN('cancel','reschedule','receipt_recovery','contact_correction')),
 actor text NOT NULL,body_hash text NOT NULL CHECK(body_hash ~ '^[a-f0-9]{64}$'),
 previous_revision integer NOT NULL,revision integer NOT NULL,
 result jsonb NOT NULL,created_at timestamptz NOT NULL,
 CHECK(previous_revision>0 AND revision>=previous_revision)
);
CREATE TABLE staff_appointment_history (
 operation_id uuid PRIMARY KEY REFERENCES staff_operations(operation_id),
 previous_start timestamptz NOT NULL,current_start timestamptz NOT NULL,
 notice_seconds bigint NOT NULL,late_exception boolean NOT NULL,reason text NOT NULL CHECK(length(reason) BETWEEN 2 AND 500)
);
CREATE TABLE receipt_recoveries (
 operation_id uuid PRIMARY KEY REFERENCES staff_operations(operation_id),booking_id uuid NOT NULL REFERENCES bookings(id),
 code_digest text NOT NULL CHECK(code_digest ~ '^[a-f0-9]{64}$'),expires_at timestamptz NOT NULL,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),superseded_at timestamptz,
 redeemed_at timestamptz,redeemed_digest text CHECK(redeemed_digest ~ '^[a-f0-9]{64}$'),
 CHECK((redeemed_at IS NULL)=(redeemed_digest IS NULL))
);
CREATE INDEX receipt_recovery_current ON receipt_recoveries(booking_id,expires_at) WHERE superseded_at IS NULL;
REVOKE ALL ON staff_operations,staff_appointment_history,receipt_recoveries FROM PUBLIC;
CREATE TRIGGER staff_operations_immutable BEFORE UPDATE OR DELETE ON staff_operations FOR EACH ROW EXECUTE FUNCTION protect_google_refresh_evidence();
CREATE TRIGGER staff_history_immutable BEFORE UPDATE OR DELETE ON staff_appointment_history FOR EACH ROW EXECUTE FUNCTION protect_google_refresh_evidence();

ALTER TABLE delivery_jobs ADD COLUMN booking_revision integer;
ALTER TABLE delivery_jobs ADD COLUMN booking_snapshot jsonb;
ALTER TABLE delivery_jobs ADD COLUMN calendar_cleanup boolean NOT NULL DEFAULT false;
UPDATE delivery_jobs SET booking_revision=1 WHERE kind IN('booking_confirmed','booking_cancelled','sheet_booking','payment_review');
CREATE FUNCTION bind_delivery_booking_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.kind IN('booking_confirmed','booking_cancelled','sheet_booking','payment_review') AND NEW.booking_revision IS NULL THEN
  SELECT revision INTO NEW.booking_revision FROM public.bookings WHERE id=NEW.record_id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER delivery_booking_revision BEFORE INSERT ON delivery_jobs FOR EACH ROW EXECUTE FUNCTION bind_delivery_booking_revision();
REVOKE ALL ON FUNCTION bind_delivery_booking_revision() FROM PUBLIC;

-- Cleanup may be reopened when a late provider creation is finally observed.
DROP INDEX delivery_recipient_version;
CREATE UNIQUE INDEX delivery_recipient_version ON delivery_jobs(kind,record_id,message_version,recipient_role)
 WHERE kind<>'payment_review' AND NOT calendar_cleanup;

ALTER TABLE booking_calendar_events ADD COLUMN revision integer NOT NULL DEFAULT 1;
CREATE TABLE booking_event_revisions (
 booking_id uuid NOT NULL REFERENCES bookings(id),revision integer NOT NULL CHECK(revision>0),
 calendar_id text NOT NULL,event_id text NOT NULL UNIQUE,
 protocol_version integer NOT NULL CHECK(protocol_version IN(1,2)),
 state text NOT NULL CHECK(state IN('preparing','waiting','ready','cancelled','failed')),
 desired_snapshot jsonb NOT NULL,meet_url text,etag text,created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,
 PRIMARY KEY(booking_id,revision),CHECK((state='ready')=(meet_url IS NOT NULL))
);
INSERT INTO booking_event_revisions(booking_id,revision,calendar_id,event_id,protocol_version,state,desired_snapshot,meet_url,created_at,updated_at)
 SELECT e.booking_id,1,e.calendar_id,e.event_id,1,e.state,
  jsonb_build_object('id',b.id,'revision',1,'starts_at',b.starts_at,'duration_minutes',b.duration_minutes,
   'email',b.email,'service_id',b.service_id,'service_name',b.service_name,'amount_paise',b.amount_paise,'question_count',b.question_count),
  e.meet_url,e.created_at,e.updated_at FROM booking_calendar_events e JOIN bookings b ON b.id=e.booking_id;
REVOKE ALL ON booking_event_revisions FROM PUBLIC;

CREATE FUNCTION public.staff_actor(p_mode text,p_session text,p_csrf text,p_write boolean,p_now timestamptz)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp AS $$
DECLARE subject text;client public.admin_sessions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,3);
 IF p_mode='company' THEN
  subject:=booking_control.authorize(p_session,'obligation_handler',CASE WHEN p_write THEN p_csrf END,p_write);
  RETURN 'company:'||encode(sha256(convert_to(subject,'UTF8')),'hex');
 ELSIF p_mode='client' THEN
  PERFORM booking_control.admission(NULL);
  SELECT * INTO client FROM public.admin_sessions WHERE token_digest=p_session FOR SHARE;
  IF NOT FOUND OR client.expires_at<=p_now OR(p_write AND client.csrf_token IS DISTINCT FROM p_csrf) THEN
   RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='Staff access required';END IF;
  RETURN 'client:'||encode(sha256(convert_to(client.google_subject,'UTF8')),'hex');
 ELSE RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='Staff access required';END IF;
END $$;
REVOKE ALL ON FUNCTION public.staff_actor(text,text,text,boolean,timestamptz) FROM PUBLIC;
