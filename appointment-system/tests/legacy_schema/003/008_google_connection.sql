CREATE TABLE google_connection (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    google_subject text NOT NULL REFERENCES admin_identity(google_subject),
    calendar_id text NOT NULL,
    refresh_token_encrypted text NOT NULL,
    scopes text NOT NULL,
    connected_at timestamptz NOT NULL
);

CREATE TABLE google_authorizations (
    state_digest text PRIMARY KEY,
    browser_digest text NOT NULL,
    session_digest text NOT NULL REFERENCES admin_sessions(token_digest) ON DELETE CASCADE,
    google_subject text NOT NULL REFERENCES admin_identity(google_subject),
    nonce text NOT NULL,
    verifier text NOT NULL,
    origin text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX google_authorizations_expiry ON google_authorizations(expires_at);
