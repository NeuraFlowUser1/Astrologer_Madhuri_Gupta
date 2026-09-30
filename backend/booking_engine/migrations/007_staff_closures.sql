-- Staff closures share the same capacity table as customer reservations.
-- Only an authenticated staff adapter may call these owner-only functions.
-- No execution grant to the public website runtime.
CREATE TABLE sarsa_booking.staff_calendar_actions (
    operation_id uuid PRIMARY KEY,
    claim_id uuid NOT NULL REFERENCES sarsa_booking.slot_claims(id),
    action text NOT NULL CHECK(action IN ('close','reopen')),
    actor text NOT NULL CHECK(length(btrim(actor)) BETWEEN 1 AND 200),
    reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 1 AND 500),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON sarsa_booking.staff_calendar_actions FROM PUBLIC;

CREATE FUNCTION sarsa_booking.close_calendar(
    p_operation uuid,p_actor text,p_reason text,p_start timestamptz,p_end timestamptz
) RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE old sarsa_booking.staff_calendar_actions%ROWTYPE; claim uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(4004002);
    SELECT * INTO old FROM sarsa_booking.staff_calendar_actions WHERE operation_id=p_operation;
    IF FOUND THEN
        IF old.action <> 'close' OR old.actor IS DISTINCT FROM p_actor
           OR old.reason IS DISTINCT FROM p_reason OR old.starts_at IS DISTINCT FROM p_start
           OR old.ends_at IS DISTINCT FROM p_end THEN
            RETURN jsonb_build_object('code','request_conflict');
        END IF;
        RETURN jsonb_build_object('code','existing','claim_id',old.claim_id);
    END IF;
    IF p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end)
       OR p_end <= p_start OR p_end <= clock_timestamp()
       OR coalesce(length(btrim(p_actor)),0) NOT BETWEEN 1 AND 200
       OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 1 AND 500 THEN
        RETURN jsonb_build_object('code','invalid_closure');
    END IF;
    PERFORM sarsa_booking.expire_holds();
    IF EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE released_at IS NULL
        AND tstzrange(starts_at,ends_at,'[)') && tstzrange(p_start,p_end,'[)')) THEN
        RETURN jsonb_build_object('code','time_already_reserved');
    END IF;
    claim := gen_random_uuid();
    BEGIN
        INSERT INTO sarsa_booking.slot_claims(id,closure_reason,starts_at,ends_at)
          VALUES(claim,p_reason,p_start,p_end);
        INSERT INTO sarsa_booking.staff_calendar_actions(operation_id,claim_id,action,actor,reason,starts_at,ends_at)
          VALUES(p_operation,claim,'close',p_actor,p_reason,p_start,p_end);
    EXCEPTION WHEN exclusion_violation THEN
        RETURN jsonb_build_object('code','time_already_reserved');
    END;
    RETURN jsonb_build_object('code','closed','claim_id',claim);
END
$body$;
CREATE FUNCTION sarsa_booking.reopen_calendar(p_operation uuid,p_claim uuid,p_actor text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE old sarsa_booking.staff_calendar_actions%ROWTYPE; claim sarsa_booking.slot_claims%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(4004002);
    SELECT * INTO old FROM sarsa_booking.staff_calendar_actions WHERE operation_id=p_operation;
    IF FOUND THEN
        IF old.action <> 'reopen' OR old.claim_id IS DISTINCT FROM p_claim
           OR old.actor IS DISTINCT FROM p_actor OR old.reason IS DISTINCT FROM p_reason THEN
            RETURN jsonb_build_object('code','request_conflict');
        END IF;
        RETURN jsonb_build_object('code','existing','claim_id',old.claim_id);
    END IF;
    IF coalesce(length(btrim(p_actor)),0) NOT BETWEEN 1 AND 200
       OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 1 AND 500 THEN
        RETURN jsonb_build_object('code','invalid_closure');
    END IF;
    SELECT * INTO claim FROM sarsa_booking.slot_claims WHERE id=p_claim FOR UPDATE;
    IF NOT FOUND OR claim.booking_id IS NOT NULL THEN RETURN jsonb_build_object('code','closure_not_found'); END IF;
    IF claim.released_at IS NOT NULL THEN RETURN jsonb_build_object('code','already_open'); END IF;
    UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp() WHERE id=p_claim;
    INSERT INTO sarsa_booking.staff_calendar_actions(operation_id,claim_id,action,actor,reason,starts_at,ends_at)
      VALUES(p_operation,p_claim,'reopen',p_actor,p_reason,claim.starts_at,claim.ends_at);
    RETURN jsonb_build_object('code','reopened','claim_id',p_claim);
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.close_calendar(uuid,text,text,timestamptz,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION sarsa_booking.reopen_calendar(uuid,uuid,text,text) FROM PUBLIC;
