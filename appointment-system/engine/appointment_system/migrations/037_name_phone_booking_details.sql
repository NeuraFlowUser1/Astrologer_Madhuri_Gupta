-- One changeover: read-only identity-pair lookup and retirement of issued codes.
-- The migration runner already holds advisory lock 4004001. Keep the existing
-- 2s lock/30s statement bounds; any failure rolls back this entire migration.
SET LOCAL ROLE appointment_system_owner;
SELECT pg_advisory_xact_lock(83124,5);
SELECT pg_advisory_xact_lock(83124,4);

CREATE FUNCTION appointment_system.booking_lookup_name(value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET search_path=pg_catalog,appointment_system,pg_temp AS $$
 SELECT lower(btrim(regexp_replace(normalize(value,NFC),
   U&'[\0009\000A\000B\000C\000D\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000]+',' ','g')))
$$;
REVOKE ALL ON FUNCTION appointment_system.booking_lookup_name(text) FROM PUBLIC;
CREATE INDEX bookings_customer_lookup ON appointment_system.bookings
 (phone,appointment_system.booking_lookup_name(full_name),starts_at,request_id);

ALTER TABLE appointment_system.request_limits DROP CONSTRAINT request_limits_scope_check;
ALTER TABLE appointment_system.request_limits ADD CONSTRAINT request_limits_scope_check CHECK
 (scope=ANY(ARRAY['context','availability','receipt','checkout','studio','studio_status',
 'contact_start','contact_email','contact_read','contact_verify',
 'booking_lookup_minute','booking_lookup_quarter_hour']));

CREATE FUNCTION appointment_system.consume_booking_lookup_limits(p_key text,p_epoch uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE instant timestamptz:=clock_timestamp();slot timestamptz;rule record;used integer;wait_seconds integer:=0;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_epoch IS NULL OR p_key IS NULL OR p_key !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='lookup admission unavailable'; END IF;
 PERFORM appointment_system.control_admission(p_epoch);
 -- Fixed order, one committed transaction; both counters are charged even
 -- when the first is already over its limit. No identity pair is stored here.
 FOR rule IN SELECT * FROM (VALUES('booking_lookup_minute',60,10),
   ('booking_lookup_quarter_hour',900,60)) AS limits(scope,width,maximum)
   ORDER BY width LOOP
  slot:=to_timestamp(floor(extract(epoch FROM instant)/rule.width)*rule.width);
  INSERT INTO appointment_system.request_limits(scope,key_digest,window_start,expires_at,attempts)
   VALUES(rule.scope,p_key,slot,slot+make_interval(secs=>rule.width)+interval '24 hours',1)
   ON CONFLICT(scope,key_digest,window_start) DO UPDATE
    SET attempts=least(appointment_system.request_limits.attempts+1,rule.maximum+1)
   RETURNING attempts INTO used;
  IF used>rule.maximum THEN
   wait_seconds:=greatest(wait_seconds,greatest(1,ceil(extract(epoch FROM slot+make_interval(secs=>rule.width)-instant))::integer));
  END IF;
 END LOOP;
 RETURN jsonb_build_object('allowed',wait_seconds=0,'retry_after',greatest(1,wait_seconds));
END $$;
REVOKE ALL ON FUNCTION appointment_system.consume_booking_lookup_limits(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.consume_booking_lookup_limits(text,uuid) TO appointment_system_web_access;


CREATE FUNCTION appointment_system.booking_receipt_facts(p_booking appointment_system.bookings,p_at timestamptz) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
 SELECT jsonb_build_object(
  'request_id',b.request_id,'booking_revision',b.revision,'meeting_mode',b.service_snapshot->>'meeting',
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
 ) FROM (SELECT (p_booking).*) b
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

$$;
REVOKE ALL ON FUNCTION appointment_system.booking_receipt_facts(appointment_system.bookings,timestamptz) FROM PUBLIC;

CREATE OR REPLACE FUNCTION appointment_system.entry_api_receipt_snapshot(p1 uuid) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
 WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
 SELECT jsonb_build_object('server_now',instant.at,
  'booking_product_enabled',appointment_system.control_snapshot()->'enabled','booking',(
   SELECT appointment_system.booking_receipt_facts(b,instant.at)||jsonb_build_object(
    'receipt_digest',a.receipt_digest,'receipt_format',b.receipt_format,'receipt_key_id',b.receipt_key_id,
    'booking_id',b.id,'context_id',b.context_id,'has_booking_email',b.email IS NOT NULL,
    'email_copy',appointment_system.receipt_copy_state(b.id),
    'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
    'receipt_expires_at',b.receipt_expires_at,'receipt_revoked_at',b.receipt_revoked_at)
   FROM appointment_system.bookings b
    JOIN appointment_system.checkout_admissions a ON a.request_id=b.request_id
    JOIN appointment_system.payment_orders p ON p.booking_id=b.id WHERE b.request_id=p1
  )) FROM instant
$$;

CREATE FUNCTION appointment_system.booking_details(p_name text,p_phone text,p_epoch uuid,p_reference uuid,
 p_as_of timestamptz,p_bucket integer,p_start timestamptz,p_last uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE instant timestamptz:=clock_timestamp();ordering_at timestamptz:=coalesce(p_as_of,instant);
 normalized text;result jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_epoch IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='lookup admission unavailable'; END IF;
 PERFORM appointment_system.control_admission(p_epoch);
 normalized:=appointment_system.booking_lookup_name(p_name);
 IF p_name IS NULL OR length(p_name) NOT BETWEEN 2 AND 100 OR normalized IS NULL OR length(normalized) NOT BETWEEN 2 AND 100
  OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$' THEN
  RETURN jsonb_build_object('code','invalid_name'); END IF;
 IF (p_as_of IS NULL AND (p_bucket IS NOT NULL OR p_start IS NOT NULL OR p_last IS NOT NULL))
  OR (p_as_of IS NOT NULL AND (p_bucket IS NULL OR p_start IS NULL OR p_last IS NULL
    OR NOT isfinite(p_as_of) OR NOT isfinite(p_start) OR p_as_of>instant OR p_as_of<instant-interval '24 hours'
    OR p_bucket NOT IN (0,1) OR p_last='00000000-0000-0000-0000-000000000000'::uuid
    OR (p_bucket=0 AND p_start<p_as_of) OR (p_bucket=1 AND p_start>=p_as_of)))
  OR (p_reference IS NOT NULL AND p_as_of IS NOT NULL) THEN
  RETURN jsonb_build_object('code','invalid_cursor'); END IF;
 IF p_reference IS NOT NULL THEN
  -- The matched row and STABLE fact helper share one read snapshot. No global
  -- reference lookup, receipt secret, contact value or action is returned.
  WITH matched AS MATERIALIZED (
   SELECT b FROM appointment_system.bookings b WHERE b.phone=p_phone
    AND appointment_system.booking_lookup_name(b.full_name)=normalized AND b.request_id=p_reference
  ) SELECT appointment_system.booking_receipt_facts(m.b,instant) INTO result FROM matched m;
  RETURN jsonb_build_object('server_now',instant,'booking',result);
 END IF;
 -- Two bounded index ranges. At most 42 candidates reach the merge; at most
 -- 21 leave SQL. Freeze the time boundary, not the underlying booking records.
 WITH future AS MATERIALIZED (
  SELECT b.request_id,b.revision,b.service_snapshot->>'name' AS service_name,b.starts_at,b.ends_at,b.practice_timezone,
   b.state,b.hold_expires_at,0 AS bucket FROM appointment_system.bookings b
  WHERE (p_bucket IS NULL OR p_bucket=0) AND b.phone=p_phone
   AND appointment_system.booking_lookup_name(b.full_name)=normalized AND b.starts_at>=ordering_at
   AND (p_bucket IS NULL OR (b.starts_at,b.request_id)>(p_start,p_last))
  ORDER BY b.starts_at,b.request_id LIMIT 21
 ), past AS MATERIALIZED (
  SELECT b.request_id,b.revision,b.service_snapshot->>'name' AS service_name,b.starts_at,b.ends_at,b.practice_timezone,
   b.state,b.hold_expires_at,1 AS bucket FROM appointment_system.bookings b
  WHERE b.phone=p_phone AND appointment_system.booking_lookup_name(b.full_name)=normalized AND b.starts_at<ordering_at
   AND (p_bucket IS NULL OR p_bucket=0 OR (b.starts_at,b.request_id)<(p_start,p_last))
  ORDER BY b.starts_at DESC,b.request_id DESC LIMIT 21
 ), page AS MATERIALIZED (
  SELECT * FROM (SELECT * FROM future UNION ALL SELECT * FROM past) candidates
  ORDER BY bucket,CASE WHEN bucket=0 THEN starts_at END,CASE WHEN bucket=0 THEN request_id END,
   CASE WHEN bucket=1 THEN starts_at END DESC,CASE WHEN bucket=1 THEN request_id END DESC LIMIT 21
 ) SELECT coalesce(jsonb_agg(jsonb_build_object('request_id',request_id,'booking_revision',revision,
    'service_name',service_name,'starts_at',starts_at,'ends_at',ends_at,'timezone',practice_timezone,'bucket',bucket,
    'appointment_state',CASE WHEN state='held' AND hold_expires_at<=instant THEN 'expired' ELSE state END)
   ORDER BY bucket,CASE WHEN bucket=0 THEN starts_at END,CASE WHEN bucket=0 THEN request_id END,
    CASE WHEN bucket=1 THEN starts_at END DESC,CASE WHEN bucket=1 THEN request_id END DESC),'[]'::jsonb)
  INTO result FROM page;
 RETURN jsonb_build_object('server_now',instant,'as_of',ordering_at,'items',result);
END $$;
REVOKE ALL ON FUNCTION appointment_system.booking_details(text,text,uuid,uuid,timestamptz,integer,timestamptz,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.booking_details(text,text,uuid,uuid,timestamptz,integer,timestamptz,uuid) TO appointment_system_web_access;

-- Audit rows survive; code authority and usable digests do not.
ALTER TABLE appointment_system.receipt_recoveries DROP CONSTRAINT receipt_recoveries_check;
ALTER TABLE appointment_system.receipt_recoveries DROP CONSTRAINT receipt_recoveries_verification_method_check;
ALTER TABLE appointment_system.receipt_recoveries ADD CONSTRAINT receipt_recoveries_verification_method_check CHECK(
 (verification_method='existing_phone_callback' AND verified_payment_id IS NOT NULL AND historical_operation_id IS NULL) OR
 (verification_method='retained_staff_operation' AND verified_payment_id IS NULL AND historical_operation_id=operation_id
  AND historical_operation_id IS NOT NULL AND previous_email IS NULL AND previous_phone IS NULL AND new_email IS NULL AND new_phone IS NULL));
ALTER TABLE appointment_system.receipt_recoveries DROP COLUMN code_digest,DROP COLUMN redeemed_digest,
 DROP COLUMN code_format,DROP COLUMN code_key_id;
ALTER TABLE appointment_system.receipt_recoveries ALTER COLUMN expires_at DROP NOT NULL,
 ALTER COLUMN expires_at DROP DEFAULT;

-- Old signatures are deliberately absent, including previously revoked overloads.
DROP FUNCTION appointment_system.recovery_protection(uuid,uuid);
DROP FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text,text);
DROP FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text);
DROP FUNCTION appointment_system.entry_redeem_receipt_recovery(uuid,text,text);
DROP FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text,text);
DROP FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text);
DROP FUNCTION appointment_system.entry_studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text);

