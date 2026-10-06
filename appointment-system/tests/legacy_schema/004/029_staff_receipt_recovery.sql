-- Staff-attested callback verification. Recovery grants never enter links or provider messages.
CREATE TABLE sarsa_booking.receipt_recoveries (
 operation_id uuid PRIMARY KEY,
 request_id uuid NOT NULL REFERENCES sarsa_booking.bookings(request_id),
 action text NOT NULL CHECK(action IN ('receipt_recovery','contact_correction')),
 actor text NOT NULL,reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 2 AND 500),
 verified_payment_id text NOT NULL,
 verification_method text NOT NULL DEFAULT 'existing_phone_callback' CHECK(verification_method='existing_phone_callback'),
 previous_revision integer NOT NULL,revision integer NOT NULL,
 previous_email text,previous_phone text,new_email text,new_phone text,
 code_digest text NOT NULL CHECK(code_digest ~ '^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '15 minutes',
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 superseded_at timestamptz,redeemed_at timestamptz,redeemed_digest text CHECK(redeemed_digest ~ '^[a-f0-9]{64}$'),
 CHECK((redeemed_at IS NULL)=(redeemed_digest IS NULL))
);
CREATE INDEX receipt_recoveries_booking ON sarsa_booking.receipt_recoveries(request_id,created_at DESC);
REVOKE ALL ON sarsa_booking.receipt_recoveries FROM PUBLIC,sarsa_booking_runtime;
CREATE FUNCTION sarsa_booking.studio_support_change(p_session text,p_client text,p_origin text,p_operation uuid,p_reference uuid,p_revision integer,
 p_action text,p_reason text,p_payment text,p_email text,p_phone text,p_digest text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;prior sarsa_booking.receipt_recoveries%ROWTYPE;b sarsa_booking.bookings%ROWTYPE;context uuid;instant timestamptz;old_snapshot jsonb;snapshot jsonb;new_revision integer;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_reference IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_action IS NULL OR p_action NOT IN ('receipt_recovery','contact_correction') OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 OR p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR (p_action='contact_correction' AND(coalesce(length(p_email),0) NOT BETWEEN 3 AND 254 OR p_email ~ '[[:cntrl:]]' OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$'))
 OR (p_action='receipt_recovery' AND(p_email IS NOT NULL OR p_phone IS NOT NULL)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT context_id INTO context FROM sarsa_booking.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE request_id=p_reference FOR UPDATE;
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM sarsa_booking.receipt_recoveries WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.request_id<>p_reference OR prior.actor<>actor OR prior.action<>p_action OR prior.reason<>p_reason OR prior.previous_revision<>p_revision OR prior.verified_payment_id<>p_payment
  OR prior.new_email IS DISTINCT FROM p_email OR prior.new_phone IS DISTINCT FROM p_phone OR prior.code_digest<>p_digest THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','support_saved','revision',prior.revision,'expires_at',prior.expires_at,'active',prior.superseded_at IS NULL AND prior.redeemed_at IS NULL AND prior.attempts<5 AND prior.expires_at>clock_timestamp());
 END IF;
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 instant:=clock_timestamp();
 IF b.state='held' OR NOT EXISTS(SELECT 1 FROM sarsa_booking.payment_observations o JOIN sarsa_booking.payment_orders p ON p.booking_id=o.booking_id
 WHERE o.booking_id=b.id AND o.payment_id=p_payment AND o.merchant_id=p.merchant_id AND o.mode=p.mode AND o.provider_order_id=p.provider_order_id
 AND o.currency=b.currency AND o.amount_paise>0 AND(o.captured OR o.refunded_paise>0)) THEN RETURN jsonb_build_object('code','support_verification_unavailable');END IF;
 IF (SELECT count(*) FROM sarsa_booking.receipt_recoveries WHERE request_id=b.request_id AND created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','support_wait');END IF;
 IF p_action='contact_correction' AND(b.state<>'confirmed' OR b.starts_at<=instant OR (b.email=p_email AND b.phone=p_phone)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 new_revision:=b.revision+CASE WHEN p_action='contact_correction' THEN 1 ELSE 0 END;
 UPDATE sarsa_booking.receipt_recoveries SET superseded_at=instant WHERE request_id=b.request_id AND superseded_at IS NULL;
 INSERT INTO sarsa_booking.receipt_recoveries(operation_id,request_id,action,actor,reason,verified_payment_id,previous_revision,revision,previous_email,previous_phone,new_email,new_phone,code_digest)
 VALUES(p_operation,b.request_id,p_action,actor,p_reason,p_payment,b.revision,new_revision,CASE WHEN p_action='contact_correction' THEN b.email END,CASE WHEN p_action='contact_correction' THEN b.phone END,p_email,p_phone,p_digest) RETURNING * INTO prior;
 IF p_action='contact_correction' THEN
  old_snapshot:=jsonb_build_object('id',b.id,'revision',b.revision,'state',b.state,'service_snapshot',b.service_snapshot,'starts_at',b.starts_at,'ends_at',b.ends_at,'full_name',b.full_name,'email',b.email,'phone',b.phone,'amount_paise',b.amount_paise);
  snapshot:=old_snapshot||jsonb_build_object('revision',new_revision,'email',p_email,'phone',p_phone);
  UPDATE sarsa_booking.bookings SET email=p_email,phone=p_phone,revision=new_revision,receipt_revoked_at=instant WHERE id=b.id;
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot) ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,new_revision,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar'))jobs(kind,role);
  INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,new_revision,jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','contact_corrected') FROM(VALUES('customer'),('client'))roles(role);
 END IF;
 RETURN jsonb_build_object('code','support_saved','revision',new_revision,'expires_at',prior.expires_at,'active',true);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $$;
CREATE FUNCTION sarsa_booking.redeem_receipt_recovery(p_reference uuid,p_code text,p_receipt text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE context uuid;b sarsa_booking.bookings%ROWTYPE;r sarsa_booking.receipt_recoveries%ROWTYPE;
BEGIN
 IF p_reference IS NULL OR p_code IS NULL OR p_code !~ '^[a-f0-9]{64}$' OR p_receipt IS NULL OR p_receipt !~ '^[a-f0-9]{64}$' THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT context_id INTO context FROM sarsa_booking.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 PERFORM 1 FROM sarsa_booking.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE request_id=p_reference FOR UPDATE;
 SELECT * INTO r FROM sarsa_booking.receipt_recoveries WHERE request_id=p_reference AND superseded_at IS NULL ORDER BY created_at DESC,operation_id DESC LIMIT 1 FOR UPDATE;
 IF NOT FOUND OR r.expires_at<=clock_timestamp() OR r.attempts>=5 THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF r.code_digest<>p_code THEN
  UPDATE sarsa_booking.receipt_recoveries SET attempts=least(5,attempts+1) WHERE operation_id=r.operation_id;
  RETURN jsonb_build_object('code','access_unavailable');
 END IF;
 IF r.redeemed_at IS NOT NULL THEN
  IF r.redeemed_digest=p_receipt AND b.receipt_revoked_at IS NULL AND EXISTS(SELECT 1 FROM sarsa_booking.checkout_admissions WHERE request_id=p_reference AND receipt_digest=p_receipt)
  THEN RETURN jsonb_build_object('code','receipt_restored');END IF;
  RETURN jsonb_build_object('code','access_unavailable');
 END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.checkout_admissions WHERE request_id=p_reference AND receipt_digest=p_receipt) THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 -- A contact correction after issuance supersedes the grant. Other time changes are safe.
 UPDATE sarsa_booking.checkout_admissions SET receipt_digest=p_receipt WHERE request_id=p_reference;
 UPDATE sarsa_booking.bookings SET receipt_revoked_at=NULL,receipt_expires_at=greatest(ends_at+interval '24 hours',clock_timestamp()+interval '24 hours') WHERE id=b.id;
 UPDATE sarsa_booking.receipt_recoveries SET redeemed_digest=p_receipt,redeemed_at=clock_timestamp() WHERE operation_id=r.operation_id;
 RETURN jsonb_build_object('code','receipt_restored');
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text),sarsa_booking.redeem_receipt_recovery(uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text),sarsa_booking.redeem_receipt_recovery(uuid,text,text) TO sarsa_booking_runtime;
