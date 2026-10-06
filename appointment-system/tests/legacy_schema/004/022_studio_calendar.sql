-- Explicit client-only Studio calendar capabilities. No grant to raw owner functions.
CREATE INDEX slot_claims_studio_page ON sarsa_booking.slot_claims(id) WHERE released_at IS NULL;

CREATE FUNCTION sarsa_booking.studio_calendar_actor(p_session text,p_client text,p_origin text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE s sarsa_booking.studio_sessions%ROWTYPE;
BEGIN
 SELECT * INTO s FROM sarsa_booking.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.role<>'client' OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
    OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
    OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities i WHERE i.role=s.role AND i.subject=s.subject)
 THEN RETURN NULL; END IF;
 RETURN 'client:'||encode(sha256(convert_to(s.subject,'UTF8')),'hex');
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_calendar_actor(text,text,text) FROM PUBLIC;

CREATE FUNCTION sarsa_booking.studio_calendar_list(p_session text,p_client text,p_origin text,p_day date,p_after uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE result jsonb; from_time timestamptz; to_time timestamptz; actor text;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_day IS NULL OR NOT isfinite(p_day) OR p_day<(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date-31
    OR p_day>(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date+366 THEN
   RETURN jsonb_build_object('code','invalid_calendar_date'); END IF;
 from_time:=p_day::timestamp AT TIME ZONE 'Asia/Kolkata';
 to_time:=(p_day+1)::timestamp AT TIME ZONE 'Asia/Kolkata';
 WITH page AS (
  SELECT s.id,s.booking_id,s.starts_at,s.ends_at,s.closure_reason,b.full_name,b.state,b.service_snapshot
  FROM sarsa_booking.slot_claims s LEFT JOIN sarsa_booking.bookings b ON b.id=s.booking_id
  WHERE s.released_at IS NULL AND s.starts_at<to_time AND s.ends_at>from_time
    AND (p_after IS NULL OR s.id>p_after) ORDER BY s.id LIMIT 51
 ), shown AS (SELECT * FROM page ORDER BY id LIMIT 50)
 SELECT jsonb_build_object('code','ok','day',p_day,'timezone','Asia/Kolkata',
   'items',coalesce((SELECT jsonb_agg(jsonb_build_object('id',id,'kind',CASE WHEN booking_id IS NULL THEN 'closure' ELSE 'appointment' END,
      'starts_at',starts_at,'ends_at',ends_at,'reason',CASE WHEN booking_id IS NULL THEN closure_reason ELSE NULL END,
      'name',CASE WHEN booking_id IS NOT NULL THEN full_name ELSE NULL END,
      'service',CASE WHEN booking_id IS NOT NULL THEN service_snapshot->>'name' ELSE NULL END,
      'state',CASE WHEN booking_id IS NOT NULL THEN state ELSE NULL END) ORDER BY id) FROM shown),'[]'::jsonb),
   'next_cursor',CASE WHEN (SELECT count(*) FROM page)>50 THEN (SELECT id FROM shown ORDER BY id DESC LIMIT 1) ELSE NULL END)
 INTO result;
 RETURN result;
END $body$;

CREATE FUNCTION sarsa_booking.studio_calendar_close(p_session text,p_client text,p_origin text,p_operation uuid,p_reason text,p_start timestamptz,p_end timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE actor text; result jsonb; active boolean;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end)
   OR p_end<=p_start OR p_end-p_start>interval '31 days'
   OR p_end>clock_timestamp()+interval '366 days' OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500
 THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
 PERFORM pg_advisory_xact_lock(4004002);
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 result:=sarsa_booking.close_calendar(p_operation,actor,p_reason,p_start,p_end);
 IF result ? 'claim_id' THEN
   SELECT released_at IS NULL INTO active FROM sarsa_booking.slot_claims WHERE id=(result->>'claim_id')::uuid;
   result:=result||jsonb_build_object('active',active);
 END IF;
 RETURN result;
END $body$;

CREATE FUNCTION sarsa_booking.studio_calendar_reopen(p_session text,p_client text,p_origin text,p_operation uuid,p_claim uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE actor text; result jsonb; active boolean;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500
 THEN RETURN jsonb_build_object('code','invalid_closure'); END IF;
 PERFORM pg_advisory_xact_lock(4004002);
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 RETURN sarsa_booking.reopen_calendar(p_operation,p_claim,actor,p_reason);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_calendar_list(text,text,text,date,uuid),
 sarsa_booking.studio_calendar_close(text,text,text,uuid,text,timestamptz,timestamptz),
 sarsa_booking.studio_calendar_reopen(text,text,text,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_calendar_list(text,text,text,date,uuid),
 sarsa_booking.studio_calendar_close(text,text,text,uuid,text,timestamptz,timestamptz),
 sarsa_booking.studio_calendar_reopen(text,text,text,uuid,uuid,text) TO sarsa_booking_runtime;