CREATE FUNCTION appointment_system.entry_studio_support_change(p_session text, p_client text, p_origin text, p_operation uuid, p_reference uuid, p_revision integer, p_action text, p_reason text, p_payment text, p_email text, p_phone text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $_$
DECLARE actor text;prior appointment_system.receipt_recoveries%ROWTYPE;b appointment_system.bookings%ROWTYPE;context uuid;instant timestamptz;old_snapshot jsonb;snapshot jsonb;new_revision integer; frozen_email_required boolean;
BEGIN
 actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_reference IS NULL OR p_revision IS NULL OR p_revision<1 OR p_revision>=2147483647
 OR p_action IS NULL OR p_action<>'contact_correction' OR coalesce(length(btrim(p_reason)),0) NOT BETWEEN 2 AND 500 OR p_reason ~ '[[:cntrl:]]'
 OR p_payment IS NULL OR p_payment !~ '^pay_[A-Za-z0-9]{1,64}$'
 OR (p_action='contact_correction' AND((p_email IS NOT NULL AND (length(p_email) NOT BETWEEN 3 AND 254 OR p_email ~ '[[:cntrl:]]' OR p_email !~ '^[^[:space:]@<>]+@[^[:space:]@<>]+\.[^[:space:]@<>]+$')) OR p_phone IS NULL OR p_phone !~ '^\+[1-9][0-9]{6,14}$')) THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 SELECT * INTO b FROM appointment_system.bookings WHERE request_id=p_reference FOR UPDATE;
 IF appointment_system.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.request_id<>p_reference OR prior.actor<>actor OR prior.action<>p_action OR prior.reason<>p_reason OR prior.previous_revision<>p_revision OR prior.verified_payment_id IS DISTINCT FROM p_payment
  OR prior.new_email IS DISTINCT FROM p_email OR prior.new_phone IS DISTINCT FROM p_phone THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','contact_corrected','revision',prior.revision,'operation_id',p_operation,'reference',prior.request_id);
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
 INSERT INTO appointment_system.receipt_recoveries(operation_id,request_id,action,actor,reason,verified_payment_id,previous_revision,revision,previous_email,previous_phone,new_email,new_phone)
 VALUES(p_operation,b.request_id,p_action,actor,p_reason,p_payment,b.revision,new_revision,CASE WHEN p_action='contact_correction' THEN b.email END,CASE WHEN p_action='contact_correction' THEN b.phone END,p_email,p_phone) RETURNING * INTO prior;
 -- Contact correction revokes the old receipt; lookup reads the corrected phone.
 -- No replacement receipt secret or customer code is issued.
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
 RETURN jsonb_build_object('code','contact_corrected','revision',new_revision,'operation_id',p_operation,'reference',b.request_id);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $_$;

REVOKE ALL ON FUNCTION appointment_system.entry_studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text) FROM PUBLIC;
CREATE FUNCTION appointment_system.studio_support_change(p_session text,p_client text,p_origin text,p_operation uuid,
 p_reference uuid,p_revision integer,p_action text,p_reason text,p_payment text,p_email text,p_phone text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']);
 IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('support-operation:'||p_operation::text,0));
 RETURN appointment_system.entry_studio_support_change(p_session,p_client,p_origin,p_operation,p_reference,p_revision,
  p_action,p_reason,p_payment,p_email,p_phone);
