-- New checkout writes remain guarded even if an old runtime writes directly.
CREATE FUNCTION booking_control.guard_checkout_admission() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE epoch uuid;
BEGIN
 SELECT activation_epoch INTO epoch FROM sarsa_booking.checkout_contexts WHERE id=NEW.context_id;
 IF NOT FOUND OR epoch IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout context required'; END IF;
 NEW.activation_epoch:=booking_control.admission(epoch);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION booking_control.guard_checkout_admission() FROM PUBLIC;
CREATE TRIGGER booking_request_admission BEFORE INSERT ON sarsa_booking.checkout_admissions
 FOR EACH ROW EXECUTE FUNCTION booking_control.guard_checkout_admission();
ALTER TABLE sarsa_booking.checkout_contexts ALTER COLUMN activation_epoch SET NOT NULL;
ALTER TABLE sarsa_booking.checkout_admissions ALTER COLUMN activation_epoch SET NOT NULL;
ALTER TABLE sarsa_booking.bookings ALTER COLUMN activation_epoch SET NOT NULL;

-- Explicit company capability. Agency spreadsheet permission is never widened.
CREATE FUNCTION booking_control.obligation_actor(p_session text,p_client text,p_origin text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $$
DECLARE principal text;
BEGIN
 IF p_origin IS DISTINCT FROM 'https://www.sarsajyotishsansthan.com/company/booking-support'
  OR NOT EXISTS(SELECT 1 FROM booking_control.company_identities WHERE audience=p_client AND enabled) THEN RETURN NULL; END IF;
 principal:=booking_control.authorize(p_session,'obligation_handler');
 IF NOT EXISTS(SELECT 1 FROM booking_control.company_identities WHERE subject=principal AND audience=p_client AND enabled) THEN RETURN NULL; END IF;
 RETURN 'company:'||encode(sha256(convert_to(principal,'UTF8')),'hex');
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION booking_control.obligation_actor(text,text,text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION sarsa_booking.studio_calendar_actor(p_session text,p_client text,p_origin text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $$
DECLARE s sarsa_booking.studio_sessions%ROWTYPE;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_origin='https://www.sarsajyotishsansthan.com/company/booking-support' THEN
  RETURN booking_control.obligation_actor(p_session,p_client,p_origin);
 END IF;
 PERFORM booking_control.admission(NULL);
 SELECT * INTO s FROM sarsa_booking.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.role<>'client' OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
  OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
  OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities i WHERE i.role=s.role AND i.subject=s.subject) THEN RETURN NULL; END IF;
 RETURN 'client:'||encode(sha256(convert_to(s.subject,'UTF8')),'hex');
END $$;

CREATE FUNCTION booking_control.obligation_summary(p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
BEGIN
 PERFORM booking_control.authorize(p_session,'obligation_handler');
 RETURN jsonb_build_object('code','ok','appointments',coalesce((
  SELECT jsonb_agg(row) FROM (SELECT b.request_id AS reference,b.full_name AS name,b.service_snapshot->>'name' AS service,
   b.starts_at,b.ends_at,b.state,b.revision,
   (SELECT id FROM sarsa_booking.slot_claims WHERE booking_id=b.id) AS claim_id
   FROM sarsa_booking.bookings b WHERE EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=b.id)
   AND b.state='confirmed' AND b.ends_at>=clock_timestamp() ORDER BY b.starts_at,b.id LIMIT 50)row),'[]'::jsonb),
  'reviews',coalesce((SELECT jsonb_agg(row) FROM(SELECT c.id AS case_id,b.request_id AS reference,c.reason,
    coalesce((SELECT max(revision) FROM sarsa_booking.staff_reviews WHERE item_key='payment:'||c.id),0) AS revision
    FROM sarsa_booking.payment_cases c JOIN sarsa_booking.bookings b ON b.id=c.booking_id
    WHERE c.resolved_at IS NULL ORDER BY c.next_check_at,c.id LIMIT 50)row),'[]'::jsonb));
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

CREATE FUNCTION booking_control.obligation_action(p_session text,p_csrf text,p_client text,p_action text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE principal text; target uuid; owned boolean;
 private_origin text:='https://www.sarsajyotishsansthan.com/company/booking-support';
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_action IS NULL OR p_action NOT IN ('lookup','detail','cancel','reschedule','support','verified_refund')
  OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 principal:=booking_control.authorize(p_session,'obligation_handler',p_csrf,p_action NOT IN ('lookup','detail'));
 IF booking_control.obligation_actor(p_session,p_client,private_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_action IN ('lookup','support') THEN
  SELECT id INTO target FROM sarsa_booking.bookings WHERE request_id=(p_data->>'reference')::uuid;
 ELSIF p_action='verified_refund' THEN
  SELECT booking_id INTO target FROM sarsa_booking.payment_cases WHERE id=(p_data->>'case_id')::uuid;
 ELSE SELECT booking_id INTO target FROM sarsa_booking.slot_claims WHERE id=(p_data->>'claim_id')::uuid; END IF;
 owned:=EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=target);
 IF target IS NULL OR NOT owned THEN RETURN jsonb_build_object('code','booking_unavailable'); END IF;
 IF p_action='lookup' THEN
  RETURN sarsa_booking.studio_booking_lookup(p_session,p_client,private_origin,(p_data->>'reference')::uuid);
 ELSIF p_action='detail' THEN
  RETURN sarsa_booking.studio_appointment_detail(p_session,p_client,private_origin,(p_data->>'claim_id')::uuid);
 ELSIF p_action='cancel' THEN
  RETURN sarsa_booking.studio_appointment_cancel(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSIF p_action='reschedule' THEN
  RETURN sarsa_booking.studio_appointment_reschedule(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason',(p_data->>'starts_at')::timestamptz);
 ELSIF p_action='support' THEN
  IF p_data->'verification_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
  RETURN sarsa_booking.studio_support_change(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'reference')::uuid,(p_data->>'expected_revision')::integer,p_data->>'action',p_data->>'reason',
   p_data->>'verified_payment_id',p_data->>'email',p_data->>'phone',p_data->>'code_digest');
 ELSE
  RETURN sarsa_booking.studio_inbox_refund_verified(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 END IF;
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;
REVOKE ALL ON FUNCTION booking_control.obligation_summary(text),booking_control.obligation_action(text,text,text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION booking_control.obligation_summary(text),booking_control.obligation_action(text,text,text,text,jsonb) TO sarsa_booking_runtime;

-- Client inbox authority follows the same commercial boundary; record-copy
-- sessions remain independent and gain no appointment/customer-support scope.
CREATE OR REPLACE FUNCTION sarsa_booking.staff_actor(p_session text,p_client text,p_origin text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $$
DECLARE s sarsa_booking.studio_sessions%ROWTYPE;principal text;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_origin='https://www.sarsajyotishsansthan.com/company/booking-support' THEN
  principal:=booking_control.obligation_actor(p_session,p_client,p_origin);
  IF principal IS NULL THEN RETURN NULL; END IF;
  RETURN jsonb_build_object('role','client','actor',principal);
 END IF;
 SELECT * INTO s FROM sarsa_booking.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
  OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
  OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities i WHERE i.role=s.role AND i.subject=s.subject) THEN RETURN NULL; END IF;
 IF s.role='client' THEN PERFORM booking_control.admission(NULL); END IF;
 RETURN jsonb_build_object('role',s.role,'actor',s.role||':'||encode(sha256(convert_to(s.subject,'UTF8')),'hex'));
END $$;
