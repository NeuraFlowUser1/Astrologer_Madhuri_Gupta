-- Complete the remaining order scan even if an earlier payment confirmed it.
-- Only server-fetched, validated Razorpay evidence reaches this function.
-- Browser signatures alone never confirm appointments. No network I/O here.
CREATE OR REPLACE FUNCTION sarsa_booking.observe_payment(
    p_context uuid,p_booking uuid,p_merchant text,p_mode text,p_version text,
    p_payment text,p_order text,p_hash text,p_status text,p_amount bigint,
    p_currency text,p_refunded bigint,p_captured boolean
) RETURNS text LANGUAGE plpgsql AS $body$
DECLARE booking sarsa_booking.bookings%ROWTYPE;
        payment sarsa_booking.payment_orders%ROWTYPE;
        accepted sarsa_booking.accepted_payments%ROWTYPE;
        observation uuid; reason text; financial_event_key text;
BEGIN
    PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM pg_advisory_xact_lock(4004002);
    PERFORM sarsa_booking.expire_holds();
    SELECT * INTO booking FROM sarsa_booking.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO payment FROM sarsa_booking.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND OR payment.merchant_id IS DISTINCT FROM p_merchant
       OR payment.mode IS DISTINCT FROM p_mode OR payment.credential_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='payment identity mismatch';
    END IF;
    IF p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$'
       OR p_order IS NULL OR p_order !~ '^order_[A-Za-z0-9]{1,64}$'
       OR p_status IS NULL OR p_status NOT IN ('created','authorized','captured','refunded','failed')
       OR p_captured IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid payment evidence';
    END IF;
    INSERT INTO sarsa_booking.payment_observations(
        id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,
        amount_paise,currency,refunded_paise,captured
    ) VALUES(gen_random_uuid(),p_booking,p_merchant,p_mode,p_payment,p_order,p_hash,p_status,
             p_amount,p_currency,p_refunded,p_captured)
    ON CONFLICT(merchant_id,mode,payment_id,evidence_hash) DO NOTHING;
    SELECT id INTO observation FROM sarsa_booking.payment_observations
      WHERE booking_id=p_booking AND merchant_id=p_merchant AND mode=p_mode
        AND payment_id=p_payment AND evidence_hash=p_hash;
    IF observation IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='payment evidence belongs to another booking';
    END IF;
    -- Uncaptured attempts are recorded, but cannot resolve the entire order.
    IF p_status NOT IN ('captured','refunded') AND NOT p_captured AND p_refunded=0 THEN RETURN 'observed'; END IF;
    SELECT * INTO accepted FROM sarsa_booking.accepted_payments WHERE booking_id=p_booking;
    IF p_order IS DISTINCT FROM payment.provider_order_id OR p_amount <> booking.amount_paise
       OR p_currency <> booking.currency THEN reason := 'payment_mismatch';
    ELSIF p_refunded > 0 OR p_status='refunded' THEN reason := 'refund_observed';
    ELSIF p_status <> 'captured' OR NOT p_captured THEN reason := 'capture_inconsistent';
    ELSIF accepted.payment_id=p_payment AND booking.state='confirmed' THEN RETURN 'confirmed';
    ELSIF accepted.payment_id IS NOT NULL THEN reason := 'additional_payment';
    ELSIF EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments
        WHERE merchant_id=p_merchant AND mode=p_mode AND payment_id=p_payment) THEN reason := 'payment_already_assigned';
    ELSIF booking.state <> 'held' OR booking.hold_expires_at <= clock_timestamp()
       OR payment.resolved_at IS NOT NULL THEN reason := 'late_payment';
    ELSIF NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE booking_id=p_booking
        AND released_at IS NULL AND starts_at=booking.starts_at AND ends_at=booking.ends_at) THEN reason := 'claim_missing';
    END IF;
    IF reason IS NOT NULL THEN
        financial_event_key := p_payment||':'||reason;
        INSERT INTO sarsa_booking.payment_cases(id,booking_id,event_key,reason)
          VALUES(gen_random_uuid(),p_booking,financial_event_key,reason)
          ON CONFLICT(booking_id,event_key) DO NOTHING;
        INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
          VALUES(gen_random_uuid(),p_booking,'payment_review','client',booking.revision,financial_event_key)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        IF booking.state IN ('held','expired') THEN
            UPDATE sarsa_booking.bookings SET state='payment_review' WHERE id=p_booking;
            UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp()
              WHERE booking_id=p_booking AND released_at IS NULL;
        END IF;
        RETURN 'payment_needs_review';
    END IF;
    INSERT INTO sarsa_booking.accepted_payments(booking_id,observation_id,merchant_id,mode,payment_id)
      VALUES(p_booking,observation,p_merchant,p_mode,p_payment);
    UPDATE sarsa_booking.bookings SET state='confirmed' WHERE id=p_booking;
    UPDATE sarsa_booking.payment_orders SET resolution='confirmed',resolved_at=clock_timestamp(),recovery_followup=true,next_check_at=clock_timestamp()
      WHERE booking_id=p_booking;
    UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=NULL
      WHERE id=p_context AND active_checkout_id=p_booking;
    INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
      SELECT gen_random_uuid(),p_booking,kind,role,booking.revision
      FROM (VALUES ('booking_ack','customer'),('booking_ack','client'),('booking_calendar','calendar'),
                   ('sheet_booking','client_sheet'),('sheet_booking','agency_sheet')) jobs(kind,role)
      ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
    RETURN 'confirmed';
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.observe_payment(uuid,uuid,text,text,text,text,text,text,text,bigint,text,bigint,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.observe_payment(uuid,uuid,text,text,text,text,text,text,text,bigint,text,bigint,boolean) TO sarsa_booking_runtime;
