WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
SELECT jsonb_build_object('server_now',instant.at,'booking',(
    SELECT jsonb_build_object(
        'request_id',b.request_id,'receipt_digest',a.receipt_digest,
        'booking_id',b.id,'context_id',b.context_id,
        'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
        'receipt_expires_at',b.receipt_expires_at,'receipt_revoked_at',b.receipt_revoked_at,
        'state',b.state,'order_state',p.state,'attempted_at',p.attempted_at,
        'provider_order_id',p.provider_order_id,'resolution',p.resolution,'resolved_at',p.resolved_at,
        'hold_expires_at',b.hold_expires_at,'service_name',b.service_snapshot->>'name',
        'amount_paise',b.amount_paise,'currency',b.currency,'starts_at',b.starts_at,'ends_at',b.ends_at,
        'practice_timezone',b.practice_timezone,
        'payment_state',CASE
          WHEN EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL) THEN 'needs_attention'
          WHEN amounts.captured_paise>0 AND amounts.refunded_paise>=amounts.captured_paise THEN 'refunded'
          WHEN amounts.refunded_paise>0 THEN 'partially_refunded'
          WHEN EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=b.id) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM sarsa_booking.payment_observations WHERE booking_id=b.id AND status='captured' AND captured) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM (
            SELECT DISTINCT ON (merchant_id,mode,payment_id) status
            FROM sarsa_booking.payment_observations WHERE booking_id=b.id
            ORDER BY merchant_id,mode,payment_id,observed_at DESC,
              CASE status WHEN 'refunded' THEN 5 WHEN 'captured' THEN 4
                WHEN 'failed' THEN 3 WHEN 'authorized' THEN 2 ELSE 1 END DESC,id DESC
          ) latest WHERE status IN ('created','authorized')) THEN 'pending'
          WHEN EXISTS(SELECT 1 FROM sarsa_booking.payment_observations WHERE booking_id=b.id AND status='failed') THEN 'failed_observed'
          ELSE 'unobserved' END,
        'captured_paise',coalesce(amounts.captured_paise,0),'refunded_paise',coalesce(amounts.refunded_paise,0),
        'payment_checked_at',(SELECT max(observed_at) FROM sarsa_booking.payment_observations WHERE booking_id=b.id),
        'meeting_state',CASE
          WHEN b.state='cancelled' THEN 'cancelled'
          WHEN EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE booking_id=b.id AND booking_revision=b.revision
                       AND kind='booking_calendar' AND state='attention') THEN 'needs_attention'
          WHEN b.state='confirmed' AND EXISTS(SELECT 1 FROM sarsa_booking.meeting_events WHERE booking_id=b.id
                       AND booking_revision=b.revision AND state='ready') THEN 'ready'
          WHEN b.state='confirmed' THEN 'preparing' ELSE 'not_created' END,
        'meet_url',CASE WHEN b.state='confirmed' THEN (SELECT meet_url FROM sarsa_booking.meeting_events
          WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready') ELSE NULL END,
        'acknowledgement_state',coalesce((SELECT sarsa_booking.email_delivery_state(id) FROM sarsa_booking.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_ack' AND recipient_role='customer'),'not_queued'),
        'meeting_email_state',coalesce((SELECT sarsa_booking.email_delivery_state(id) FROM sarsa_booking.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_details' AND recipient_role='customer'),'not_queued')
    ) FROM sarsa_booking.bookings b
      JOIN sarsa_booking.checkout_admissions a ON a.request_id=b.request_id
      JOIN sarsa_booking.payment_orders p ON p.booking_id=b.id
      LEFT JOIN LATERAL (
        SELECT accepted.amount_paise AS captured_paise,coalesce(max(o.refunded_paise),0) AS refunded_paise
        FROM sarsa_booking.accepted_payments a
        JOIN sarsa_booking.payment_observations accepted ON accepted.id=a.observation_id
        JOIN sarsa_booking.payment_observations o ON o.booking_id=a.booking_id AND o.merchant_id=a.merchant_id
          AND o.mode=a.mode AND o.payment_id=a.payment_id
        WHERE a.booking_id=b.id
        GROUP BY accepted.amount_paise
      ) amounts ON true
    WHERE b.request_id=%s
)) FROM instant
