-- Durable Contact foundation. Enquiry intake remains CLOSED until all consumers
-- and the final frontend have passed acceptance. No fake booking rows.
CREATE TABLE sarsa_booking.contact_intake (
 id boolean PRIMARY KEY DEFAULT true CHECK(id), public_open boolean NOT NULL DEFAULT false
);
INSERT INTO sarsa_booking.contact_intake DEFAULT VALUES;
CREATE TABLE sarsa_booking.enquiries (
 request_id uuid PRIMARY KEY,
 email_key text NOT NULL CHECK(email_key ~ '^[a-f0-9]{64}$'),
 receipt_digest text NOT NULL CHECK(receipt_digest ~ '^[a-f0-9]{64}$'),
 request_fingerprint text NOT NULL CHECK(request_fingerprint ~ '^[a-f0-9]{64}$'),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 generation integer NOT NULL DEFAULT 1 CHECK(generation BETWEEN 1 AND 3),
 code_digest text CHECK(code_digest ~ '^[a-f0-9]{64}$'),
 code_ciphertext text CHECK(length(code_ciphertext) BETWEEN 100 AND 8192),
 code_expires_at timestamptz NOT NULL,
 resend_after timestamptz NOT NULL,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 verified_at timestamptz,
 receipt_expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '24 hours',
 CHECK((code_digest IS NULL)=(code_ciphertext IS NULL)),
 CHECK(verified_at IS NULL OR (code_digest IS NULL AND code_ciphertext IS NULL))
);
CREATE INDEX contact_expiry ON sarsa_booking.enquiries(code_expires_at) WHERE code_ciphertext IS NOT NULL;
CREATE TABLE sarsa_booking.enquiry_resends (
 operation_id uuid PRIMARY KEY,
 request_id uuid NOT NULL REFERENCES sarsa_booking.enquiries(request_id),
 generation integer NOT NULL CHECK(generation BETWEEN 2 AND 3)
);
CREATE TABLE sarsa_booking.enquiry_delivery_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES sarsa_booking.enquiries(request_id),
 kind text NOT NULL CHECK(kind IN ('verification','acknowledgement','practice_notice','client_sheet','agency_sheet')),
 generation integer NOT NULL CHECK(generation BETWEEN 0 AND 3),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','processing','accepted','done','uncertain','failed','attention','expired','suppressed')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 deadline_at timestamptz NOT NULL,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 lease_token uuid,lease_expires_at timestamptz,
 first_attempt_at timestamptz,provider_id text,last_error_code text,
 UNIQUE(request_id,kind,generation),
 CHECK((kind='verification' AND generation>0) OR (kind<>'verification' AND generation=0))
);
CREATE INDEX enquiry_delivery_due ON sarsa_booking.enquiry_delivery_jobs(next_attempt_at,id)
 WHERE state IN ('pending','processing','uncertain','failed');
REVOKE ALL ON sarsa_booking.contact_intake,sarsa_booking.enquiries,sarsa_booking.enquiry_resends,sarsa_booking.enquiry_delivery_jobs FROM PUBLIC;
GRANT SELECT ON sarsa_booking.contact_intake,sarsa_booking.enquiries,sarsa_booking.enquiry_resends,sarsa_booking.enquiry_delivery_jobs TO sarsa_booking_runtime;
GRANT INSERT,UPDATE ON sarsa_booking.enquiries,sarsa_booking.enquiry_delivery_jobs TO sarsa_booking_runtime;
GRANT INSERT ON sarsa_booking.enquiry_resends TO sarsa_booking_runtime;

