-- Finite, privacy-minimized diagnostic families; business evidence is separate.
CREATE TABLE sarsa_booking.operational_incidents(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),version integer NOT NULL DEFAULT 1 CHECK(version=1),
 project text NOT NULL DEFAULT '004' CHECK(project='004'),
 operation text NOT NULL CHECK(operation IN('control','provider_event','recovery','verification','enquiry','staff','checkout','booking','availability','site')),
 stage text NOT NULL CHECK(stage IN('request','provider','storage','recovery','diagnostic')),
 code text NOT NULL CHECK(code IN('service_unavailable','storage_unavailable','time_budget','unexpected_failure','provider_rejected','result_invalid')),
 first_seen_at timestamptz NOT NULL,last_seen_at timestamptz NOT NULL,
 first_reference uuid NOT NULL,last_reference uuid NOT NULL,
 occurrences integer NOT NULL CHECK(occurrences>0),elapsed_ms integer NOT NULL CHECK(elapsed_ms BETWEEN 0 AND 60000),
 UNIQUE(operation,stage,code)
);
REVOKE ALL ON sarsa_booking.operational_incidents FROM PUBLIC;
CREATE FUNCTION sarsa_booking.record_operation_incident(p_reference uuid,p_operation text,p_stage text,p_code text,p_elapsed integer)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
BEGIN
 IF p_reference IS NULL OR p_operation IS NULL OR p_stage IS NULL OR p_code IS NULL OR p_elapsed IS NULL
   OR p_elapsed NOT BETWEEN 0 AND 60000 THEN RETURN false; END IF;
 INSERT INTO sarsa_booking.operational_incidents(operation,stage,code,first_seen_at,last_seen_at,first_reference,last_reference,occurrences,elapsed_ms)
 VALUES(p_operation,p_stage,p_code,clock_timestamp(),clock_timestamp(),p_reference,p_reference,1,p_elapsed)
 ON CONFLICT(operation,stage,code) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_reference=excluded.last_reference,
 occurrences=CASE WHEN operational_incidents.last_reference=excluded.last_reference THEN operational_incidents.occurrences ELSE
   least(2147483647,operational_incidents.occurrences::bigint+1)::integer END,elapsed_ms=excluded.elapsed_ms;
 RETURN true;
END $body$;
CREATE FUNCTION sarsa_booking.read_operation_incidents(p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $body$
DECLARE result jsonb;
BEGIN
 PERFORM booking_control.authorize(p_session,'service_controller');
 SELECT coalesce(jsonb_agg(row),'[]'::jsonb) INTO result FROM
 (SELECT id,version,project,operation,stage,code,first_seen_at,last_seen_at,last_reference,occurrences,elapsed_ms
  FROM sarsa_booking.operational_incidents ORDER BY last_seen_at DESC,id LIMIT 100) row;
 RETURN jsonb_build_object('version',1,'project','004','incidents',result);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.record_operation_incident(uuid,text,text,text,integer),sarsa_booking.read_operation_incidents(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.read_operation_incidents(text) TO sarsa_booking_control;

GRANT EXECUTE ON FUNCTION sarsa_booking.record_operation_incident(uuid,text,text,text,integer) TO sarsa_booking_runtime;
