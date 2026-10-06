-- Sarsa004 only. Run through the checked migration runner on the development
-- branch first. No catalogue values or provider credentials are seeded.
CREATE SCHEMA sarsa_booking;
REVOKE ALL ON SCHEMA sarsa_booking FROM PUBLIC;

CREATE TABLE sarsa_booking.schema_migrations (
    version text PRIMARY KEY,
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sarsa_booking.checkout_contexts (
    id uuid PRIMARY KEY,
    credential_digest text NOT NULL UNIQUE CHECK (credential_digest ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    active_checkout_id uuid,
    CHECK (expires_at > created_at)
);

-- Admissions are committed separately so a rejected hold cannot erase attempts.
CREATE TABLE sarsa_booking.checkout_admissions (
    request_id uuid PRIMARY KEY,
    context_id uuid NOT NULL REFERENCES sarsa_booking.checkout_contexts(id),
    receipt_digest text NOT NULL CHECK (receipt_digest ~ '^[a-f0-9]{64}$'),
    request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
    outcome text NOT NULL DEFAULT 'pending' CHECK (outcome IN ('pending','rejected','committed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (request_id, context_id)
);
CREATE INDEX admissions_context_time ON sarsa_booking.checkout_admissions(context_id, created_at);

CREATE TABLE sarsa_booking.bookings (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    context_id uuid NOT NULL,
    state text NOT NULL CHECK (state IN ('held','confirmed','expired','cancelled','payment_review')),
    service_id text NOT NULL CHECK (length(service_id) BETWEEN 1 AND 80),
    policy_version text NOT NULL CHECK (policy_version ~ '^[a-f0-9]{64}$'),
    service_snapshot jsonb NOT NULL CHECK (jsonb_typeof(service_snapshot) = 'object'),
    amount_paise bigint NOT NULL CHECK (amount_paise > 0),
    currency text NOT NULL CHECK (currency = 'INR'),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    practice_timezone text NOT NULL CHECK (length(practice_timezone) > 0),
    full_name text NOT NULL CHECK (length(btrim(full_name)) BETWEEN 2 AND 100),
    email text NOT NULL CHECK (length(btrim(email)) BETWEEN 3 AND 254),
    phone text NOT NULL CHECK (phone ~ '^\+[1-9][0-9]{6,14}$'),
    preparation jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(preparation) = 'object'),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    hold_expires_at timestamptz NOT NULL,
    receipt_expires_at timestamptz NOT NULL,
    receipt_revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, context_id),
    FOREIGN KEY (request_id, context_id) REFERENCES sarsa_booking.checkout_admissions(request_id, context_id),
    CHECK (ends_at > starts_at),
    CHECK (hold_expires_at > created_at AND hold_expires_at <= starts_at),
    CHECK (receipt_expires_at >= ends_at)
);
-- The pointer must refer to a booking in this same context, not just any UUID.
ALTER TABLE sarsa_booking.checkout_contexts ADD CONSTRAINT same_context_checkout
    FOREIGN KEY (active_checkout_id, id) REFERENCES sarsa_booking.bookings(id, context_id);
CREATE UNIQUE INDEX one_held_booking_per_context ON sarsa_booking.bookings(context_id) WHERE state = 'held';

-- One practitioner: every live interval (booking or manual closure) shares this
-- exclusion constraint. Half-open intervals allow adjacent appointments.
CREATE TABLE sarsa_booking.slot_claims (
    id uuid PRIMARY KEY,
    booking_id uuid UNIQUE REFERENCES sarsa_booking.bookings(id),
    closure_reason text,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    released_at timestamptz,
    CHECK ((booking_id IS NULL) <> (closure_reason IS NULL)),
    CHECK (ends_at > starts_at),
    EXCLUDE USING gist (tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (released_at IS NULL)
);

CREATE TABLE sarsa_booking.payment_orders (
    booking_id uuid PRIMARY KEY REFERENCES sarsa_booking.bookings(id),
    merchant_id text NOT NULL CHECK (length(merchant_id) > 0),
    mode text NOT NULL CHECK (mode IN ('test','live')),
    credential_version text NOT NULL CHECK (length(credential_version) > 0),
    provider_order_id text,
    state text NOT NULL DEFAULT 'not_attempted' CHECK (state IN ('not_attempted','creating','creation_unknown','ready','failed')),
    attempted_at timestamptz,
    resolution text CHECK (resolution IN ('never_attempted_abandoned','creation_definitely_rejected','provider_terminal','studio_reviewed','confirmed')),
    resolved_at timestamptz,
    resolution_actor text,
    resolution_note text,
    next_check_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    UNIQUE (merchant_id, mode, provider_order_id),
    CHECK ((state = 'not_attempted') = (attempted_at IS NULL)),
    CHECK (state <> 'ready' OR provider_order_id IS NOT NULL),
    CHECK ((resolution IS NULL) = (resolved_at IS NULL)),
    CHECK (resolution <> 'never_attempted_abandoned' OR state = 'not_attempted'),
    CHECK (resolution <> 'creation_definitely_rejected' OR (state = 'failed' AND provider_order_id IS NULL)),
    CHECK (resolution <> 'studio_reviewed' OR
           (resolution_actor IS NOT NULL AND length(btrim(resolution_actor)) > 0 AND
            resolution_note IS NOT NULL AND length(btrim(resolution_note)) > 0))
);
CREATE INDEX unresolved_orders_due ON sarsa_booking.payment_orders(next_check_at, booking_id) WHERE resolved_at IS NULL;

-- Immutable observations preserve refunds/disputes and out-of-order evidence.
CREATE TABLE sarsa_booking.payment_observations (
    id uuid PRIMARY KEY,
    booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
    merchant_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('test','live')),
    payment_id text NOT NULL,
    provider_order_id text NOT NULL,
    evidence_hash text NOT NULL CHECK (evidence_hash ~ '^[a-f0-9]{64}$'),
    status text NOT NULL,
    amount_paise bigint NOT NULL CHECK (amount_paise >= 0),
    currency text NOT NULL,
    refunded_paise bigint NOT NULL DEFAULT 0 CHECK (refunded_paise >= 0 AND refunded_paise <= amount_paise),
    observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (merchant_id, mode, payment_id, evidence_hash),
    UNIQUE (id, booking_id, merchant_id, mode, payment_id)
);
CREATE TABLE sarsa_booking.accepted_payments (
    booking_id uuid PRIMARY KEY REFERENCES sarsa_booking.bookings(id),
    observation_id uuid NOT NULL UNIQUE,
    merchant_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('test','live')),
    payment_id text NOT NULL,
    UNIQUE (merchant_id, mode, payment_id),
    FOREIGN KEY (observation_id, booking_id, merchant_id, mode, payment_id)
        REFERENCES sarsa_booking.payment_observations(id, booking_id, merchant_id, mode, payment_id)
);
CREATE TABLE sarsa_booking.payment_cases (
    id uuid PRIMARY KEY,
    booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
    event_key text NOT NULL CHECK (length(event_key) > 0),
    reason text NOT NULL,
    next_check_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolution_actor text,
    resolution_note text,
    UNIQUE (booking_id, event_key),
    CHECK (resolved_at IS NULL OR (resolution_actor IS NOT NULL AND resolution_note IS NOT NULL))
);
CREATE INDEX payment_cases_due ON sarsa_booking.payment_cases(next_check_at, id) WHERE resolved_at IS NULL;

CREATE TABLE sarsa_booking.delivery_jobs (
    id uuid PRIMARY KEY,
    booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
    kind text NOT NULL,
    recipient_role text NOT NULL,
    booking_revision integer NOT NULL CHECK (booking_revision > 0),
    event_key text NOT NULL DEFAULT '',
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','accepted','delivered','failed','uncertain','suppressed','attention')),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_token uuid,
    lease_expires_at timestamptz,
    first_attempt_at timestamptz,
    provider_id text,
    destination text,
    payload jsonb,
    UNIQUE (kind, booking_id, recipient_role, booking_revision, event_key),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK ((kind = 'payment_review' AND recipient_role = 'client' AND length(event_key) > 0)
       OR (event_key = '' AND (
            (kind = 'booking_ack' AND recipient_role IN ('customer','client')) OR
            (kind = 'booking_calendar' AND recipient_role = 'calendar') OR
            (kind = 'booking_details' AND recipient_role = 'customer') OR
            (kind = 'booking_cancelled' AND recipient_role IN ('customer','client','calendar')) OR
            (kind = 'sheet_booking' AND recipient_role IN ('client_sheet','agency_sheet')))))
);
CREATE INDEX delivery_jobs_due ON sarsa_booking.delivery_jobs(next_attempt_at,id) WHERE state IN ('pending','failed','uncertain');

CREATE TABLE sarsa_booking.provider_inbox (
    provider text NOT NULL CHECK (provider IN ('razorpay','resend')),
    account_id text NOT NULL,
    environment text NOT NULL CHECK (environment IN ('test','live')),
    event_id text NOT NULL,
    body_hash text NOT NULL CHECK (body_hash ~ '^[a-f0-9]{64}$'),
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    PRIMARY KEY (provider,account_id,environment,event_id)
);
REVOKE ALL ON ALL TABLES IN SCHEMA sarsa_booking FROM PUBLIC;