-- PostgreSQL requires UPDATE privilege for a locking read. Keep the public
-- switch owner-controlled: this narrow wrapper only reads and locks its row.
-- The shared row lock lasts through the caller's transaction, including insert.
CREATE FUNCTION sarsa_booking.lock_contact_intake() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE opened boolean;
BEGIN
 SELECT public_open INTO opened FROM sarsa_booking.contact_intake WHERE id=true FOR SHARE;
 RETURN coalesce(opened,false);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.lock_contact_intake() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.lock_contact_intake() TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.enquiry_view(p_id uuid,p_receipt text) RETURNS jsonb LANGUAGE sql AS $body$
 SELECT coalesce((SELECT jsonb_build_object('code','ok','request_id',e.request_id,
  'state',CASE WHEN e.verified_at IS NOT NULL THEN 'received' WHEN e.attempts>=5 THEN 'locked'
    WHEN e.code_expires_at<=clock_timestamp() OR e.code_digest IS NULL THEN 'expired' ELSE 'awaiting_verification' END,
  'generation',e.generation,'server_now',clock_timestamp(),'code_expires_at',e.code_expires_at,
  'resend_after',e.resend_after,'sends_remaining',3-e.generation)
  FROM sarsa_booking.enquiries e WHERE e.request_id=p_id AND e.receipt_digest=p_receipt
   AND e.receipt_expires_at>clock_timestamp()),jsonb_build_object('code','access_unavailable'));
$body$;

