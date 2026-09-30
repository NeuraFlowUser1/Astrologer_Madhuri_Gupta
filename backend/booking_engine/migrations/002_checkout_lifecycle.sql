-- Functions run with the caller's privileges. No PUBLIC execution and no
-- SECURITY DEFINER bypass. Browser routes must first authorize the receipt.
CREATE FUNCTION sarsa_booking.expire_holds() RETURNS integer
LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    -- Global expiry never locks or clears checkout contexts: schedule-only work
    -- cannot invert context -> schedule ordering used by payment finalizers.
    PERFORM pg_advisory_xact_lock(4004002);
    WITH expired AS (
        UPDATE sarsa_booking.bookings SET state='expired'
        WHERE state='held' AND hold_expires_at <= clock_timestamp()
        RETURNING id
    )
    UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp()
    WHERE released_at IS NULL AND booking_id IN (SELECT id FROM expired);
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END
$body$;

CREATE FUNCTION sarsa_booking.start_order_creation(p_context uuid, p_booking uuid)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
        booking sarsa_booking.bookings%ROWTYPE;
        payment sarsa_booking.payment_orders%ROWTYPE;
BEGIN
    SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND OR ctx.active_checkout_id IS DISTINCT FROM p_booking THEN
        RAISE EXCEPTION USING ERRCODE='P0401', MESSAGE='checkout ownership mismatch';
    END IF;
    PERFORM pg_advisory_xact_lock(4004002);
    SELECT * INTO booking FROM sarsa_booking.bookings
      WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401', MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO payment FROM sarsa_booking.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503', MESSAGE='order intent missing'; END IF;
    IF booking.state <> 'held' OR booking.hold_expires_at <= clock_timestamp()
       OR payment.state <> 'not_attempted' OR payment.resolved_at IS NOT NULL THEN
        RETURN false;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE booking_id=p_booking
        AND released_at IS NULL AND starts_at=booking.starts_at AND ends_at=booking.ends_at) THEN
        RAISE EXCEPTION USING ERRCODE='P0503', MESSAGE='reservation claim missing';
    END IF;
    UPDATE sarsa_booking.payment_orders SET state='creating',attempted_at=clock_timestamp()
      WHERE booking_id=p_booking;
    RETURN true;
END
$body$;

CREATE FUNCTION sarsa_booking.abandon_unattempted(p_context uuid, p_booking uuid)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
        booking sarsa_booking.bookings%ROWTYPE;
        payment sarsa_booking.payment_orders%ROWTYPE;
BEGIN
    SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401', MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM pg_advisory_xact_lock(4004002);
    SELECT * INTO booking FROM sarsa_booking.bookings
      WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401', MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO payment FROM sarsa_booking.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0503', MESSAGE='order intent missing'; END IF;
    IF payment.resolution='never_attempted_abandoned' THEN RETURN true; END IF;
    IF ctx.active_checkout_id IS DISTINCT FROM p_booking THEN
        RAISE EXCEPTION USING ERRCODE='P0401', MESSAGE='checkout ownership mismatch';
    END IF;
    IF payment.state <> 'not_attempted' OR payment.attempted_at IS NOT NULL
       OR payment.provider_order_id IS NOT NULL OR payment.resolved_at IS NOT NULL
       OR booking.state NOT IN ('held','expired')
       OR EXISTS(SELECT 1 FROM sarsa_booking.payment_observations WHERE booking_id=p_booking) THEN
        RETURN false;
    END IF;
    UPDATE sarsa_booking.bookings SET state='expired' WHERE id=p_booking;
    UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp()
      WHERE booking_id=p_booking AND released_at IS NULL;
    UPDATE sarsa_booking.payment_orders SET resolution='never_attempted_abandoned',resolved_at=clock_timestamp()
      WHERE booking_id=p_booking;
    UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=NULL WHERE id=p_context;
    RETURN true;
END
$body$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sarsa_booking FROM PUBLIC;
