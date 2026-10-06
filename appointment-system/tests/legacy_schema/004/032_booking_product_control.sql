-- Company product control is distinct from practice intake/payment readiness.
-- No customer records or provider credentials belong in this schema.
CREATE SCHEMA booking_control;
REVOKE ALL ON SCHEMA booking_control FROM PUBLIC;
CREATE ROLE sarsa_booking_control NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE TABLE booking_control.product_state (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 project text NOT NULL CHECK(project='004'),
 environment text NOT NULL CHECK(environment='production'),
 origin text NOT NULL CHECK(origin='https://www.sarsajyotishsansthan.com'),
 enabled boolean NOT NULL,
 restore_generation uuid NOT NULL,
 generation_sequence bigint NOT NULL CHECK(generation_sequence>0),
 revision bigint NOT NULL CHECK(revision>0),
 activation_epoch uuid NOT NULL,
 updated_at timestamptz NOT NULL,
 provenance text NOT NULL CHECK(provenance IN ('existing_service','company_command','restore_reconciliation'))
);
INSERT INTO booking_control.product_state VALUES
 (true,'004','production','https://www.sarsajyotishsansthan.com',true,
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
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO s FROM booking_control.product_state WHERE singleton;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='booking control unavailable'; END IF;
 IF NOT s.enabled THEN RAISE EXCEPTION USING ERRCODE='P0444',MESSAGE='booking disabled'; END IF;
 IF p_epoch IS NOT NULL AND p_epoch IS DISTINCT FROM s.activation_epoch THEN
  RAISE EXCEPTION USING ERRCODE='P0409',MESSAGE='booking activation changed';
 END IF;
 RETURN s.activation_epoch;
END $body$;
REVOKE ALL ON FUNCTION booking_control.snapshot(),booking_control.admission(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA booking_control TO sarsa_booking_runtime,sarsa_booking_control;
GRANT EXECUTE ON FUNCTION booking_control.snapshot(),booking_control.admission(uuid) TO sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION booking_control.snapshot() TO sarsa_booking_control;

ALTER TABLE sarsa_booking.checkout_contexts ADD COLUMN activation_epoch uuid;
ALTER TABLE sarsa_booking.checkout_admissions ADD COLUMN activation_epoch uuid;
ALTER TABLE sarsa_booking.bookings ADD COLUMN activation_epoch uuid;
UPDATE sarsa_booking.checkout_contexts SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state);
UPDATE sarsa_booking.checkout_admissions SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state);
UPDATE sarsa_booking.bookings SET activation_epoch=(SELECT activation_epoch FROM booking_control.product_state);

CREATE FUNCTION booking_control.guard_context() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
BEGIN NEW.activation_epoch:=booking_control.admission(NEW.activation_epoch); RETURN NEW; END $body$;
CREATE FUNCTION booking_control.guard_booking() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $body$
DECLARE epoch uuid;
BEGIN
 SELECT activation_epoch INTO epoch FROM sarsa_booking.checkout_contexts WHERE id=NEW.context_id;
 NEW.activation_epoch:=booking_control.admission(epoch);
 RETURN NEW;
END $body$;
CREATE FUNCTION booking_control.guard_order_attempt() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $body$
DECLARE epoch uuid;
BEGIN
 IF NEW.attempted_at IS NOT NULL AND (TG_OP='INSERT' OR OLD.attempted_at IS NULL) THEN
  SELECT activation_epoch INTO epoch FROM sarsa_booking.bookings WHERE id=NEW.booking_id;
  PERFORM booking_control.admission(epoch);
 END IF;
 RETURN NEW;
END $body$;
REVOKE ALL ON FUNCTION booking_control.guard_context(),booking_control.guard_booking(),booking_control.guard_order_attempt() FROM PUBLIC;
CREATE TRIGGER booking_context_admission BEFORE INSERT ON sarsa_booking.checkout_contexts
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_context();
CREATE TRIGGER booking_row_admission BEFORE INSERT ON sarsa_booking.bookings
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_booking();
CREATE TRIGGER booking_order_admission BEFORE INSERT OR UPDATE ON sarsa_booking.payment_orders
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_order_attempt();

