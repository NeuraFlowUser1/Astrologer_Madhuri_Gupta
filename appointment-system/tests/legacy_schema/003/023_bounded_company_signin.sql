-- Company-only bounded sign-in; no customer data or raw network address.
CREATE TABLE booking_control.login_limits (
 key_hash text NOT NULL CHECK(key_hash ~ '^[a-f0-9]{64}$'),
 window_start timestamptz NOT NULL,expires_at timestamptz NOT NULL,
 attempts integer NOT NULL CHECK(attempts>0),PRIMARY KEY(key_hash,window_start)
);
REVOKE ALL ON booking_control.login_limits FROM PUBLIC;
CREATE FUNCTION booking_control.login_admission(p_risk text,p_state text,p_browser text,p_audience text,p_nonce text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $$
DECLARE instant timestamptz:=clock_timestamp();start_at timestamptz;used integer;total integer;
BEGIN
 IF p_risk IS NULL OR p_risk !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='sign-in source required';END IF;
 start_at:=to_timestamp(floor(extract(epoch FROM instant)/600)*600);
 DELETE FROM booking_control.login_limits WHERE (key_hash,window_start) IN
  (SELECT key_hash,window_start FROM booking_control.login_limits WHERE expires_at<=instant LIMIT 100);
 -- Always lock global before source: concurrent requests cannot deadlock.
 INSERT INTO booking_control.login_limits VALUES(repeat('0',64),start_at,start_at+interval '1 day',1)
 ON CONFLICT(key_hash,window_start) DO UPDATE SET attempts=least(booking_control.login_limits.attempts+1,61)
 RETURNING attempts INTO total;
 INSERT INTO booking_control.login_limits VALUES(p_risk,start_at,start_at+interval '1 day',1)
 ON CONFLICT(key_hash,window_start) DO UPDATE SET attempts=least(booking_control.login_limits.attempts+1,11)
 RETURNING attempts INTO used;
 IF used>10 OR total>60 THEN RETURN jsonb_build_object('allowed',false);END IF;
 PERFORM booking_control.login_start(p_state,p_browser,p_audience,p_nonce);
 RETURN jsonb_build_object('allowed',true);
END $$;
REVOKE ALL ON FUNCTION booking_control.login_admission(text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION booking_control.login_admission(text,text,text,text,text) TO astro_booking_control;
