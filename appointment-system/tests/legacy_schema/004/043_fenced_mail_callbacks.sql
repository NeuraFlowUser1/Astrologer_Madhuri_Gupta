-- Signed callbacks retain exact message facts without completing another lease.
CREATE OR REPLACE FUNCTION sarsa_booking.email_recipient_suppressed(p_destination text) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM sarsa_booking.email_observations o JOIN sarsa_booking.delivery_jobs j ON j.id=o.job_id
  WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
 OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o JOIN sarsa_booking.enquiry_delivery_jobs j ON j.id=o.job_id
  WHERE lower(j.destination)=lower(p_destination) AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
$$;
CREATE OR REPLACE FUNCTION sarsa_booking.reconcile_enquiry_email_event() RETURNS boolean LANGUAGE plpgsql AS $body$
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
  IF fault IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   fault:='email_event_invalid'; END IF;
  IF fault IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   fault:='email_event_job_unmatched'; END IF;
  IF fault IS NULL AND sarsa_booking.append_mail_acceptance('contact',j.id,j.message_digest,provider_uuid)<>'accepted' THEN
   fault:='email_event_provider_conflict'; END IF;
  IF fault IS NOT NULL THEN
   UPDATE sarsa_booking.provider_inbox SET attempts=attempts+1,last_error_code=fault,next_attempt_at=clock_timestamp()+interval '1 hour'
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id; RETURN false;
  END IF;
  INSERT INTO sarsa_booking.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
   VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET provider_id=provider_uuid::text,
   state=CASE WHEN state IN ('attention','suppressed','expired') THEN state ELSE 'accepted' END WHERE id=j.id
    AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE sarsa_booking.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
   WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP; RETURN false;
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
  IF code IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   code:='email_event_invalid'; END IF;
  IF code IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   code:='email_event_job_unmatched'; END IF;
  IF code IS NULL AND sarsa_booking.append_mail_acceptance('booking',j.id,j.message_hash,provider_uuid)<>'accepted' THEN
   code:='email_event_provider_conflict'; END IF;
  IF code IS NOT NULL THEN
    UPDATE sarsa_booking.provider_inbox SET attempts=attempts+1,last_error_code=code,
      next_attempt_at=clock_timestamp()+interval '1 hour' WHERE provider=e.provider AND account_id=e.account_id
      AND environment=e.environment AND event_id=e.event_id;
    RETURN false;
  END IF;
  INSERT INTO sarsa_booking.email_observations(event_id,job_id,provider_id,event_type,occurred_at)
    VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE sarsa_booking.delivery_jobs SET provider_id=provider_uuid::text,accepted_at=coalesce(accepted_at,clock_timestamp()),
    state=CASE WHEN state IN ('attention','suppressed') THEN state ELSE 'accepted' END
    WHERE id=j.id AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE sarsa_booking.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP;
 RETURN false;
END $body$;


CREATE OR REPLACE FUNCTION sarsa_booking.begin_email_send(p_job uuid,p_lease uuid,p_message jsonb,p_hash text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE; owner_id uuid;
 policy sarsa_booking.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp(); blocked text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
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
 ELSIF sarsa_booking.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed';
 END IF;
 IF blocked IS NOT NULL THEN
   UPDATE sarsa_booking.delivery_jobs SET state='attention',last_error_code=blocked,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
   RETURN NULL;
 END IF;
 IF p_message IS NULL OR jsonb_typeof(p_message)<>'object' OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$'
   OR p_message->>'from' IS DISTINCT FROM 'Sarsa Jyotish Sansthan <bookings@mail.sarsajyotishsansthan.com>'
   OR p_message->'to' IS DISTINCT FROM jsonb_build_array(j.destination)
   OR p_message->>'reply_to' IS DISTINCT FROM 'sarsajyotish@gmail.com'
   OR (p_message->'tags' IS DISTINCT FROM jsonb_build_array(jsonb_build_object('name','project','value','sarsa004'),
       jsonb_build_object('name','job_id','value',j.id::text)) AND p_message->'tags' IS DISTINCT FROM
       jsonb_build_array(jsonb_build_object('name','project','value','sarsa004'),jsonb_build_object('name','job_id','value',j.id::text),
       jsonb_build_object('name','message_version','value',j.template_version::text)))
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
   first_attempt_at=coalesce(first_attempt_at,instant),prior_send_uncertain=send_uncertain,send_uncertain=true,ever_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $body$;

CREATE OR REPLACE FUNCTION sarsa_booking.begin_enquiry_send(p_job uuid,p_lease uuid,p_cipher text,p_digest text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;
 owner_id uuid; policy sarsa_booking.email_policy%ROWTYPE; instant timestamptz:=clock_timestamp();blocked text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.kind NOT IN ('verification','acknowledgement','practice_notice') OR p_lease IS NULL
  OR j.lease_token IS DISTINCT FROM p_lease OR j.state<>'processing' OR j.lease_expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
 IF NOT sarsa_booking.contact_job_eligible(e,j) OR (j.deadline_at<=instant AND (j.kind NOT IN('acknowledgement','practice_notice') OR j.send_uncertain OR coalesce(j.last_error_code,'') NOT IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) THEN blocked:='contact_deadline_or_state';
 ELSIF j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours' THEN blocked:='email_retry_window_closed';
 ELSIF sarsa_booking.email_recipient_suppressed(j.destination) THEN blocked:='email_recipient_suppressed'; END IF;
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
   next_attempt_at=CASE WHEN kind='verification' THEN least(deadline_at,instant+interval '15 minutes') ELSE instant+interval '15 minutes' END,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 INSERT INTO sarsa_booking.email_reservations(enquiry_job_id) VALUES(j.id) ON CONFLICT(enquiry_job_id) DO NOTHING;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET message_ciphertext=p_cipher,message_digest=p_digest,
  first_attempt_at=coalesce(first_attempt_at,instant),prior_send_uncertain=send_uncertain,send_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $body$;
