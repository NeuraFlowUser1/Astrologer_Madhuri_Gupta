-- Resolve entered civil time with the same database timezone rules as slots.
SET LOCAL ROLE appointment_system_owner;
CREATE FUNCTION appointment_system.studio_time_context(p_session text,p_client text,p_origin text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO pg_catalog,appointment_system,pg_temp AS $$
DECLARE zone text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']);
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN
  RETURN jsonb_build_object('code','access_unavailable');END IF;
 zone:=appointment_system.current_business()->>'timezone';
 RETURN jsonb_build_object('code','ok','timezone',zone,'today',(clock_timestamp() AT TIME ZONE zone)::date);
END $$;
CREATE FUNCTION appointment_system.studio_resolve_time(p_session text,p_client text,p_origin text,p_local text,p_zone text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO pg_catalog,appointment_system,pg_temp AS $$
DECLARE context jsonb;local_time timestamp;instant timestamptz;zone text;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']);
 context:=appointment_system.studio_time_context(p_session,p_client,p_origin);
 IF context->>'code'<>'ok' THEN RETURN context;END IF;
 zone:=context->>'timezone';
 IF p_zone IS DISTINCT FROM zone THEN RETURN jsonb_build_object('code','timezone_changed');END IF;
 IF p_local IS NULL OR p_local !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$' THEN
  RETURN jsonb_build_object('code','invalid_local_time');END IF;
 BEGIN local_time:=p_local::timestamp;EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN
  RETURN jsonb_build_object('code','invalid_local_time');END;
 IF to_char(local_time,'YYYY-MM-DD"T"HH24:MI')<>p_local THEN
  RETURN jsonb_build_object('code','invalid_local_time');END IF;
 instant:=local_time AT TIME ZONE zone;
 -- A skipped daylight-saving time must not silently become a later time.
 IF instant AT TIME ZONE zone<>local_time THEN RETURN jsonb_build_object('code','invalid_local_time');END IF;
 RETURN jsonb_build_object('code','ok','timezone',zone,'local',p_local,'instant',instant);
END $$;
REVOKE ALL ON FUNCTION appointment_system.studio_time_context(text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION appointment_system.studio_resolve_time(text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.studio_time_context(text,text,text) TO appointment_system_staff_access,appointment_system_company_access;
GRANT EXECUTE ON FUNCTION appointment_system.studio_resolve_time(text,text,text,text,text) TO appointment_system_staff_access,appointment_system_company_access;
RESET ROLE;
