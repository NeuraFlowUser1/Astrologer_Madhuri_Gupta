CREATE TABLE admin_identity (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    google_subject text NOT NULL UNIQUE,
    authorized_at timestamptz NOT NULL
);
CREATE TABLE admin_login_challenges (
    token_digest text PRIMARY KEY,
    nonce text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE admin_sessions (
    token_digest text PRIMARY KEY,
    google_subject text NOT NULL REFERENCES admin_identity(google_subject),
    csrf_token text NOT NULL,
    expires_at timestamptz NOT NULL
);
