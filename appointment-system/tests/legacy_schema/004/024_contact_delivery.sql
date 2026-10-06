-- Separate enquiry ownership, shared mail allowance. No public activation.
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN destination text;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN message_ciphertext text CHECK(length(message_ciphertext) BETWEEN 100 AND 32768);
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN message_digest text CHECK(message_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN template_version integer NOT NULL DEFAULT 1 CHECK(template_version=1);
-- Optional enquiry sub-limits reserve room in the overall Sarsa allocation.
-- Zero until the owner approves capacity; runtime cannot change email_policy.
ALTER TABLE sarsa_booking.email_policy ADD COLUMN contact_daily_limit integer NOT NULL DEFAULT 0 CHECK(contact_daily_limit>=0);
ALTER TABLE sarsa_booking.email_policy ADD COLUMN contact_monthly_limit integer NOT NULL DEFAULT 0 CHECK(contact_monthly_limit>=0);
ALTER TABLE sarsa_booking.email_policy ADD CHECK(contact_daily_limit<=daily_limit AND contact_monthly_limit<=monthly_limit);
-- Booking inserts remain valid; all reservations continue to count together.
ALTER TABLE sarsa_booking.email_reservations DROP CONSTRAINT email_reservations_pkey;
ALTER TABLE sarsa_booking.email_reservations ALTER COLUMN job_id DROP NOT NULL;
ALTER TABLE sarsa_booking.email_reservations ADD UNIQUE(job_id);
ALTER TABLE sarsa_booking.email_reservations ADD COLUMN enquiry_job_id uuid UNIQUE REFERENCES sarsa_booking.enquiry_delivery_jobs(id);
ALTER TABLE sarsa_booking.email_reservations ADD CHECK((job_id IS NULL)<>(enquiry_job_id IS NULL));
CREATE TABLE sarsa_booking.enquiry_email_observations (
 event_id text PRIMARY KEY,job_id uuid NOT NULL REFERENCES sarsa_booking.enquiry_delivery_jobs(id),
 provider_id uuid NOT NULL,event_type text NOT NULL CHECK(event_type IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed')),
 occurred_at timestamptz NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX enquiry_mail_observation_job ON sarsa_booking.enquiry_email_observations(job_id,event_type);
CREATE UNIQUE INDEX enquiry_email_provider ON sarsa_booking.enquiry_delivery_jobs(provider_id)
 WHERE provider_id IS NOT NULL AND kind IN ('verification','acknowledgement','practice_notice');
REVOKE ALL ON sarsa_booking.enquiry_email_observations FROM PUBLIC;
GRANT SELECT,INSERT ON sarsa_booking.enquiry_email_observations TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.contact_job_eligible(e sarsa_booking.enquiries,j sarsa_booking.enquiry_delivery_jobs)
RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT CASE WHEN j.kind='verification' THEN e.verified_at IS NULL AND e.generation=j.generation
    AND e.code_digest IS NOT NULL AND e.attempts<5 AND e.code_expires_at>clock_timestamp()
   ELSE e.verified_at IS NOT NULL END
$$;
CREATE FUNCTION sarsa_booking.claim_enquiry_delivery(p_lane text) RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE candidate record;e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;
BEGIN
 IF p_lane IS NULL OR p_lane NOT IN ('email','google') THEN RETURN NULL; END IF;
 FOR candidate IN SELECT id,request_id FROM sarsa_booking.enquiry_delivery_jobs
  WHERE (CASE WHEN kind IN ('client_sheet','agency_sheet') THEN 'google' ELSE 'email' END)=p_lane
   AND state IN ('pending','failed','uncertain','processing') AND next_attempt_at<=clock_timestamp()
   AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) ORDER BY (kind='verification') DESC,next_attempt_at,id LIMIT 20 LOOP
  SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=candidate.request_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id=candidate.id
    AND state IN ('pending','failed','uncertain','processing') AND next_attempt_at<=clock_timestamp()
    AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF NOT sarsa_booking.contact_job_eligible(e,j) OR j.deadline_at<=clock_timestamp() THEN
   UPDATE sarsa_booking.enquiry_delivery_jobs SET state=CASE WHEN kind='verification' THEN 'expired' ELSE 'attention' END,
    last_error_code='contact_deadline_or_state',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   CONTINUE;
  END IF;
  IF j.provider_id IS NOT NULL THEN
   UPDATE sarsa_booking.enquiry_delivery_jobs SET state=CASE WHEN p_lane='email' THEN 'accepted' ELSE 'done' END,
    lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; CONTINUE;
  END IF;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
   lease_expires_at=clock_timestamp()+interval '180 seconds',attempts=attempts+1,
   destination=coalesce(destination,CASE WHEN kind='practice_notice' THEN 'sarsajyotish@gmail.com'
    WHEN p_lane='email' THEN e.payload->>'email' ELSE NULL END) WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j)||jsonb_build_object('payload',e.payload,'verified_at',e.verified_at,
    'code_ciphertext',CASE WHEN j.kind='verification' THEN e.code_ciphertext END,'code_expires_at',e.code_expires_at);
 END LOOP;
 RETURN NULL;
END $body$;

CREATE FUNCTION sarsa_booking.email_recipient_suppressed(p_destination text) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM sarsa_booking.email_observations o JOIN sarsa_booking.delivery_jobs j ON j.id=o.job_id
   WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained'))
 OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o JOIN sarsa_booking.enquiry_delivery_jobs j ON j.id=o.job_id
   WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained'))
$$;
CREATE FUNCTION sarsa_booking.begin_enquiry_send(p_job uuid,p_lease uuid,p_cipher text,p_digest text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;
 owner_id uuid; policy sarsa_booking.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp();blocked text;
BEGIN
 SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.kind NOT IN ('verification','acknowledgement','practice_notice') OR p_lease IS NULL
  OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
 IF NOT sarsa_booking.contact_job_eligible(e,j) OR j.deadline_at<=instant THEN blocked:='contact_deadline_or_state';
 ELSIF j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours' THEN blocked:='email_retry_window_closed';
 ELSIF j.kind<>'practice_notice' AND sarsa_booking.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed'; END IF;
 IF blocked IS NOT NULL THEN
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state=CASE WHEN kind='verification' THEN 'expired' ELSE 'attention' END,
   last_error_code=blocked,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 IF j.provider_id IS NOT NULL THEN
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state='accepted',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 IF p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 32768 OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
  OR (j.first_attempt_at IS NOT NULL AND (j.message_ciphertext IS DISTINCT FROM p_cipher OR j.message_digest IS DISTINCT FROM p_digest)) THEN RETURN NULL; END IF;
 -- Same lock and same ledger as booking sends. Never acquire an enquiry after it.
 PERFORM pg_advisory_xact_lock(4004003);
 SELECT * INTO policy FROM sarsa_booking.email_policy WHERE id=true;
 IF policy.daily_limit<=0 OR policy.monthly_limit<=0 OR policy.contact_daily_limit<=0 OR policy.contact_monthly_limit<=0 THEN blocked:='email_budget_unconfigured';
 ELSIF NOT EXISTS(SELECT 1 FROM sarsa_booking.email_reservations WHERE enquiry_job_id=j.id) AND (
   (SELECT count(*) FROM sarsa_booking.email_reservations WHERE reserved_at>=instant-interval '24 hours')>=policy.daily_limit OR
   (SELECT count(*) FROM sarsa_booking.email_reservations WHERE reserved_at>=instant-interval '31 days')>=policy.monthly_limit OR
   (SELECT count(*) FROM sarsa_booking.email_reservations WHERE enquiry_job_id IS NOT NULL AND reserved_at>=instant-interval '24 hours')>=policy.contact_daily_limit OR
   (SELECT count(*) FROM sarsa_booking.email_reservations WHERE enquiry_job_id IS NOT NULL AND reserved_at>=instant-interval '31 days')>=policy.contact_monthly_limit)
 THEN blocked:='email_budget_exhausted'; END IF;
 IF blocked IS NOT NULL THEN
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state='pending',last_error_code=blocked,
   next_attempt_at=least(deadline_at,instant+interval '15 minutes'),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 INSERT INTO sarsa_booking.email_reservations(enquiry_job_id) VALUES(j.id) ON CONFLICT(enquiry_job_id) DO NOTHING;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET message_ciphertext=p_cipher,message_digest=p_digest,
  first_attempt_at=coalesce(first_attempt_at,instant) WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $body$;

CREATE FUNCTION sarsa_booking.finish_enquiry_delivery(p_job uuid,p_lease uuid,p_provider text,p_error text,p_attention boolean,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;owner_id uuid;is_mail boolean;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 3600 OR p_attention IS NULL
   OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
 SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR p_lease IS NULL OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing'
   OR j.lease_expires_at<=clock_timestamp() THEN RETURN false; END IF;
 is_mail:=j.kind IN ('verification','acknowledgement','practice_notice');
 IF NOT sarsa_booking.contact_job_eligible(e,j) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL THEN
  IF is_mail THEN
   IF j.first_attempt_at IS NULL OR j.message_digest IS NULL OR p_provider !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN RETURN false; END IF;
   PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-mail-provider:'||p_provider,0));
   IF EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=p_provider AND recipient_role IN ('customer','client'))
    OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE provider_id=p_provider AND id<>j.id AND kind IN ('verification','acknowledgement','practice_notice')) THEN
    UPDATE sarsa_booking.enquiry_delivery_jobs SET state='attention',last_error_code='email_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    RETURN false;
   END IF;
  ELSIF p_provider !~ '^[A-Za-z0-9_-]{1,200}$' THEN RETURN false; END IF;
  IF j.provider_id IS NOT NULL AND j.provider_id<>p_provider THEN RETURN false; END IF;
 END IF;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET provider_id=coalesce(p_provider,provider_id),
  state=CASE WHEN p_provider IS NOT NULL OR provider_id IS NOT NULL THEN CASE WHEN is_mail THEN 'accepted' ELSE 'done' END
   WHEN p_attention THEN 'attention' ELSE 'uncertain' END,last_error_code=p_error,
  next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
 RETURN true;
END $body$;

-- Immutable attempted identity, with deliberate ciphertext erasure on completion.
CREATE FUNCTION sarsa_booking.protect_enquiry_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.request_id IS DISTINCT FROM OLD.request_id
  OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.generation IS DISTINCT FROM OLD.generation
  OR NEW.deadline_at IS DISTINCT FROM OLD.deadline_at OR NEW.created_at IS DISTINCT FROM OLD.created_at
  OR (OLD.provider_id IS NOT NULL AND NEW.provider_id IS DISTINCT FROM OLD.provider_id)
  OR (OLD.first_attempt_at IS NOT NULL AND (NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at
   OR NEW.destination IS DISTINCT FROM OLD.destination OR NEW.message_digest IS DISTINCT FROM OLD.message_digest
   OR NEW.template_version IS DISTINCT FROM OLD.template_version
   OR (NEW.message_ciphertext IS DISTINCT FROM OLD.message_ciphertext AND NEW.message_ciphertext IS NOT NULL))) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Enquiry delivery identity is immutable'; END IF;
 IF NEW.state IN ('accepted','done','suppressed','expired','attention') THEN NEW.message_ciphertext:=NULL; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER enquiry_delivery_identity BEFORE UPDATE ON sarsa_booking.enquiry_delivery_jobs
 FOR EACH ROW EXECUTE FUNCTION sarsa_booking.protect_enquiry_delivery();

CREATE FUNCTION sarsa_booking.reconcile_enquiry_email_event() RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE candidate record;e sarsa_booking.provider_inbox%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;provider_uuid uuid;occurred timestamptz;fault text;
BEGIN
 FOR candidate IN SELECT p.event_id,p.payload FROM sarsa_booking.provider_inbox p
  JOIN sarsa_booking.enquiry_delivery_jobs d ON d.id::text=p.payload->>'job_id'
  WHERE p.provider='resend' AND p.account_id='bookings@mail.sarsajyotishsansthan.com' AND p.environment='live'
    AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp() ORDER BY p.next_attempt_at,p.received_at LIMIT 20 LOOP
  SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id::text=candidate.payload->>'job_id' FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO e FROM sarsa_booking.provider_inbox WHERE provider='resend' AND account_id='bookings@mail.sarsajyotishsansthan.com'
   AND environment='live' AND event_id=candidate.event_id AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  fault:=NULL;
  BEGIN
   provider_uuid:=(e.payload->>'email_id')::uuid;occurred:=(e.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN provider_uuid:=NULL;occurred:=NULL; END;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.kind NOT IN ('verification','acknowledgement','practice_notice') OR j.first_attempt_at IS NULL OR j.message_digest IS NULL
   OR provider_uuid IS NULL OR occurred IS NULL OR NOT isfinite(occurred)
   OR e.payload->>'event' IS NULL OR e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed') THEN fault:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text)
   OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id)
   OR EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=provider_uuid::text AND recipient_role IN ('customer','client'))
   THEN fault:='email_event_provider_conflict'; END IF;
  IF fault IS NOT NULL THEN
   UPDATE sarsa_booking.provider_inbox SET attempts=attempts+1,last_error_code=fault,next_attempt_at=clock_timestamp()+interval '1 hour'
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id; RETURN false;
  END IF;
  INSERT INTO sarsa_booking.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
   VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET provider_id=provider_uuid::text,
   state=CASE WHEN state IN ('processing','attention','suppressed','expired') THEN state ELSE 'accepted' END WHERE id=j.id;
  UPDATE sarsa_booking.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
   WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP; RETURN false;
