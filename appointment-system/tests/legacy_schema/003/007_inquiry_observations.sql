-- Source attribution does not change the existing verification purpose.
ALTER TABLE inquiries ADD COLUMN source text,
    ADD COLUMN seen_at timestamptz,
    ADD COLUMN seen_by text;
UPDATE inquiries SET source=CASE WHEN kind='prashna' THEN 'prashna' ELSE 'contact' END;
ALTER TABLE inquiries ALTER COLUMN source SET NOT NULL;
ALTER TABLE inquiries ADD CONSTRAINT inquiry_source CHECK (source IN ('home','contact','prashna'));
CREATE INDEX inquiry_pages ON inquiries(created_at DESC,id DESC);

-- Retain only observation metadata, never webhook bodies, email content or OTPs.
-- Unknown email IDs are retained and joined once send acceptance is recorded.
CREATE TABLE email_events (
    event_id text PRIMARY KEY,
    provider_id uuid NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL
);
CREATE INDEX email_event_lookup ON email_events(provider_id,event_type,occurred_at);
CREATE TABLE verification_emails (
    challenge_id uuid PRIMARY KEY,
    provider_id uuid NOT NULL UNIQUE,
    purpose text NOT NULL,
    accepted_at timestamptz NOT NULL
);
CREATE INDEX rate_limit_expiry ON rate_limits(resets_at);
CREATE INDEX challenge_expiry ON email_challenges(expires_at);
CREATE INDEX verification_expiry ON email_verifications(expires_at);
