-- Unknown historical timing cannot create a fresh late-move entitlement.
CREATE OR REPLACE FUNCTION appointment_system.entry_studio_appointment_reschedule(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text, p_start timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text;old appointment_system.staff_appointment_actions%ROWTYPE;b appointment_system.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;spec jsonb;local_start timestamp;offer record;new_end timestamptz;deadline timestamptz;late boolean;old_snapshot jsonb;snapshot jsonb;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_start IS NULL OR NOT isfinite(p_start) OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('staff-appointment-operation:'||p_operation::text,0));
 SELECT s.booking_id,bk.context_id INTO booking,context FROM appointment_system.slot_claims s JOIN appointment_system.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 SELECT p.specification INTO spec FROM appointment_system.intake_settings s JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','time_unavailable'); END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO old FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'reschedule' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision
  OR old.reason IS DISTINCT FROM p_reason OR old.new_starts_at IS DISTINCT FROM p_start THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','rescheduled','revision',old.revision,'starts_at',old.new_starts_at,'ends_at',old.new_ends_at);
 END IF;

 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking;
 PERFORM appointment_system.lock_capacity_window(
  p_start-make_interval(mins=>(spec->>'buffer_before_minutes')::integer),
  p_start+(b.ends_at-b.starts_at)+make_interval(mins=>(spec->>'buffer_after_minutes')::integer),
  (SELECT starts_at FROM appointment_system.slot_claims WHERE id=p_claim),
  (SELECT ends_at FROM appointment_system.slot_claims WHERE id=p_claim));

 PERFORM appointment_system.lock_move_capacity(booking,
  p_start-make_interval(mins=>(spec->>'buffer_before_minutes')::integer),
  p_start+(b.ends_at-b.starts_at)+make_interval(mins=>(spec->>'buffer_after_minutes')::integer));
 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id=p_claim AND released_at IS NULL)
 THEN RETURN jsonb_build_object('code','appointment_unavailable');END IF;
 IF p_start=b.starts_at THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 late:=b.starts_at<instant+interval '12 hours';
 IF late AND (b.preparation->'_legacy_late_reschedule_used'='true'::jsonb OR EXISTS(SELECT 1 FROM appointment_system.staff_appointment_actions WHERE booking_id=b.id AND late_exception))
 THEN RETURN jsonb_build_object('code','late_reschedule_used');END IF;
 IF late AND b.original_starts_at IS NULL AND b.reschedule_deadline_at IS NULL
 THEN RETURN jsonb_build_object('code','original_time_review_required');END IF;
 deadline:=coalesce(b.reschedule_deadline_at,CASE WHEN late THEN b.original_starts_at+interval '14 days' END);
 SELECT * INTO offer FROM appointment_system.schedule_starts(spec,
  (extract(epoch FROM b.ends_at-b.starts_at)/60)::integer,
  (p_start AT TIME ZONE (spec->>'timezone'))::date,instant,deadline) s WHERE s.starts_at=p_start;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','time_unavailable'); END IF;
 new_end:=offer.ends_at;
 IF EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id<>p_claim AND released_at IS NULL
  AND tstzrange(starts_at,ends_at,'[)')&&tstzrange(offer.occupied_start,offer.occupied_end,'[)'))
 THEN RETURN jsonb_build_object('code','time_already_reserved'); END IF;
 old_snapshot:=appointment_system.booking_snapshot(b.id);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
 BEGIN
  UPDATE appointment_system.slot_claims SET starts_at=offer.occupied_start,ends_at=offer.occupied_end WHERE id=p_claim;
  UPDATE appointment_system.bookings SET starts_at=p_start,ends_at=new_end,revision=revision+1,
  hold_expires_at=least(hold_expires_at,p_start),receipt_expires_at=greatest(receipt_expires_at,new_end+interval '24 hours'),reschedule_deadline_at=deadline WHERE id=b.id;
  INSERT INTO appointment_system.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance,new_starts_at,new_ends_at,late_exception)
  VALUES(p_operation,p_claim,b.id,'reschedule',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,
  CASE WHEN late THEN 'late_reschedule_review' ELSE 'free_reschedule' END,p_start,new_end,late);
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,b.revision+1,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar')) jobs(kind,role) WHERE kind<>'booking_calendar' OR spec->>'meeting'='google_meet';
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,b.revision+1,jsonb_build_object('booking_id',b.id,'reference',b.request_id,
  'service',b.service_snapshot->>'name','starts_at',p_start,'ends_at',new_end,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','rescheduled') FROM(VALUES('customer'),('client')) roles(role);
 EXCEPTION WHEN exclusion_violation THEN RETURN jsonb_build_object('code','time_already_reserved');END;
 RETURN jsonb_build_object('code','rescheduled','revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
END $$;
