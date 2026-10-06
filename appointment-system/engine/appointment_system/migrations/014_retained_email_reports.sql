-- Untagged historical reports are matched only by a saved accepted provider
-- identity, retained account, exact protocol and recipient digest. No current
-- tag binding or unknown provider identity is guessed.
CREATE FUNCTION appointment_system.resolved_mail_job(p_account text,p_payload jsonb) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
 SELECT CASE WHEN p_payload->>'job_id' ~ '^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
  THEN (p_payload->>'job_id')::uuid ELSE
  (SELECT CASE WHEN count(*)=1 THEN min(id::text)::uuid END FROM (
   SELECT id FROM appointment_system.delivery_jobs WHERE provider_id=p_payload->>'email_id'
    AND mail_event_account_id=p_account AND mail_format='resend-legacy-untagged-job-v1'
    AND first_attempt_at IS NOT NULL AND appointment_system.is_email_job(kind,recipient_role)
    AND encode(sha256(convert_to(lower(trim(destination)),'UTF8')),'hex')=p_payload->>'recipient_hash'
   UNION ALL
   SELECT id FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=p_payload->>'email_id'
    AND mail_event_account_id=p_account AND mail_format='resend-legacy-untagged-job-v1'
    AND first_attempt_at IS NOT NULL AND kind IN('acknowledgement','practice_notice')
    AND encode(sha256(convert_to(lower(trim(destination)),'UTF8')),'hex')=p_payload->>'recipient_hash'
  ) owned WHERE p_payload->>'mail_format'='resend-legacy-untagged-job-v1'
   AND p_payload->>'binding_version'='2') END;
$$;
ALTER FUNCTION appointment_system.resolved_mail_job(text,jsonb) OWNER TO appointment_system_owner;
REVOKE ALL ON FUNCTION appointment_system.resolved_mail_job(text,jsonb) FROM PUBLIC;
CREATE OR REPLACE FUNCTION appointment_system.entry_reconcile_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE e appointment_system.provider_inbox%ROWTYPE; j appointment_system.delivery_jobs%ROWTYPE;
 candidate record; provider_uuid uuid; job_uuid uuid; occurred timestamptz; code text;
BEGIN
 FOR candidate IN SELECT p.account_id,p.event_id,p.payload FROM appointment_system.provider_inbox p
   WHERE p.provider='resend' AND p.environment='live' AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp()
    AND (p.account_id=appointment_system.installation_value('sender.email')
     OR EXISTS(SELECT 1 FROM appointment_system.mail_connection m WHERE p.account_id=m.account_id
      OR EXISTS(SELECT 1 FROM jsonb_array_elements(m.legacy_identities) a WHERE a->>'event_account_id'=p.account_id)))
    AND NOT EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs c WHERE c.id::text=appointment_system.resolved_mail_job(p.account_id,p.payload)::text)
    AND NOT EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail c WHERE c.id::text=appointment_system.resolved_mail_job(p.account_id,p.payload)::text)
   ORDER BY p.next_attempt_at,p.received_at,p.event_id LIMIT 20 LOOP
  code:=NULL;
  BEGIN
    job_uuid:=(appointment_system.resolved_mail_job(candidate.account_id,candidate.payload)::text)::uuid;
    provider_uuid:=(candidate.payload->>'email_id')::uuid;
    occurred:=(candidate.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN
    job_uuid:=NULL;provider_uuid:=NULL;occurred:=NULL;
  END;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=job_uuid FOR UPDATE SKIP LOCKED;
  IF NOT FOUND AND EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE id=job_uuid) THEN CONTINUE; END IF;
  SELECT * INTO e FROM appointment_system.provider_inbox WHERE provider='resend'
    AND account_id=candidate.account_id AND environment='live' AND event_id=candidate.event_id
    AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.id IS NULL OR e.account_id IS DISTINCT FROM coalesce(j.mail_event_account_id,appointment_system.installation_value('sender.email')) OR provider_uuid IS NULL OR occurred IS NULL OR
    NOT appointment_system.is_email_job(j.kind,j.recipient_role) OR j.first_attempt_at IS NULL OR j.message_snapshot IS NULL THEN
    code:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text) OR
    EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id AND recipient_role IN ('customer','client')) OR
    EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND kind IN ('verification','acknowledgement','practice_notice')) THEN
    code:='email_event_provider_conflict';
  ELSIF e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed')
    OR e.payload->>'event' IS NULL THEN code:='email_event_invalid';
  END IF;
  IF code IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   code:='email_event_invalid'; END IF;
  IF code IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR (e.payload->>'mail_format' IS NOT NULL AND e.payload->>'mail_format' IS DISTINCT FROM j.mail_format) OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   code:='email_event_job_unmatched'; END IF;
  IF code IS NULL AND appointment_system.append_mail_acceptance('booking',j.id,j.message_hash,provider_uuid)<>'accepted' THEN
   code:='email_event_provider_conflict'; END IF;
  IF code IS NOT NULL THEN
    UPDATE appointment_system.provider_inbox SET attempts=attempts+1,last_error_code=code,
      next_attempt_at=clock_timestamp()+interval '1 hour' WHERE provider=e.provider AND account_id=e.account_id
      AND environment=e.environment AND event_id=e.event_id;
    RETURN false;
  END IF;
  INSERT INTO appointment_system.email_observations(event_id,job_id,provider_id,event_type,occurred_at)
    VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE appointment_system.delivery_jobs SET provider_id=provider_uuid::text,accepted_at=coalesce(accepted_at,clock_timestamp()),
    state=CASE WHEN state IN ('needs_review','suppressed') THEN state ELSE 'completed' END
    WHERE id=j.id AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE appointment_system.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP;
 RETURN false;
