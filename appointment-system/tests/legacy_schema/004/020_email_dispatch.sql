-- Durable mail admission. Default budget is zero until shared-team capacity is approved.
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN message_snapshot jsonb;
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN template_version integer NOT NULL DEFAULT 1 CHECK(template_version>0);
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN message_hash text;
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN send_deadline_at timestamptz;
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN ever_uncertain boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN accepted_at timestamptz;
CREATE UNIQUE INDEX email_provider_identity ON sarsa_booking.delivery_jobs(provider_id)
 WHERE recipient_role IN ('customer','client') AND provider_id IS NOT NULL;
CREATE TABLE sarsa_booking.email_policy (
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 daily_limit integer NOT NULL DEFAULT 0 CHECK(daily_limit BETWEEN 0 AND 100),
 monthly_limit integer NOT NULL DEFAULT 0 CHECK(monthly_limit BETWEEN 0 AND 3000)
);
INSERT INTO sarsa_booking.email_policy DEFAULT VALUES;
CREATE TABLE sarsa_booking.email_reservations (
 job_id uuid PRIMARY KEY REFERENCES sarsa_booking.delivery_jobs(id),
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX email_reservation_time ON sarsa_booking.email_reservations(reserved_at);
CREATE TABLE sarsa_booking.email_observations (
 event_id text PRIMARY KEY,
 job_id uuid NOT NULL REFERENCES sarsa_booking.delivery_jobs(id),
 provider_id uuid NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('email.sent','email.delivered','email.delivery_delayed',
   'email.bounced','email.complained','email.failed','email.suppressed')),
 occurred_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX email_observation_job ON sarsa_booking.email_observations(job_id,event_type);
REVOKE ALL ON sarsa_booking.email_policy,sarsa_booking.email_reservations,sarsa_booking.email_observations FROM PUBLIC;
GRANT SELECT ON sarsa_booking.email_policy,sarsa_booking.email_reservations,sarsa_booking.email_observations TO sarsa_booking_runtime;
GRANT INSERT ON sarsa_booking.email_reservations,sarsa_booking.email_observations TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.is_email_job(k text,r text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$ SELECT (k='booking_ack' AND r IN ('customer','client'))
 OR(k='booking_details' AND r='customer') OR(k='booking_cancelled' AND r IN ('customer','client'))
 OR(k='payment_review' AND r='client') $$;

CREATE FUNCTION sarsa_booking.claim_email_delivery() RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE; candidate record; link text;
BEGIN
 FOR candidate IN SELECT id,booking_id FROM sarsa_booking.delivery_jobs
   WHERE sarsa_booking.is_email_job(kind,recipient_role) AND state IN ('pending','failed','uncertain','processing')
   AND next_attempt_at<=clock_timestamp() AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
   ORDER BY next_attempt_at,id LIMIT 20 LOOP
  SELECT * INTO b FROM sarsa_booking.bookings WHERE id=candidate.booking_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=candidate.id
    AND state IN ('pending','failed','uncertain','processing') AND next_attempt_at<=clock_timestamp()
    AND(lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF j.provider_id IS NOT NULL THEN
    UPDATE sarsa_booking.delivery_jobs SET state='accepted',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF j.kind<>'payment_review' AND (j.booking_revision<>b.revision OR
    (j.kind='booking_cancelled' AND b.state<>'cancelled') OR (j.kind<>'booking_cancelled' AND b.state<>'confirmed')) THEN
    UPDATE sarsa_booking.delivery_jobs SET state=CASE WHEN first_attempt_at IS NULL THEN 'suppressed' ELSE 'attention' END,
      last_error_code='email_obsolete_revision',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF j.kind='booking_details' THEN
    SELECT meet_url INTO link FROM sarsa_booking.meeting_events WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready';
    IF link IS NULL THEN
      UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '30 seconds' WHERE id=j.id;
      CONTINUE;
    END IF;
  END IF;
  UPDATE sarsa_booking.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
    lease_expires_at=clock_timestamp()+interval '180 seconds',attempts=attempts+1,
    send_deadline_at=coalesce(send_deadline_at,CASE WHEN kind IN ('booking_ack','booking_details') THEN b.starts_at
      ELSE clock_timestamp()+interval '24 hours' END),
    destination=coalesce(destination,CASE WHEN recipient_role='customer' THEN b.email ELSE 'sarsajyotish@gmail.com' END),
    payload=coalesce(payload,jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name',
      'starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,
      'meet_url',CASE WHEN kind='booking_details' THEN link ELSE NULL END))
    WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j);
 END LOOP;
 RETURN NULL;
END $body$;

CREATE FUNCTION sarsa_booking.begin_email_send(p_job uuid,p_lease uuid,p_message jsonb,p_hash text)
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
 ELSIF j.recipient_role='customer' AND EXISTS(SELECT 1 FROM sarsa_booking.email_observations o
   JOIN sarsa_booking.delivery_jobs d ON d.id=o.job_id WHERE d.destination=j.destination
   AND o.event_type IN ('email.bounced','email.complained')) THEN blocked:='email_recipient_suppressed';
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

CREATE FUNCTION sarsa_booking.finish_email_delivery(p_job uuid,p_lease uuid,p_provider uuid,p_error text,p_attention boolean,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 900 OR p_attention IS NULL
   OR(p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
 SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR NOT sarsa_booking.is_email_job(j.kind,j.recipient_role) OR j.lease_token IS DISTINCT FROM p_lease
   OR p_lease IS NULL OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() THEN RETURN false; END IF;
 IF p_provider IS NOT NULL AND (j.first_attempt_at IS NULL OR j.message_snapshot IS NULL) THEN RETURN false; END IF;
 IF p_provider IS NOT NULL AND j.provider_id IS NOT NULL AND j.provider_id<>p_provider::text THEN
   UPDATE sarsa_booking.delivery_jobs SET state='attention',last_error_code='email_provider_conflict',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN false;
 END IF;
 UPDATE sarsa_booking.delivery_jobs SET provider_id=coalesce(p_provider::text,provider_id),
   accepted_at=CASE WHEN p_provider IS NOT NULL THEN coalesce(accepted_at,clock_timestamp()) ELSE accepted_at END,
   state=CASE WHEN p_provider IS NOT NULL OR provider_id IS NOT NULL THEN 'accepted' WHEN p_attention THEN 'attention' ELSE 'uncertain' END,
   last_error_code=p_error,next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
 RETURN true;
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.is_email_job(text,text),sarsa_booking.claim_email_delivery(),
 sarsa_booking.begin_email_send(uuid,uuid,jsonb,text),sarsa_booking.finish_email_delivery(uuid,uuid,uuid,text,boolean,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.is_email_job(text,text),sarsa_booking.claim_email_delivery(),
 sarsa_booking.begin_email_send(uuid,uuid,jsonb,text),sarsa_booking.finish_email_delivery(uuid,uuid,uuid,text,boolean,integer) TO sarsa_booking_runtime;

-- One signed inbox report per transaction; lock job before inbox, never booking afterward.
CREATE FUNCTION sarsa_booking.reconcile_email_event() RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.provider_inbox%ROWTYPE; j sarsa_booking.delivery_jobs%ROWTYPE;
 candidate record; provider_uuid uuid; job_uuid uuid; occurred timestamptz; code text;
BEGIN
 FOR candidate IN SELECT event_id,payload FROM sarsa_booking.provider_inbox
   WHERE provider='resend' AND account_id='bookings@mail.sarsajyotishsansthan.com' AND environment='live'
     AND processed_at IS NULL AND next_attempt_at<=clock_timestamp()
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
  IF j.id IS NULL OR provider_uuid IS NULL OR occurred IS NULL OR
    NOT sarsa_booking.is_email_job(j.kind,j.recipient_role) OR j.first_attempt_at IS NULL OR j.message_snapshot IS NULL THEN
    code:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text) OR
    EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id AND recipient_role IN ('customer','client')) THEN
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

CREATE FUNCTION sarsa_booking.email_delivery_state(p_job uuid) RETURNS text LANGUAGE sql STABLE AS $$
 SELECT CASE
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.complained') THEN 'complained'
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.bounced') THEN 'bounced'
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.suppressed') THEN 'suppressed'
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.delivered') THEN 'delivered'
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.failed') THEN 'failed'
 WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations WHERE job_id=d.id AND event_type='email.delivery_delayed') THEN 'delayed'
 WHEN d.provider_id IS NOT NULL THEN 'accepted'
 ELSE d.state END FROM sarsa_booking.delivery_jobs d WHERE id=p_job AND sarsa_booking.is_email_job(d.kind,d.recipient_role)
$$;
REVOKE ALL ON FUNCTION sarsa_booking.reconcile_email_event(),sarsa_booking.email_delivery_state(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.reconcile_email_event(),sarsa_booking.email_delivery_state(uuid) TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.protect_email_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF sarsa_booking.is_email_job(OLD.kind,OLD.recipient_role) AND OLD.first_attempt_at IS NOT NULL AND
   (NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at OR NEW.message_snapshot IS DISTINCT FROM OLD.message_snapshot
    OR NEW.template_version IS DISTINCT FROM OLD.template_version OR NEW.message_hash IS DISTINCT FROM OLD.message_hash OR NEW.destination IS DISTINCT FROM OLD.destination
    OR NEW.booking_id IS DISTINCT FROM OLD.booking_id OR NEW.booking_revision IS DISTINCT FROM OLD.booking_revision
    OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.recipient_role IS DISTINCT FROM OLD.recipient_role
    OR NEW.event_key IS DISTINCT FROM OLD.event_key OR NEW.send_deadline_at IS DISTINCT FROM OLD.send_deadline_at) THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Attempted email identity is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER email_snapshot_immutable BEFORE UPDATE ON sarsa_booking.delivery_jobs
 FOR EACH ROW EXECUTE FUNCTION sarsa_booking.protect_email_snapshot();
REVOKE ALL ON FUNCTION sarsa_booking.protect_email_snapshot() FROM PUBLIC;