CREATE FUNCTION sarsa_booking.start_enquiry(p_id uuid,p_receipt text,p_fingerprint text,p_payload jsonb,p_digest text,p_cipher text,p_email_key text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE; opened boolean; quota jsonb;
BEGIN
 -- Scope request lock before row access; exact retries never replace code/content.
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-contact:'||p_id::text,0));
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=p_id FOR UPDATE;
 IF FOUND THEN
   IF e.receipt_digest IS DISTINCT FROM p_receipt OR e.request_fingerprint IS DISTINCT FROM p_fingerprint
     OR e.payload IS DISTINCT FROM p_payload THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
   RETURN sarsa_booking.enquiry_view(p_id,p_receipt);
 END IF;
 opened:=sarsa_booking.lock_contact_intake();
 IF opened IS DISTINCT FROM true THEN RETURN jsonb_build_object('code','contact_unavailable'); END IF;
 IF p_id IS NULL OR p_receipt IS NULL OR p_receipt !~ '^[a-f0-9]{64}$' OR p_fingerprint IS NULL OR p_fingerprint !~ '^[a-f0-9]{64}$'
   OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192
   OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR octet_length(p_payload::text)>16000
   OR p_email_key IS NULL OR p_email_key !~ '^[a-f0-9]{64}$' OR p_payload->>'email' IS NULL THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 quota:=sarsa_booking.consume_request_limit('contact_email',p_email_key);
 IF quota->>'allowed' IS DISTINCT FROM 'true' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 INSERT INTO sarsa_booking.enquiries(request_id,email_key,receipt_digest,request_fingerprint,payload,code_digest,code_ciphertext,code_expires_at,resend_after)
 VALUES(p_id,p_email_key,p_receipt,p_fingerprint,p_payload,p_digest,p_cipher,clock_timestamp()+interval '5 minutes',clock_timestamp()+interval '60 seconds');
 INSERT INTO sarsa_booking.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT request_id,'verification',generation,code_expires_at FROM sarsa_booking.enquiries WHERE request_id=p_id;
 RETURN sarsa_booking.enquiry_view(p_id,p_receipt);
END $body$;

CREATE FUNCTION sarsa_booking.resend_enquiry(p_id uuid,p_receipt text,p_operation uuid,p_generation integer,p_digest text,p_cipher text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE; old sarsa_booking.enquiry_resends%ROWTYPE; inserted uuid; opened boolean; quota jsonb;
BEGIN
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=p_id FOR UPDATE;
 IF NOT FOUND OR e.receipt_digest IS DISTINCT FROM p_receipt OR e.receipt_expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM sarsa_booking.enquiry_resends WHERE operation_id=p_operation;
 IF FOUND THEN
   IF old.request_id<>p_id THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
   RETURN sarsa_booking.enquiry_view(p_id,p_receipt);
 END IF;
 IF e.verified_at IS NOT NULL THEN RETURN sarsa_booking.enquiry_view(p_id,p_receipt); END IF;
 opened:=sarsa_booking.lock_contact_intake();
 IF opened IS DISTINCT FROM true THEN RETURN jsonb_build_object('code','contact_unavailable'); END IF;
 IF e.generation>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF e.resend_after>clock_timestamp() THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 IF p_generation IS DISTINCT FROM e.generation+1 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF p_operation IS NULL OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
   OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 quota:=sarsa_booking.consume_request_limit('contact_email',e.email_key);
 IF quota->>'allowed' IS DISTINCT FROM 'true' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 INSERT INTO sarsa_booking.enquiry_resends(operation_id,request_id,generation) VALUES(p_operation,p_id,p_generation)
 ON CONFLICT(operation_id) DO NOTHING RETURNING operation_id INTO inserted;
 IF inserted IS NULL THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
  WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','uncertain','failed');
 UPDATE sarsa_booking.enquiries SET generation=p_generation,code_digest=p_digest,code_ciphertext=p_cipher,
   code_expires_at=clock_timestamp()+interval '5 minutes',resend_after=clock_timestamp()+interval '60 seconds',attempts=0 WHERE request_id=p_id;
 INSERT INTO sarsa_booking.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT request_id,'verification',generation,code_expires_at FROM sarsa_booking.enquiries WHERE request_id=p_id;
 RETURN sarsa_booking.enquiry_view(p_id,p_receipt);
END $body$;

CREATE FUNCTION sarsa_booking.verify_enquiry(p_id uuid,p_receipt text,p_generation integer,p_digest text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE e sarsa_booking.enquiries%ROWTYPE;
BEGIN
 SELECT * INTO e FROM sarsa_booking.enquiries WHERE request_id=p_id FOR UPDATE;
 IF NOT FOUND OR e.receipt_digest IS DISTINCT FROM p_receipt OR e.receipt_expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 -- Retrying the original enquiry's completed request never consumes another code.
 IF e.verified_at IS NOT NULL THEN RETURN sarsa_booking.enquiry_view(p_id,p_receipt); END IF;
 IF p_generation IS DISTINCT FROM e.generation THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF e.attempts>=5 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF e.code_expires_at<=clock_timestamp() OR e.code_digest IS NULL THEN
   UPDATE sarsa_booking.enquiries SET code_digest=NULL,code_ciphertext=NULL WHERE request_id=p_id;
   UPDATE sarsa_booking.enquiry_delivery_jobs SET state='expired',lease_token=NULL,lease_expires_at=NULL
     WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','uncertain','failed');
   RETURN jsonb_build_object('code','verification_expired'); END IF;
 IF p_digest IS NULL OR p_digest IS DISTINCT FROM e.code_digest THEN
   UPDATE sarsa_booking.enquiries SET attempts=attempts+1,
     code_digest=CASE WHEN attempts>=4 THEN NULL ELSE code_digest END,
     code_ciphertext=CASE WHEN attempts>=4 THEN NULL ELSE code_ciphertext END WHERE request_id=p_id;
   IF e.attempts>=4 THEN
     UPDATE sarsa_booking.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
       WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','uncertain','failed');
   END IF;
   RETURN jsonb_build_object('code',CASE WHEN e.attempts>=4 THEN 'verification_limit' ELSE 'verification_incorrect' END);
 END IF;
 UPDATE sarsa_booking.enquiries SET verified_at=clock_timestamp(),code_digest=NULL,code_ciphertext=NULL WHERE request_id=p_id;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL
   WHERE request_id=p_id AND kind='verification' AND state IN ('pending','processing','uncertain','failed');
 INSERT INTO sarsa_booking.enquiry_delivery_jobs(request_id,kind,generation,deadline_at)
 SELECT p_id,k,0,clock_timestamp()+interval '24 hours' FROM unnest(ARRAY['acknowledgement','practice_notice','client_sheet','agency_sheet']) k;
 RETURN sarsa_booking.enquiry_view(p_id,p_receipt);
END $body$;

CREATE FUNCTION sarsa_booking.expire_enquiry_codes() RETURNS integer LANGUAGE plpgsql AS $body$
DECLARE e record; used integer:=0;
BEGIN
 FOR e IN SELECT request_id FROM sarsa_booking.enquiries WHERE code_ciphertext IS NOT NULL
   AND code_expires_at<=clock_timestamp() ORDER BY code_expires_at LIMIT 100 FOR UPDATE SKIP LOCKED LOOP
  UPDATE sarsa_booking.enquiries SET code_digest=NULL,code_ciphertext=NULL WHERE request_id=e.request_id;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state='expired',lease_token=NULL,lease_expires_at=NULL
   WHERE request_id=e.request_id AND kind='verification' AND state IN ('pending','processing','uncertain','failed');
  used:=used+1;
 END LOOP;
 RETURN used;
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.enquiry_view(uuid,text),sarsa_booking.start_enquiry(uuid,text,text,jsonb,text,text,text),
 sarsa_booking.resend_enquiry(uuid,text,uuid,integer,text,text),sarsa_booking.verify_enquiry(uuid,text,integer,text),
 sarsa_booking.expire_enquiry_codes() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.enquiry_view(uuid,text),sarsa_booking.start_enquiry(uuid,text,text,jsonb,text,text,text),
 sarsa_booking.resend_enquiry(uuid,text,uuid,integer,text,text),sarsa_booking.verify_enquiry(uuid,text,integer,text),
 sarsa_booking.expire_enquiry_codes() TO sarsa_booking_runtime;

ALTER TABLE sarsa_booking.request_limits DROP CONSTRAINT request_limits_scope_check;
ALTER TABLE sarsa_booking.request_limits ADD CONSTRAINT request_limits_scope_check
 CHECK(scope IN ('context','availability','receipt','checkout','studio','studio_status',
                'contact_start','contact_email','contact_read','contact_verify'));
CREATE OR REPLACE FUNCTION sarsa_booking.consume_request_limit(p_scope text,p_key text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE instant timestamptz := clock_timestamp();
        start_at timestamptz; width integer; maximum integer; used integer;
BEGIN
    CASE p_scope
      WHEN 'contact_start' THEN width:=3600; maximum:=10;
      WHEN 'contact_email' THEN width:=3600; maximum:=3;
      WHEN 'contact_read' THEN width:=60; maximum:=30;
      WHEN 'contact_verify' THEN width:=3600; maximum:=30;
      WHEN 'studio' THEN width:=3600; maximum:=20;
      WHEN 'studio_status' THEN width:=60; maximum:=60;
      WHEN 'context' THEN width:=3600; maximum:=20;
      WHEN 'availability' THEN width:=60; maximum:=60;
      WHEN 'receipt' THEN width:=60; maximum:=30;
      WHEN 'checkout' THEN width:=3600; maximum:=30;
      ELSE RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='unsupported request scope';
    END CASE;
    start_at:=to_timestamp(floor(extract(epoch FROM instant)/width)*width);
    INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
      VALUES(p_scope,p_key,start_at,start_at+make_interval(secs=>width)+interval '24 hours',1)
      ON CONFLICT(scope,key_digest,window_start) DO UPDATE
      SET attempts=least(sarsa_booking.request_limits.attempts+1,maximum+1)
      RETURNING attempts INTO used;
    RETURN jsonb_build_object('allowed',used<=maximum,
      'retry_after',greatest(1,ceil(extract(epoch FROM start_at+make_interval(secs=>width)-instant))::integer));
END
$body$;

CREATE FUNCTION sarsa_booking.protect_enquiry_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.request_id IS DISTINCT FROM OLD.request_id OR NEW.receipt_digest IS DISTINCT FROM OLD.receipt_digest
  OR NEW.email_key IS DISTINCT FROM OLD.email_key OR NEW.payload IS DISTINCT FROM OLD.payload
  OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR NEW.created_at IS DISTINCT FROM OLD.created_at
  OR NEW.receipt_expires_at IS DISTINCT FROM OLD.receipt_expires_at
  OR (OLD.verified_at IS NOT NULL AND NEW.verified_at IS DISTINCT FROM OLD.verified_at)
  OR NEW.generation<OLD.generation OR NEW.generation>OLD.generation+1
  OR (NEW.generation=OLD.generation AND NEW.code_digest IS NOT NULL AND
    (NEW.code_digest IS DISTINCT FROM OLD.code_digest OR NEW.code_ciphertext IS DISTINCT FROM OLD.code_ciphertext)) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Enquiry identity is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER enquiry_identity BEFORE UPDATE ON sarsa_booking.enquiries FOR EACH ROW EXECUTE FUNCTION sarsa_booking.protect_enquiry_identity();
REVOKE ALL ON FUNCTION sarsa_booking.protect_enquiry_identity() FROM PUBLIC;