END $$;
CREATE OR REPLACE FUNCTION appointment_system.entry_reconcile_enquiry_email_event() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE candidate record;e appointment_system.provider_inbox%ROWTYPE;j appointment_system.enquiry_delivery_jobs%ROWTYPE;provider_uuid uuid;occurred timestamptz;fault text;
BEGIN
 FOR candidate IN SELECT p.account_id,p.event_id,p.payload FROM appointment_system.provider_inbox p
  JOIN appointment_system.enquiry_delivery_jobs d ON d.id::text=appointment_system.resolved_mail_job(p.account_id,p.payload)::text
  WHERE p.provider='resend' AND p.account_id=coalesce(d.mail_event_account_id,appointment_system.installation_value('sender.email')) AND p.environment='live'
    AND p.processed_at IS NULL AND p.next_attempt_at<=clock_timestamp() ORDER BY p.next_attempt_at,p.received_at LIMIT 20 LOOP
  SELECT * INTO j FROM appointment_system.enquiry_delivery_jobs WHERE id::text=appointment_system.resolved_mail_job(candidate.account_id,candidate.payload)::text FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO e FROM appointment_system.provider_inbox WHERE provider='resend' AND account_id=candidate.account_id
   AND environment='live' AND event_id=candidate.event_id AND processed_at IS NULL AND next_attempt_at<=clock_timestamp() FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  fault:=NULL;
  BEGIN
   provider_uuid:=(e.payload->>'email_id')::uuid;occurred:=(e.payload->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN provider_uuid:=NULL;occurred:=NULL; END;
  IF provider_uuid IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||provider_uuid::text,0)); END IF;
  IF j.kind NOT IN ('verification','acknowledgement','practice_notice') OR j.first_attempt_at IS NULL OR j.message_digest IS NULL
   OR provider_uuid IS NULL OR occurred IS NULL OR NOT isfinite(occurred)
   OR e.payload->>'event' IS NULL OR e.payload->>'event' NOT IN ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed','email.suppressed') THEN fault:='email_event_job_unmatched';
  ELSIF (j.provider_id IS NOT NULL AND j.provider_id<>provider_uuid::text)
   OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=provider_uuid::text AND id<>j.id)
   OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=provider_uuid::text AND recipient_role IN ('customer','client'))
   THEN fault:='email_event_provider_conflict'; END IF;
  IF fault IS NULL AND (occurred>clock_timestamp()+interval '5 minutes' OR NOT isfinite(occurred)) THEN
   fault:='email_event_invalid'; END IF;
  IF fault IS NULL AND e.payload->>'binding_version' IS NOT NULL AND (
   e.payload->>'binding_version'<>'2' OR (e.payload->>'mail_format' IS NOT NULL AND e.payload->>'mail_format' IS DISTINCT FROM j.mail_format) OR e.payload->>'recipient_hash' IS DISTINCT FROM
   encode(sha256(convert_to(lower(trim(j.destination)),'UTF8')),'hex') OR
   (e.payload->>'message_version' IS NOT NULL AND e.payload->>'message_version'<>j.template_version::text)) THEN
   fault:='email_event_job_unmatched'; END IF;
  IF fault IS NULL AND appointment_system.append_mail_acceptance('contact',j.id,j.message_digest,provider_uuid)<>'accepted' THEN
   fault:='email_event_provider_conflict'; END IF;
  IF fault IS NOT NULL THEN
   UPDATE appointment_system.provider_inbox SET attempts=attempts+1,last_error_code=fault,next_attempt_at=clock_timestamp()+interval '1 hour'
    WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id; RETURN false;
  END IF;
  INSERT INTO appointment_system.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
   VALUES(e.event_id,j.id,provider_uuid,e.payload->>'event',occurred) ON CONFLICT(event_id) DO NOTHING;
  UPDATE appointment_system.enquiry_delivery_jobs SET provider_id=provider_uuid::text,
   state=CASE WHEN state IN ('needs_review','suppressed','suppressed') THEN state ELSE 'completed' END WHERE id=j.id
    AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp());
  UPDATE appointment_system.provider_inbox SET processed_at=clock_timestamp(),last_error_code=NULL,attempts=attempts+1
   WHERE provider=e.provider AND account_id=e.account_id AND environment=e.environment AND event_id=e.event_id;
  RETURN true;
 END LOOP; RETURN false;
END $$;