END $$;
REVOKE ALL ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text)
 TO appointment_system_staff_access,appointment_system_company_access;

CREATE OR REPLACE FUNCTION appointment_system.entry_control_obligation_action(p_session text, p_csrf text, p_client text, p_action text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text; target uuid; owned boolean;
 private_origin text:=(appointment_system.installation_value('origin')||'/company/booking-support');
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_action IS NULL OR p_action NOT IN ('lookup','detail','cancel','reschedule','support','verified_refund','resource_reviewed')
  OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 principal:=appointment_system.control_authorize(p_session,'obligation_handler',p_csrf,p_action NOT IN ('lookup','detail'));
 IF appointment_system.control_obligation_actor(p_session,p_client,private_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_action IN ('lookup','support') THEN
  SELECT id INTO target FROM appointment_system.bookings WHERE request_id=(p_data->>'reference')::uuid;
 ELSIF p_action IN('verified_refund','resource_reviewed') THEN
  SELECT booking_id INTO target FROM appointment_system.payment_cases WHERE id=(p_data->>'case_id')::uuid;
 ELSE SELECT booking_id INTO target FROM appointment_system.slot_claims WHERE id=(p_data->>'claim_id')::uuid; END IF;
 owned:=EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=target);
 IF target IS NULL OR NOT owned THEN RETURN jsonb_build_object('code','booking_unavailable'); END IF;
 IF p_action='lookup' THEN
  RETURN appointment_system.studio_booking_lookup(p_session,p_client,private_origin,(p_data->>'reference')::uuid);
 ELSIF p_action='detail' THEN
  RETURN appointment_system.studio_appointment_detail(p_session,p_client,private_origin,(p_data->>'claim_id')::uuid);
 ELSIF p_action='cancel' THEN
  RETURN appointment_system.studio_appointment_cancel(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSIF p_action='reschedule' THEN
  RETURN appointment_system.studio_appointment_reschedule(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason',(p_data->>'starts_at')::timestamptz);
 ELSIF p_action='support' THEN
  IF p_data->'verification_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
  RETURN appointment_system.studio_support_change(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'reference')::uuid,(p_data->>'expected_revision')::integer,p_data->>'action',p_data->>'reason',
   p_data->>'verified_payment_id',p_data->>'email',p_data->>'phone');
 ELSIF p_action='resource_reviewed' THEN
  RETURN appointment_system.studio_inbox_resource_reviewed(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSE
  RETURN appointment_system.studio_inbox_refund_verified(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 END IF;
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;
-- Take maintenance before caller validation's booking barrier, including the
-- company wrapper. Do not upgrade a shared booking barrier during maintenance.
CREATE OR REPLACE FUNCTION appointment_system.control_obligation_action(p_session text,p_csrf text,p_client text,p_action text,p_data jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,5);
 PERFORM appointment_system.require_registered_caller(ARRAY['company']);
 RETURN appointment_system.entry_control_obligation_action(p_session,p_csrf,p_client,p_action,p_data);
END $$;
CREATE OR REPLACE FUNCTION appointment_system.entry_studio_action_result(p_session text, p_client text, p_origin text, p_operation uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal_actor text; appointment appointment_system.staff_appointment_actions%ROWTYPE;
 recovery appointment_system.receipt_recoveries%ROWTYPE;review appointment_system.staff_reviews%ROWTYPE;
 target uuid;reference uuid;matches integer;result jsonb;
BEGIN
 principal_actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
 IF principal_actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT * INTO appointment FROM appointment_system.staff_appointment_actions WHERE operation_id=p_operation AND staff_appointment_actions.actor=principal_actor;
 SELECT * INTO recovery FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation AND receipt_recoveries.actor=principal_actor;
 SELECT * INTO review FROM appointment_system.staff_reviews WHERE operation_id=p_operation AND staff_reviews.actor=principal_actor;
 matches:=(CASE WHEN appointment.operation_id IS NOT NULL THEN 1 ELSE 0 END)
  +(CASE WHEN recovery.operation_id IS NOT NULL THEN 1 ELSE 0 END)+(CASE WHEN review.operation_id IS NOT NULL THEN 1 ELSE 0 END);
 IF matches=0 THEN RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 IF matches<>1 THEN RETURN jsonb_build_object('code','operation_conflict','operation_id',p_operation);END IF;
 IF appointment.operation_id IS NOT NULL THEN
  target:=appointment.booking_id;
  result:=jsonb_build_object('code',CASE WHEN appointment.action='cancel' THEN 'cancelled' ELSE 'rescheduled' END,
   'revision',appointment.revision,'operation_id',p_operation,'starts_at',appointment.new_starts_at,'ends_at',appointment.new_ends_at);
 ELSIF recovery.operation_id IS NOT NULL THEN
  SELECT id INTO target FROM appointment_system.bookings WHERE request_id=recovery.request_id;
  result:=jsonb_build_object('code',CASE WHEN recovery.action='contact_correction' THEN 'contact_corrected' ELSE 'operation_retired' END,
   'revision',recovery.revision,'operation_id',p_operation,'reference',recovery.request_id);
 ELSE
  IF review.item_key NOT LIKE 'payment:%' OR review.action NOT IN('verified_refund','resource_reviewed') THEN
   RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
  SELECT booking_id INTO target FROM appointment_system.payment_cases WHERE id=substring(review.item_key FROM 9)::uuid;
  result:=jsonb_build_object('code',CASE WHEN review.action='verified_refund' THEN 'refund_verified' ELSE 'resource_reviewed' END,
   'revision',review.revision,'operation_id',p_operation);
 END IF;
 IF principal_actor LIKE 'company:%' AND NOT(EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=target)) THEN
  RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 SELECT request_id INTO reference FROM appointment_system.bookings WHERE id=target;
 RETURN result||jsonb_build_object('reference',reference);
END $$;
RESET ROLE;
