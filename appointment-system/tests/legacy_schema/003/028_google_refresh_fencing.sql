-- Additive grant fencing: provider calls occur outside these short SQL leases.
ALTER TABLE google_connection ADD COLUMN revision bigint NOT NULL DEFAULT 1 CHECK(revision>0);
ALTER TABLE google_connection ADD COLUMN refresh_lease uuid;
ALTER TABLE google_connection ADD COLUMN refresh_lease_until timestamptz;
ALTER TABLE google_connection ADD COLUMN access_encrypted text;
ALTER TABLE google_connection ADD COLUMN access_expires_at timestamptz;
ALTER TABLE google_connection ADD COLUMN last_error_code text;
ALTER TABLE google_authorizations ADD COLUMN expected_revision bigint NOT NULL DEFAULT 0 CHECK(expected_revision>=0);
CREATE TABLE google_refresh_evidence (
 id uuid PRIMARY KEY,grant_revision bigint NOT NULL CHECK(grant_revision>0),
 lease uuid NOT NULL,result text NOT NULL CHECK(result IN('committed','stale','failed')),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON google_refresh_evidence FROM PUBLIC;
CREATE FUNCTION protect_google_refresh_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Google refresh evidence is immutable'; END $$;
REVOKE ALL ON FUNCTION protect_google_refresh_evidence() FROM PUBLIC;
CREATE TRIGGER google_refresh_evidence_immutable BEFORE UPDATE OR DELETE ON google_refresh_evidence
 FOR EACH ROW EXECUTE FUNCTION protect_google_refresh_evidence();
