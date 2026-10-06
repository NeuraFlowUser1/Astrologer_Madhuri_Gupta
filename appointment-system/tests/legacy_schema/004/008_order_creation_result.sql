-- A lost create-order response is an unresolved attempt, not permission to retry.
CREATE FUNCTION sarsa_booking.record_order_creation(
    p_context uuid,p_booking uuid,p_merchant text,p_mode text,p_version text,p_order text
) RETURNS text LANGUAGE plpgsql AS $body$
DECLARE payment sarsa_booking.payment_orders%ROWTYPE;
BEGIN
    PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM pg_advisory_xact_lock(4004002);
    PERFORM 1 FROM sarsa_booking.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO payment FROM sarsa_booking.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND OR payment.merchant_id IS DISTINCT FROM p_merchant
       OR payment.mode IS DISTINCT FROM p_mode OR payment.credential_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='payment identity mismatch';
    END IF;
    IF payment.state NOT IN ('creating','creation_unknown','ready') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='payment creation was not claimed';
    END IF;
    IF p_order IS NOT NULL AND p_order !~ '^order_[A-Za-z0-9]{1,64}$' THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid provider order';
    END IF;
    IF payment.provider_order_id IS NOT NULL THEN
        IF p_order IS NOT NULL AND p_order <> payment.provider_order_id THEN
            RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='provider order conflict';
        END IF;
        RETURN payment.state;
    END IF;
    UPDATE sarsa_booking.payment_orders SET
      state=CASE WHEN p_order IS NULL THEN 'creation_unknown' ELSE 'ready' END,
      provider_order_id=p_order,next_check_at=clock_timestamp()
      WHERE booking_id=p_booking;
    RETURN CASE WHEN p_order IS NULL THEN 'creation_unknown' ELSE 'ready' END;
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.record_order_creation(uuid,uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.record_order_creation(uuid,uuid,text,text,text,text) TO sarsa_booking_runtime;
