-- Older verification receipts and unlinked delivery reports are evidence, not
-- current challenges, jobs or authorisation. Preserve their exact known facts.
SET LOCAL ROLE appointment_system_owner;
CREATE TABLE appointment_system.historical_verification_receipts (
 challenge_id uuid PRIMARY KEY, provider_id uuid NOT NULL UNIQUE,
 mail_account_id text NOT NULL CHECK(mail_account_id ~ '^[A-Za-z0-9_-]{1,80}$'),
 purpose text NOT NULL CHECK(purpose IN ('booking','contact','prashna')),
 accepted_at timestamptz NOT NULL,
 UNIQUE(challenge_id,provider_id,mail_account_id)
);
CREATE TABLE appointment_system.historical_email_observations (
 event_id text PRIMARY KEY CHECK(event_id ~ '^[A-Za-z0-9_-]{1,128}$'),
 provider_id uuid NOT NULL,mail_account_id text NOT NULL,
 classification text NOT NULL CHECK(classification IN ('verification','unmatched')),
 challenge_id uuid,
 event_type text NOT NULL CHECK(event_type IN ('email.sent','email.delivered','email.delivery_delayed',
  'email.bounced','email.complained','email.failed','email.suppressed')),
 occurred_at timestamptz NOT NULL,recorded_at timestamptz NOT NULL,
 CHECK((classification='verification')=(challenge_id IS NOT NULL)),
 CHECK(mail_account_id ~ '^[A-Za-z0-9_-]{1,80}$'),
 FOREIGN KEY(challenge_id,provider_id,mail_account_id)
  REFERENCES appointment_system.historical_verification_receipts(challenge_id,provider_id,mail_account_id)
);
CREATE INDEX historical_mail_provider ON appointment_system.historical_email_observations(provider_id,mail_account_id);
REVOKE ALL ON appointment_system.historical_verification_receipts,appointment_system.historical_email_observations FROM PUBLIC;
GRANT SELECT ON appointment_system.historical_verification_receipts,appointment_system.historical_email_observations TO appointment_system_backup_access;

-- A provider ID already proven to belong to a retired verification message
-- cannot become evidence for a newly queued booking, enquiry or code.
CREATE OR REPLACE FUNCTION appointment_system.append_mail_acceptance(p_kind text,p_job uuid,p_hash text,p_provider uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE data jsonb;acceptance_result text:='accepted';
BEGIN
 IF p_kind IS NULL OR p_hash IS NULL OR p_kind NOT IN('booking','contact','verification') OR p_job IS NULL OR p_provider IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RETURN 'invalid';END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(j) INTO data FROM appointment_system.delivery_jobs j WHERE id=p_job AND appointment_system.is_email_job(j.kind,j.recipient_role) FOR UPDATE;
 ELSIF p_kind='verification' THEN
  SELECT to_jsonb(j) INTO data FROM appointment_system.booking_verification_mail j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT to_jsonb(j) INTO data FROM appointment_system.enquiry_delivery_jobs j WHERE id=p_job AND kind IN('verification','acknowledgement','practice_notice') FOR UPDATE;
 END IF;
 IF data IS NULL OR data->>'first_attempt_at' IS NULL OR coalesce(data->>'message_hash',data->>'message_digest') IS DISTINCT FROM p_hash THEN RETURN 'invalid';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('appointment-mail-provider:'||p_provider::text,0));
 IF EXISTS(SELECT 1 FROM appointment_system.historical_verification_receipts WHERE provider_id=p_provider)
 OR EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE provider_id=p_provider AND result='accepted' AND(kind<>p_kind OR job_id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='accepted' AND(provider_id<>p_provider OR message_hash<>p_hash))
 OR EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE provider_id=p_provider::text AND recipient_role IN('customer','client') AND(p_kind<>'booking' OR id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.enquiry_delivery_jobs WHERE provider_id=p_provider::text AND kind IN('verification','acknowledgement','practice_notice') AND(p_kind<>'contact' OR id<>p_job))
 OR EXISTS(SELECT 1 FROM appointment_system.booking_verification_mail WHERE provider_id=p_provider AND(p_kind<>'verification' OR id<>p_job))
 OR(data->>'provider_id' IS NOT NULL AND data->>'provider_id'<>p_provider::text) THEN acceptance_result:='conflict';END IF;
 INSERT INTO appointment_system.mail_acceptance_claims(kind,job_id,provider_id,message_hash,result)
 VALUES(p_kind,p_job,p_provider,p_hash,acceptance_result) ON CONFLICT DO NOTHING;
 RETURN acceptance_result;
END $$;
RESET ROLE;
