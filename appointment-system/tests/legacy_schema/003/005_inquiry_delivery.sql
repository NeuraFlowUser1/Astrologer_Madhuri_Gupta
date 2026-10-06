-- Separate recovery for each inquiry recipient. 'sent' means provider accepted,
-- not inbox delivery; the latter requires provider delivery events.
ALTER TABLE delivery_jobs
    ADD COLUMN recipient_role text CHECK (recipient_role IN ('customer','client')),
    ADD COLUMN message_version integer NOT NULL DEFAULT 1 CHECK (message_version > 0),
    ADD COLUMN next_attempt_at timestamptz,
    ADD COLUMN first_attempt_at timestamptz,
    ADD COLUMN send_uncertain boolean NOT NULL DEFAULT false,
    ADD COLUMN lease_token uuid,
    ADD COLUMN lease_until timestamptz,
    ADD COLUMN message_payload jsonb,
    ADD COLUMN provider_id uuid UNIQUE,
    ADD COLUMN accepted_at timestamptz,
    ADD COLUMN last_error_code text;
UPDATE delivery_jobs SET next_attempt_at=created_at;
ALTER TABLE delivery_jobs ALTER COLUMN next_attempt_at SET NOT NULL;

-- Former inquiry jobs did not identify recipients. Expand pending intent only;
-- historical outcomes cannot establish which recipient was actually notified.
UPDATE delivery_jobs SET recipient_role='customer', dedupe_key=dedupe_key || ':customer',
    last_error_code=CASE WHEN state='pending' THEN NULL ELSE 'legacy_outcome_unknown' END,
    state=CASE WHEN state='pending' THEN 'pending' ELSE 'failed' END
    WHERE kind='inquiry_received';
INSERT INTO delivery_jobs (id,dedupe_key,kind,record_id,state,created_at,next_attempt_at,recipient_role,last_error_code)
    SELECT gen_random_uuid(), regexp_replace(dedupe_key, ':customer$', ':client'), kind,record_id,state,
        created_at,next_attempt_at,'client',last_error_code
    FROM delivery_jobs WHERE kind='inquiry_received' AND recipient_role='customer';
ALTER TABLE delivery_jobs ADD CONSTRAINT inquiry_delivery_has_recipient
    CHECK (kind<>'inquiry_received' OR recipient_role IS NOT NULL);
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_lease_pair
    CHECK ((lease_token IS NULL) = (lease_until IS NULL));
CREATE UNIQUE INDEX delivery_recipient_version ON delivery_jobs(kind,record_id,message_version,recipient_role);
CREATE INDEX delivery_due ON delivery_jobs(next_attempt_at,id) WHERE state='pending';
CREATE INDEX delivery_expired_lease ON delivery_jobs(lease_until,id) WHERE state='processing';
