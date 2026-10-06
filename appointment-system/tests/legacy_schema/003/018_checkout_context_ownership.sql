CREATE TABLE checkout_contexts (
    id uuid PRIMARY KEY,
    credential_digest text NOT NULL CHECK (credential_digest ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    active_checkout_id uuid REFERENCES bookings(id),
    CHECK (expires_at > created_at)
);
ALTER TABLE bookings ADD COLUMN checkout_context_id uuid REFERENCES checkout_contexts(id);
CREATE INDEX checkout_contexts_unresolved ON checkout_contexts(active_checkout_id)
    WHERE active_checkout_id IS NOT NULL;
CREATE INDEX checkout_contexts_expiry ON checkout_contexts(expires_at)
    WHERE active_checkout_id IS NULL;
-- Existing receipts and identities remain unchanged. There is no guessed
-- context backfill from an email or a one-way stored receipt digest.
REVOKE ALL ON checkout_contexts FROM PUBLIC;
