-- Booking experience: one canonical email rule, versioned optional email,
-- practice-local DOB validation, stable code-policy bindings and conditional mail.
-- Earlier migration bytes and accepted booking/policy snapshots remain unchanged.
ALTER TABLE appointment_system.bookings ALTER COLUMN email DROP NOT NULL;
ALTER TABLE appointment_system.bookings DROP CONSTRAINT bookings_email_check;
ALTER TABLE appointment_system.bookings ADD CONSTRAINT bookings_email_check CHECK
 (email IS NULL OR (length(email) BETWEEN 3 AND 254
  AND email ~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$'));

CREATE OR REPLACE FUNCTION appointment_system.validate_business(p_spec jsonb) RETURNS boolean
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE item jsonb; other jsonb; windows jsonb; ids text[]:=ARRAY[]::text[];
 quantity integer; opening time; closing time;
BEGIN
 IF octet_length(p_spec::text)>131072 OR NOT appointment_system.exact_keys(p_spec,ARRAY[
  'version','timezone','services','weekly_windows','slot_step_minutes','notice_minutes',
  'horizon_days','buffer_before_minutes','buffer_after_minutes','booking_verification',
  'required_contacts','meeting','email_budget']) THEN RETURN false; END IF;
 IF p_spec->'version' IS DISTINCT FROM '1'::jsonb
  OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=p_spec->>'timezone')
  OR NOT appointment_system.bounded_integer(p_spec->'slot_step_minutes',5,120)
  OR (p_spec->>'slot_step_minutes')::integer%5<>0
  OR NOT appointment_system.bounded_integer(p_spec->'notice_minutes',0,10080)
  OR NOT appointment_system.bounded_integer(p_spec->'horizon_days',1,365)
  OR NOT appointment_system.bounded_integer(p_spec->'buffer_before_minutes',0,120)
  OR NOT appointment_system.bounded_integer(p_spec->'buffer_after_minutes',0,120)
  OR jsonb_typeof(p_spec->'meeting') IS DISTINCT FROM 'string'
  OR p_spec->>'meeting' NOT IN ('internal','google_meet')
  OR NOT appointment_system.exact_keys(p_spec->'booking_verification',ARRAY['email','sms'])
  OR jsonb_typeof(p_spec#>'{booking_verification,email}') IS DISTINCT FROM 'boolean'
  OR p_spec#>'{booking_verification,sms}' IS DISTINCT FROM 'false'::jsonb
  OR p_spec->'required_contacts' NOT IN ('[]'::jsonb,'["phone"]'::jsonb,'["email"]'::jsonb,'["email","phone"]'::jsonb,'["phone","email"]'::jsonb)
  OR (p_spec->'required_contacts' @> '["email"]'::jsonb) IS DISTINCT FROM (p_spec#>'{booking_verification,email}'='true'::jsonb)
  OR jsonb_typeof(p_spec->'services') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'services') NOT BETWEEN 1 AND 100
  OR jsonb_typeof(p_spec->'weekly_windows') IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_spec->'weekly_windows') NOT BETWEEN 1 AND 28
 THEN RETURN false; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_spec->'services') LOOP
  IF NOT appointment_system.exact_keys(item,ARRAY['id','name','enabled','duration_minutes','pricing','required_preparation'])
   OR jsonb_typeof(item->'id') IS DISTINCT FROM 'string'
   OR jsonb_typeof(item->'name') IS DISTINCT FROM 'string'
   OR coalesce(item->>'id','') !~ '^[a-z0-9][a-z0-9-]{0,79}$'
   OR item->>'id'=ANY(ids)
   OR coalesce(length(btrim(item->>'name')),0) NOT BETWEEN 1 AND 150
   OR item->>'name' ~ '[[:cntrl:]]'
   OR jsonb_typeof(item->'enabled') IS DISTINCT FROM 'boolean'
   OR NOT appointment_system.bounded_integer(item->'duration_minutes',5,480)
   OR (item->>'duration_minutes')::integer%5<>0
   OR NOT appointment_system.exact_keys(item->'pricing',ARRAY['kind','amount_paise','maximum_questions'])
   OR coalesce(item#>>'{pricing,kind}','') NOT IN ('fixed','per_question')
   OR NOT appointment_system.bounded_integer(item#>'{pricing,amount_paise}',1,2147483647)
   OR NOT appointment_system.bounded_integer(item#>'{pricing,maximum_questions}',1,10)
   OR ((item#>>'{pricing,amount_paise}')::bigint*(item#>>'{pricing,maximum_questions}')::bigint)>2147483647
   OR (item#>>'{pricing,kind}'='fixed' AND item#>'{pricing,maximum_questions}'<>'1'::jsonb)
   OR jsonb_typeof(item->'required_preparation') IS DISTINCT FROM 'array'
  THEN RETURN false; END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(item->'required_preparation') a
   WHERE jsonb_typeof(a) IS DISTINCT FROM 'string'
    OR a#>>'{}' NOT IN ('birth_date','birth_time','birth_place','notes'))
   OR (SELECT count(*) FROM jsonb_array_elements(item->'required_preparation')) <>
      (SELECT count(DISTINCT a) FROM jsonb_array_elements(item->'required_preparation') a)
  THEN RETURN false; END IF;
  ids:=array_append(ids,item->>'id');
 END LOOP;
 FOR item IN SELECT value FROM jsonb_array_elements(p_spec->'weekly_windows') LOOP
  IF NOT appointment_system.exact_keys(item,ARRAY['weekday','start','end'])
   OR NOT appointment_system.bounded_integer(item->'weekday',0,6)
   OR coalesce(item->>'start','') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
   OR coalesce(item->>'end','') !~ '^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$'
  THEN RETURN false; END IF;
  opening:=(item->>'start')::time; closing:=(item->>'end')::time;
  IF opening>=closing THEN RETURN false; END IF;
  FOR other IN SELECT value FROM jsonb_array_elements(p_spec->'weekly_windows') LOOP
   IF item<>other AND item->'weekday'=other->'weekday'
    AND (other->>'start') ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
    AND (other->>'end') ~ '^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$'
    AND opening<(other->>'end')::time AND (other->>'start')::time<closing
   THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 IF (SELECT count(*) FROM jsonb_array_elements(p_spec->'weekly_windows')) <>
    (SELECT count(DISTINCT w) FROM jsonb_array_elements(p_spec->'weekly_windows') w)
 THEN RETURN false; END IF;
 IF NOT appointment_system.exact_keys(p_spec->'email_budget',
  ARRAY['daily','rolling','verification_daily','verification_rolling'])
 THEN RETURN false; END IF;
 FOR item IN SELECT value FROM jsonb_each(p_spec->'email_budget') LOOP
  IF NOT appointment_system.bounded_integer(item,0,100000) THEN RETURN false; END IF;
 END LOOP;
 IF (p_spec#>>'{email_budget,daily}')::integer>(p_spec#>>'{email_budget,rolling}')::integer
  OR (p_spec#>>'{email_budget,verification_daily}')::integer>(p_spec#>>'{email_budget,daily}')::integer
  OR (p_spec#>>'{email_budget,verification_rolling}')::integer>(p_spec#>>'{email_budget,rolling}')::integer
  OR (p_spec#>>'{email_budget,verification_daily}')::integer>(p_spec#>>'{email_budget,verification_rolling}')::integer
 THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.entry_public_policy() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE spec jsonb; version text; browsing boolean;
BEGIN
 PERFORM appointment_system.control_admission(NULL);
 SELECT p.specification,p.version,s.schedule_browsing_open INTO spec,version,browsing FROM appointment_system.intake_settings s
 JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton FOR SHARE OF s;
 RETURN jsonb_build_object('policy',spec,'quote_version',version,'server_now',clock_timestamp(),
  'schedule_browsing_open',browsing,'booking_verification_policy_hash',appointment_system.verification_policy(spec));
END $$;

CREATE OR REPLACE FUNCTION appointment_system.entry_reserve_configured_checkout(p_context uuid, p_request uuid, p_receipt text, p_fingerprint text, p_input jsonb, p_expected jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE ctx appointment_system.checkout_contexts%ROWTYPE; admission appointment_system.checkout_admissions%ROWTYPE;
 settings appointment_system.intake_settings%ROWTYPE; spec jsonb; service jsonb; instant timestamptz:=clock_timestamp();
 starts timestamptz; offer record; identifier uuid; existing_id uuid; reason text; quantity integer;
 grant_row appointment_system.booking_verification_grants%ROWTYPE; preparation jsonb; birth_day date;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 SELECT * INTO settings FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
 SELECT specification INTO spec FROM appointment_system.booking_policies WHERE version=settings.policy_version;
 SELECT * INTO ctx FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND OR ctx.expires_at<=instant THEN RETURN jsonb_build_object('code','context_expired'); END IF;
 PERFORM appointment_system.control_admission(ctx.activation_epoch);
 SELECT * INTO admission FROM appointment_system.checkout_admissions WHERE request_id=p_request AND context_id=p_context;
 IF NOT FOUND OR admission.receipt_digest IS DISTINCT FROM p_receipt
  OR admission.request_fingerprint IS DISTINCT FROM p_fingerprint
  OR p_input->>'request_id' IS DISTINCT FROM p_request::text
  OR appointment_system.settings_digest(p_input) IS DISTINCT FROM p_fingerprint
 THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
 IF admission.outcome='committed' THEN
  SELECT id INTO existing_id FROM appointment_system.bookings WHERE request_id=p_request;
  RETURN jsonb_build_object('code','existing','booking_id',existing_id);
 END IF;
 IF admission.outcome<>'pending' THEN RETURN jsonb_build_object('code','request_rejected'); END IF;
 IF settings.policy_version IS DISTINCT FROM p_input->>'quote_version' THEN reason:='quote_changed';
 ELSIF p_expected IS NULL OR NOT settings.public_open OR p_expected IS DISTINCT FROM
  jsonb_build_object('merchant_id',settings.merchant_id,'mode',settings.payment_mode,'credential_version',settings.credential_version)
 THEN reason:='payment_not_configured';
 ELSIF NOT appointment_system.bounded_integer(coalesce(p_input->'questions','1'::jsonb),1,10)
 THEN reason:='invalid_details'; END IF;
 IF reason IS NULL THEN
  quantity:=coalesce((p_input->>'questions')::integer,1);
  service:=appointment_system.service_quote(spec,p_input->>'service_id',quantity);
  IF service IS NULL THEN reason:='service_unavailable'; END IF;
 END IF;
 IF reason IS NULL THEN
  IF coalesce(p_input->>'starts_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
  THEN reason:='invalid_time';
  ELSE
   BEGIN starts:=(p_input->>'starts_at')::timestamptz;
   EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN reason:='invalid_time'; END;
  END IF;
 END IF;
 IF reason IS NULL THEN
  SELECT * INTO offer FROM appointment_system.schedule_starts(spec,(service->>'duration_minutes')::integer,
   (starts AT TIME ZONE(spec->>'timezone'))::date,instant) WHERE starts_at=starts;
  IF NOT FOUND OR NOT isfinite(starts) THEN reason:='time_unavailable'; END IF;
 END IF;
 IF reason IS NULL THEN
  IF jsonb_typeof(p_input->'full_name') IS DISTINCT FROM 'string'
   OR coalesce(length(btrim(p_input->>'full_name')),0) NOT BETWEEN 2 AND 100
   OR p_input->>'full_name' ~ '[[:cntrl:]]'
   OR coalesce(p_input->'normalization_version','2'::jsonb) NOT IN ('1'::jsonb,'2'::jsonb,'3'::jsonb)
   OR (CASE WHEN p_input->>'email' IS NULL THEN
       p_input->'normalization_version' IS DISTINCT FROM '3'::jsonb
       OR spec#>'{booking_verification,email}' IS DISTINCT FROM 'false'::jsonb
       OR p_input->>'verification_grant' IS NOT NULL
      ELSE jsonb_typeof(p_input->'email') IS DISTINCT FROM 'string'
       OR p_input->>'email' !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$'
       OR length(p_input->>'email') NOT BETWEEN 3 AND 254 END)
   OR (spec->'required_contacts' @> '["phone"]'::jsonb AND coalesce(p_input->>'phone','') !~ '^\+[1-9][0-9]{6,14}$')
   OR (coalesce(p_input->>'phone','')<>'' AND p_input->>'phone' !~ '^\+[1-9][0-9]{6,14}$')
  THEN reason:='invalid_details'; END IF;
  IF reason IS NULL THEN
   IF p_input->>'birth_date' IS NOT NULL THEN
    IF jsonb_typeof(p_input->'birth_date') IS DISTINCT FROM 'string' OR p_input->>'birth_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN reason:='invalid_details';
    ELSE
     BEGIN
      birth_day:=(p_input->>'birth_date')::date;
      IF to_char(birth_day,'YYYY-MM-DD')<>p_input->>'birth_date' OR birth_day>(instant AT TIME ZONE(spec->>'timezone'))::date THEN reason:='invalid_details'; END IF;
     EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN reason:='invalid_details'; END;
    END IF;
   END IF;
   IF (p_input->'birth_time' IS NOT NULL AND jsonb_typeof(p_input->'birth_time') IS DISTINCT FROM 'string')
    OR coalesce(p_input->>'birth_time','') !~ '^(|([01][0-9]|2[0-3]):[0-5][0-9])$'
    OR (p_input->'birth_place' IS NOT NULL AND jsonb_typeof(p_input->'birth_place') IS DISTINCT FROM 'string')
    OR coalesce(length(p_input->>'birth_place'),0)>200
    OR (p_input->'notes' IS NOT NULL AND jsonb_typeof(p_input->'notes') IS DISTINCT FROM 'string')
    OR coalesce(length(p_input->>'notes'),0)>4000 THEN reason:='invalid_details'; END IF;
  END IF;
  preparation:=jsonb_build_object('birth_date',p_input->'birth_date','birth_time',p_input->'birth_time',
   'birth_place',p_input->'birth_place','notes',p_input->'notes');
  IF reason IS NULL AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(service->'required_preparation') field
   WHERE coalesce(length(btrim(p_input->>field)),0)=0)
  THEN reason:='preparation_required'; END IF;
 END IF;
 IF reason IS NULL AND spec#>'{booking_verification,email}'='true'::jsonb THEN
  SELECT * INTO grant_row FROM appointment_system.booking_verification_grants
  WHERE digest=p_input->>'verification_grant' AND context_id=p_context AND email=p_input->>'email'
   AND purpose='booking' AND policy_digest=appointment_system.verification_policy(spec)
   AND expires_at>instant AND consumed_request IS NULL AND revoked_at IS NULL;
  IF NOT FOUND THEN reason:='verification_required'; END IF;
 END IF;
 IF reason IS NOT NULL THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code',reason);
 END IF;
 -- Lock relevant expired bookings in sorted order before touching capacity.
 PERFORM appointment_system.lock_capacity_window(offer.occupied_start,offer.occupied_end);
 instant:=clock_timestamp();
 IF offer.starts_at<instant+make_interval(mins=>(spec->>'notice_minutes')::integer) THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END IF;
 IF spec#>'{booking_verification,email}'='true'::jsonb THEN
  SELECT * INTO grant_row FROM appointment_system.booking_verification_grants
   WHERE digest=p_input->>'verification_grant' AND context_id=p_context AND email=p_input->>'email'
    AND purpose='booking' AND policy_digest=appointment_system.verification_policy(spec)
    AND expires_at>instant AND consumed_request IS NULL AND revoked_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN
   UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
   RETURN jsonb_build_object('code','verification_required');
  END IF;
 END IF;
 PERFORM appointment_system.expire_relevant(offer.occupied_start,offer.occupied_end);
 IF ctx.active_checkout_id IS NOT NULL THEN
  -- Clear only this context's pointer after proving the old order is resolved.
  IF EXISTS(SELECT 1 FROM appointment_system.payment_orders WHERE booking_id=ctx.active_checkout_id AND resolved_at IS NOT NULL)
  THEN UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL WHERE id=p_context;
  ELSE
   UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
   RETURN jsonb_build_object('code','checkout_in_progress');
  END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE released_at IS NULL
  AND tstzrange(starts_at,ends_at,'[)')&&tstzrange(offer.occupied_start,offer.occupied_end,'[)'))
 THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END IF;
 identifier:=gen_random_uuid();
 BEGIN
  INSERT INTO appointment_system.bookings(id,request_id,context_id,state,service_id,policy_version,service_snapshot,
   amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,preparation,
   hold_expires_at,receipt_expires_at,created_at,original_starts_at,activation_epoch,receipt_format,receipt_key_id)
  VALUES(identifier,p_request,p_context,'held',service->>'id',settings.policy_version,service,
   (service->>'amount_paise')::bigint,'INR',offer.starts_at,offer.ends_at,spec->>'timezone',
   p_input->>'full_name',p_input->>'email',nullif(p_input->>'phone',''),preparation,
   least(offer.starts_at,instant+interval '10 minutes'),offer.ends_at+interval '24 hours',instant,
   offer.starts_at,ctx.activation_epoch,'v1',p_input#>>'{_receipt,key_id}');
  INSERT INTO appointment_system.slot_claims(id,booking_id,starts_at,ends_at)
  VALUES(gen_random_uuid(),identifier,offer.occupied_start,offer.occupied_end);
  INSERT INTO appointment_system.payment_orders(booking_id,merchant_id,mode,credential_version)
  VALUES(identifier,settings.merchant_id,settings.payment_mode,settings.credential_version);
  IF grant_row.digest IS NOT NULL THEN
   UPDATE appointment_system.booking_verification_grants SET consumed_request=p_request
   WHERE digest=grant_row.digest AND consumed_request IS NULL AND expires_at>clock_timestamp() AND revoked_at IS NULL;
   IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='verification changed'; END IF;
  END IF;
  UPDATE appointment_system.checkout_contexts SET active_checkout_id=identifier WHERE id=p_context;
  UPDATE appointment_system.checkout_admissions SET outcome='committed' WHERE request_id=p_request;
 EXCEPTION WHEN exclusion_violation THEN
  UPDATE appointment_system.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','time_unavailable');
 END;
 RETURN jsonb_build_object('code','reserved','booking_id',identifier);
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.start_booking_verification(p_context uuid, p_operation uuid, p_email text, p_digest text, p_cipher text, p_recipient text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;ctx jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;
 a appointment_system.booking_verification_actions%ROWTYPE;fingerprint text;instant timestamptz:=clock_timestamp();job uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 locked:=appointment_system.lock_booking_verification_context(p_context);
 IF locked->>'code'<>'ok' THEN RETURN locked; END IF;ctx:=locked->'context';
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_email IS NULL OR length(p_email) NOT BETWEEN 3 AND 254
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_recipient IS NULL OR p_recipient !~ '^[a-f0-9]{64}$'
  OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 OR p_key IS NULL OR p_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','start','context',p_context,'email',p_email));
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'start' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  IF a.result->>'code'<>'ok' OR a.result ? 'booking_verification_policy_hash' THEN RETURN a.result; END IF;
  SELECT * INTO c FROM appointment_system.booking_verification_challenges
   WHERE id=(a.result->>'challenge_id')::uuid AND context_id=p_context AND email=p_email;
  IF NOT FOUND THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
  RETURN a.result||jsonb_build_object('booking_verification_policy_hash',c.policy_digest);
 END IF;
 IF ctx->>'unresolved_booking_id' IS NOT NULL THEN RETURN jsonb_build_object('code','request_unresolved'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-recipient:'||p_recipient,0));
 IF (SELECT count(*) FROM appointment_system.booking_verification_mail m JOIN appointment_system.booking_verification_challenges x ON x.id=m.challenge_id
   WHERE x.recipient_hash=p_recipient AND m.created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=(ctx->>'verification_id')::uuid FOR UPDATE;
 IF FOUND AND c.verified_at IS NULL AND c.email=p_email AND c.policy_digest=locked->>'policy_digest' AND c.expires_at>instant AND c.attempts<5 THEN
  SELECT id INTO job FROM appointment_system.booking_verification_mail WHERE challenge_id=c.id AND generation=c.generation;
  result:=jsonb_build_object('code','ok','booking_verification_policy_hash',c.policy_digest,'challenge_id',c.id,'generation',c.generation,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 ELSE
  UPDATE appointment_system.booking_verification_grants SET revoked_at=instant WHERE context_id=p_context AND consumed_request IS NULL AND revoked_at IS NULL;
  IF c.id IS NOT NULL THEN
   UPDATE appointment_system.booking_verification_mail SET state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,code_ciphertext=NULL,message_ciphertext=NULL,
    lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_replaced' WHERE challenge_id=c.id;
   UPDATE appointment_system.booking_verification_challenges SET code_ciphertext=NULL WHERE id=c.id;
  END IF;
  INSERT INTO appointment_system.booking_verification_challenges(id,context_id,email,recipient_hash,policy_digest,activation_epoch,code_digest,code_ciphertext,digest_key_id,expires_at)
   VALUES(p_operation,p_context,p_email,p_recipient,locked->>'policy_digest',(ctx->>'activation_epoch')::uuid,p_digest,p_cipher,p_key,instant+interval '5 minutes') RETURNING * INTO c;
  INSERT INTO appointment_system.booking_verification_mail(challenge_id,context_id,generation,destination,code_ciphertext)
   VALUES(c.id,p_context,1,p_email,p_cipher) RETURNING id INTO job;
  UPDATE appointment_system.checkout_contexts SET verification_id=c.id WHERE id=p_context;
  result:=jsonb_build_object('code','ok','booking_verification_policy_hash',c.policy_digest,'challenge_id',c.id,'generation',1,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 END IF;
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'start',fingerprint,result);
 RETURN result;
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.resend_booking_verification(p_context uuid, p_operation uuid, p_challenge uuid, p_email text, p_generation integer, p_digest text, p_cipher text, p_key text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;a appointment_system.booking_verification_actions%ROWTYPE;
 fingerprint text;instant timestamptz:=clock_timestamp();job uuid;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 locked:=appointment_system.lock_booking_verification_context(p_context);IF locked->>'code'<>'ok' THEN RETURN locked; END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','resend','context',p_context,'challenge',p_challenge,'email',p_email,'generation',p_generation));
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_generation IS NULL OR p_generation NOT BETWEEN 1 AND 3
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192 OR p_key IS NULL OR p_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$'
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'resend' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;IF a.result->>'code'<>'ok' OR a.result ? 'booking_verification_policy_hash' THEN RETURN a.result; END IF;
  SELECT * INTO c FROM appointment_system.booking_verification_challenges
   WHERE id=p_challenge AND context_id=p_context AND email=p_email;
  IF NOT FOUND THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
  RETURN a.result||jsonb_build_object('booking_verification_policy_hash',c.policy_digest);
 END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=p_challenge AND context_id=p_context AND email=p_email FOR UPDATE;
 IF NOT FOUND OR (locked#>>'{context,verification_id}') IS DISTINCT FROM c.id::text OR c.policy_digest IS DISTINCT FROM locked->>'policy_digest' OR c.generation<>p_generation OR c.verified_at IS NOT NULL
 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF c.generation>=3 OR c.attempts>=5 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 IF c.last_code_at>instant-interval '60 seconds' THEN RETURN jsonb_build_object('code','please_wait'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-recipient:'||c.recipient_hash,0));
 IF (SELECT count(*) FROM appointment_system.booking_verification_mail m JOIN appointment_system.booking_verification_challenges x ON x.id=m.challenge_id
  WHERE x.recipient_hash=c.recipient_hash AND m.created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','verification_limit'); END IF;
 UPDATE appointment_system.booking_verification_mail SET state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,code_ciphertext=NULL,message_ciphertext=NULL,
  lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_replaced' WHERE challenge_id=c.id;
 UPDATE appointment_system.booking_verification_challenges SET generation=generation+1,attempts=0,code_digest=p_digest,code_ciphertext=p_cipher,digest_key_id=p_key,
  expires_at=instant+interval '5 minutes',last_code_at=instant WHERE id=c.id RETURNING * INTO c;
 INSERT INTO appointment_system.booking_verification_mail(challenge_id,context_id,generation,destination,code_ciphertext) VALUES(c.id,p_context,c.generation,p_email,p_cipher) RETURNING id INTO job;
 result:=jsonb_build_object('code','ok','booking_verification_policy_hash',c.policy_digest,'challenge_id',c.id,'generation',c.generation,'expires_at',c.expires_at,'state','awaiting_verification','mail_job_id',job);
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'resend',fingerprint,result);
 RETURN result;
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.verify_booking_code(p_context uuid, p_operation uuid, p_challenge uuid, p_email text, p_generation integer, p_digest text, p_grant text, p_cipher text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE locked jsonb;c appointment_system.booking_verification_challenges%ROWTYPE;a appointment_system.booking_verification_actions%ROWTYPE;
 fingerprint text;instant timestamptz:=clock_timestamp();expiry timestamptz;result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);locked:=appointment_system.lock_booking_verification_context(p_context);
 IF locked->>'code'<>'ok' THEN RETURN locked; END IF;
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_generation IS NULL OR p_generation NOT BETWEEN 1 AND 3
  OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' OR p_grant IS NULL OR p_grant !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR length(p_cipher) NOT BETWEEN 100 AND 8192
 THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 fingerprint:=appointment_system.settings_digest(jsonb_build_object('action','verify','context',p_context,'challenge',p_challenge,'email',p_email,'generation',p_generation,'code_digest',p_digest));
 PERFORM pg_advisory_xact_lock(hashtextextended('booking-verification-operation:'||p_operation::text,0));
 SELECT * INTO a FROM appointment_system.booking_verification_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF a.context_id<>p_context OR a.action<>'verify' OR a.input_digest<>fingerprint THEN RETURN jsonb_build_object('code','request_conflict'); END IF;IF a.result->>'code'<>'ok' OR a.result ? 'booking_verification_policy_hash' THEN RETURN a.result; END IF;
  SELECT * INTO c FROM appointment_system.booking_verification_challenges
   WHERE id=p_challenge AND context_id=p_context AND email=p_email;
  IF NOT FOUND THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
  RETURN a.result||jsonb_build_object('booking_verification_policy_hash',c.policy_digest);
 END IF;
 SELECT * INTO c FROM appointment_system.booking_verification_challenges WHERE id=p_challenge AND context_id=p_context AND email=p_email FOR UPDATE;
 IF NOT FOUND OR c.id::text IS DISTINCT FROM locked#>>'{context,verification_id}' OR c.policy_digest IS DISTINCT FROM locked->>'policy_digest' OR c.generation<>p_generation OR c.verified_at IS NOT NULL
 THEN RETURN jsonb_build_object('code','verification_changed'); END IF;
 IF c.expires_at<=instant THEN result:=jsonb_build_object('code','verification_expired');
 ELSIF c.attempts>=5 THEN result:=jsonb_build_object('code','verification_locked');
 ELSIF c.code_digest IS DISTINCT FROM p_digest THEN
  UPDATE appointment_system.booking_verification_challenges SET attempts=attempts+1 WHERE id=c.id;
  result:=jsonb_build_object('code','verification_incorrect');
 ELSE
  expiry:=least((locked#>>'{context,expires_at}')::timestamptz,instant+interval '30 minutes');
  INSERT INTO appointment_system.booking_verification_grants(digest,context_id,email,purpose,policy_digest,expires_at) VALUES(p_grant,p_context,p_email,'booking',c.policy_digest,expiry);
  UPDATE appointment_system.booking_verification_challenges SET verified_at=instant,grant_digest=p_grant,code_ciphertext=NULL WHERE id=c.id;
  UPDATE appointment_system.booking_verification_mail SET code_ciphertext=NULL,message_ciphertext=NULL,state=CASE WHEN state='completed' THEN state ELSE 'suppressed' END,
   lease_token=NULL,lease_expires_at=NULL,last_error_code='verification_completed' WHERE challenge_id=c.id;
  result:=jsonb_build_object('code','ok','booking_verification_policy_hash',c.policy_digest,'state','verified','grant_ciphertext',p_cipher,'expires_at',expiry);
 END IF;
 INSERT INTO appointment_system.booking_verification_actions(operation_id,context_id,action,input_digest,result) VALUES(p_operation,p_context,'verify',fingerprint,result);
 RETURN result;
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.entry_observe_payment(p_context uuid, p_booking uuid, p_merchant text, p_mode text, p_version text, p_payment text, p_order text, p_hash text, p_status text, p_amount bigint, p_currency text, p_refunded bigint, p_captured boolean) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE booking appointment_system.bookings%ROWTYPE;
        payment appointment_system.payment_orders%ROWTYPE;
        accepted appointment_system.accepted_payments%ROWTYPE;
        observation uuid; reason text; financial_event_key text;
BEGIN
    PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
    PERFORM 1 FROM appointment_system.intake_settings WHERE singleton FOR SHARE;
    PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    SELECT * INTO booking FROM appointment_system.bookings WHERE id=p_booking AND context_id=p_context FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout ownership mismatch'; END IF;
    PERFORM 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking ORDER BY id FOR UPDATE;
    SELECT * INTO payment FROM appointment_system.payment_orders WHERE booking_id=p_booking FOR UPDATE;
    IF NOT FOUND OR payment.merchant_id IS DISTINCT FROM p_merchant
       OR payment.mode IS DISTINCT FROM p_mode OR payment.credential_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='payment identity mismatch';
    END IF;
    IF p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$'
       OR p_order IS NULL OR p_order !~ '^order_[A-Za-z0-9]{1,64}$'
       OR p_status IS NULL OR p_status NOT IN ('created','authorized','captured','refunded','failed')
       OR p_captured IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid payment evidence';
    END IF;
    INSERT INTO appointment_system.payment_observations(
        id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,
        amount_paise,currency,refunded_paise,captured
    ) VALUES(gen_random_uuid(),p_booking,p_merchant,p_mode,p_payment,p_order,p_hash,p_status,
             p_amount,p_currency,p_refunded,p_captured)
    ON CONFLICT(merchant_id,mode,payment_id,evidence_hash) DO NOTHING;
    SELECT id INTO observation FROM appointment_system.payment_observations
      WHERE booking_id=p_booking AND merchant_id=p_merchant AND mode=p_mode
        AND payment_id=p_payment AND evidence_hash=p_hash;
    IF observation IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='payment evidence belongs to another booking';
    END IF;
    -- Uncaptured attempts are recorded, but cannot resolve the entire order.
    IF p_status NOT IN ('captured','refunded') AND NOT p_captured AND p_refunded=0 THEN RETURN 'observed'; END IF;
    SELECT * INTO accepted FROM appointment_system.accepted_payments WHERE booking_id=p_booking;
    IF p_order IS DISTINCT FROM payment.provider_order_id OR p_amount <> booking.amount_paise
       OR p_currency <> booking.currency THEN reason := 'payment_mismatch';
    ELSIF p_refunded > 0 OR p_status='refunded' THEN reason := 'refund_observed';
    ELSIF p_status <> 'captured' OR NOT p_captured THEN reason := 'capture_inconsistent';
    ELSIF accepted.payment_id=p_payment AND booking.state IN ('confirmed','cancelled') THEN
        RETURN CASE WHEN booking.state='confirmed' THEN 'confirmed' ELSE 'observed' END;
    ELSIF accepted.payment_id IS NOT NULL THEN reason := 'additional_payment';
    ELSIF EXISTS(SELECT 1 FROM appointment_system.accepted_payments
        WHERE merchant_id=p_merchant AND mode=p_mode AND payment_id=p_payment) THEN reason := 'payment_already_assigned';
    ELSIF NOT EXISTS(SELECT 1 FROM appointment_system.control_product_state WHERE singleton AND enabled
        AND activation_epoch=booking.activation_epoch) THEN reason := 'booking_disabled';
    ELSIF booking.state <> 'held' OR booking.hold_expires_at <= clock_timestamp()
       OR payment.resolved_at IS NOT NULL THEN reason := 'late_payment';
    ELSIF NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE booking_id=p_booking
        AND released_at IS NULL AND starts_at<=booking.starts_at AND ends_at>=booking.ends_at) THEN reason := 'claim_missing';
    END IF;
    IF reason IS NOT NULL THEN
        financial_event_key := p_payment||':'||reason;
        INSERT INTO appointment_system.payment_cases(id,booking_id,event_key,reason)
          VALUES(gen_random_uuid(),p_booking,financial_event_key,reason)
          ON CONFLICT(booking_id,event_key) DO NOTHING;
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
          VALUES(gen_random_uuid(),p_booking,'payment_review','client',booking.revision,financial_event_key)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        IF booking.state IN ('held','expired') THEN
            UPDATE appointment_system.bookings SET state='payment_review' WHERE id=p_booking;
            UPDATE appointment_system.slot_claims SET released_at=clock_timestamp()
              WHERE booking_id=p_booking AND released_at IS NULL;
        END IF;
        RETURN 'payment_needs_review';
    END IF;
    INSERT INTO appointment_system.accepted_payments(booking_id,observation_id,merchant_id,mode,payment_id)
      VALUES(p_booking,observation,p_merchant,p_mode,p_payment);
    UPDATE appointment_system.bookings SET state='confirmed' WHERE id=p_booking;
    UPDATE appointment_system.payment_orders SET resolution='confirmed',resolved_at=clock_timestamp(),recovery_followup=true,next_check_at=clock_timestamp()
      WHERE booking_id=p_booking;
    UPDATE appointment_system.checkout_contexts SET active_checkout_id=NULL
      WHERE id=p_context AND active_checkout_id=p_booking;
    INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
      SELECT gen_random_uuid(),p_booking,kind,role,booking.revision
      FROM (VALUES ('booking_ack','customer'),('booking_ack','client'),('booking_calendar','calendar'),
                   ('sheet_booking','client_sheet'),('sheet_booking','agency_sheet')) jobs(kind,role)
      WHERE (kind<>'booking_calendar' OR booking.service_snapshot->>'meeting'='google_meet')
       AND (role<>'customer' OR booking.email IS NOT NULL)
      ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
    RETURN 'confirmed';
END
$_$;

CREATE OR REPLACE FUNCTION appointment_system.entry_finish_google_delivery(p_job uuid, p_lease uuid, p_state text, p_provider text, p_meet text, p_error text, p_delay integer) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE; booking uuid; stale boolean; expected_event text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
    IF p_state IS NULL OR p_state NOT IN ('done','waiting','failed','attention','obsolete') OR p_delay IS NULL OR p_delay NOT BETWEEN 15 AND 3600
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN RETURN false; END IF;
    SELECT booking_id INTO booking FROM appointment_system.delivery_jobs WHERE id=p_job;
    SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR SHARE;
    IF NOT FOUND THEN RETURN false; END IF;
    SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=p_job FOR UPDATE;
    IF NOT FOUND OR j.lease_token IS DISTINCT FROM p_lease OR p_lease IS NULL OR j.state<>'processing'
       OR j.lease_expires_at<=clock_timestamp() OR NOT appointment_system.transport_claim_current(to_jsonb(j)) THEN RETURN false; END IF;
    IF j.kind NOT IN ('booking_calendar','sheet_booking') AND NOT(j.kind='booking_cancelled' AND j.recipient_role='calendar') THEN RETURN false; END IF;
    stale:=b.state<>'confirmed' OR b.revision<>j.booking_revision;
    IF p_state='obsolete' THEN
      IF j.kind<>'booking_calendar' OR NOT stale THEN RETURN false; END IF;
      UPDATE appointment_system.meeting_events SET state='cancelled',meet_url=NULL WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    ELSIF j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN
      expected_event:=appointment_system.calendar_event_identity(b.id,j.booking_revision,b.calendar_protocol);
      IF p_provider IS DISTINCT FROM expected_event THEN RETURN false; END IF;
      INSERT INTO appointment_system.meeting_events(booking_id,booking_revision,event_id,state,meet_url)
        VALUES(b.id,j.booking_revision,p_provider,CASE WHEN p_state='done' THEN 'ready' ELSE 'waiting' END,p_meet)
        ON CONFLICT(booking_id,booking_revision) DO UPDATE SET state=excluded.state,meet_url=excluded.meet_url;
      IF stale THEN
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
          VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',j.booking_revision,j.payload)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO UPDATE
          SET state='pending',next_attempt_at=clock_timestamp(),lease_token=NULL,lease_expires_at=NULL;
      ELSIF p_state='done' THEN
        INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key,payload) SELECT gen_random_uuid(),b.id,'sheet_booking',destination,j.booking_revision,'meeting-ready',appointment_system.booking_snapshot(b.id) FROM unnest(ARRAY['client_sheet','agency_sheet'])destination ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        IF b.email IS NOT NULL THEN
         INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
          VALUES(gen_random_uuid(),b.id,'booking_details','customer',j.booking_revision)
          ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
        END IF;
      END IF;
    ELSIF j.kind='booking_cancelled' AND p_state='done' THEN
      UPDATE appointment_system.meeting_events SET state='cancelled',meet_url=NULL
        WHERE booking_id=b.id AND booking_revision=j.booking_revision;
    END IF;
    UPDATE appointment_system.delivery_jobs SET state=CASE WHEN p_state='obsolete' THEN 'suppressed' WHEN stale AND j.kind='booking_calendar' AND p_state IN ('done','waiting') THEN 'suppressed'
      WHEN p_state='done' THEN 'completed' WHEN p_state='attention' THEN 'needs_review' WHEN p_state='waiting' THEN 'retry_wait' ELSE 'retry_wait' END,
      provider_id=coalesce(p_provider,provider_id),last_error_code=p_error,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
    RETURN true;
END
$_$;

CREATE OR REPLACE FUNCTION appointment_system.entry_studio_appointment_cancel(p_session text, p_client text, p_origin text, p_operation uuid, p_claim uuid, p_revision integer, p_reason text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE actor text;old appointment_system.staff_appointment_actions%ROWTYPE;b appointment_system.bookings%ROWTYPE;
 booking uuid;context uuid;instant timestamptz;guidance text;snapshot jsonb;old_snapshot jsonb;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_claim IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('staff-appointment-operation:'||p_operation::text,0));
 SELECT s.booking_id,bk.context_id INTO booking,context FROM appointment_system.slot_claims s JOIN appointment_system.bookings bk ON bk.id=s.booking_id WHERE s.id=p_claim;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO old FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation;
 IF FOUND THEN
  IF old.action<>'cancel' OR old.actor IS DISTINCT FROM actor OR old.claim_id IS DISTINCT FROM p_claim OR old.previous_revision IS DISTINCT FROM p_revision OR old.reason IS DISTINCT FROM p_reason THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','cancelled','revision',old.revision,'policy_guidance',old.policy_guidance);
 END IF;
 SELECT * INTO b FROM appointment_system.bookings WHERE id=booking FOR UPDATE;
 instant:=clock_timestamp();
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 IF b.state<>'confirmed' OR b.starts_at<=instant OR NOT EXISTS(SELECT 1 FROM appointment_system.slot_claims WHERE id=p_claim AND released_at IS NULL) THEN RETURN jsonb_build_object('code','appointment_unavailable'); END IF;
 guidance:=CASE WHEN EXISTS(SELECT 1 FROM appointment_system.staff_appointment_actions WHERE booking_id=b.id AND action='reschedule') THEN 'staff_review' WHEN b.starts_at>=instant+interval '24 hours' THEN 'full_refund_review' WHEN b.starts_at>=instant+interval '12 hours' THEN 'staff_review' ELSE 'late_reschedule_review' END;
 old_snapshot:=appointment_system.booking_snapshot(b.id);
 snapshot:=old_snapshot||jsonb_build_object('revision',b.revision+1,'state','cancelled','cancelled_at',instant);
 INSERT INTO appointment_system.staff_appointment_actions(operation_id,claim_id,booking_id,action,actor,reason,previous_revision,revision,starts_at,notice_seconds,policy_guidance)
 VALUES(p_operation,p_claim,b.id,'cancel',actor,p_reason,b.revision,b.revision+1,b.starts_at,floor(extract(epoch FROM b.starts_at-instant))::bigint,guidance);
 UPDATE appointment_system.bookings SET state='cancelled',cancelled_at=instant,revision=revision+1 WHERE id=b.id;
 UPDATE appointment_system.slot_claims SET released_at=instant WHERE id=p_claim;
 -- Never erase accepted evidence or revoke an in-flight completion lease.
 UPDATE appointment_system.delivery_jobs SET state='suppressed',last_error_code='appointment_cancelled'
 WHERE booking_id=b.id AND booking_revision=b.revision AND kind IN ('booking_ack','booking_details','booking_calendar')
 AND state IN ('pending','retry_wait') AND first_attempt_at IS NULL AND payload IS NULL AND provider_id IS NULL AND lease_token IS NULL;
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 SELECT gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot
 WHERE b.service_snapshot->>'meeting'='google_meet'
 ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
 SELECT gen_random_uuid(),b.id,'sheet_booking',role,b.revision+1,snapshot FROM (VALUES('client_sheet'),('agency_sheet')) roles(role);
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision)
 SELECT gen_random_uuid(),b.id,'booking_cancelled',role,b.revision+1 FROM (VALUES('customer'),('client')) roles(role) WHERE role<>'customer' OR b.email IS NOT NULL;
 RETURN jsonb_build_object('code','cancelled','revision',b.revision+1,'policy_guidance',guidance);
END $$;

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
  SELECT gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot
 WHERE b.service_snapshot->>'meeting'='google_meet' ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,kind,role,b.revision+1,snapshot FROM(VALUES('sheet_booking','client_sheet'),('sheet_booking','agency_sheet'),('booking_calendar','calendar')) jobs(kind,role) WHERE kind<>'booking_calendar' OR b.service_snapshot->>'meeting'='google_meet';
  INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,payload)
  SELECT gen_random_uuid(),b.id,'booking_ack',role,b.revision+1,jsonb_build_object('booking_id',b.id,'reference',b.request_id,
  'service',b.service_snapshot->>'name','starts_at',p_start,'ends_at',new_end,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','rescheduled') FROM(VALUES('customer'),('client')) roles(role) WHERE role<>'customer' OR b.email IS NOT NULL;
 EXCEPTION WHEN exclusion_violation THEN RETURN jsonb_build_object('code','time_already_reserved');END;
 RETURN jsonb_build_object('code','rescheduled','revision',b.revision+1,'starts_at',p_start,'ends_at',new_end);
END $$;

CREATE OR REPLACE FUNCTION appointment_system.entry_studio_support_change(p_session text, p_client text, p_origin text, p_operation uuid, p_reference uuid, p_revision integer, p_action text, p_reason text, p_payment text, p_email text, p_phone text, p_digest text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.receipt_recoveries%ROWTYPE;b appointment_system.bookings%ROWTYPE;context uuid;instant timestamptz;old_snapshot jsonb;snapshot jsonb;new_revision integer; frozen_email_required boolean;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_reference IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_action IS NULL OR p_action NOT IN ('receipt_recovery','contact_correction') OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 OR p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR (p_action='contact_correction' AND((p_email IS NOT NULL AND (length(p_email) NOT BETWEEN 3 AND 254 OR p_email ~ '[[:cntrl:]]' OR p_email !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$')) OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$'))
 OR (p_action='receipt_recovery' AND(p_email IS NOT NULL OR p_phone IS NOT NULL)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.request_id<>p_reference OR prior.actor<>actor OR prior.action<>p_action OR prior.reason<>p_reason OR prior.previous_revision<>p_revision OR prior.verified_payment_id IS DISTINCT FROM p_payment
  OR prior.new_email IS DISTINCT FROM p_email OR prior.new_phone IS DISTINCT FROM p_phone OR prior.code_digest<>p_digest THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','support_saved','revision',prior.revision,'expires_at',prior.expires_at,'active',prior.superseded_at IS NULL AND prior.redeemed_at IS NULL AND prior.attempts<5 AND prior.expires_at>clock_timestamp());
 END IF;
 IF p_action='contact_correction' THEN
  SELECT (specification#>>'{booking_verification,email}')::boolean INTO frozen_email_required
   FROM appointment_system.booking_policies WHERE version=b.policy_version;
  IF frozen_email_required IS NULL OR (frozen_email_required AND p_email IS NULL) THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 END IF;
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 instant:=clock_timestamp();
 IF b.state='held' OR NOT EXISTS(SELECT 1 FROM appointment_system.payment_observations o JOIN appointment_system.payment_orders p ON p.booking_id=o.booking_id
 WHERE o.booking_id=b.id AND o.payment_id=p_payment AND o.merchant_id=p.merchant_id AND o.mode=p.mode AND o.provider_order_id=p.provider_order_id
 AND o.currency=b.currency AND o.amount_paise>0 AND(o.captured OR o.refunded_paise>0)) THEN RETURN jsonb_build_object('code','support_verification_unavailable');END IF;
 IF (SELECT count(*) FROM appointment_system.receipt_recoveries WHERE request_id=b.request_id AND created_at>instant-interval '1 hour')>=3 THEN RETURN jsonb_build_object('code','support_wait');END IF;
 IF p_action='contact_correction' AND(b.state<>'confirmed' OR b.starts_at<=instant OR (b.email IS NOT DISTINCT FROM p_email AND b.phone IS NOT DISTINCT FROM p_phone)) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
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
  SELECT gen_random_uuid(),b.id,'booking_ack',role,new_revision,jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'change_kind','contact_corrected') FROM(VALUES('customer'),('client'))roles(role) WHERE role<>'customer' OR p_email IS NOT NULL;
 END IF;
 RETURN jsonb_build_object('code','support_saved','revision',new_revision,'expires_at',prior.expires_at,'active',true);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

CREATE OR REPLACE FUNCTION appointment_system.entry_studio_booking_lookup(p_session text, p_client text, p_origin text, p_reference uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE b appointment_system.bookings%ROWTYPE;result jsonb;
BEGIN
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 SELECT jsonb_build_object('code','ok','reference',b.request_id,'revision',b.revision,'state',b.state,'name',b.full_name,'email',b.email,'phone',b.phone,'contact_email_required',(SELECT (specification#>>'{booking_verification,email}')::boolean FROM appointment_system.booking_policies WHERE version=b.policy_version),
 'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,
 'claim_id',(SELECT id FROM appointment_system.slot_claims WHERE booking_id=b.id),
 'unresolved_payments',(SELECT count(*) FROM appointment_system.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL),
 'payments',coalesce((SELECT jsonb_agg(x ORDER BY x.observed_at DESC,x.id DESC) FROM (SELECT id,payment_id,status,amount_paise,refunded_paise,currency,captured,observed_at FROM appointment_system.payment_observations WHERE booking_id=b.id ORDER BY observed_at DESC,id DESC LIMIT 20)x),'[]'::jsonb)) INTO result;
 RETURN result;
END $$;

-- A receipt copy uses the existing durable notification lane and provider evidence.
ALTER TABLE appointment_system.delivery_jobs ADD COLUMN receipt_copy_request jsonb;
ALTER TABLE appointment_system.delivery_jobs ADD CONSTRAINT receipt_copy_metadata_check CHECK (
 ((kind='booking_receipt')=(receipt_copy_request IS NOT NULL) AND
  (receipt_copy_request IS NULL OR (
   appointment_system.exact_keys(receipt_copy_request,ARRAY['version','operation_id','expected_revision','input_fingerprint','accepted_at'])
   AND receipt_copy_request->'version'='1'::jsonb
   AND receipt_copy_request->>'operation_id' ~ '^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$'
   AND receipt_copy_request->>'operation_id'<>'00000000-0000-0000-0000-000000000000'
   AND appointment_system.bounded_integer(receipt_copy_request->'expected_revision',1,2147483647)
   AND (receipt_copy_request->>'expected_revision')::integer=booking_revision
   AND receipt_copy_request->>'input_fingerprint' ~ '^[a-f0-9]{64}$'
   AND receipt_copy_request->>'accepted_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
   AND event_key='receipt:'||(receipt_copy_request->>'operation_id')
   AND recipient_role='customer' AND destination IS NOT NULL AND send_deadline_at IS NOT NULL
   AND send_deadline_at>(receipt_copy_request->>'accepted_at')::timestamptz
   AND send_deadline_at<=(receipt_copy_request->>'accepted_at')::timestamptz+interval '23 hours'))) IS TRUE);
CREATE UNIQUE INDEX receipt_copy_operation_identity ON appointment_system.delivery_jobs(booking_id,event_key)
 WHERE kind='booking_receipt' AND recipient_role='customer';

CREATE FUNCTION appointment_system.receipt_copy_state(p_booking uuid,p_operation uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE b appointment_system.bookings%ROWTYPE;j appointment_system.delivery_jobs%ROWTYPE;
 used integer; instant timestamptz:=clock_timestamp(); next_at timestamptz; public_state text:='not_requested';
 reason text; pending boolean; uncertain boolean;
BEGIN
 SELECT * INTO b FROM appointment_system.bookings WHERE id=p_booking;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND kind='booking_receipt'
  AND (p_operation IS NULL OR event_key='receipt:'||p_operation::text)
  ORDER BY receipt_copy_request->>'accepted_at' DESC,id DESC LIMIT 1;
 SELECT count(*),max((receipt_copy_request->>'accepted_at')::timestamptz)+interval '60 seconds' INTO used,next_at
  FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND kind='booking_receipt'
   AND (receipt_copy_request->>'accepted_at')::timestamptz>instant-interval '24 hours';
 SELECT coalesce(bool_or(state IN ('pending','processing','retry_wait','delivery_unknown') AND provider_id IS NULL
  AND NOT(first_attempt_at IS NULL AND (booking_revision<>b.revision OR b.state<>'confirmed' OR send_deadline_at<=instant))),false),
  coalesce(bool_or(send_uncertain AND provider_id IS NULL AND state IN ('delivery_unknown','needs_review')),false)
  INTO pending,uncertain FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND kind='booking_receipt';
 IF j.id IS NOT NULL THEN
  public_state:=appointment_system.email_delivery_state(j.id);
  public_state:=CASE
   WHEN public_state='delivered' THEN 'delivered'
   WHEN public_state='accepted' THEN 'provider_accepted'
   WHEN j.provider_id IS NOT NULL AND public_state NOT IN ('failed','bounced','complained','suppressed') THEN 'provider_accepted'
   WHEN j.first_attempt_at IS NULL AND NOT j.send_uncertain AND (j.booking_revision<>b.revision OR b.state<>'confirmed') THEN 'superseded'
   WHEN j.first_attempt_at IS NULL AND j.send_deadline_at<=instant THEN 'needs_attention'
   WHEN public_state='processing' THEN 'processing'
   WHEN public_state IN ('pending','retry_wait') THEN 'pending'
   ELSE 'needs_attention' END;
 END IF;
 reason:=CASE WHEN b.state<>'confirmed' OR b.receipt_revoked_at IS NOT NULL OR b.receipt_expires_at<=instant THEN 'booking_unavailable'
  WHEN uncertain THEN 'delivery_unknown' WHEN pending THEN 'delivery_pending'
  WHEN b.email IS NOT NULL AND appointment_system.email_recipient_suppressed(b.email) THEN 'destination_unavailable'
  WHEN NOT EXISTS(SELECT 1 FROM appointment_system.email_policy WHERE id)
   OR NOT EXISTS(SELECT 1 FROM appointment_system.mail_connection WHERE singleton AND active_key_id=ANY(retained_keys))
   OR coalesce(appointment_system.installation_value('sender.formatted'),'')='' THEN 'copy_unavailable'
  WHEN used>=3 THEN 'quota' WHEN next_at>instant THEN 'cooldown' ELSE NULL END;
 IF used>=3 THEN SELECT min((receipt_copy_request->>'accepted_at')::timestamptz)+interval '24 hours' INTO next_at
  FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND kind='booking_receipt'
   AND (receipt_copy_request->>'accepted_at')::timestamptz>instant-interval '24 hours'; END IF;
 RETURN jsonb_build_object('operation_id',j.receipt_copy_request->>'operation_id','booking_revision',j.booking_revision,
  'state',public_state,'has_booking_email',b.email IS NOT NULL,
  'target_hint',CASE WHEN j.destination IS NOT NULL THEN left(left(split_part(j.destination,'@',1),1)||'***@'||split_part(j.destination,'@',2),254) ELSE NULL END,
  'next_request_at',CASE WHEN next_at>instant THEN next_at ELSE NULL END,'remaining_requests',greatest(0,3-used),
  'can_request',reason IS NULL,'blocked_reason',reason);
END $$;

CREATE FUNCTION appointment_system.entry_request_receipt_copy(p_request uuid,p_receipt text,p_operation uuid,p_revision integer,p_input jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE b appointment_system.bookings%ROWTYPE;admission appointment_system.checkout_admissions%ROWTYPE;
 j appointment_system.delivery_jobs%ROWTYPE; target text; digest text; copy_state jsonb; instant timestamptz:=clock_timestamp();
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.control_admission(NULL);
 IF p_operation IS NULL OR p_operation='00000000-0000-0000-0000-000000000000' OR p_revision IS NULL OR p_revision NOT BETWEEN 1 AND 2147483647
  OR NOT appointment_system.exact_keys(p_input,ARRAY['email','sending_ready']) OR jsonb_typeof(p_input->'sending_ready') IS DISTINCT FROM 'boolean'
  OR (p_input->>'email' IS NOT NULL AND (jsonb_typeof(p_input->'email') IS DISTINCT FROM 'string' OR length(p_input->>'email') NOT BETWEEN 3 AND 254
   OR p_input->>'email' !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$')) THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_request FOR UPDATE;
 IF NOT FOUND OR b.receipt_revoked_at IS NOT NULL OR b.receipt_expires_at<=instant THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO admission FROM appointment_system.checkout_admissions WHERE request_id=b.request_id;
 IF admission.receipt_digest IS DISTINCT FROM p_receipt THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 digest:=appointment_system.settings_digest(jsonb_build_object('version',1,'request_id',p_request,'operation_id',p_operation,'expected_revision',p_revision,'email',p_input->'email'));
 SELECT * INTO j FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND event_key='receipt:'||p_operation::text AND kind='booking_receipt' FOR UPDATE;
 IF FOUND THEN
  IF j.receipt_copy_request->>'input_fingerprint' IS DISTINCT FROM digest THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','receipt_copy_accepted','replayed',true,'request_id',b.request_id,'operation_id',p_operation,
   'booking_revision',j.booking_revision,'email_copy',appointment_system.receipt_copy_state(b.id,p_operation));
 END IF;
 IF b.state<>'confirmed' THEN RETURN jsonb_build_object('code','booking_not_confirmed'); END IF;
 IF b.revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 IF b.email IS NOT NULL AND p_input->>'email' IS NOT NULL AND p_input->>'email' IS DISTINCT FROM b.email THEN RETURN jsonb_build_object('code','email_destination_conflict'); END IF;
 target:=coalesce(b.email,p_input->>'email');
 IF target IS NULL THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 IF p_input->'sending_ready' IS DISTINCT FROM 'true'::jsonb OR NOT EXISTS(SELECT 1 FROM appointment_system.email_policy WHERE id)
  OR NOT EXISTS(SELECT 1 FROM appointment_system.mail_connection WHERE singleton AND active_key_id=ANY(retained_keys))
  OR coalesce(appointment_system.installation_value('sender.formatted'),'')='' THEN RETURN jsonb_build_object('code','copy_unavailable'); END IF;
 IF appointment_system.email_recipient_suppressed(target) THEN RETURN jsonb_build_object('code','email_destination_unavailable'); END IF;
 UPDATE appointment_system.delivery_jobs SET state='suppressed',last_error_code=CASE WHEN booking_revision<>b.revision THEN 'email_copy_superseded' ELSE 'email_deadline_passed' END,lease_token=NULL,lease_expires_at=NULL
  WHERE booking_id=b.id AND kind='booking_receipt' AND first_attempt_at IS NULL AND provider_id IS NULL
   AND state IN ('pending','retry_wait','delivery_unknown') AND (booking_revision<>b.revision OR send_deadline_at<=instant);
 copy_state:=appointment_system.receipt_copy_state(b.id);
 IF copy_state->>'blocked_reason' IN ('delivery_pending','delivery_unknown') THEN RETURN jsonb_build_object('code','copy_pending','email_copy',copy_state); END IF;
 IF (copy_state->>'remaining_requests')::integer=0 THEN RETURN jsonb_build_object('code','copy_limit','email_copy',copy_state,'retry_after',greatest(1,ceil(extract(epoch FROM (copy_state->>'next_request_at')::timestamptz-instant))::integer)); END IF;
 IF (copy_state->>'next_request_at')::timestamptz>instant THEN RETURN jsonb_build_object('code','copy_cooldown','email_copy',copy_state,'retry_after',greatest(1,ceil(extract(epoch FROM (copy_state->>'next_request_at')::timestamptz-instant))::integer)); END IF;
 INSERT INTO appointment_system.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key,destination,send_deadline_at,receipt_copy_request)
 VALUES(gen_random_uuid(),b.id,'booking_receipt','customer',b.revision,'receipt:'||p_operation::text,target,
  least(instant+interval '23 hours',b.receipt_expires_at),jsonb_build_object('version',1,'operation_id',p_operation,'expected_revision',p_revision,
   'input_fingerprint',digest,'accepted_at',to_char(instant AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')));
 RETURN jsonb_build_object('code','receipt_copy_accepted','replayed',false,'request_id',b.request_id,'operation_id',p_operation,
  'booking_revision',b.revision,'email_copy',appointment_system.receipt_copy_state(b.id,p_operation));
END $$;

CREATE FUNCTION appointment_system.request_receipt_copy(p_request uuid,p_receipt text,p_operation uuid,p_revision integer,p_input jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
BEGIN PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 RETURN appointment_system.entry_request_receipt_copy(p_request,p_receipt,p_operation,p_revision,p_input); END $$;
ALTER FUNCTION appointment_system.receipt_copy_state(uuid,uuid) OWNER TO appointment_system_owner;
ALTER FUNCTION appointment_system.entry_request_receipt_copy(uuid,text,uuid,integer,jsonb) OWNER TO appointment_system_owner;
ALTER FUNCTION appointment_system.request_receipt_copy(uuid,text,uuid,integer,jsonb) OWNER TO appointment_system_owner;
REVOKE ALL ON FUNCTION appointment_system.receipt_copy_state(uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION appointment_system.entry_request_receipt_copy(uuid,text,uuid,integer,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION appointment_system.request_receipt_copy(uuid,text,uuid,integer,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.request_receipt_copy(uuid,text,uuid,integer,jsonb) TO appointment_system_web_access;

ALTER TABLE appointment_system.delivery_jobs DROP CONSTRAINT delivery_jobs_destination_check;
ALTER TABLE appointment_system.delivery_jobs ADD CONSTRAINT delivery_jobs_destination_check CHECK ((((kind = 'payment_review'::text) AND (recipient_role = 'client'::text) AND (length(event_key) > 0)) OR ((event_key = ''::text) AND (((kind = 'booking_ack'::text) AND (recipient_role = ANY (ARRAY['customer'::text, 'client'::text]))) OR ((kind = 'booking_calendar'::text) AND (recipient_role = 'calendar'::text)) OR ((kind = 'booking_details'::text) AND (recipient_role = 'customer'::text)) OR ((kind = 'booking_cancelled'::text) AND (recipient_role = ANY (ARRAY['customer'::text, 'client'::text, 'calendar'::text]))) OR ((kind = 'sheet_booking'::text) AND (recipient_role = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text]))))) OR ((event_key = 'meeting-ready'::text) AND (kind = 'sheet_booking'::text) AND (recipient_role = ANY (ARRAY['client_sheet'::text, 'agency_sheet'::text])))) OR (kind='booking_receipt' AND recipient_role='customer' AND event_key ~ '^receipt:[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$'));
CREATE OR REPLACE FUNCTION appointment_system.is_email_job(k text, r text) RETURNS boolean
    LANGUAGE sql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$ SELECT (k='booking_ack' AND r IN ('customer','client'))
 OR(k='booking_details' AND r='customer') OR(k='booking_cancelled' AND r IN ('customer','client'))
 OR(k='payment_review' AND r='client') OR(k='booking_receipt' AND r='customer') $$;

CREATE OR REPLACE FUNCTION appointment_system.protect_email_snapshot() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF OLD.receipt_copy_request IS NOT NULL AND ROW(NEW.id,NEW.booking_id,NEW.booking_revision,NEW.kind,NEW.recipient_role,
  NEW.event_key,NEW.destination,NEW.send_deadline_at,NEW.receipt_copy_request) IS DISTINCT FROM
  ROW(OLD.id,OLD.booking_id,OLD.booking_revision,OLD.kind,OLD.recipient_role,OLD.event_key,OLD.destination,OLD.send_deadline_at,OLD.receipt_copy_request)
 THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Accepted receipt copy identity is immutable'; END IF;
 IF appointment_system.is_email_job(OLD.kind,OLD.recipient_role) AND OLD.message_snapshot IS NOT NULL AND
   ((OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at AND NOT(NEW.first_attempt_at IS NULL AND NOT OLD.prior_send_uncertain AND NOT NEW.send_uncertain AND NEW.last_error_code IN('daily_quota_exceeded','monthly_quota_exceeded','provider_rate_limited'))) OR NEW.message_snapshot IS DISTINCT FROM OLD.message_snapshot
    OR NEW.template_version IS DISTINCT FROM OLD.template_version OR NEW.message_hash IS DISTINCT FROM OLD.message_hash OR NEW.destination IS DISTINCT FROM OLD.destination
    OR NEW.booking_id IS DISTINCT FROM OLD.booking_id OR NEW.booking_revision IS DISTINCT FROM OLD.booking_revision
    OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.recipient_role IS DISTINCT FROM OLD.recipient_role
    OR NEW.event_key IS DISTINCT FROM OLD.event_key OR NEW.send_deadline_at IS DISTINCT FROM OLD.send_deadline_at) THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='Attempted email identity is immutable';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION appointment_system.entry_claim_email_delivery() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE j appointment_system.delivery_jobs%ROWTYPE; b appointment_system.bookings%ROWTYPE; candidate record; link text;
BEGIN
 FOR candidate IN SELECT id,booking_id FROM appointment_system.delivery_jobs
   WHERE appointment_system.is_email_job(kind,recipient_role) AND state IN ('pending','retry_wait','delivery_unknown','processing')
   AND next_attempt_at<=clock_timestamp() AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
   ORDER BY next_attempt_at,id LIMIT 20 LOOP
  SELECT * INTO b FROM appointment_system.bookings WHERE id=candidate.booking_id FOR SHARE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  SELECT * INTO j FROM appointment_system.delivery_jobs WHERE id=candidate.id
    AND state IN ('pending','retry_wait','delivery_unknown','processing') AND next_attempt_at<=clock_timestamp()
    AND(lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp()) FOR UPDATE SKIP LOCKED;
  IF NOT FOUND THEN CONTINUE; END IF;
  IF j.provider_id IS NOT NULL THEN
    UPDATE appointment_system.delivery_jobs SET state='completed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF j.kind<>'payment_review' AND (j.booking_revision<>b.revision OR
    (j.kind='booking_cancelled' AND b.state<>'cancelled') OR (j.kind<>'booking_cancelled' AND b.state<>'confirmed')) THEN
    UPDATE appointment_system.delivery_jobs SET state=CASE WHEN first_attempt_at IS NULL THEN 'suppressed' ELSE 'needs_review' END,
      last_error_code='email_obsolete_revision',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
    CONTINUE;
  END IF;
  IF coalesce(j.send_deadline_at,CASE WHEN j.kind IN ('booking_ack','booking_details') THEN b.starts_at ELSE clock_timestamp()+interval '24 hours' END)<=clock_timestamp() THEN
    UPDATE appointment_system.delivery_jobs SET state=CASE WHEN first_attempt_at IS NULL THEN 'suppressed' ELSE 'needs_review' END,
     last_error_code='email_deadline_passed',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE;
  END IF;
  IF j.kind IN ('booking_details','booking_receipt') AND b.service_snapshot->>'meeting'='google_meet' THEN
    SELECT meet_url INTO link FROM appointment_system.meeting_events WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready';
    IF link IS NULL THEN
      IF j.kind='booking_receipt' AND EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE booking_id=b.id
       AND booking_revision=b.revision AND kind='booking_calendar' AND state='needs_review') THEN
       UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='email_meeting_unavailable',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;
      ELSE
       UPDATE appointment_system.delivery_jobs SET next_attempt_at=least(clock_timestamp()+interval '30 seconds',coalesce(send_deadline_at,b.starts_at)) WHERE id=j.id;
      END IF;
      CONTINUE;
    END IF;
  END IF;
  IF j.attempts>=20 THEN UPDATE appointment_system.delivery_jobs SET state='needs_review',last_error_code='job_attempt_limit',lease_token=NULL,lease_expires_at=NULL WHERE id=j.id;CONTINUE; END IF;
  UPDATE appointment_system.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
    lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=attempts+1,
    send_deadline_at=coalesce(send_deadline_at,CASE WHEN kind IN ('booking_ack','booking_details') THEN b.starts_at
      ELSE clock_timestamp()+interval '24 hours' END),
    destination=coalesce(destination,CASE WHEN recipient_role='customer' THEN b.email ELSE appointment_system.installation_value('owners.client_email') END),
    payload=CASE WHEN message_snapshot IS NULL AND first_attempt_at IS NULL THEN coalesce(payload,'{}'::jsonb)||jsonb_build_object('booking_id',b.id,'reference',b.request_id,'service',b.service_snapshot->>'name',
      'starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,'practice_timezone',b.practice_timezone,'meeting',b.service_snapshot->>'meeting',
      'meet_url',CASE WHEN kind IN ('booking_details','booking_receipt') THEN link ELSE NULL END) ELSE payload END
    WHERE id=j.id RETURNING * INTO j;
  RETURN to_jsonb(j);
 END LOOP;
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION appointment_system.entry_api_receipt_snapshot(p1 uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
SELECT (SELECT to_jsonb(q.value) FROM (WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
SELECT jsonb_build_object('server_now',instant.at,'booking_product_enabled',appointment_system.control_snapshot()->'enabled','booking',(
    SELECT jsonb_build_object(
        'request_id',b.request_id,'receipt_digest',a.receipt_digest,
        'receipt_format',b.receipt_format,'receipt_key_id',b.receipt_key_id,
        'booking_id',b.id,'context_id',b.context_id,'booking_revision',b.revision,'meeting_mode',b.service_snapshot->>'meeting',
        'has_booking_email',b.email IS NOT NULL,'email_copy',appointment_system.receipt_copy_state(b.id),
        'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
        'receipt_expires_at',b.receipt_expires_at,'receipt_revoked_at',b.receipt_revoked_at,
        'state',b.state,'order_state',p.state,'attempted_at',p.attempted_at,
        'provider_order_id',p.provider_order_id,'resolution',p.resolution,'resolved_at',p.resolved_at,
        'hold_expires_at',b.hold_expires_at,'service_name',b.service_snapshot->>'name',
        'amount_paise',b.amount_paise,'currency',b.currency,'starts_at',b.starts_at,'ends_at',b.ends_at,
        'practice_timezone',b.practice_timezone,
        'payment_state',CASE
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL) THEN 'needs_attention'
          WHEN amounts.captured_paise>0 AND amounts.refunded_paise>=amounts.captured_paise THEN 'refunded'
          WHEN amounts.refunded_paise>0 THEN 'partially_refunded'
          WHEN EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=b.id) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_observations WHERE booking_id=b.id AND status='captured' AND captured) THEN 'captured'
          WHEN EXISTS(SELECT 1 FROM (
            SELECT DISTINCT ON (merchant_id,mode,payment_id) status
            FROM appointment_system.payment_observations WHERE booking_id=b.id
            ORDER BY merchant_id,mode,payment_id,observed_at DESC,
              CASE status WHEN 'refunded' THEN 5 WHEN 'captured' THEN 4
                WHEN 'failed' THEN 3 WHEN 'authorized' THEN 2 ELSE 1 END DESC,id DESC
          ) latest WHERE status IN ('created','authorized')) THEN 'pending'
          WHEN EXISTS(SELECT 1 FROM appointment_system.payment_observations WHERE booking_id=b.id AND status='failed') THEN 'failed_observed'
          ELSE 'unobserved' END,
        'captured_paise',coalesce(amounts.captured_paise,0),'refunded_paise',coalesce(amounts.refunded_paise,0),
        'payment_checked_at',(SELECT max(observed_at) FROM appointment_system.payment_observations WHERE booking_id=b.id),
        'meeting_state',CASE
          WHEN b.state='cancelled' THEN 'cancelled' WHEN b.service_snapshot->>'meeting'='internal' THEN 'not_created'
          WHEN EXISTS(SELECT 1 FROM appointment_system.delivery_jobs WHERE booking_id=b.id AND booking_revision=b.revision
                       AND kind='booking_calendar' AND state='needs_review') THEN 'needs_attention'
          WHEN b.state='confirmed' AND EXISTS(SELECT 1 FROM appointment_system.meeting_events WHERE booking_id=b.id
                       AND booking_revision=b.revision AND state='ready') THEN 'ready'
          WHEN b.state='confirmed' THEN 'preparing' ELSE 'not_created' END,
        'meet_url',CASE WHEN b.state='confirmed' THEN (SELECT meet_url FROM appointment_system.meeting_events
          WHERE booking_id=b.id AND booking_revision=b.revision AND state='ready') ELSE NULL END,
        'acknowledgement_state',CASE WHEN b.email IS NULL THEN 'not_requested' ELSE coalesce((SELECT appointment_system.email_delivery_state(id) FROM appointment_system.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_ack' AND recipient_role='customer'),'not_queued') END,
        'meeting_email_state',CASE WHEN b.email IS NULL THEN 'not_requested' ELSE coalesce((SELECT appointment_system.email_delivery_state(id) FROM appointment_system.delivery_jobs WHERE booking_id=b.id
           AND booking_revision=b.revision AND kind='booking_details' AND recipient_role='customer'),'not_queued') END
    ) FROM appointment_system.bookings b
      JOIN appointment_system.checkout_admissions a ON a.request_id=b.request_id
      JOIN appointment_system.payment_orders p ON p.booking_id=b.id
      LEFT JOIN LATERAL (
        SELECT accepted.amount_paise AS captured_paise,coalesce(max(o.refunded_paise),0) AS refunded_paise
        FROM appointment_system.accepted_payments a
        JOIN appointment_system.payment_observations accepted ON accepted.id=a.observation_id
        JOIN appointment_system.payment_observations o ON o.booking_id=a.booking_id AND o.merchant_id=a.merchant_id
          AND o.mode=a.mode AND o.payment_id=a.payment_id
        WHERE a.booking_id=b.id
        GROUP BY accepted.amount_paise
      ) amounts ON true
    WHERE b.request_id=p1
)) FROM instant) q(value))
$$;
