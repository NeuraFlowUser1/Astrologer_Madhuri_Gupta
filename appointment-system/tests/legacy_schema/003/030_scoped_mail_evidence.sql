-- A provider reference belongs to exactly one saved intent, across all mail.
CREATE FUNCTION public.mail_payload_hash(p jsonb) RETURNS text LANGUAGE sql IMMUTABLE STRICT
 AS $$ SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p::text,'UTF8')),'hex') $$;
ALTER TABLE public.delivery_jobs ADD COLUMN mail_payload_hash text CHECK(mail_payload_hash ~ '^[a-f0-9]{64}$'),
 ADD COLUMN mail_key text, ADD COLUMN mail_policy_version integer,
 ADD COLUMN mail_product_revision bigint, ADD COLUMN mail_product_generation uuid;
UPDATE public.delivery_jobs SET mail_payload_hash=public.mail_payload_hash(message_payload),
 mail_key=CASE WHEN kind='inquiry_received' THEN 'inquiry/'||id::text||'/v'||message_version
  ELSE 'booking/'||record_id::text||'/'||kind||'/'||recipient_role||'/v'||message_version END,
 mail_policy_version=1 WHERE message_payload IS NOT NULL;
CREATE TABLE public.mail_provider_ownership (
 provider_id uuid PRIMARY KEY, purpose text NOT NULL CHECK(purpose IN ('delivery','verification')),
 intent_id uuid NOT NULL, payload_hash text CHECK(payload_hash ~ '^[a-f0-9]{64}$'),
 observed_at timestamptz NOT NULL, UNIQUE(provider_id,purpose,intent_id)
);
DO $body$
BEGIN
 IF EXISTS(SELECT provider_id FROM (
  SELECT provider_id,'delivery' purpose,id intent_id FROM public.delivery_jobs WHERE provider_id IS NOT NULL
  UNION SELECT provider_id,'verification',challenge_id FROM public.verification_emails
  UNION SELECT provider_id,'verification',challenge_id FROM public.verification_mail_evidence
 ) x GROUP BY provider_id HAVING count(*)>1) THEN
  RAISE EXCEPTION USING ERRCODE='P0430',MESSAGE='historical mail identity conflict needs review';
 END IF;
END $body$;
INSERT INTO public.mail_provider_ownership
 SELECT provider_id,'delivery',id,mail_payload_hash,COALESCE(accepted_at,created_at)
 FROM public.delivery_jobs WHERE provider_id IS NOT NULL;
INSERT INTO public.mail_provider_ownership
 SELECT e.provider_id,'verification',e.challenge_id,m.message_hash,e.accepted_at
 FROM public.verification_emails e LEFT JOIN public.verification_mail m USING(challenge_id)
 ON CONFLICT DO NOTHING;
INSERT INTO public.mail_provider_ownership
 SELECT provider_id,'verification',challenge_id,message_hash,observed_at FROM public.verification_mail_evidence
 ON CONFLICT DO NOTHING;
CREATE TABLE public.mail_acceptance_evidence (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),job_id uuid NOT NULL REFERENCES public.delivery_jobs(id),
 provider_id uuid NOT NULL REFERENCES public.mail_provider_ownership(provider_id),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[a-f0-9]{64}$'),mail_key text NOT NULL,
 provenance text NOT NULL CHECK(provenance IN ('send_reply','signed_callback')),
 observed_at timestamptz NOT NULL,UNIQUE(job_id,provider_id,payload_hash,mail_key,provenance)
);
CREATE INDEX mail_acceptance_job ON public.mail_acceptance_evidence(job_id,observed_at,id);
ALTER TABLE public.verification_mail ADD COLUMN sender text, ADD COLUMN recipient_hash text;
CREATE TABLE public.mail_recipient_suppressions (
 recipient_hash text NOT NULL CHECK(recipient_hash ~ '^[a-f0-9]{64}$'),
 event_id text NOT NULL REFERENCES public.email_events(event_id),provider_id uuid NOT NULL,
 reason text NOT NULL CHECK(reason IN ('email.bounced','email.complained','email.suppressed')),
 observed_at timestamptz NOT NULL,PRIMARY KEY(recipient_hash,event_id)
);
CREATE TABLE public.mail_acceptance_conflicts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),job_id uuid NOT NULL REFERENCES public.delivery_jobs(id),
 provider_id uuid NOT NULL,payload_hash text NOT NULL,code text NOT NULL CHECK(code IN
 ('provider_owned_elsewhere','multiple_provider_references','message_identity_changed')),
 observed_at timestamptz NOT NULL,UNIQUE(job_id,provider_id,payload_hash,code)
);
CREATE FUNCTION public.protect_mail_fact() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN RAISE EXCEPTION USING ERRCODE='P0430',MESSAGE='immutable mail evidence'; END $body$;
CREATE TRIGGER immutable_mail_owner BEFORE UPDATE OR DELETE ON public.mail_provider_ownership
 FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
CREATE TRIGGER immutable_mail_acceptance BEFORE UPDATE OR DELETE ON public.mail_acceptance_evidence
 FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
CREATE TRIGGER immutable_mail_conflicts BEFORE UPDATE OR DELETE ON public.mail_acceptance_conflicts
 FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
CREATE TRIGGER immutable_mail_suppression BEFORE UPDATE OR DELETE ON public.mail_recipient_suppressions
 FOR EACH ROW EXECUTE FUNCTION public.protect_mail_fact();
CREATE FUNCTION public.protect_mail_intent() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
 IF OLD.mail_payload_hash IS NOT NULL AND ROW(NEW.message_payload,NEW.mail_payload_hash,NEW.mail_key,
  NEW.mail_policy_version,NEW.mail_product_revision,NEW.mail_product_generation,NEW.message_version)
  IS DISTINCT FROM ROW(OLD.message_payload,OLD.mail_payload_hash,OLD.mail_key,
  OLD.mail_policy_version,OLD.mail_product_revision,OLD.mail_product_generation,OLD.message_version) THEN
  RAISE EXCEPTION USING ERRCODE='P0430',MESSAGE='attempted mail identity changed';
 END IF;
 IF NEW.mail_payload_hash IS NOT NULL AND NEW.mail_payload_hash IS DISTINCT FROM public.mail_payload_hash(NEW.message_payload) THEN
  RAISE EXCEPTION USING ERRCODE='P0430',MESSAGE='mail payload hash mismatch';
 END IF;
 RETURN NEW;
END $body$;
CREATE TRIGGER immutable_mail_intent BEFORE UPDATE ON public.delivery_jobs
 FOR EACH ROW EXECUTE FUNCTION public.protect_mail_intent();
REVOKE ALL ON public.mail_provider_ownership,public.mail_acceptance_evidence,public.mail_acceptance_conflicts,public.mail_recipient_suppressions FROM PUBLIC;
REVOKE ALL ON FUNCTION public.mail_payload_hash(jsonb),public.protect_mail_fact(),public.protect_mail_intent() FROM PUBLIC;
