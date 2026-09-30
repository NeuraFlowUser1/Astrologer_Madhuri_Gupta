-- Atomic slot move with immutable revision history and bounded late exception.
ALTER TABLE sarsa_booking.staff_appointment_actions DROP CONSTRAINT staff_appointment_actions_action_check;
ALTER TABLE sarsa_booking.staff_appointment_actions ADD CHECK(action IN ('cancel','reschedule'));
ALTER TABLE sarsa_booking.staff_appointment_actions ADD COLUMN new_starts_at timestamptz;
ALTER TABLE sarsa_booking.staff_appointment_actions ADD COLUMN new_ends_at timestamptz;
ALTER TABLE sarsa_booking.staff_appointment_actions ADD COLUMN late_exception boolean NOT NULL DEFAULT false;
ALTER TABLE sarsa_booking.staff_appointment_actions ADD CHECK((action='cancel' AND new_starts_at IS NULL AND new_ends_at IS NULL AND NOT late_exception)
 OR(action='reschedule' AND new_starts_at IS NOT NULL AND new_ends_at IS NOT NULL AND new_ends_at>new_starts_at));
ALTER TABLE sarsa_booking.bookings ADD COLUMN reschedule_deadline_at timestamptz;
CREATE FUNCTION sarsa_booking.studio_appointment_reschedule(p_session text,p_client text,p_origin text,p_operation uuid,p_claim uuid,p_revision integer,p_reason text,p_start timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;old sarsa_booking.staff_appointment_actions%ROWTYPE;b sarsa_booking.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;spec jsonb;local_start timestamp;new_end timestamptz;deadline timestamptz;late boolean;old_snapshot jsonb;snapshot jsonb;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_start IS NULL OR NOT isfinite(p_start) OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT s.booking_id,bk.context_id INTO booking,context FROM sarsa_booking.slot_claims s JOIN sarsa_booking.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=context FOR UPDATE;
 PERFORM pg_advisory_xact_lock(4004002);
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO old FROM sarsa_booking.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'reschedule' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision
  OR old.reason IS DISTINCT FROM p_reason OR old.new_starts_at IS DISTINCT FROM p_start THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','rescheduled','revision',old.revision,'starts_at',old.new_starts_at,'ends_at',old.new_ends_at);
 END IF;
 PERFORM sarsa_booking.expire_holds();
 SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE id=p_claim AND released_at IS NULL)
 THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 IF p_start=b.starts_at THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 late:=b.starts_at<instant+interval '12 hours';
 IF late AND EXISTS(SELECT 1 FROM sarsa_booking.staff_appointment_actions WHERE booking_id=b.id AND late_exception)
 THEN RETURN jsonb_build_object('code','late_reschedule_used');END IF;
 deadline:=coalesce(b.reschedule_deadline_at,CASE WHEN late THEN b.starts_at+interval '14 days' END);
 SELECT p.specification INTO spec FROM sarsa_booking.intake_settings s JOIN sarsa_booking.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 IF spec IS NULL OR spec->>'timezone'<>'Asia/Kolkata' THEN RETURN jsonb_build_object('code','time_unavailable');END IF;
 local_start:=p_start AT TIME ZONE 'Asia/Kolkata';new_end:=p_start+(b.ends_at-b.starts_at);
 IF extract(second FROM local_start)<>0 OR extract(minute FROM local_start)::integer%(spec->>'slot_step_minutes')::integer<>0
 OR NOT(spec->'weekdays' @> to_jsonb(extract(isodow FROM local_start)::integer-1))
 OR p_start<instant+make_interval(mins=>(spec->>'notice_minutes')::integer)
 OR(deadline IS NOT NULL AND p_start>deadline)
 OR(deadline IS NULL AND local_start::date>(instant AT TIME ZONE 'Asia/Kolkata')::date+(spec->>'advance_days')::integer)
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(spec->'windows') w WHERE local_start::time>=(w->>0)::time
 AND(new_end AT TIME ZONE 'Asia/Kolkata')::date=local_start::date AND(new_end AT TIME ZONE 'Asia/Kolkata')::time<=(w->>1)::time)
 THEN RETURN jsonb_build_object('code','time_unavailable');END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE id<>p_claim AND released_at IS NULL AND tstzrange(starts_at,ends_at,'[)')&&tstzrange(p_start,new_end,'[)'))
 THEN RETURN jsonb_build_object('code','time_already_reserved');END IF;
 old_snapshot:=jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,'service_snapshot',b.service_snapshot,
 'starts_at',b.starts_at,'ends_at',b.ends_at,'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
 BEGIN
  UPDATE sarsa_booking.slot_claims SET starts_at=p_start,ends_at=new_end WHERE id=p_claim;
  UPDATE sarsa_booking.bookings SET starts_at=p_start,ends_at=new_end,revision=revision+1,
  hold_expires_at=least(hold_expires_at,p_start),receipt_expires_at=greatest(receipt_expires_at,new_end+interval '24 hours'),reschedule_deadline_at=deadline WHERE id=b.id;
  INSERT INTO sarsa_booking.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance,new_starts_at,new_ends_at,late_exception)
  VALUES(p_operation,p_claim,b.id,'reschedule',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,
  CASE WHEN late THEN 'late_reschedule_review' ELSE 'free_reschedule' END,p_start,new_end,late);
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,b.revision+1,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar')) jobs(kind,role);
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,b.revision+1,jsonb_build_object('booking_id',b.id,'reference',b.request_id,
  'service',b.service_snapshot->>'name','starts_at',p_start,'ends_at',new_end,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','rescheduled') FROM(VALUES('customer'),('client')) roles(role);
 EXCEPTION WHEN exclusion_violation THEN RETURN jsonb_build_object('code','time_already_reserved');END;
 RETURN jsonb_build_object('code','rescheduled','revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_appointment_reschedule(text,text,text,uuid,uuid,integer,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_appointment_reschedule(text,text,text,uuid,uuid,integer,text,timestamptz) TO sarsa_booking_runtime;

CREATE OR REPLACE FUNCTION sarsa_booking.studio_appointment_detail(p_session text,p_client text,p_origin text,p_claim uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE b sarsa_booking.bookings%ROWTYPE;
BEGIN
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT booking.* INTO b FROM sarsa_booking.bookings booking JOIN sarsa_booking.slot_claims s ON s.booking_id=booking.id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 RETURN jsonb_build_object('code','ok','claim_id',p_claim,'revision',b.revision,'state',b.state,'name',b.full_name,
 'service',b.service_snapshot->>'name','reference',b.request_id,'starts_at',b.starts_at,'ends_at',b.ends_at,
 'can_cancel',b.state='confirmed' AND b.starts_at>clock_timestamp(),
 'can_reschedule',b.state='confirmed' AND b.starts_at>clock_timestamp(),
 'policy_guidance',CASE WHEN EXISTS(SELECT 1 FROM sarsa_booking.staff_appointment_actions WHERE booking_id=b.id AND action='reschedule') THEN 'staff_review' WHEN b.starts_at>=clock_timestamp()+interval '24 hours' THEN 'full_refund_review'
 WHEN b.starts_at>=clock_timestamp()+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END);
END $$;

CREATE OR REPLACE FUNCTION sarsa_booking.studio_appointment_cancel(p_session text,p_client text,p_origin text,p_operation uuid,p_claim uuid,p_revision integer,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;old sarsa_booking.staff_appointment_actions%ROWTYPE;b sarsa_booking.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;guidance text;snapshot jsonb;old_snapshot jsonb;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 SELECT s.booking_id,bk.context_id INTO booking,context FROM sarsa_booking.slot_claims s JOIN sarsa_booking.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=context FOR UPDATE;
 PERFORM pg_advisory_xact_lock(4004002);
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM sarsa_booking.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'cancel' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision OR old.reason IS DISTINCT FROM p_reason THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','cancelled','revision',old.revision,'policy_guidance',old.policy_guidance);
 END IF;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM sarsa_booking.slot_claims WHERE id=p_claim AND released_at IS NULL) THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 guidance:=CASE WHEN EXISTS(SELECT 1 FROM sarsa_booking.staff_appointment_actions WHERE booking_id=b.id AND action='reschedule') THEN 'staff_review' WHEN b.starts_at>=instant+interval '24 hours' THEN 'full_refund_review' WHEN b.starts_at>=instant+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END;
 old_snapshot:=jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,'service_snapshot',b.service_snapshot,
 'starts_at',b.starts_at,'ends_at',b.ends_at,'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'state','cancelled');
 INSERT INTO sarsa_booking.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance)
 VALUES(p_operation,p_claim,b.id,'cancel',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,guidance);
 UPDATE sarsa_booking.bookings SET state='cancelled',revision=revision+1 WHERE id=b.id;
 UPDATE sarsa_booking.slot_claims SET released_at=instant WHERE id=p_claim;
 -- Never erase accepted evidence or revoke an in-flight completion lease.
 UPDATE sarsa_booking.delivery_jobs SET state='suppressed',last_error_code='appointment_cancelled'
 WHERE booking_id=b.id AND booking_revision=b.revision AND kind IN ('booking_ack','booking_details','booking_calendar')
 AND state IN ('pending','failed') AND first_attempt_at IS NULL AND payload IS NULL AND provider_id IS NULL AND lease_token IS NULL;
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot)
 ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 SELECT gen_random_uuid(),b.id,'sheet_booking',role,b.revision+1,snapshot FROM (VALUES('client_sheet'),('agency_sheet')) roles(role);
 INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
 SELECT gen_random_uuid(),b.id,'booking_cancelled',role,b.revision+1 FROM (VALUES('customer'),('client')) roles(role);
 RETURN jsonb_build_object('code','cancelled','revision',b.revision+1,'policy_guidance',guidance);
END $$;

-- Reconcile an expired old creation lease by deleting its original event, never recreating it.
CREATE OR REPLACE FUNCTION sarsa_booking.claim_google_delivery()
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
    RETURN to_jsonb(j)||jsonb_build_object('obsolete',j.kind='booking_calendar' AND (b.state<>'confirmed' OR b.revision<>j.booking_revision));
END
$body$;

CREATE OR REPLACE FUNCTION sarsa_booking.finish_google_delivery(p_job uuid,p_lease uuid,p_state text,
    p_provider text,p_meet text,p_error text,p_delay integer)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE j sarsa_booking.delivery_jobs%ROWTYPE; b sarsa_booking.bookings%ROWTYPE; booking uuid; stale boolean; expected_event text;
BEGIN
    IF p_state IS NULL OR p_state NOT IN ('done','waiting','failed','attention','obsolete') OR p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 3600
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
    SELECT booking_id INTO booking FROM sarsa_booking.delivery_jobs WHERE id=p_job;
    SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR SHARE;
    IF NOT FOUND THEN RETURN false; END IF;
    SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=p_job FOR UPDATE;
    IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR p_lease IS NULL OR j.state<>'processing'
       OR j.lease_expires_at<=clock_timestamp() THEN RETURN false; END IF;
    IF j.kind NOT IN ('booking_calendar','sheet_booking') AND NOT(j.kind='booking_cancelled' AND j.recipient_role='calendar') THEN RETURN false; END IF;
    stale:=b.state<>'confirmed' OR b.revision<>j.booking_revision;
    IF p_state='obsolete' THEN
      IF j.kind<>'booking_calendar' OR NOT stale THEN RETURN false; END IF;
      UPDATE sarsa_booking.meeting_events SET state='cancelled',meet_url=NULL WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    ELSIF j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN
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
    UPDATE sarsa_booking.delivery_jobs SET state=CASE WHEN p_state='obsolete' THEN 'suppressed' WHEN stale AND j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN 'suppressed'
      WHEN p_state='done' THEN 'delivered' WHEN p_state='attention' THEN 'attention' WHEN p_state='waiting' THEN 'pending' ELSE 'failed' END,
      provider_id=coalesce(p_provider,provider_id),last_error_code=p_error,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
    RETURN true;
END
$body$;
