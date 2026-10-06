-- Keep exact original keys; only new verified settings add merchant metadata.
ALTER TABLE payment_orders ADD COLUMN merchant_id text CHECK(merchant_id ~ '^[A-Za-z0-9]{1,64}$');
ALTER TABLE payment_orders ADD COLUMN credential_version text;
UPDATE payment_orders SET credential_version='legacy_'||key_id;
ALTER TABLE payment_orders ALTER COLUMN credential_version SET NOT NULL;
ALTER TABLE payment_orders ALTER COLUMN credential_version SET DEFAULT 'legacy_unbound';
ALTER TABLE payment_orders ADD COLUMN order_search_from timestamptz;
ALTER TABLE payment_orders ADD COLUMN order_search_until timestamptz;
UPDATE payment_orders SET order_search_from=attempted_at-interval '5 minutes',order_search_until=attempted_at+interval '1 day' WHERE attempted_at IS NOT NULL;
ALTER TABLE payment_orders ADD CONSTRAINT payment_search_window CHECK(
 (order_search_from IS NULL)=(order_search_until IS NULL) AND (order_search_until IS NULL OR order_search_until>=order_search_from));
CREATE FUNCTION bind_payment_search_window() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.attempted_at IS NOT NULL AND NEW.attempted_at IS DISTINCT FROM OLD.attempted_at THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='first order attempt is immutable';END IF;
 IF NEW.credential_version='legacy_unbound' THEN NEW.credential_version:='legacy_'||NEW.key_id;END IF;
 IF TG_OP='UPDATE' AND (NEW.key_id,NEW.mode,NEW.merchant_id,NEW.credential_version) IS DISTINCT FROM
  (OLD.key_id,OLD.mode,OLD.merchant_id,OLD.credential_version) THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='payment identity is immutable';END IF;
 IF TG_OP='UPDATE' AND OLD.order_search_from IS NOT NULL AND (NEW.order_search_from,NEW.order_search_until) IS DISTINCT FROM
  (OLD.order_search_from,OLD.order_search_until) THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='order search window is immutable';END IF;
 IF NEW.attempted_at IS NOT NULL AND NEW.order_search_from IS NULL THEN
  NEW.order_search_from:=NEW.attempted_at-interval '5 minutes';NEW.order_search_until:=NEW.attempted_at+interval '1 day';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION bind_payment_search_window() FROM PUBLIC;
CREATE TRIGGER payment_identity_search BEFORE INSERT OR UPDATE ON payment_orders FOR EACH ROW EXECUTE FUNCTION bind_payment_search_window();
