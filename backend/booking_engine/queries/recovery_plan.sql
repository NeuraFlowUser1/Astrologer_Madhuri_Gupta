-- Read-only, privacy-minimized scheduling hints. Claims remain authoritative.
-- A live lease postpones a hint; it never removes the durable obligation.
WITH work AS (
    SELECT CASE WHEN sarsa_booking.is_email_job(kind,recipient_role) THEN 'email' ELSE 'google' END lane,
           greatest(next_attempt_at,coalesce(lease_expires_at,next_attempt_at)) due
    FROM sarsa_booking.delivery_jobs
    WHERE state IN ('pending','failed','uncertain','processing')
      AND (sarsa_booking.is_email_job(kind,recipient_role) OR kind IN ('booking_calendar','sheet_booking')
           OR (kind='booking_cancelled' AND recipient_role='calendar'))
    UNION ALL
    SELECT CASE WHEN kind IN ('client_sheet','agency_sheet') THEN 'contact_google' ELSE 'contact_email' END,
           greatest(next_attempt_at,coalesce(lease_expires_at,next_attempt_at))
    FROM sarsa_booking.enquiry_delivery_jobs WHERE state IN ('pending','failed','uncertain','processing')
    UNION ALL
    SELECT 'contact_email',code_expires_at FROM sarsa_booking.enquiries WHERE code_ciphertext IS NOT NULL
    UNION ALL
    SELECT CASE WHEN provider='resend' THEN 'email_events' ELSE 'payment_events' END,
           greatest(next_attempt_at,coalesce(lease_expires_at,next_attempt_at))
    FROM sarsa_booking.provider_inbox WHERE processed_at IS NULL
    UNION ALL
    SELECT 'payment',greatest(next_check_at,coalesce(lease_expires_at,next_check_at),
        CASE WHEN state='creating' THEN attempted_at+interval '30 seconds' ELSE next_check_at END)
    FROM sarsa_booking.payment_orders
    WHERE resolved_at IS NULL OR (recovery_followup AND resolution='confirmed')
    UNION ALL
    SELECT 'maintenance',min(expires_at)+interval '24 hours' FROM sarsa_booking.google_attempts
     WHERE expires_at<statement_timestamp()-interval '24 hours'
    UNION ALL
    SELECT 'maintenance',min(s.expires_at)+interval '24 hours' FROM sarsa_booking.studio_sessions s
     WHERE s.expires_at<statement_timestamp()-interval '24 hours'
       AND NOT EXISTS(SELECT 1 FROM sarsa_booking.google_attempts a WHERE a.session_digest=s.digest)
    UNION ALL
    SELECT 'maintenance',min(expires_at)+interval '24 hours' FROM sarsa_booking.request_limits
     WHERE expires_at<statement_timestamp()-interval '24 hours'
), lanes(lane) AS (VALUES ('email'),('google'),('email_events'),('payment_events'),('payment'),('contact_email'),('contact_google'),('maintenance')),
next_work AS (
    SELECT lanes.lane,min(work.due) due FROM lanes LEFT JOIN work USING(lane) GROUP BY lanes.lane
)
SELECT jsonb_build_object(
    'lanes',(SELECT jsonb_object_agg(lane,CASE WHEN due IS NULL THEN NULL ELSE
        greatest(0,least(900,ceil(extract(epoch FROM due-statement_timestamp()))))::integer END) FROM next_work),
    'attention',EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE state='attention'
        OR (state='pending' AND last_error_code IN ('email_budget_unconfigured','email_budget_exhausted'))
        OR (state IN ('failed','uncertain') AND first_attempt_at<statement_timestamp()-interval '5 minutes'))
        OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE state='attention'
            OR (state='pending' AND last_error_code IN ('email_budget_unconfigured','email_budget_exhausted'))
            OR (state IN ('failed','uncertain') AND first_attempt_at<statement_timestamp()-interval '5 minutes'))
        OR EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE resolved_at IS NULL)
        OR EXISTS(SELECT 1 FROM work WHERE lane<>'maintenance' AND due<statement_timestamp()-interval '5 minutes')
        OR EXISTS(SELECT 1 FROM sarsa_booking.provider_inbox WHERE processed_at IS NULL
            AND last_error_code IS NOT NULL AND received_at<statement_timestamp()-interval '5 minutes')
        OR EXISTS(SELECT 1 FROM sarsa_booking.bookings b
            WHERE b.state='confirmed' AND b.ends_at>statement_timestamp()
              AND b.starts_at<statement_timestamp()+interval '60 minutes'
              AND (NOT EXISTS(SELECT 1 FROM sarsa_booking.meeting_events m
                    WHERE m.booking_id=b.id AND m.booking_revision=b.revision AND m.state='ready')
                OR NOT EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs d
                    WHERE d.booking_id=b.id AND d.booking_revision=b.revision
                      AND d.kind='booking_details' AND d.recipient_role='customer' AND d.provider_id IS NOT NULL)))
);
