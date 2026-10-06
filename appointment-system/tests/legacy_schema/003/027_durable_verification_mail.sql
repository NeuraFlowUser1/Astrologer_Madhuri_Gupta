-- A challenge is not a received enquiry. Only short-lived encrypted mail is queued.
CREATE TABLE verification_mail (
 challenge_id uuid PRIMARY KEY, purpose text NOT NULL CHECK(purpose IN('booking','contact','prashna')),
 message_ciphertext text CHECK(length(message_ciphertext)<=12000), message_hash text NOT NULL CHECK(message_hash ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN('pending','processing','accepted','uncertain','failed','expired','superseded')),
 next_attempt_at timestamptz NOT NULL,first_attempt_at timestamptz,attempts integer NOT NULL DEFAULT 0,
 lease_token uuid,lease_until timestamptz,provider_id uuid UNIQUE,error_code text,
 CHECK((lease_token IS NULL)=(lease_until IS NULL)),CHECK(attempts>=0)
);
CREATE INDEX verification_mail_due ON verification_mail(next_attempt_at,challenge_id) WHERE state IN('pending','uncertain','processing');
CREATE INDEX verification_cipher_expiry ON verification_mail(expires_at,challenge_id) WHERE message_ciphertext IS NOT NULL;
CREATE TABLE verification_mail_evidence (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),challenge_id uuid NOT NULL REFERENCES verification_mail(challenge_id),
 provider_id uuid NOT NULL UNIQUE,message_hash text NOT NULL,observed_at timestamptz NOT NULL,
 UNIQUE(challenge_id,provider_id)
);
CREATE TABLE verification_mail_conflicts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),challenge_id uuid NOT NULL REFERENCES verification_mail(challenge_id),
 provider_id uuid NOT NULL,message_hash text NOT NULL CHECK(message_hash ~ '^[a-f0-9]{64}$'),
 code text NOT NULL CHECK(code IN('provider_reference_owned_elsewhere','multiple_provider_references','message_snapshot_conflict')),
 observed_at timestamptz NOT NULL,UNIQUE(challenge_id,provider_id,message_hash,code)
);
REVOKE ALL ON verification_mail,verification_mail_evidence,verification_mail_conflicts FROM PUBLIC;
ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_jobs_kind_check;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_jobs_kind_check CHECK(kind IN('booking_confirmed','booking_cancelled','payment_review','inquiry_received','payment_event','sheet_booking','sheet_inquiry','verification_email'));
ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_recipient_required;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_recipient_required CHECK(
 (kind IN('payment_event','verification_email') AND recipient_role IS NULL) OR
 (kind='inquiry_received' AND recipient_role IN('customer','client')) OR
 (kind IN('booking_confirmed','booking_cancelled') AND recipient_role IN('calendar','customer','client')) OR
 (kind='payment_review' AND recipient_role='client') OR
 (kind IN('sheet_booking','sheet_inquiry') AND recipient_role IN('client_sheet','agency_sheet')));
