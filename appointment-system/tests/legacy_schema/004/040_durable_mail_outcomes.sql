-- Late mail acceptance is evidence; only the current lease may complete a task.
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN send_uncertain boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN send_uncertain boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN prior_send_uncertain boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN prior_send_uncertain boolean NOT NULL DEFAULT false;
UPDATE sarsa_booking.delivery_jobs SET send_uncertain=true WHERE first_attempt_at IS NOT NULL AND provider_id IS NULL;
UPDATE sarsa_booking.enquiry_delivery_jobs SET send_uncertain=true WHERE first_attempt_at IS NOT NULL AND provider_id IS NULL;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs DROP CONSTRAINT enquiry_delivery_jobs_template_version_check;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD CHECK(template_version IN(1,2,3));
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN product_revision bigint;
ALTER TABLE sarsa_booking.enquiry_delivery_jobs ADD COLUMN product_generation uuid;
CREATE TABLE sarsa_booking.mail_acceptance_claims(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),kind text NOT NULL CHECK(kind IN('booking','contact')),job_id uuid NOT NULL,
 provider_id uuid NOT NULL,message_hash text NOT NULL CHECK(message_hash ~ '^[a-f0-9]{64}$'),
 result text NOT NULL CHECK(result IN('accepted','conflict')),observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(kind,job_id,provider_id,message_hash,result));
