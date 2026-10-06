-- A booking hold and its order intent are committed together. Provider calls
-- happen after commit; attempted_at is never reset after uncertain creation.
CREATE TABLE payment_orders (
    booking_id uuid PRIMARY KEY REFERENCES bookings(id),
    key_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('test','live')),
    receipt text NOT NULL UNIQUE CHECK (length(receipt) <= 40),
    amount_paise integer NOT NULL CHECK (amount_paise > 0),
    state text NOT NULL DEFAULT 'preparing' CHECK (state IN ('preparing','ready','creation_unknown','failed')),
    order_id text,
    attempted_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL,
    UNIQUE(key_id, order_id),
    CHECK ((state = 'ready') = (order_id IS NOT NULL))
);

-- Retain only verification facts, not customer details from provider payloads.
CREATE TABLE payment_observations (
    key_id text NOT NULL,
    payment_id text NOT NULL,
    booking_id uuid NOT NULL REFERENCES bookings(id),
    order_id text NOT NULL,
    status text NOT NULL,
    amount_paise integer NOT NULL CHECK (amount_paise > 0),
    currency text NOT NULL,
    amount_refunded integer NOT NULL CHECK (amount_refunded >= 0),
    disposition text NOT NULL CHECK (disposition IN ('pending','accepted','review')),
    observed_at timestamptz NOT NULL,
    PRIMARY KEY(key_id, payment_id)
);
CREATE INDEX payment_orders_unresolved ON payment_orders(created_at)
    WHERE state IN ('preparing','creation_unknown');
CREATE INDEX payment_observations_review ON payment_observations(observed_at)
    WHERE disposition = 'review';
