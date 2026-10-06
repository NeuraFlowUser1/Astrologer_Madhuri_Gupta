-- Preserve legacy birth_details; never invent structured values for old rows.
ALTER TABLE bookings
    ADD COLUMN birth_date date,
    ADD COLUMN birth_time time,
    ADD COLUMN birth_place text NOT NULL DEFAULT '' CHECK (length(birth_place) <= 200),
    ADD COLUMN notes text NOT NULL DEFAULT '' CHECK (length(notes) <= 4000),
    ADD COLUMN quote_version text CHECK (quote_version ~ '^[a-f0-9]{64}$'),
    ADD COLUMN receipt_digest text CHECK (receipt_digest ~ '^[a-f0-9]{64}$'),
    ADD COLUMN receipt_expires_at timestamptz,
    ADD CONSTRAINT booking_receipt_pair CHECK ((receipt_digest IS NULL) = (receipt_expires_at IS NULL));

ALTER TABLE inquiries
    ADD COLUMN receipt_digest text CHECK (receipt_digest ~ '^[a-f0-9]{64}$'),
    ADD COLUMN receipt_expires_at timestamptz,
    ADD CONSTRAINT inquiry_receipt_pair CHECK ((receipt_digest IS NULL) = (receipt_expires_at IS NULL));

-- Acceptance by the email provider is not proof of inbox delivery.
ALTER TABLE email_challenges RENAME COLUMN delivered TO send_accepted;
