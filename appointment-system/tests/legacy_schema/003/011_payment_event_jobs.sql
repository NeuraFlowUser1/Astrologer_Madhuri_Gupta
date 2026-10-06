ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_jobs_kind_check;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_jobs_kind_check CHECK
    (kind IN ('booking_confirmed','booking_cancelled','payment_review','inquiry_received','payment_event'));
ALTER TABLE payment_events ADD COLUMN record_id uuid NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX payment_event_record ON payment_events(record_id);
INSERT INTO delivery_jobs(id,dedupe_key,kind,record_id,created_at,next_attempt_at,dispatch_after)
SELECT gen_random_uuid(), 'payment_event:' || record_id || ':', 'payment_event', record_id,
       received_at,next_attempt_at,next_attempt_at
FROM payment_events WHERE processed_at IS NULL;
