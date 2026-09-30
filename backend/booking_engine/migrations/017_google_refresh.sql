-- One bounded refresh operation per saved account connection. No network I/O
-- occurs while a row lock is held; connection revision belongs to user consent.
ALTER TABLE sarsa_booking.google_connections ADD COLUMN refresh_lease uuid;
ALTER TABLE sarsa_booking.google_connections ADD COLUMN refresh_lease_until timestamptz;
ALTER TABLE sarsa_booking.google_connections ADD COLUMN refresh_revision bigint;
ALTER TABLE sarsa_booking.google_connections ADD CONSTRAINT google_refresh_lease_complete
    CHECK ((refresh_lease IS NULL AND refresh_lease_until IS NULL AND refresh_revision IS NULL)
        OR (refresh_lease IS NOT NULL AND refresh_lease_until IS NOT NULL
            AND refresh_revision IS NOT NULL AND refresh_revision>0));

CREATE FUNCTION sarsa_booking.claim_google_refresh(p_role text,p_client text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE g sarsa_booking.google_connections%ROWTYPE; token uuid;
BEGIN
    SELECT * INTO g FROM sarsa_booking.google_connections WHERE role=p_role FOR UPDATE;
    IF NOT FOUND OR p_client IS NULL OR g.client_id<>p_client
       OR (g.grant_expires_at IS NOT NULL AND g.grant_expires_at<=clock_timestamp())
       OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities WHERE role=g.role AND subject=g.subject)
       OR (g.refresh_revision=g.revision AND g.refresh_lease_until>clock_timestamp()) THEN RETURN NULL; END IF;
    token:=gen_random_uuid();
    UPDATE sarsa_booking.google_connections SET refresh_lease=token,
      refresh_lease_until=clock_timestamp()+interval '90 seconds',refresh_revision=revision WHERE role=p_role;
    RETURN jsonb_build_object('role',g.role,'subject',g.subject,'client_id',g.client_id,
      'revision',g.revision,'lease',token,'encrypted_grant',g.encrypted_grant,'server_now',clock_timestamp());
END
$body$;

CREATE FUNCTION sarsa_booking.finish_google_refresh(p_role text,p_client text,p_subject text,
    p_revision bigint,p_lease uuid,p_encrypted text,p_expires timestamptz)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_encrypted IS NULL OR length(p_encrypted) NOT BETWEEN 100 AND 32768
       OR (p_expires IS NOT NULL AND (NOT isfinite(p_expires) OR p_expires<=clock_timestamp())) THEN RETURN false; END IF;
    UPDATE sarsa_booking.google_connections SET encrypted_grant=p_encrypted,grant_expires_at=p_expires,
      refresh_lease=NULL,refresh_lease_until=NULL,refresh_revision=NULL
      WHERE role=p_role AND client_id=p_client AND subject=p_subject AND revision=p_revision
        AND refresh_revision=revision AND refresh_lease=p_lease AND refresh_lease_until>clock_timestamp()
        AND EXISTS(SELECT 1 FROM sarsa_booking.studio_identities i WHERE i.role=p_role AND i.subject=p_subject);
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_google_refresh(text,text),
    sarsa_booking.finish_google_refresh(text,text,text,bigint,uuid,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_google_refresh(text,text),
    sarsa_booking.finish_google_refresh(text,text,text,bigint,uuid,text,timestamptz) TO sarsa_booking_runtime;
