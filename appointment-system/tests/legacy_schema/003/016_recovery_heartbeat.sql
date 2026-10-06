CREATE TABLE recovery_heartbeat (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    last_completed_at timestamptz NOT NULL,
    needs_attention integer NOT NULL CHECK (needs_attention >= 0),
    run_id uuid NOT NULL
);

COMMENT ON TABLE recovery_heartbeat IS
    'One privacy-safe status row for the external recovery monitor; never stores customer data.';
