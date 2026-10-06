-- Pseudonymous fixed-window counters. Browser contact details are never keys.
CREATE TABLE sarsa_booking.request_limits (
    scope text NOT NULL CHECK(scope IN ('context','availability','receipt','checkout')),
    key_digest text NOT NULL CHECK(key_digest ~ '^[a-f0-9]{64}$'),
    window_start timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    attempts integer NOT NULL CHECK(attempts>0),
    PRIMARY KEY(scope,key_digest,window_start)
);
CREATE INDEX request_limits_expiry ON sarsa_booking.request_limits(expires_at);
REVOKE ALL ON sarsa_booking.request_limits FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON sarsa_booking.request_limits TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.consume_request_limit(p_scope text,p_key text)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE instant timestamptz := clock_timestamp();
        start_at timestamptz; width integer; maximum integer; used integer;
BEGIN
    CASE p_scope
      WHEN 'context' THEN width:=3600; maximum:=20;
      WHEN 'availability' THEN width:=60; maximum:=60;
      WHEN 'receipt' THEN width:=60; maximum:=30;
      WHEN 'checkout' THEN width:=3600; maximum:=30;
      ELSE RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='unsupported request scope';
    END CASE;
    start_at:=to_timestamp(floor(extract(epoch FROM instant)/width)*width);
    INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,expires_at,attempts)
      VALUES(p_scope,p_key,start_at,start_at+make_interval(secs=>width)+interval '24 hours',1)
      ON CONFLICT(scope,key_digest,window_start) DO UPDATE
      SET attempts=least(sarsa_booking.request_limits.attempts+1,maximum+1)
      RETURNING attempts INTO used;
    RETURN jsonb_build_object('allowed',used<=maximum,
      'retry_after',greatest(1,ceil(extract(epoch FROM start_at+make_interval(secs=>width)-instant))::integer));
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.consume_request_limit(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.consume_request_limit(text,text) TO sarsa_booking_runtime;
