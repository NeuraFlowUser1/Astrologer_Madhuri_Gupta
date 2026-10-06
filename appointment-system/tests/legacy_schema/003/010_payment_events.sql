CREATE TABLE payment_events (
    key_id text NOT NULL,
    event_id text NOT NULL,
    account_id text NOT NULL,
    kind text NOT NULL,
    payment_id text NOT NULL,
    payload_hash text NOT NULL,
    received_at timestamptz NOT NULL,
    processed_at timestamptz,
    next_attempt_at timestamptz NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    PRIMARY KEY(key_id,event_id)
);
CREATE INDEX payment_events_due ON payment_events(next_attempt_at)
    WHERE processed_at IS NULL;