END $body$;

ALTER TABLE sarsa_booking.google_workbooks ADD COLUMN next_enquiry_row integer NOT NULL DEFAULT 2 CHECK(next_enquiry_row BETWEEN 2 AND 10001);
CREATE TABLE sarsa_booking.enquiry_sheet_rows (
 role text NOT NULL REFERENCES sarsa_booking.google_workbooks(role),job_id uuid NOT NULL REFERENCES sarsa_booking.enquiry_delivery_jobs(id),
 row_number integer NOT NULL CHECK(row_number BETWEEN 2 AND 10000),
 values_json jsonb NOT NULL CHECK(jsonb_typeof(values_json)='array' AND jsonb_array_length(values_json)=10),
 PRIMARY KEY(role,job_id),UNIQUE(role,row_number)
);
REVOKE ALL ON sarsa_booking.enquiry_sheet_rows FROM PUBLIC;
GRANT SELECT,INSERT ON sarsa_booking.enquiry_sheet_rows TO sarsa_booking_runtime;
CREATE FUNCTION sarsa_booking.assign_enquiry_row(p_role text,p_job uuid,p_values jsonb) RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE w sarsa_booking.google_workbooks%ROWTYPE;old sarsa_booking.enquiry_sheet_rows%ROWTYPE;
BEGIN
 IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_values IS NULL OR jsonb_typeof(p_values)<>'array' OR jsonb_array_length(p_values)<>10
  OR p_values->>0 IS DISTINCT FROM '004-sarsa-jyotish-sansthan' OR p_values->>1 IS DISTINCT FROM p_job::text THEN RETURN NULL; END IF;
 SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role AND state='ready' FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs j JOIN sarsa_booking.enquiries e USING(request_id)
  WHERE j.id=p_job AND j.kind=CASE WHEN p_role='client' THEN 'client_sheet' ELSE 'agency_sheet' END
   AND j.request_id::text=p_values->>2 AND e.verified_at IS NOT NULL
   AND (p_values->>3)::timestamptz=e.verified_at AND p_values->>4=e.payload->>'name'
   AND p_values->>5=e.payload->>'email' AND p_values->>6=e.payload->>'phone'
   AND p_values->>7=e.payload->>'subject' AND p_values->>8=e.payload->>'message'
   AND p_values->>9='received') THEN RETURN NULL; END IF;
 SELECT * INTO old FROM sarsa_booking.enquiry_sheet_rows WHERE role=p_role AND job_id=p_job;
 IF FOUND THEN
  IF old.values_json IS DISTINCT FROM p_values THEN RETURN NULL; END IF;
  RETURN jsonb_build_object('row',old.row_number,'spreadsheet_id',w.spreadsheet_id,'intent',w.intent,'values',old.values_json);
 END IF;
 IF w.next_enquiry_row>10000 THEN RETURN NULL; END IF;
 INSERT INTO sarsa_booking.enquiry_sheet_rows VALUES(p_role,p_job,w.next_enquiry_row,p_values);
 UPDATE sarsa_booking.google_workbooks SET next_enquiry_row=next_enquiry_row+1 WHERE role=p_role;
 RETURN jsonb_build_object('row',w.next_enquiry_row,'spreadsheet_id',w.spreadsheet_id,'intent',w.intent,'values',p_values);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.contact_job_eligible(sarsa_booking.enquiries,sarsa_booking.enquiry_delivery_jobs),
 sarsa_booking.claim_enquiry_delivery(text),sarsa_booking.email_recipient_suppressed(text),
 sarsa_booking.begin_enquiry_send(uuid,uuid,text,text),sarsa_booking.finish_enquiry_delivery(uuid,uuid,text,text,boolean,integer),
 sarsa_booking.protect_enquiry_delivery(),sarsa_booking.reconcile_enquiry_email_event(),sarsa_booking.assign_enquiry_row(text,uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.contact_job_eligible(sarsa_booking.enquiries,sarsa_booking.enquiry_delivery_jobs),
 sarsa_booking.claim_enquiry_delivery(text),sarsa_booking.email_recipient_suppressed(text),
 sarsa_booking.begin_enquiry_send(uuid,uuid,text,text),sarsa_booking.finish_enquiry_delivery(uuid,uuid,text,text,boolean,integer),
 sarsa_booking.reconcile_enquiry_email_event(),sarsa_booking.assign_enquiry_row(text,uuid,jsonb) TO sarsa_booking_runtime;

-- Preserve booking admission/event semantics while sharing suppression and routing.
CREATE OR REPLACE FUNCTION sarsa_booking.begin_email_send(p_job uuid,p_lease uuid,p_message jsonb,p_hash text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE; owner_id uuid;
 policy sarsa_booking.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp(); blocked text;
BEGIN
 SELECT booking_id INTO owner_id FROM sarsa_booking.delivery_jobs WHERE id=p_job;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE id=owner_id FOR SHARE;
 SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT sarsa_booking.is_email_job(j.kind,j.recipient_role) OR p_lease IS NULL
   OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
 IF j.provider_id IS NOT NULL THEN
   UPDATE sarsa_booking.delivery_jobs SET state='accepted',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF j.kind<>'payment_review' AND (b.revision<>j.booking_revision OR
   (j.kind='booking_cancelled' AND b.state<>'cancelled') OR(j.kind<>'booking_cancelled' AND b.state<>'confirmed')) THEN
   blocked:='email_obsolete_revision';
 ELSIF j.send_deadline_at IS NULL OR j.send_deadline_at<=instant THEN blocked:='email_deadline_passed';
 ELSIF j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours' THEN blocked:='email_retry_window_closed';
 ELSIF j.recipient_role='customer' AND sarsa_booking.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed';
 END IF;
 IF blocked IS NOT NULL THEN
   UPDATE sarsa_booking.delivery_jobs SET state='attention',last_error_code=blocked,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF p_message IS NULL OR jsonb_typeof(p_message)<>'object' OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$'
   OR p_message->>'from' IS DISTINCT FROM 'Sarsa Jyotish Sansthan <bookings@mail.sarsajyotishsansthan.com>'
   OR p_message->'to' IS DISTINCT FROM jsonb_build_array(j.destination)
   OR p_message->>'reply_to' IS DISTINCT FROM 'sarsajyotish@gmail.com'
   OR p_message->'tags' IS DISTINCT FROM jsonb_build_array(jsonb_build_object('name','project','value','sarsa004'),
       jsonb_build_object('name','job_id','value',j.id::text))
   OR (j.message_snapshot IS NOT NULL AND (j.message_snapshot IS DISTINCT FROM p_message OR j.message_hash IS DISTINCT FROM p_hash)) THEN
   RETURN NULL;
 END IF;
 -- Stable global quota lock is after booking/job; no path takes it in reverse order.
 PERFORM pg_advisory_xact_lock(4004003);
 SELECT * INTO policy FROM sarsa_booking.email_policy WHERE id=true;
 IF policy.daily_limit<=0 OR policy.monthly_limit<=0 THEN
   UPDATE sarsa_booking.delivery_jobs SET state='pending',last_error_code='email_budget_unconfigured',
     next_attempt_at=instant+interval '15 minutes',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.email_reservations WHERE job_id=j.id) THEN
   IF (SELECT count(*) FROM sarsa_booking.email_reservations WHERE reserved_at>=instant-interval '24 hours')>=policy.daily_limit
     OR(SELECT count(*) FROM sarsa_booking.email_reservations WHERE reserved_at>=instant-interval '31 days')>=policy.monthly_limit THEN
     UPDATE sarsa_booking.delivery_jobs SET state='pending',last_error_code='email_budget_exhausted',
       next_attempt_at=instant+interval '15 minutes',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
     RETURN NULL;
   END IF;
   INSERT INTO sarsa_booking.email_reservations(job_id) VALUES(j.id);
 END IF;
 UPDATE sarsa_booking.delivery_jobs SET message_snapshot=p_message,message_hash=p_hash,
   first_attempt_at=coalesce(first_attempt_at,instant),ever_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $body$;

CREATE OR REPLACE FUNCTION sarsa_booking.reconcile_email_event() RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.provider_inbox%ROWTYPE; j sarsa_booking.delivery_jobs%ROWTYPE;
 candidate record; provider_uuid uuid; job_uuid uuid; occurred timestamptz; code text;
BEGIN
 FOR candidate IN SELECT event_id,payload FROM sarsa_booking.provider_inbox
   WHERE provider='resend' AND account_id='bookings@mail.sarsajyotishsansthan.com' AND environment='live'
     AND processed_at IS NULL AND next_attempt_at<=clock_timestamp()
     AND NOT EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs c WHERE c.id::text=payload->>'job_id')
   ORDER BY next_attempt_at,received_at,event_id LIMIT 20 LOOP
  code:=NULL;
  BEGIN
    job_uuid:=(candidate.payload->>'job_id')::uuid;
    provider_uuid:=(candidate.payload->>'email_id')::uuid;
    occurred:=(candidate.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN
    job_uuid:=NULL;provider_uuid:=NULL;occurred:=NULL;
  END;
  SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=job_uuid FOR UPDATE SKIP LOCKED;
  IF NOT FOUND AND EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE id=job_uuid) THEN CONTINUE; END IF;
  SELECT * INTO e FROM sarsa_booking.provider_inbox WHERE provider='resend'
    AND account_id='bookings@mail.sarsajyotishsansthan.com' AND environment='live' AND event_id=candidate.event_id
    AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.id IS NULL OR provider_uuid IS NULL OR occurred IS NULL OR
    NOT sarsa_booking.is_email_job(j.kind,j.recipient_role) OR j.first_attempt_at IS NULL OR j.message_snapshot IS NULL THEN
    code:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text) OR
    EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id AND recipient_role IN ('customer','client')) OR
    EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND kind IN ('verification','acknowledgement','practice_notice')) THEN
    code:='email_event_provider_conflict';
  ELSIF e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed')
    OR e.payload->>'event' IS NULL THEN code:='email_event_invalid';
  END IF;
  IF code IS NOT NULL THEN
    UPDATE sarsa_booking.provider_inbox SET attempts=attempts+1,last_error_code=code,
      next_attempt_at=clock_timestamp()+interval '1 hour' WHERE provider=e.provider AND account_id=e.account_id
      AND environment=e.environment AND event_id=e.event_id;
    RETURN false;
  END IF;
  INSERT INTO sarsa_booking.email_observations(event_id,job_id,provider_id,event_type,occurred_at)
    VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE sarsa_booking.delivery_jobs SET provider_id=provider_uuid::text,accepted_at=coalesce(accepted_at,clock_timestamp()),
    state=CASE WHEN state='processing' THEN state WHEN state IN ('attention','suppressed') THEN state ELSE 'accepted' END
    WHERE id=j.id;
  UPDATE sarsa_booking.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP;
 RETURN false;
