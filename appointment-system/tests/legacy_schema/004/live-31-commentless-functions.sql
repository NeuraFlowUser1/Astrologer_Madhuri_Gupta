-- Read-only capture of the four published 004/31 function definitions on 2026-10-04.
-- Only the reviewed comment-line removal differs from the hash-pinned migrations.
-- Synthetic fixture input; never apply this file to a hosted database.

CREATE OR REPLACE FUNCTION sarsa_booking.admit_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
        admission sarsa_booking.checkout_admissions%ROWTYPE;
        count_recent integer;
BEGIN
    SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND OR ctx.expires_at <= clock_timestamp() THEN RETURN 'context_expired'; END IF;
    SELECT * INTO admission FROM sarsa_booking.checkout_admissions WHERE request_id=p_request;
    IF FOUND THEN
        IF admission.context_id IS DISTINCT FROM p_context OR admission.receipt_digest IS DISTINCT FROM p_receipt
           OR admission.request_fingerprint IS DISTINCT FROM p_fingerprint THEN RETURN 'request_conflict'; END IF;
        RETURN admission.outcome;
    END IF;
    SELECT count(*) INTO count_recent FROM sarsa_booking.checkout_admissions
      WHERE context_id=p_context AND created_at > clock_timestamp()-interval '1 hour';
    IF count_recent >= 6 THEN RETURN 'rate_limited'; END IF;
    BEGIN
        INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint)
          VALUES (p_request,p_context,p_receipt,p_fingerprint);
    EXCEPTION WHEN unique_violation THEN


        RETURN 'request_conflict';
    END;
    RETURN 'pending';
END
$function$
;

CREATE OR REPLACE FUNCTION sarsa_booking.claim_google_workbook(p_role text, p_client text)
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
DECLARE g sarsa_booking.google_connections%ROWTYPE; w sarsa_booking.google_workbooks%ROWTYPE; token uuid; action text;
BEGIN
    IF p_role IS NULL OR p_role NOT IN ('client','agency') OR p_client IS NULL THEN RETURN NULL; END IF;
    PERFORM pg_advisory_xact_lock(CASE WHEN p_role='client' THEN 4004201 ELSE 4004202 END);
    SELECT * INTO g FROM sarsa_booking.google_connections WHERE role=p_role AND client_id=p_client;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO w FROM sarsa_booking.google_workbooks WHERE role=p_role FOR UPDATE;
    token:=gen_random_uuid();
    IF NOT FOUND THEN
      INSERT INTO sarsa_booking.google_workbooks(role,subject,client_id,state,lease,lease_until,connection_revision)
        VALUES(p_role,g.subject,p_client,'creating',token,clock_timestamp()+interval '180 seconds',g.revision) RETURNING * INTO w;
      action:='create';
    ELSE
      IF w.subject<>g.subject OR w.client_id<>p_client THEN RETURN NULL; END IF;
      IF w.state='ready' THEN action:='ready';
      ELSE
        IF w.lease_until>clock_timestamp() AND w.connection_revision=g.revision THEN RETURN NULL; END IF;
        UPDATE sarsa_booking.google_workbooks SET lease=token,lease_until=clock_timestamp()+interval '180 seconds',
          connection_revision=g.revision WHERE role=p_role RETURNING * INTO w;


        action:='discover';
      END IF;
    END IF;
    RETURN to_jsonb(w)||jsonb_build_object('action',action);
END
$function$
;

CREATE OR REPLACE FUNCTION sarsa_booking.expire_holds()
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE changed integer;
BEGIN


    PERFORM pg_advisory_xact_lock(4004002);
    WITH expired AS (
        UPDATE sarsa_booking.bookings SET state='expired'
        WHERE state='held' AND hold_expires_at <= clock_timestamp()
        RETURNING id
    )
    UPDATE sarsa_booking.slot_claims SET released_at=clock_timestamp()
    WHERE released_at IS NULL AND booking_id IN (SELECT id FROM expired);
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END
$function$
;

CREATE OR REPLACE FUNCTION sarsa_booking.reserve_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text, p_input jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
        admission sarsa_booking.checkout_admissions%ROWTYPE;
        settings sarsa_booking.intake_settings%ROWTYPE;
        spec jsonb;
        service jsonb;
        local_start timestamp;
        local_now timestamp;
        starts timestamptz;
        ends timestamptz;
        instant timestamptz;
        booking_id uuid;
        reason text;