CREATE INDEX mail_acceptance_lookup ON sarsa_booking.mail_acceptance_claims(kind,job_id,result);
CREATE UNIQUE INDEX mail_accepted_owner ON sarsa_booking.mail_acceptance_claims(provider_id) WHERE result='accepted';
REVOKE ALL ON sarsa_booking.mail_acceptance_claims FROM PUBLIC;
GRANT SELECT ON sarsa_booking.mail_acceptance_claims TO sarsa_booking_runtime;
CREATE FUNCTION sarsa_booking.append_mail_acceptance(p_kind text,p_job uuid,p_hash text,p_provider uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE data jsonb;acceptance_result text:='accepted';
BEGIN
 IF p_kind NOT IN('booking','contact') OR p_job IS NULL OR p_provider IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RETURN 'invalid'; END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.delivery_jobs j WHERE id=p_job AND sarsa_booking.is_email_job(j.kind,j.recipient_role) FOR UPDATE;
 ELSE
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.enquiry_delivery_jobs j WHERE id=p_job AND kind IN('verification','acknowledgement','practice_notice') FOR UPDATE;
 END IF;
 IF data IS NULL OR data->>'first_attempt_at' IS NULL OR coalesce(data->>'message_hash',data->>'message_digest') IS DISTINCT FROM p_hash THEN RETURN 'invalid'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-mail-provider:'||p_provider::text,0));
 IF EXISTS(SELECT 1 FROM sarsa_booking.mail_acceptance_claims WHERE provider_id=p_provider AND result='accepted' AND(kind<>p_kind OR job_id<>p_job))
 OR EXISTS(SELECT 1 FROM sarsa_booking.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='accepted' AND(provider_id<>p_provider OR message_hash<>p_hash))
 OR EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE provider_id=p_provider::text AND recipient_role IN('customer','client') AND(p_kind<>'booking' OR id<>p_job))
 OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE provider_id=p_provider::text AND kind IN('verification','acknowledgement','practice_notice') AND(p_kind<>'contact' OR id<>p_job))
 OR(data->>'provider_id' IS NOT NULL AND data->>'provider_id'<>p_provider::text) THEN acceptance_result:='conflict'; END IF;
 INSERT INTO sarsa_booking.mail_acceptance_claims(kind,job_id,provider_id,message_hash,result)
 VALUES(p_kind,p_job,p_provider,p_hash,acceptance_result) ON CONFLICT DO NOTHING;
 RETURN acceptance_result;
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.append_mail_acceptance(text,uuid,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.append_mail_acceptance(text,uuid,text,uuid) TO sarsa_booking_runtime;

CREATE OR REPLACE FUNCTION sarsa_booking.finish_email_delivery(p_job uuid,p_lease uuid,p_provider uuid,p_error text,p_attention boolean,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 86400 OR p_attention IS NULL
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

CREATE OR REPLACE FUNCTION sarsa_booking.finish_enquiry_delivery(p_job uuid,p_lease uuid,p_provider text,p_error text,p_attention boolean,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;owner_id uuid;is_mail boolean;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 86400 OR p_attention IS NULL
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

CREATE OR REPLACE FUNCTION sarsa_booking.claim_enquiry_delivery(p_lane text) RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE candidate record;e sarsa_booking.enquiries%ROWTYPE;j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
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
  IF NOT sarsa_booking.contact_job_eligible(e,j) OR (j.deadline_at<=clock_timestamp() AND (j.kind NOT IN('acknowledgement','practice_notice') OR j.send_uncertain OR coalesce(j.last_error_code,'') NOT IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) THEN
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
    'render_version',CASE WHEN j.first_attempt_at IS NULL AND j.message_ciphertext IS NULL THEN CASE WHEN coalesce((booking_control.snapshot()->>'enabled')::boolean,false) THEN 2 ELSE 3 END ELSE j.template_version END,
    'observed_product_revision',(booking_control.snapshot()->>'revision')::bigint,
    'observed_product_generation',booking_control.snapshot()->>'generation',
    'code_ciphertext',CASE WHEN j.kind='verification' THEN e.code_ciphertext END,'code_expires_at',e.code_expires_at);
 END LOOP;
 RETURN NULL;
END $body$;

CREATE OR REPLACE FUNCTION sarsa_booking.protect_email_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF sarsa_booking.is_email_job(OLD.kind,OLD.recipient_role) AND OLD.message_snapshot IS NOT NULL AND
   ((OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at AND NOT(NEW.first_attempt_at IS NULL AND NOT OLD.prior_send_uncertain AND NOT NEW.send_uncertain AND NEW.last_error_code IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) OR NEW.message_snapshot IS DISTINCT FROM OLD.message_snapshot
    OR NEW.template_version IS DISTINCT FROM OLD.template_version OR NEW.message_hash IS DISTINCT FROM OLD.message_hash OR NEW.destination IS DISTINCT FROM OLD.destination
    OR NEW.booking_id IS DISTINCT FROM OLD.booking_id OR NEW.booking_revision IS DISTINCT FROM OLD.booking_revision
    OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.recipient_role IS DISTINCT FROM OLD.recipient_role
    OR NEW.event_key IS DISTINCT FROM OLD.event_key OR NEW.send_deadline_at IS DISTINCT FROM OLD.send_deadline_at) THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Attempted email identity is immutable';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION sarsa_booking.protect_enquiry_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.request_id IS DISTINCT FROM OLD.request_id
  OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.generation IS DISTINCT FROM OLD.generation
  OR NEW.deadline_at IS DISTINCT FROM OLD.deadline_at OR NEW.created_at IS DISTINCT FROM OLD.created_at
  OR (OLD.provider_id IS NOT NULL AND NEW.provider_id IS DISTINCT FROM OLD.provider_id)
  OR (OLD.message_ciphertext IS NOT NULL AND ((OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at AND NOT(NEW.first_attempt_at IS NULL AND NOT OLD.prior_send_uncertain AND NOT NEW.send_uncertain AND NEW.last_error_code IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited')))
   OR NEW.destination IS DISTINCT FROM OLD.destination OR NEW.message_digest IS DISTINCT FROM OLD.message_digest
   OR NEW.template_version IS DISTINCT FROM OLD.template_version
   OR (NEW.message_ciphertext IS DISTINCT FROM OLD.message_ciphertext AND NEW.message_ciphertext IS NOT NULL))) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Enquiry delivery identity is immutable'; END IF;
 IF NEW.state IN ('accepted','done','suppressed','expired','attention') THEN NEW.message_ciphertext:=NULL; END IF;
 RETURN NEW;
END $$;

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
   next_attempt_at=CASE WHEN kind='verification' THEN least(deadline_at,instant+interval '15 minutes') ELSE instant+interval '15 minutes' END,lease_token=NULL,lease_expires_at=NULL WHERE id=j.id; RETURN NULL;
 END IF;
 INSERT INTO sarsa_booking.email_reservations(enquiry_job_id) VALUES(j.id) ON CONFLICT(enquiry_job_id) DO NOTHING;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET message_ciphertext=p_cipher,message_digest=p_digest,
  first_attempt_at=coalesce(first_attempt_at,instant),prior_send_uncertain=send_uncertain,send_uncertain=true WHERE id=j.id RETURNING * INTO j;
 RETURN to_jsonb(j);
END $body$;

CREATE FUNCTION sarsa_booking.begin_contact_send(p_job uuid,p_lease uuid,p_cipher text,p_digest text,p_revision bigint,p_generation uuid,p_template integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE j sarsa_booking.enquiry_delivery_jobs%ROWTYPE;snapshot jsonb;owner_id uuid;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
 PERFORM 1 FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
 SELECT * INTO j FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR j.lease_expires_at<=clock_timestamp() THEN RETURN NULL; END IF;
 IF j.first_attempt_at IS NULL AND j.message_ciphertext IS NULL THEN
  snapshot:=booking_control.snapshot();
  IF p_revision IS DISTINCT FROM (snapshot->>'revision')::bigint OR p_generation IS DISTINCT FROM (snapshot->>'generation')::uuid
   OR p_template IS DISTINCT FROM (CASE WHEN coalesce((snapshot->>'enabled')::boolean,false) THEN 2 ELSE 3 END) THEN
   UPDATE sarsa_booking.enquiry_delivery_jobs SET state='pending',next_attempt_at=clock_timestamp(),lease_token=NULL,lease_expires_at=NULL,last_error_code='message_policy_changed' WHERE id=j.id;
   RETURN NULL;
  END IF;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET product_revision=p_revision,product_generation=p_generation,template_version=p_template WHERE id=j.id;
 END IF;
 RETURN sarsa_booking.begin_enquiry_send(p_job,p_lease,p_cipher,p_digest);
END $$;
CREATE FUNCTION sarsa_booking.finish_mail_attempt(p_kind text,p_job uuid,p_lease uuid,p_provider uuid,p_hash text,p_error text,p_attention boolean,p_delay integer,p_rejected boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE data jsonb;saved boolean;appended text;previous_uncertainty boolean;quota boolean;owner_id uuid;
BEGIN
 IF p_kind NOT IN('booking','contact') OR p_delay NOT BETWEEN 15 AND 86400 OR p_rejected IS NULL THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_kind='booking' THEN
  SELECT booking_id INTO owner_id FROM sarsa_booking.delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM sarsa_booking.bookings WHERE id=owner_id FOR SHARE;
 ELSE
  SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
 END IF;
 IF p_provider IS NOT NULL THEN
  appended:=sarsa_booking.append_mail_acceptance(p_kind,p_job,p_hash,p_provider);
  IF appended<>'accepted' THEN p_provider:=NULL;p_attention:=true;p_error:='email_provider_conflict';END IF;
 END IF;
 IF p_kind='booking' THEN
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.delivery_jobs j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.enquiry_delivery_jobs j WHERE id=p_job FOR UPDATE;
 END IF;
 IF data IS NULL OR (data->>'lease_token')::uuid IS DISTINCT FROM p_lease OR(data->>'lease_expires_at')::timestamptz<=clock_timestamp() OR data->>'state'<>'processing' THEN RETURN false; END IF;
 previous_uncertainty:=(data->>'prior_send_uncertain')::boolean;
 quota:=p_provider IS NULL AND p_rejected AND NOT previous_uncertainty AND p_error IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited');
 IF p_kind='booking' THEN
  saved:=sarsa_booking.finish_email_delivery(p_job,p_lease,p_provider,p_error,p_attention,p_delay);
  IF saved THEN
   UPDATE sarsa_booking.delivery_jobs SET send_uncertain=previous_uncertainty OR(NOT p_rejected AND p_provider IS NULL),
    first_attempt_at=CASE WHEN quota THEN NULL ELSE first_attempt_at END,
    state=CASE WHEN quota THEN 'pending' ELSE state END,attempts=greatest(0,attempts-CASE WHEN quota THEN 1 ELSE 0 END) WHERE id=p_job;
  END IF;
 ELSE
  saved:=sarsa_booking.finish_enquiry_delivery(p_job,p_lease,p_provider::text,p_error,p_attention,p_delay);
  IF saved THEN
   UPDATE sarsa_booking.enquiry_delivery_jobs SET send_uncertain=previous_uncertainty OR(NOT p_rejected AND p_provider IS NULL),
    first_attempt_at=CASE WHEN quota THEN NULL ELSE first_attempt_at END,
    state=CASE WHEN quota THEN 'pending' ELSE state END,attempts=greatest(0,attempts-CASE WHEN quota THEN 1 ELSE 0 END) WHERE id=p_job;
  END IF;
 END IF;
 RETURN saved;
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.begin_contact_send(uuid,uuid,text,text,bigint,uuid,integer),sarsa_booking.finish_mail_attempt(text,uuid,uuid,uuid,text,text,boolean,integer,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.begin_contact_send(uuid,uuid,text,text,bigint,uuid,integer),sarsa_booking.finish_mail_attempt(text,uuid,uuid,uuid,text,text,boolean,integer,boolean) TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.adopt_mail_acceptance(p_kind text,p_job uuid,p_lease uuid)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE data jsonb;fact sarsa_booking.mail_acceptance_claims%ROWTYPE;owner_id uuid;conflict boolean;
BEGIN
 IF p_kind NOT IN('booking','contact') OR p_lease IS NULL THEN RETURN 'missing';END IF;
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_kind='booking' THEN
  SELECT booking_id INTO owner_id FROM sarsa_booking.delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM sarsa_booking.bookings WHERE id=owner_id FOR SHARE;
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.delivery_jobs j WHERE id=p_job FOR UPDATE;
 ELSE
  SELECT request_id INTO owner_id FROM sarsa_booking.enquiry_delivery_jobs WHERE id=p_job;
  PERFORM 1 FROM sarsa_booking.enquiries WHERE request_id=owner_id FOR SHARE;
  SELECT to_jsonb(j) INTO data FROM sarsa_booking.enquiry_delivery_jobs j WHERE id=p_job FOR UPDATE;
 END IF;
 IF data IS NULL OR(data->>'lease_token')::uuid IS DISTINCT FROM p_lease OR(data->>'lease_expires_at')::timestamptz<=clock_timestamp() THEN RETURN 'missing';END IF;
 conflict:=EXISTS(SELECT 1 FROM sarsa_booking.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='conflict');
 SELECT * INTO fact FROM sarsa_booking.mail_acceptance_claims WHERE kind=p_kind AND job_id=p_job AND result='accepted' ORDER BY observed_at,id LIMIT 1;
 IF NOT FOUND AND NOT conflict THEN RETURN 'missing';END IF;
 IF NOT conflict AND coalesce(data->>'message_hash',data->>'message_digest') IS DISTINCT FROM fact.message_hash THEN conflict:=true;END IF;
 IF p_kind='booking' THEN
  UPDATE sarsa_booking.delivery_jobs SET state=CASE WHEN conflict THEN 'attention' ELSE 'accepted' END,
   provider_id=CASE WHEN conflict THEN provider_id ELSE fact.provider_id::text END,
   accepted_at=CASE WHEN conflict THEN accepted_at ELSE coalesce(accepted_at,fact.observed_at) END,
   last_error_code=CASE WHEN conflict THEN 'email_provider_conflict' ELSE NULL END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
 ELSE
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state=CASE WHEN conflict THEN 'attention' ELSE 'accepted' END,
   provider_id=CASE WHEN conflict THEN provider_id ELSE fact.provider_id::text END,
   last_error_code=CASE WHEN conflict THEN 'email_provider_conflict' ELSE NULL END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
 END IF;
 RETURN CASE WHEN conflict THEN 'conflict' ELSE 'accepted' END;
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.adopt_mail_acceptance(text,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.adopt_mail_acceptance(text,uuid,uuid) TO sarsa_booking_runtime;
