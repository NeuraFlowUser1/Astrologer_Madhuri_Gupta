-- One clinician, fixed 30-minute slots. All application schedule writes also
-- acquire the same transaction-scoped advisory lock before reading occupancy.
CREATE TABLE IF NOT EXISTS bookings (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    request_hash text NOT NULL,
    service_id text NOT NULL CHECK (service_id IN ('vedic-astrology','numerology','vastu','laal-kitaab','prashna-kundali','name-change')),
    service_name text NOT NULL,
    question_count integer NOT NULL CHECK (question_count BETWEEN 1 AND 10),
    amount_paise integer NOT NULL CHECK (amount_paise > 0),
    currency text NOT NULL CHECK (currency = 'INR'),
    duration_minutes integer NOT NULL CHECK (duration_minutes = 30),
    starts_at timestamptz NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text NOT NULL,
    birth_details text NOT NULL DEFAULT '',
    state text NOT NULL CHECK (state IN ('held','confirmed','expired','cancelled','payment_review')),
    hold_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    cancelled_at timestamptz,
    cancelled_by text,
    CHECK (service_id = 'prashna-kundali' OR question_count = 1),
    CHECK (extract(second FROM starts_at) = 0),
    CHECK (extract(minute FROM starts_at AT TIME ZONE 'Asia/Kolkata') IN (0,30))
);
CREATE INDEX IF NOT EXISTS bookings_starts_at ON bookings(starts_at);

CREATE TABLE IF NOT EXISTS closures (
    id uuid PRIMARY KEY,
    day date NOT NULL,
    start_time text,
    end_time text,
    reason text NOT NULL DEFAULT '',
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    reopened_at timestamptz,
    reopened_by text,
    CHECK ((start_time IS NULL) = (end_time IS NULL))
);

-- Bookings and closures share this key: neither can occupy a slot the other owns.
CREATE TABLE IF NOT EXISTS slot_claims (
    starts_at timestamptz PRIMARY KEY,
    booking_id uuid REFERENCES bookings(id),
    closure_id uuid REFERENCES closures(id),
    CHECK ((booking_id IS NULL) <> (closure_id IS NULL))
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id text PRIMARY KEY,
    booking_id uuid NOT NULL REFERENCES bookings(id),
    amount_paise integer NOT NULL CHECK (amount_paise > 0),
    currency text NOT NULL CHECK (currency = 'INR'),
    received_at timestamptz NOT NULL,
    disposition text NOT NULL CHECK (disposition IN ('accepted','review'))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_payment ON payments(booking_id) WHERE disposition = 'accepted';

CREATE TABLE IF NOT EXISTS inquiries (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    request_hash text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('contact','prashna')),
    name text NOT NULL,
    email text NOT NULL,
    phone text NOT NULL DEFAULT '',
    dob text NOT NULL DEFAULT '',
    subject text NOT NULL,
    message text NOT NULL,
    location text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL
);

-- Store delivery intent in the same transaction as the booking/inquiry.
-- A later provider worker delivers these; queued is never presented as sent.
CREATE TABLE IF NOT EXISTS delivery_jobs (
    id uuid PRIMARY KEY,
    dedupe_key text NOT NULL UNIQUE,
    kind text NOT NULL CHECK (kind IN ('booking_confirmed','booking_cancelled','payment_review','inquiry_received')),
    record_id uuid NOT NULL,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','sent','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at timestamptz NOT NULL
);

-- Codes and one-use verification credentials are stored only as keyed digests.
CREATE TABLE IF NOT EXISTS email_challenges (
    email text NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('booking','contact','prashna')),
    challenge_id uuid NOT NULL,
    code_digest text NOT NULL,
    expires_at timestamptz NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    delivered boolean NOT NULL DEFAULT false,
    PRIMARY KEY(email,purpose)
);
CREATE TABLE IF NOT EXISTS email_verifications (
    token_digest text PRIMARY KEY,
    email text NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('booking','contact','prashna')),
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
    key text PRIMARY KEY,
    count integer NOT NULL CHECK (count > 0),
    resets_at timestamptz NOT NULL
);
