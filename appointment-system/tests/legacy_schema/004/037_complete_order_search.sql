-- One bounded page per pass; do not adopt a match before proving uniqueness.
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN order_search_match text CHECK(order_search_match ~ '^order_[A-Za-z0-9]{1,64}$');
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN order_search_conflict boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN order_search_from timestamptz;
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN order_search_until timestamptz;
UPDATE sarsa_booking.payment_orders SET order_search_from=attempted_at-interval '5 minutes',order_search_until=attempted_at+interval '1 day' WHERE attempted_at IS NOT NULL;
ALTER TABLE sarsa_booking.payment_orders ADD CONSTRAINT complete_search_window CHECK(
 (order_search_from IS NULL)=(order_search_until IS NULL) AND (order_search_until IS NULL OR order_search_until>=order_search_from));
CREATE FUNCTION sarsa_booking.bind_order_search_window() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.attempted_at IS NOT NULL AND NEW.attempted_at IS DISTINCT FROM OLD.attempted_at THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='first order attempt is immutable';END IF;
 IF TG_OP='UPDATE' AND OLD.order_search_from IS NOT NULL AND (NEW.order_search_from,NEW.order_search_until) IS DISTINCT FROM
  (OLD.order_search_from,OLD.order_search_until) THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='order search window is immutable';END IF;
 IF NEW.attempted_at IS NOT NULL AND NEW.order_search_from IS NULL THEN
  NEW.order_search_from:=NEW.attempted_at-interval '5 minutes';NEW.order_search_until:=NEW.attempted_at+interval '1 day';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.bind_order_search_window() FROM PUBLIC;
CREATE TRIGGER saved_order_search_window BEFORE INSERT OR UPDATE ON sarsa_booking.payment_orders
 FOR EACH ROW EXECUTE FUNCTION sarsa_booking.bind_order_search_window();
ALTER FUNCTION sarsa_booking.claim_payment_recovery(integer) RENAME TO claim_payment_recovery_v1;
REVOKE ALL ON FUNCTION sarsa_booking.claim_payment_recovery_v1(integer) FROM PUBLIC,sarsa_booking_runtime;
CREATE FUNCTION sarsa_booking.claim_payment_recovery(p_limit integer) RETURNS jsonb LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
 SELECT coalesce(jsonb_agg(j.value||jsonb_build_object('order_search_match',p.order_search_match,
  'order_search_conflict',p.order_search_conflict,'order_search_from',p.order_search_from,
  'order_search_until',p.order_search_until,'attempted_at',p.attempted_at,'created_at',b.created_at)), '[]'::jsonb)
 FROM jsonb_array_elements(sarsa_booking.claim_payment_recovery_v1(p_limit))j
 JOIN sarsa_booking.payment_orders p ON p.booking_id=(j.value->>'booking_id')::uuid
 JOIN sarsa_booking.bookings b ON b.id=p.booking_id;
$$;
CREATE FUNCTION sarsa_booking.advance_order_search(p_booking uuid,p_lease uuid,p_skip integer,p_candidates text[],p_complete boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE row sarsa_booking.payment_orders%ROWTYPE;candidate text;conflict boolean;
BEGIN
 IF p_candidates IS NULL OR cardinality(p_candidates)>2 OR p_complete IS NULL OR p_skip IS NULL OR p_skip<0
  OR EXISTS(SELECT 1 FROM unnest(p_candidates)c WHERE c IS NULL OR c !~ '^order_[A-Za-z0-9]{1,64}$') THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid order search page';END IF;
 SELECT * INTO row FROM sarsa_booking.payment_orders WHERE booking_id=p_booking FOR UPDATE;
 IF NOT FOUND OR row.lease_token IS DISTINCT FROM p_lease OR row.lease_expires_at<=clock_timestamp()
  OR row.order_search_skip<>p_skip OR row.provider_order_id IS NOT NULL THEN RETURN jsonb_build_object('code','lease_lost');END IF;
 SELECT min(c) INTO candidate FROM(SELECT unnest(p_candidates)c UNION SELECT row.order_search_match WHERE row.order_search_match IS NOT NULL)q;
 conflict:=row.order_search_conflict OR (SELECT count(DISTINCT c)>1 FROM(SELECT unnest(p_candidates)c UNION SELECT row.order_search_match WHERE row.order_search_match IS NOT NULL)q);
 UPDATE sarsa_booking.payment_orders SET order_search_skip=CASE WHEN p_complete THEN 0 ELSE p_skip+90 END,
  order_search_match=candidate,order_search_conflict=conflict WHERE booking_id=p_booking;
 IF conflict THEN
  INSERT INTO sarsa_booking.payment_cases(id,booking_id,event_key,reason) VALUES(gen_random_uuid(),p_booking,'unknown-order:'||p_booking,'multiple_provider_orders') ON CONFLICT DO NOTHING;
 END IF;
 RETURN jsonb_build_object('code',CASE WHEN conflict THEN 'conflict' WHEN p_complete AND candidate IS NOT NULL THEN 'match'
  WHEN p_complete THEN 'not_found' ELSE 'pending' END,'order_id',CASE WHEN p_complete AND NOT conflict THEN candidate END);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_payment_recovery(integer),sarsa_booking.advance_order_search(uuid,uuid,integer,text[],boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_payment_recovery(integer),sarsa_booking.advance_order_search(uuid,uuid,integer,text[],boolean) TO sarsa_booking_runtime;
