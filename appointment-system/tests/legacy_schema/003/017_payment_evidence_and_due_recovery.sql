-- Preserve immutable money evidence alongside the legacy compatible projection.
CREATE TABLE payment_evidence_journal (
    id uuid PRIMARY KEY,
    key_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('test','live')),
    payment_id text NOT NULL,
    booking_id uuid NOT NULL REFERENCES bookings(id),
    order_id text NOT NULL,
    evidence_hash text NOT NULL CHECK (evidence_hash ~ '^[a-f0-9]{64}$'),
    status text NOT NULL,
    amount_paise integer NOT NULL CHECK (amount_paise > 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    amount_refunded integer NOT NULL CHECK (amount_refunded >= 0),
    captured boolean,
    provenance text NOT NULL CHECK (provenance IN ('legacy_snapshot','provider_fetch')),
    observed_at timestamptz NOT NULL,
    UNIQUE(key_id,mode,payment_id,evidence_hash)
);
CREATE INDEX payment_evidence_by_booking ON payment_evidence_journal(booking_id,observed_at,id);

-- A legacy snapshot supplies no historical capture flag that was not saved.
INSERT INTO payment_evidence_journal
    (id,key_id,mode,payment_id,booking_id,order_id,evidence_hash,status,
     amount_paise,currency,amount_refunded,captured,provenance,observed_at)
SELECT gen_random_uuid(),p.key_id,o.mode,p.payment_id,p.booking_id,p.order_id,
       encode(sha256(convert_to(jsonb_build_object('legacy_snapshot',p)::text,'UTF8')),'hex'),
       p.status,p.amount_paise,p.currency,p.amount_refunded,NULL,'legacy_snapshot',p.observed_at
FROM payment_observations p JOIN payment_orders o ON o.booking_id=p.booking_id AND o.key_id=p.key_id;

CREATE TABLE accepted_payment_bindings (
    booking_id uuid PRIMARY KEY REFERENCES bookings(id),
    key_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('test','live')),
    payment_id text NOT NULL,
    ledger_payment_id text NOT NULL UNIQUE REFERENCES payments(payment_id),
    provenance text NOT NULL CHECK (provenance IN ('legacy_snapshot','provider_fetch')),
    accepted_at timestamptz NOT NULL,
    UNIQUE(key_id,mode,payment_id)
);
-- Seed only an exact known ledger/order/observation association. Other historical
-- references remain in the original ledger and retain their existing access.
INSERT INTO accepted_payment_bindings
    (booking_id,key_id,mode,payment_id,ledger_payment_id,provenance,accepted_at)
SELECT l.booking_id,o.key_id,o.mode,p.payment_id,l.payment_id,'legacy_snapshot',l.received_at
FROM payments l JOIN payment_orders o ON o.booking_id=l.booking_id
JOIN payment_observations p ON p.booking_id=l.booking_id AND p.key_id=o.key_id
    AND p.order_id=o.order_id AND l.payment_id=o.key_id||':'||p.payment_id
WHERE l.disposition='accepted' AND l.amount_paise=o.amount_paise
    AND p.amount_paise=o.amount_paise AND l.currency='INR' AND p.currency='INR';

CREATE TABLE payment_case_actions (
    id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES payment_cases(id),
    actor text NOT NULL,
    resolution text NOT NULL,
    note text NOT NULL CHECK (length(note) <= 500),
    recorded_at timestamptz NOT NULL,
    provenance text NOT NULL CHECK (provenance IN ('legacy_snapshot','staff_action'))
);
INSERT INTO payment_case_actions (id,case_id,actor,resolution,note,recorded_at,provenance)
SELECT gen_random_uuid(),id,handled_by,resolution,COALESCE(note,''),handled_at,'legacy_snapshot'
FROM payment_cases WHERE state='handled';

ALTER TABLE payment_orders
    ADD COLUMN next_check_at timestamptz,
    ADD COLUMN check_lease_token uuid,
    ADD COLUMN check_lease_until timestamptz,
    ADD COLUMN order_search_skip integer NOT NULL DEFAULT 0 CHECK (order_search_skip >= 0),
    ADD COLUMN order_search_match text,
    ADD COLUMN order_search_conflict boolean NOT NULL DEFAULT false,
    ADD COLUMN payment_scan_cursor text,
    ADD CONSTRAINT payment_check_lease_pair CHECK
        ((check_lease_token IS NULL) = (check_lease_until IS NULL));
UPDATE payment_orders SET next_check_at=COALESCE(last_checked_at,created_at);
CREATE INDEX payment_orders_due_recovery ON payment_orders(next_check_at,created_at,booking_id)
    WHERE state IN ('ready','creation_unknown');

-- Distinct money cases for one appointment need distinct saved notices. Their
-- exact dedupe keys remain unique; ordinary appointment/enquiry versions keep
-- the historical recipient/version uniqueness rule.
DROP INDEX delivery_recipient_version;
CREATE UNIQUE INDEX delivery_recipient_version ON delivery_jobs(kind,record_id,message_version,recipient_role)
    WHERE kind<>'payment_review';

REVOKE ALL ON payment_evidence_journal,accepted_payment_bindings,payment_case_actions FROM PUBLIC;

CREATE TABLE payment_callback_references (
    key_id text NOT NULL,
    payment_id text NOT NULL,
    booking_id uuid NOT NULL REFERENCES bookings(id),
    order_id text NOT NULL,
    received_at timestamptz NOT NULL,
    PRIMARY KEY(key_id,payment_id)
);
REVOKE ALL ON payment_callback_references FROM PUBLIC;
