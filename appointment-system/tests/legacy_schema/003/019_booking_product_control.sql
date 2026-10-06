-- Company product control is distinct from practice intake/payment readiness.
-- No customer records or provider credentials belong in this schema.
CREATE SCHEMA booking_control;
REVOKE ALL ON SCHEMA booking_control FROM PUBLIC;
CREATE ROLE astro_booking_control NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE TABLE booking_control.product_state (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 project text NOT NULL CHECK(project='003'),
 environment text NOT NULL CHECK(environment='production'),
 origin text NOT NULL CHECK(origin='https://astroadvicebykundansingh.com'),
 enabled boolean NOT NULL,
 restore_generation uuid NOT NULL,
 generation_sequence bigint NOT NULL CHECK(generation_sequence>0),
 revision bigint NOT NULL CHECK(revision>0),
 activation_epoch uuid NOT NULL,
 updated_at timestamptz NOT NULL,
 provenance text NOT NULL CHECK(provenance IN ('existing_service','company_command','restore_reconciliation'))
);
INSERT INTO booking_control.product_state VALUES
 (true,'003','production','https://astroadvicebykundansingh.com',true,
  gen_random_uuid(),1,1,gen_random_uuid(),clock_timestamp(),'existing_service');

CREATE TABLE booking_control.operations (
 id uuid PRIMARY KEY,
 actor_subject text NOT NULL,
 body_hash text NOT NULL CHECK(body_hash~'^[a-f0-9]{64}$'),
 expected_generation uuid NOT NULL,
 expected_revision bigint NOT NULL,
 target_enabled boolean NOT NULL,
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 5 AND 300),
 result_snapshot jsonb NOT NULL CHECK(jsonb_typeof(result_snapshot)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE booking_control.publications (
 operation_id uuid PRIMARY KEY REFERENCES booking_control.operations(id),
 snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','published','superseded','attention')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease_token uuid,
 lease_until timestamptz,
 published_at timestamptz,
 last_error text CHECK(last_error~'^[a-z0-9_]{1,80}$'),
 CHECK((lease_token IS NULL)=(lease_until IS NULL)),
 CHECK((state='published')=(published_at IS NOT NULL))
);
CREATE INDEX product_publications_due ON booking_control.publications(next_attempt_at,operation_id)
 WHERE state='pending';
REVOKE ALL ON ALL TABLES IN SCHEMA booking_control FROM PUBLIC;

CREATE FUNCTION booking_control.snapshot() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
 SELECT jsonb_build_object('version',1,'project',project,'environment',environment,'origin',origin,
  'enabled',enabled,'restore_generation',restore_generation::text,
  'generation_sequence',generation_sequence::text,'revision',revision::text,
  'activation_epoch',activation_epoch::text)
 FROM booking_control.product_state WHERE singleton
$body$;

CREATE FUNCTION booking_control.admission(p_epoch uuid DEFAULT NULL) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
DECLARE s booking_control.product_state%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,3);
 SELECT * INTO s FROM booking_control.product_state WHERE singleton;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='booking control unavailable'; END IF;
 IF NOT s.enabled THEN RAISE EXCEPTION USING ERRCODE='P0444',MESSAGE='booking disabled'; END IF;
 IF p_epoch IS NOT NULL AND p_epoch IS DISTINCT FROM s.activation_epoch THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='booking activation changed';
 END IF;
 RETURN s.activation_epoch;
END $body$;
REVOKE ALL ON FUNCTION booking_control.snapshot(),booking_control.admission(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA booking_control TO astro_booking_control;
-- The reviewed provisioner grants only these two readers to the actual runtime login.
GRANT EXECUTE ON FUNCTION booking_control.snapshot() TO astro_booking_control;

ALTER TABLE bookings ADD COLUMN activation_epoch uuid;
ALTER TABLE checkout_contexts ADD COLUMN activation_epoch uuid;
ALTER TABLE email_challenges ADD COLUMN activation_epoch uuid;
ALTER TABLE email_verifications ADD COLUMN activation_epoch uuid;
UPDATE bookings SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state);
UPDATE checkout_contexts SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state);
UPDATE email_challenges SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state) WHERE purpose='booking';
UPDATE email_verifications SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state) WHERE purpose='booking';

CREATE FUNCTION booking_control.guard_new_admission() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN NEW.activation_epoch:=booking_control.admission(NEW.activation_epoch); RETURN NEW; END $body$;
CREATE FUNCTION booking_control.guard_booking_challenge() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN
 IF NEW.purpose='booking' THEN NEW.activation_epoch:=booking_control.admission(NEW.activation_epoch); END IF;
 RETURN NEW;
END $body$;
CREATE FUNCTION booking_control.guard_order_attempt() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,public,pg_temp AS $body$
DECLARE epoch uuid;
BEGIN
 IF NEW.attempted_at IS NOT NULL AND (TG_OP='INSERT' OR OLD.attempted_at IS NULL) THEN
  SELECT activation_epoch INTO epoch FROM public.bookings WHERE id=NEW.booking_id;
  PERFORM booking_control.admission(epoch);
 END IF;
 RETURN NEW;
END $body$;
REVOKE ALL ON FUNCTION booking_control.guard_new_admission(),booking_control.guard_booking_challenge(),booking_control.guard_order_attempt() FROM PUBLIC;
CREATE TRIGGER booking_row_admission BEFORE INSERT ON bookings
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_new_admission();
CREATE TRIGGER checkout_context_admission BEFORE INSERT ON checkout_contexts
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_new_admission();
CREATE TRIGGER booking_code_admission BEFORE INSERT OR UPDATE ON email_challenges
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_booking_challenge();
CREATE TRIGGER booking_token_admission BEFORE INSERT ON email_verifications
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_booking_challenge();
CREATE TRIGGER booking_order_admission BEFORE INSERT OR UPDATE ON payment_orders
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_order_attempt();
