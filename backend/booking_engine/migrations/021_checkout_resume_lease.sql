-- Browser resume shares the recovery lease. Repeated clicks cannot fan out
-- provider reads; the receipt status endpoint remains strictly read-only.
ALTER TABLE sarsa_booking.payment_orders ADD COLUMN resume_started_at timestamptz;

CREATE FUNCTION sarsa_booking.claim_checkout_resume(p_booking uuid)
RETURNS jsonb LANGUAGE sql AS $body$
    WITH claimed AS (
        UPDATE sarsa_booking.payment_orders p
        SET lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+interval '90 seconds',
            resume_started_at=clock_timestamp()
        WHERE p.booking_id=p_booking AND p.state='ready' AND p.provider_order_id IS NOT NULL
          AND p.resolved_at IS NULL
          AND (p.lease_expires_at IS NULL OR p.lease_expires_at<=clock_timestamp())
          AND (p.resume_started_at IS NULL OR p.resume_started_at<=clock_timestamp()-interval '15 seconds')
          AND EXISTS(SELECT 1 FROM sarsa_booking.bookings b
            JOIN sarsa_booking.checkout_contexts c ON c.id=b.context_id
            WHERE b.id=p.booking_id AND b.state='held' AND b.hold_expires_at>clock_timestamp()
              AND c.active_checkout_id=b.id)
        RETURNING p.*
    ) SELECT (SELECT jsonb_build_object('booking_id',booking_id,'lease_token',lease_token,
        'recovery_cursor',recovery_cursor,'order_search_skip',order_search_skip) FROM claimed)
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_checkout_resume(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_checkout_resume(uuid) TO sarsa_booking_runtime;
