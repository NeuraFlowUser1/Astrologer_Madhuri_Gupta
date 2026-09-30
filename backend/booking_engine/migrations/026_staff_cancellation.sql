-- Audited client-only cancellation; financial resolution remains independent.
CREATE TABLE sarsa_booking.staff_appointment_actions (
 operation_id uuid PRIMARY KEY,
 claim_id uuid NOT NULL REFERENCES sarsa_booking.slot_claims(id),
 booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
 action text NOT NULL CHECK(action='cancel'), actor text NOT NULL,
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 2 AND 500),
 previous_revision integer NOT NULL, revision integer NOT NULL,
 starts_at timestamptz NOT NULL, notice_seconds bigint NOT NULL,
 policy_guidance text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(booking_id,revision), CHECK(revision=previous_revision+1)
);
REVOKE ALL ON sarsa_booking.staff_appointment_actions FROM PUBLIC,sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.studio_appointment_detail(p_session text,p_client text,p_origin text,p_claim uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE b sarsa_booking.bookings%ROWTYPE;
BEGIN
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT booking.* INTO b FROM sarsa_booking.bookings booking JOIN sarsa_booking.slot_claims s ON s.booking_id=booking.id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 RETURN jsonb_build_object('code','ok','claim_id',p_claim,'revision',b.revision,'state',b.state,'name',b.full_name,
 'service',b.service_snapshot->>'name','reference',b.request_id,'starts_at',b.starts_at,'ends_at',b.ends_at,
 'can_cancel',b.state='confirmed' AND b.starts_at>clock_timestamp(),
 'policy_guidance',CASE WHEN b.starts_at>=clock_timestamp()+interval '24 hours' THEN 'full_refund_review'
 WHEN b.starts_at>=clock_timestamp()+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END);
END $$;

CREATE FUNCTION sarsa_booking.studio_appointment_cancel(p_session text,p_client text,p_origin text,p_operation uuid,p_claim uuid,p_revision integer,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;old sarsa_booking.staff_appointment_actions%ROWTYPE;b sarsa_booking.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;guidance text;snapshot jsonb;old_snapshot jsonb;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 SELECT s.booking_id,bk.context_id INTO booking,context FROM sarsa_booking.slot_claims s JOIN sarsa_booking.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=context FOR UPDATE;
 PERFORM pg_advisory_xact_lock(4004002);
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM sarsa_booking.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision OR old.reason IS DISTINCT FROM p_reason THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','cancelled','revision',old.revision,'policy_guidance',old.policy_guidance);
 END IF;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE id=p_claim AND released_at IS NULL) THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 guidance:=CASE WHEN b.starts_at>=instant+interval '24 hours' THEN 'full_refund_review' WHEN b.starts_at>=instant+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END;
 old_snapshot:=jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,'service_snapshot',b.service_snapshot,
 'starts_at',b.starts_at,'ends_at',b.ends_at,'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'state','cancelled');
 INSERT INTO sarsa_booking.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance)
 VALUES(p_operation,p_claim,b.id,'cancel',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,guidance);
 UPDATE sarsa_booking.bookings SET state='cancelled',revision=revision+1 WHERE id=b.id;
 UPDATE sarsa_booking.slot_claims SET released_at=instant WHERE id=p_claim;
 -- Never erase accepted evidence or revoke an in-flight completion lease.
 UPDATE sarsa_booking.delivery_jobs SET state='suppressed',last_error_code='appointment_cancelled'
 WHERE booking_id=b.id AND booking_revision=b.revision AND kind IN ('booking_ack','booking_details','booking_calendar')
 AND state IN ('pending','failed') AND first_attempt_at IS NULL AND payload IS NULL AND provider_id IS NULL AND lease_token IS NULL;
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot)
 ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 SELECT gen_random_uuid(),b.id,'sheet_booking',role,b.revision+1,snapshot FROM (VALUES('client_sheet'),('agency_sheet')) roles(role);
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
 SELECT gen_random_uuid(),b.id,'booking_cancelled',role,b.revision+1 FROM (VALUES('customer'),('client')) roles(role);
 RETURN jsonb_build_object('code','cancelled','revision',b.revision+1,'policy_guidance',guidance);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_appointment_detail(text,text,text,uuid),sarsa_booking.studio_appointment_cancel(text,text,text,uuid,uuid,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_appointment_detail(text,text,text,uuid),sarsa_booking.studio_appointment_cancel(text,text,text,uuid,uuid,integer,text) TO sarsa_booking_runtime;

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
    ELSIF accepted.payment_id=p_payment AND booking.state IN ('confirmed','cancelled') THEN
        RETURN CASE WHEN booking.state='confirmed' THEN 'confirmed' ELSE 'observed' END;
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
