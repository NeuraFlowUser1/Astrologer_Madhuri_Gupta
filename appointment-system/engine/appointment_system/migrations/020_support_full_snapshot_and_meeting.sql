-- Contact correction preserves every saved field and the accepted meeting choice.
SET LOCAL ROLE appointment_system_owner;
CREATE OR REPLACE FUNCTION appointment_system.entry_studio_support_change(p_session text, p_client text, p_origin text, p_operation uuid, p_reference uuid, p_revision integer, p_action text, p_reason text, p_payment text, p_email text, p_phone text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.receipt_recoveries%ROWTYPE;b appointment_system.bookings%ROWTYPE;context uuid;instant timestamptz;old_snapshot jsonb;snapshot jsonb;new_revision integer;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_reference IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_action IS NULL OR p_action NOT IN ('receipt_recovery','contact_correction') OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 OR p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR (p_action='contact_correction' AND(coalesce(length(p_email),0) NOT BETWEEN 3 AND 254 OR p_email ~ '[[:cntrl:]]' OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$'))
 OR (p_action='receipt_recovery' AND(p_email IS NOT NULL OR p_phone IS NOT NULL)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.request_id<>p_reference OR prior.actor<>actor OR prior.action<>p_action OR prior.reason<>p_reason OR prior.previous_revision<>p_revision OR prior.verified_payment_id<>p_payment
  OR prior.new_email IS DISTINCT FROM p_email OR prior.new_phone IS DISTINCT FROM p_phone OR prior.code_digest<>p_digest THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','support_saved','revision',prior.revision,'expires_at',prior.expires_at,'active',prior.superseded_at IS NULL AND prior.redeemed_at IS NULL AND prior.attempts<5 AND prior.expires_at>clock_timestamp());
 END IF;
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 instant:=clock_timestamp();
 IF b.state='held' OR NOT EXISTS(SELECT 1 FROM appointment_system.payment_observations o JOIN appointment_system.payment_orders p ON p.booking_id=o.booking_id
 WHERE o.booking_id=b.id AND o.payment_id=p_payment AND o.merchant_id=p.merchant_id AND o.mode=p.mode AND o.provider_order_id=p.provider_order_id
 AND o.currency=b.currency AND o.amount_paise>0 AND(o.captured OR o.refunded_paise>0)) THEN RETURN jsonb_build_object('code','support_verification_unavailable');END IF;
 IF (SELECT count(*) FROM appointment_system.receipt_recoveries WHERE request_id=b.request_id AND created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','support_wait');END IF;
 IF p_action='contact_correction' AND(b.state<>'confirmed' OR b.starts_at<=instant OR (b.email=p_email AND b.phone=p_phone)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 new_revision:=b.revision+CASE WHEN p_action='contact_correction' THEN 1 ELSE 0 END;
 UPDATE appointment_system.receipt_recoveries SET superseded_at=instant WHERE request_id=b.request_id AND superseded_at IS NULL;
 INSERT INTO appointment_system.receipt_recoveries(operation_id,request_id,action,actor,reason,verified_payment_id,previous_revision,revision,previous_email,previous_phone,new_email,new_phone,code_digest)
 VALUES(p_operation,b.request_id,p_action,actor,p_reason,p_payment,b.revision,new_revision,CASE WHEN p_action='contact_correction' THEN b.email END,CASE WHEN p_action='contact_correction' THEN b.phone END,p_email,p_phone,p_digest) RETURNING * INTO prior;
 -- A verified support replacement invalidates old receipt access immediately.
 -- The new digest is installed only by the one-use customer redemption below.
 UPDATE appointment_system.bookings SET receipt_revoked_at=instant WHERE id=b.id;
 IF p_action='contact_correction' THEN
  old_snapshot:=appointment_system.booking_snapshot(b.id);
  UPDATE appointment_system.bookings SET email=p_email,phone=p_phone,revision=new_revision WHERE id=b.id;
  snapshot:=appointment_system.booking_snapshot(b.id);
  IF b.service_snapshot->>'meeting'='google_meet' THEN
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  END IF;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,new_revision,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar'))jobs(kind,role) WHERE kind<>'booking_calendar' OR b.service_snapshot->>'meeting'='google_meet';
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,new_revision,jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','contact_corrected') FROM(VALUES('customer'),('client'))roles(role);
 END IF;
 RETURN jsonb_build_object('code','support_saved','revision',new_revision,'expires_at',prior.expires_at,'active',true);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

RESET ROLE;