END $body$;


-- Minimal customer delivery facts; acceptance is distinct from inbox delivery.
CREATE OR REPLACE FUNCTION sarsa_booking.enquiry_view(p_id uuid,p_receipt text) RETURNS jsonb LANGUAGE sql AS $body$
 SELECT coalesce((SELECT jsonb_build_object('code','ok','request_id',e.request_id,
  'state',CASE WHEN e.verified_at IS NOT NULL THEN 'received' WHEN e.attempts>=5 THEN 'locked'
    WHEN e.code_expires_at<=clock_timestamp() OR e.code_digest IS NULL THEN 'expired' ELSE 'awaiting_verification' END,
  'generation',e.generation,'server_now',clock_timestamp(),'code_expires_at',e.code_expires_at,
  'resend_after',e.resend_after,'sends_remaining',3-e.generation,
  'verification_delivery',coalesce((SELECT CASE
    WHEN EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type IN ('email.bounced','email.complained','email.suppressed')) THEN 'failed'
    WHEN EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.delivered') THEN 'delivered'
    WHEN EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.failed') THEN 'failed'
    WHEN j.state IN ('attention','expired','suppressed') OR (j.state='pending' AND j.last_error_code IN ('email_budget_unconfigured','email_budget_exhausted')) THEN 'unavailable'
    WHEN EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND o.event_type='email.delivery_delayed') THEN 'delayed'
    WHEN j.provider_id IS NOT NULL THEN 'accepted' ELSE 'queued' END
   FROM sarsa_booking.enquiry_delivery_jobs j WHERE j.request_id=e.request_id AND j.kind='verification' AND j.generation=e.generation),'unavailable'))
  FROM sarsa_booking.enquiries e WHERE e.request_id=p_id AND e.receipt_digest=p_receipt
   AND e.receipt_expires_at>clock_timestamp()),jsonb_build_object('code','access_unavailable'));
