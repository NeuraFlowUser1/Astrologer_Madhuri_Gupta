ALTER TABLE payment_orders
    ADD COLUMN last_checked_at timestamptz,
    ADD COLUMN check_attempts integer NOT NULL DEFAULT 0 CHECK (check_attempts >= 0);

CREATE INDEX payment_orders_due_check ON payment_orders(last_checked_at,created_at)
    WHERE state IN ('ready','creation_unknown');
