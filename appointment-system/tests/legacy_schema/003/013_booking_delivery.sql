ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_jobs_recipient_role_check;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_jobs_recipient_role_check
    CHECK (recipient_role IN ('calendar','customer','client'));
ALTER TABLE delivery_jobs DROP CONSTRAINT inquiry_delivery_has_recipient;

-- Expand any pre-existing unfinished booking intent into explicit operations.
UPDATE delivery_jobs
SET recipient_role='calendar', dedupe_key=dedupe_key || ':calendar',
    state=CASE WHEN state='pending' THEN 'pending' ELSE 'failed' END,
    last_error_code=CASE WHEN state='pending' THEN last_error_code ELSE 'legacy_outcome_unknown' END
WHERE kind IN ('booking_confirmed','booking_cancelled') AND recipient_role IS NULL;

INSERT INTO delivery_jobs
    (id,dedupe_key,kind,record_id,state,attempts,created_at,next_attempt_at,
     recipient_role,message_version,last_error_code,dispatch_after)
SELECT gen_random_uuid(),regexp_replace(dedupe_key,':calendar$',':' || role),kind,record_id,
       state,0,created_at,next_attempt_at,role,1,last_error_code,dispatch_after
FROM delivery_jobs CROSS JOIN (VALUES ('customer'),('client')) AS roles(role)
WHERE kind IN ('booking_confirmed','booking_cancelled') AND recipient_role='calendar'
ON CONFLICT(dedupe_key) DO NOTHING;

UPDATE delivery_jobs
SET recipient_role='client', dedupe_key=dedupe_key || ':client',
    state=CASE WHEN state='pending' THEN 'pending' ELSE 'failed' END,
    last_error_code=CASE WHEN state='pending' THEN last_error_code ELSE 'legacy_outcome_unknown' END
WHERE kind='payment_review' AND recipient_role IS NULL;

ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_recipient_required CHECK (
    (kind='payment_event' AND recipient_role IS NULL) OR
    (kind='inquiry_received' AND recipient_role IN ('customer','client')) OR
    (kind IN ('booking_confirmed','booking_cancelled') AND recipient_role IN ('calendar','customer','client')) OR
    (kind='payment_review' AND recipient_role='client')
);

CREATE TABLE booking_calendar_events (
    booking_id uuid PRIMARY KEY REFERENCES bookings(id),
    calendar_id text NOT NULL,
    event_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK (state IN ('preparing','waiting','ready','cancelled','failed')),
    meet_url text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CHECK ((state='ready') = (meet_url IS NOT NULL))
);