BEGIN
    SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('code','context_expired'); END IF;
    SELECT * INTO admission FROM sarsa_booking.checkout_admissions
      WHERE request_id=p_request AND context_id=p_context;
    IF NOT FOUND OR admission.receipt_digest IS DISTINCT FROM p_receipt
       OR admission.request_fingerprint IS DISTINCT FROM p_fingerprint THEN
        RETURN jsonb_build_object('code','request_conflict');
    END IF;


    IF admission.outcome='committed' THEN
        SELECT id INTO booking_id FROM sarsa_booking.bookings WHERE request_id=p_request;
        RETURN jsonb_build_object('code','existing','booking_id',booking_id);
    END IF;
    IF admission.outcome='rejected' THEN RETURN jsonb_build_object('code','request_rejected'); END IF;
    IF ctx.expires_at <= clock_timestamp() THEN RETURN jsonb_build_object('code','context_expired'); END IF;

    IF ctx.active_checkout_id IS NOT NULL THEN
        UPDATE sarsa_booking.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
        RETURN jsonb_build_object('code','checkout_in_progress');
    END IF;
    PERFORM pg_advisory_xact_lock(4004002);
    PERFORM sarsa_booking.expire_holds();
    SELECT * INTO settings FROM sarsa_booking.intake_settings WHERE singleton FOR SHARE;
    IF NOT FOUND OR NOT settings.public_open THEN reason := 'intake_closed';
    ELSIF settings.policy_version IS DISTINCT FROM p_input->>'quote_version' THEN reason := 'quote_changed';
    END IF;
    IF reason IS NULL THEN
        SELECT specification INTO spec FROM sarsa_booking.booking_policies WHERE version=settings.policy_version;
        SELECT item INTO service FROM jsonb_array_elements(spec->'services') item
          WHERE item->>'id'=p_input->>'service_id';
        IF service IS NULL THEN reason := 'service_unavailable'; END IF;
    END IF;
    IF reason IS NULL THEN


        IF coalesce(p_input->>'starts_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
            reason := 'invalid_time';
        ELSE
            BEGIN
                starts := (p_input->>'starts_at')::timestamptz;
            EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
                reason := 'invalid_time';
            END;
        END IF;
    END IF;
    IF reason IS NULL THEN
        instant := clock_timestamp();
        local_start := starts AT TIME ZONE (spec->>'timezone');
        local_now := instant AT TIME ZONE (spec->>'timezone');
        ends := starts+make_interval(mins=>(service->>'duration_minutes')::integer);
        IF NOT isfinite(starts) OR extract(second FROM local_start) <> 0
           OR extract(minute FROM local_start)::integer % (spec->>'slot_step_minutes')::integer <> 0
           OR NOT (spec->'weekdays' @> to_jsonb((extract(isodow FROM local_start)::integer-1)))
           OR local_start::date < local_now::date
           OR local_start::date > local_now::date+(spec->>'advance_days')::integer
           OR starts < instant+make_interval(mins=>(spec->>'notice_minutes')::integer)
           OR NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(spec->'windows') w
                WHERE local_start::time >= (w->>0)::time
                  AND (ends AT TIME ZONE (spec->>'timezone'))::date=local_start::date
                  AND (ends AT TIME ZONE (spec->>'timezone'))::time <= (w->>1)::time
           ) THEN reason := 'time_unavailable';
        END IF;
    END IF;
    IF reason IS NULL AND EXISTS (
        SELECT 1 FROM sarsa_booking.slot_claims WHERE released_at IS NULL
          AND tstzrange(starts_at,ends_at,'[)') && tstzrange(starts,ends,'[)')
    ) THEN reason := 'time_unavailable'; END IF;
    IF reason IS NOT NULL THEN
        UPDATE sarsa_booking.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
        RETURN jsonb_build_object('code',reason);
    END IF;
    booking_id := gen_random_uuid();


    BEGIN
        INSERT INTO sarsa_booking.bookings(
            id,request_id,context_id,state,service_id,policy_version,service_snapshot,
            amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,
            preparation,hold_expires_at,receipt_expires_at,created_at
        ) VALUES (
            booking_id,p_request,p_context,'held',service->>'id',settings.policy_version,service,
            (service->>'amount_paise')::bigint,service->>'currency',starts,ends,spec->>'timezone',
            p_input->>'full_name',p_input->>'email',p_input->>'phone',
            jsonb_build_object('birth_date',p_input->'birth_date','birth_time',p_input->'birth_time',
                               'birth_place',p_input->'birth_place','notes',p_input->'notes'),
            least(starts,instant+make_interval(mins=>(spec->>'hold_minutes')::integer)),
            ends+make_interval(hours=>(spec->>'receipt_after_hours')::integer),instant
        );
        INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at)
          VALUES(gen_random_uuid(),booking_id,starts,ends);
        INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version)
          VALUES(booking_id,settings.merchant_id,settings.payment_mode,settings.credential_version);
        UPDATE sarsa_booking.checkout_contexts SET active_checkout_id=booking_id WHERE id=p_context;
        UPDATE sarsa_booking.checkout_admissions SET outcome='committed' WHERE request_id=p_request;
    EXCEPTION WHEN exclusion_violation THEN
        UPDATE sarsa_booking.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
        RETURN jsonb_build_object('code','time_unavailable');
    END;
    RETURN jsonb_build_object('code','reserved','booking_id',booking_id);
END
$function$
;

