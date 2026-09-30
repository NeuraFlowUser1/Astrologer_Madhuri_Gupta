CREATE TABLE sarsa_booking.meeting_events (
    booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
    booking_revision integer NOT NULL,
    event_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK(state IN ('waiting','ready','cancelled')),
    meet_url text,
    PRIMARY KEY(booking_id,booking_revision),
    CHECK((state='ready' AND meet_url IS NOT NULL AND meet_url ~ '^https://meet[.]google[.]com/[a-z]{3}-[a-z]{4}-[a-z]{3}$')
       OR (state<>'ready' AND meet_url IS NULL))
);
ALTER TABLE sarsa_booking.delivery_jobs ADD COLUMN last_error_code text;
REVOKE ALL ON sarsa_booking.meeting_events FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON sarsa_booking.meeting_events TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.claim_google_delivery()
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE;
BEGIN
    -- Lock booking before job, matching completion and appointment changes.
    SELECT * INTO j FROM sarsa_booking.delivery_jobs d
      WHERE (d.kind IN ('booking_calendar','sheet_booking') OR (d.kind='booking_cancelled' AND d.recipient_role='calendar'))
      AND d.state IN ('pending','failed','uncertain','processing') AND d.next_attempt_at<=clock_timestamp()
      AND (d.lease_expires_at IS NULL OR d.lease_expires_at<=clock_timestamp())
      ORDER BY d.next_attempt_at,d.id LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO b FROM sarsa_booking.bookings WHERE id=j.booking_id FOR SHARE;
    SELECT * INTO j FROM sarsa_booking.delivery_jobs d WHERE d.id=j.id
      AND d.state IN ('pending','failed','uncertain','processing') AND d.next_attempt_at<=clock_timestamp()
      AND (d.lease_expires_at IS NULL OR d.lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF j.payload IS NULL AND j.kind IN ('booking_calendar','sheet_booking')
       AND (b.state<>'confirmed' OR b.revision<>j.booking_revision) THEN
      UPDATE sarsa_booking.delivery_jobs SET state='suppressed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
      RETURN NULL;
    END IF;
    IF j.kind='booking_cancelled' AND j.payload IS NULL AND b.revision<>j.booking_revision THEN
      UPDATE sarsa_booking.delivery_jobs SET state='attention',last_error_code='google_cancellation_snapshot_missing',
        lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
      RETURN NULL;
    END IF;
    UPDATE sarsa_booking.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
      lease_expires_at=clock_timestamp()+interval '180 seconds',attempts=attempts+1,
      first_attempt_at=coalesce(first_attempt_at,clock_timestamp()),
      payload=coalesce(payload,jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,
        'service_snapshot',b.service_snapshot,'starts_at',b.starts_at,'ends_at',b.ends_at,
        'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise))
      WHERE id=j.id RETURNING * INTO j;
    RETURN to_jsonb(j);
END
$body$;

CREATE FUNCTION sarsa_booking.finish_google_delivery(p_job uuid,p_lease uuid,p_state text,
    p_provider text,p_meet text,p_error text,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE; booking uuid; stale boolean; expected_event text;
BEGIN
    IF p_state IS NULL OR p_state NOT IN ('done','waiting','failed','attention') OR p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 3600
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
    SELECT booking_id INTO booking FROM sarsa_booking.delivery_jobs WHERE id=p_job;
    SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR SHARE;
    IF NOT FOUND THEN RETURN false; END IF;
    SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=p_job FOR UPDATE;
    IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR p_lease IS NULL OR j.state<>'processing'
       OR j.lease_expires_at<=clock_timestamp() THEN RETURN false; END IF;
    IF j.kind NOT IN ('booking_calendar','sheet_booking') AND NOT(j.kind='booking_cancelled' AND j.recipient_role='calendar') THEN RETURN false; END IF;
    stale:=b.state<>'confirmed' OR b.revision<>j.booking_revision;
    IF j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN
      expected_event:='sarsa'||encode(sha256(convert_to('004-sarsa-jyotish-sansthan:'||b.id::text||':'||j.booking_revision::text,'UTF8')),'hex');
      IF p_provider IS DISTINCT FROM expected_event THEN RETURN false; END IF;
      INSERT INTO sarsa_booking.meeting_events(booking_id,booking_revision,event_id,state,meet_url)
        VALUES(b.id,j.booking_revision,p_provider,CASE WHEN p_state='done' THEN 'ready' ELSE 'waiting' END,p_meet)
        ON CONFLICT(booking_id,booking_revision) DO UPDATE SET state=excluded.state,meet_url=excluded.meet_url;
      IF stale THEN
        INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
          VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',j.booking_revision,j.payload)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO UPDATE
          SET state='pending',next_attempt_at=clock_timestamp(),lease_token=NULL,lease_expires_at=NULL;
      ELSIF p_state='done' THEN
        INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
          VALUES(gen_random_uuid(),b.id,'booking_details','customer',j.booking_revision)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
      END IF;
    ELSIF j.kind='booking_cancelled' AND p_state='done' THEN
      UPDATE sarsa_booking.meeting_events SET state='cancelled',meet_url=NULL
        WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    END IF;
    UPDATE sarsa_booking.delivery_jobs SET state=CASE WHEN stale AND j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN 'suppressed'
      WHEN p_state='done' THEN 'delivered' WHEN p_state='attention' THEN 'attention' WHEN p_state='waiting' THEN 'pending' ELSE 'failed' END,
      provider_id=coalesce(p_provider,provider_id),last_error_code=p_error,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
    RETURN true;
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_google_delivery(),
    sarsa_booking.finish_google_delivery(uuid,uuid,text,text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_google_delivery(),
    sarsa_booking.finish_google_delivery(uuid,uuid,text,text,text,text,integer) TO sarsa_booking_runtime;
