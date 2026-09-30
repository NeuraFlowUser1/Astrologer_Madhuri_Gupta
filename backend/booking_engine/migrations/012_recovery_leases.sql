ALTER TABLE sarsa_booking.payment_orders ADD COLUMN lease_token uuid;
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN recovery_followup boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN last_recovery_error text;
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN recovery_cursor integer NOT NULL DEFAULT 0 CHECK(recovery_cursor>=0);
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN order_search_skip integer NOT NULL DEFAULT 0 CHECK(order_search_skip>=0);
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE sarsa_booking.payment_orders ADD CONSTRAINT order_lease_pair
    CHECK((lease_token IS NULL)=(lease_expires_at IS NULL));
ALTER TABLE sarsa_booking.provider_inbox ADD COLUMN lease_token uuid;
ALTER TABLE sarsa_booking.provider_inbox ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE sarsa_booking.provider_inbox ADD COLUMN last_error_code text;
ALTER TABLE sarsa_booking.provider_inbox ADD CONSTRAINT inbox_lease_pair
    CHECK((lease_token IS NULL)=(lease_expires_at IS NULL));
CREATE INDEX provider_inbox_due ON sarsa_booking.provider_inbox(next_attempt_at,received_at)
    WHERE processed_at IS NULL;

CREATE INDEX payment_followup_due ON sarsa_booking.payment_orders(next_check_at,booking_id)
    WHERE recovery_followup AND resolution='confirmed';

-- Claim-only transaction: never acquire context/schedule locks while holding
-- these row locks, and commit the lease before any provider request.
CREATE FUNCTION sarsa_booking.claim_payment_recovery(p_limit integer)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE result jsonb;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 20 OR p_limit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid recovery batch';
    END IF;
    WITH due AS (
        SELECT p.booking_id FROM sarsa_booking.payment_orders p
        WHERE (p.resolved_at IS NULL OR (p.recovery_followup AND p.resolution='confirmed')) AND p.next_check_at<=clock_timestamp()
          AND (p.lease_expires_at IS NULL OR p.lease_expires_at<=clock_timestamp())
          AND (p.state<>'creating' OR p.attempted_at<=clock_timestamp()-interval '30 seconds')
        ORDER BY p.next_check_at,p.booking_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), claimed AS (
        UPDATE sarsa_booking.payment_orders p
          SET recovery_followup=true,lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=p.attempts+1
          FROM due WHERE p.booking_id=due.booking_id RETURNING p.*
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('booking_id',p.booking_id,'context_id',b.context_id,
        'lease_token',p.lease_token,'attempts',p.attempts,'merchant_id',p.merchant_id,'mode',p.mode,
        'credential_version',p.credential_version,'provider_order_id',p.provider_order_id,'state',p.state,
        'amount_paise',b.amount_paise,'currency',b.currency,'hold_expires_at',b.hold_expires_at,
        'server_now',clock_timestamp(),'recovery_cursor',p.recovery_cursor,'order_search_skip',p.order_search_skip)), '[]'::jsonb)
        INTO result FROM claimed p JOIN sarsa_booking.bookings b ON b.id=p.booking_id;
    RETURN result;
END
$body$;
CREATE FUNCTION sarsa_booking.finish_payment_recovery(p_booking uuid,p_lease uuid,p_delay integer,p_cursor integer,p_skip integer,p_error text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 3600 OR p_delay IS NULL OR p_cursor IS NULL OR p_cursor<0 OR p_skip IS NULL OR p_skip<0 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid recovery delay';
    END IF;
    UPDATE sarsa_booking.payment_orders SET lease_token=NULL,lease_expires_at=NULL,
      next_check_at=clock_timestamp()+make_interval(secs=>p_delay),recovery_cursor=p_cursor,order_search_skip=p_skip,recovery_followup=(p_cursor>0 OR p_error IS NOT NULL),last_recovery_error=p_error
      WHERE booking_id=p_booking AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;
CREATE FUNCTION sarsa_booking.claim_payment_events(p_limit integer)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE result jsonb;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 20 OR p_limit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event batch';
    END IF;
    WITH due AS (
        SELECT provider,account_id,environment,event_id FROM sarsa_booking.provider_inbox
        WHERE provider='razorpay' AND processed_at IS NULL AND next_attempt_at<=clock_timestamp()
          AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
        ORDER BY next_attempt_at,received_at,event_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), claimed AS (
        UPDATE sarsa_booking.provider_inbox p SET lease_token=gen_random_uuid(),
          lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=p.attempts+1
        FROM due d WHERE (p.provider,p.account_id,p.environment,p.event_id)=(d.provider,d.account_id,d.environment,d.event_id)
        RETURNING p.*
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('provider',provider,'account_id',account_id,
        'environment',environment,'event_id',event_id,'payload',payload,'lease_token',lease_token,'attempts',attempts)), '[]'::jsonb)
        INTO result FROM claimed;
    RETURN result;
END
$body$;
CREATE FUNCTION sarsa_booking.finish_payment_event(
    p_account text,p_mode text,p_event text,p_lease uuid,p_done boolean,p_delay integer,p_error text
) RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 3600 OR p_delay IS NULL OR p_done IS NULL
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event outcome';
    END IF;
    UPDATE sarsa_booking.provider_inbox SET lease_token=NULL,lease_expires_at=NULL,
      processed_at=CASE WHEN p_done THEN clock_timestamp() ELSE NULL END,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),last_error_code=p_error
      WHERE provider='razorpay' AND account_id=p_account AND environment=p_mode AND event_id=p_event
        AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_payment_recovery(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION sarsa_booking.finish_payment_recovery(uuid,uuid,integer,integer,integer,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION sarsa_booking.claim_payment_events(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION sarsa_booking.finish_payment_event(text,text,text,uuid,boolean,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_payment_recovery(integer),
    sarsa_booking.finish_payment_recovery(uuid,uuid,integer,integer,integer,text),
    sarsa_booking.claim_payment_events(integer),
    sarsa_booking.finish_payment_event(text,text,text,uuid,boolean,integer,text) TO sarsa_booking_runtime;
