CREATE TABLE payment_cases (
    id uuid PRIMARY KEY,
    booking_id uuid NOT NULL REFERENCES bookings(id),
    key_id text NOT NULL,
    external_reference text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('late_or_mismatched_payment','refund','dispute')),
    state text NOT NULL DEFAULT 'open' CHECK (state IN ('open','handled')),
    created_at timestamptz NOT NULL,
    handled_at timestamptz,
    handled_by text,
    resolution text CHECK (resolution IN ('checked_no_action','customer_contacted','refund_handled')),
    note text CHECK (length(note) <= 500),
    UNIQUE(key_id,external_reference,kind),
    CHECK ((state='handled') = (handled_at IS NOT NULL AND handled_by IS NOT NULL AND resolution IS NOT NULL))
);
CREATE INDEX payment_cases_open ON payment_cases(created_at,id) WHERE state='open';