-- Shared control lock comes before the legacy context/capacity locks. Replays
-- first prove their original context/receipt; reading them creates no new work.
ALTER FUNCTION sarsa_booking.admit_checkout(uuid,uuid,text,text) RENAME TO admit_checkout_before_product_control;
CREATE FUNCTION sarsa_booking.admit_checkout(p_context uuid,p_request uuid,p_receipt text,p_fingerprint text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $body$
DECLARE a sarsa_booking.checkout_admissions%ROWTYPE; epoch uuid; result text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO a FROM sarsa_booking.checkout_admissions WHERE request_id=p_request;
 IF FOUND THEN
  RETURN sarsa_booking.admit_checkout_before_product_control(p_context,p_request,p_receipt,p_fingerprint);
 END IF;
 SELECT activation_epoch INTO epoch FROM sarsa_booking.checkout_contexts WHERE id=p_context;
 PERFORM booking_control.admission(epoch);
 result:=sarsa_booking.admit_checkout_before_product_control(p_context,p_request,p_receipt,p_fingerprint);
 IF result='pending' THEN UPDATE sarsa_booking.checkout_admissions SET activation_epoch=epoch WHERE request_id=p_request; END IF;
 RETURN result;
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.admit_checkout_before_product_control(uuid,uuid,text,text),
 sarsa_booking.admit_checkout(uuid,uuid,text,text) FROM PUBLIC,sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION sarsa_booking.admit_checkout(uuid,uuid,text,text) TO sarsa_booking_runtime;

ALTER FUNCTION sarsa_booking.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb)
 RENAME TO reserve_configured_before_product_control;
CREATE FUNCTION sarsa_booking.reserve_configured_checkout(p_context uuid,p_request uuid,p_receipt text,p_fingerprint text,p_input jsonb,p_expected jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $body$
DECLARE a sarsa_booking.checkout_admissions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO a FROM sarsa_booking.checkout_admissions WHERE request_id=p_request;
 IF NOT FOUND OR a.context_id IS DISTINCT FROM p_context OR a.receipt_digest IS DISTINCT FROM p_receipt
  OR a.request_fingerprint IS DISTINCT FROM p_fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
 IF a.outcome<>'committed' THEN PERFORM booking_control.admission(a.activation_epoch); END IF;
 RETURN sarsa_booking.reserve_configured_before_product_control(p_context,p_request,p_receipt,p_fingerprint,p_input,p_expected);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.reserve_configured_before_product_control(uuid,uuid,text,text,jsonb,jsonb),
 sarsa_booking.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb) FROM PUBLIC,sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION sarsa_booking.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb) TO sarsa_booking_runtime;

ALTER FUNCTION sarsa_booking.start_order_creation(uuid,uuid) RENAME TO start_order_before_product_control;
CREATE FUNCTION sarsa_booking.start_order_creation(p_context uuid,p_booking uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $body$
DECLARE epoch uuid; attempted timestamptz;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT b.activation_epoch,o.attempted_at INTO epoch,attempted FROM sarsa_booking.bookings b
 JOIN sarsa_booking.payment_orders o ON o.booking_id=b.id WHERE b.id=p_booking AND b.context_id=p_context;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
 IF attempted IS NULL THEN PERFORM booking_control.admission(epoch); END IF;
 RETURN sarsa_booking.start_order_before_product_control(p_context,p_booking);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.start_order_before_product_control(uuid,uuid),sarsa_booking.start_order_creation(uuid,uuid)
 FROM PUBLIC,sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION sarsa_booking.start_order_creation(uuid,uuid) TO sarsa_booking_runtime;