$body$;


-- Provider identities are exclusive across both kinds of mail, including racing callbacks.
CREATE OR REPLACE FUNCTION sarsa_booking.finish_email_delivery(p_job uuid,p_lease uuid,p_provider uuid,p_error text,p_attention boolean,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 900 OR p_attention IS NULL
   OR(p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
 SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT sarsa_booking.is_email_job(j.kind,j.recipient_role) OR j.lease_token IS DISTINCT FROM p_lease
   OR p_lease IS NULL OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() THEN RETURN false; END IF;
 IF p_provider IS NOT NULL AND (j.first_attempt_at IS NULL OR j.message_snapshot IS NULL) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-mail-provider:'||p_provider::text,0)); END IF;
 IF p_provider IS NOT NULL AND ((j.provider_id IS NOT NULL AND j.provider_id<>p_provider::text)
   OR EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=p_provider::text AND id<>j.id AND recipient_role IN ('customer','client'))
   OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE provider_id=p_provider::text AND kind IN ('verification','acknowledgement','practice_notice'))) THEN
   UPDATE sarsa_booking.delivery_jobs SET state='attention',last_error_code='email_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN false;
 END IF;
 UPDATE sarsa_booking.delivery_jobs SET provider_id=coalesce(p_provider::text,provider_id),
   accepted_at=CASE WHEN p_provider IS NOT NULL THEN coalesce(accepted_at,clock_timestamp()) ELSE accepted_at END,
   state=CASE WHEN p_provider IS NOT NULL OR provider_id IS NOT NULL THEN 'accepted' WHEN p_attention THEN 'attention' ELSE 'uncertain' END,
   last_error_code=p_error,next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
 RETURN true;
END $body$;
