-- Daily limits use UTC even when a database session uses another timezone.
CREATE OR REPLACE FUNCTION appointment_system.reserve_delivery_budget(p_class text,p_job uuid)
RETURNS text LANGUAGE plpgsql SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE p_booking uuid;p_enquiry uuid;p_code uuid;p_verification boolean;instant timestamptz;
 day_start timestamptz;budget jsonb;c appointment_system.mail_connection%ROWTYPE;
 daily integer;rolling integer;vd integer;vr integer;dc bigint;rc bigint;vc bigint;vrc bigint;nc bigint;nrc bigint;
BEGIN
 IF p_class IS NULL OR p_class NOT IN ('booking_notification','enquiry_notification','enquiry_code','booking_code') OR p_job IS NULL THEN RETURN 'email_budget_invalid'; END IF;
 p_booking:=CASE WHEN p_class='booking_notification' THEN p_job END;
 p_enquiry:=CASE WHEN p_class IN ('enquiry_notification','enquiry_code') THEN p_job END;
 p_code:=CASE WHEN p_class='booking_code' THEN p_job END;p_verification:=p_class IN ('enquiry_code','booking_code');
 PERFORM pg_advisory_xact_lock(4004003);
 instant:=clock_timestamp();
 SELECT * INTO c FROM appointment_system.mail_connection WHERE singleton;
 IF NOT FOUND THEN RETURN 'email_budget_unconfigured'; END IF;
 SELECT p.specification->'email_budget' INTO budget FROM appointment_system.intake_settings s
 JOIN appointment_system.booking_policies p ON p.version=s.policy_version WHERE s.singleton;
 daily:=least((budget->>'daily')::integer,c.daily_allowance);rolling:=least((budget->>'rolling')::integer,c.rolling_allowance);
 vd:=least((budget->>'verification_daily')::integer,daily);vr:=least((budget->>'verification_rolling')::integer,rolling);
 IF daily IS NULL OR rolling IS NULL OR daily<=0 OR rolling<=0 THEN RETURN 'email_budget_unconfigured'; END IF;
 IF EXISTS(SELECT 1 FROM appointment_system.email_reservations WHERE job_id=p_booking OR enquiry_job_id=p_enquiry OR verification_job_id=p_code) THEN RETURN NULL; END IF;
 day_start:=date_trunc('day',instant AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
 SELECT count(*) FILTER(WHERE reserved_at>=day_start),count(*),
  count(*) FILTER(WHERE verification AND reserved_at>=day_start),count(*) FILTER(WHERE verification),
  count(*) FILTER(WHERE NOT verification AND reserved_at>=day_start),count(*) FILTER(WHERE NOT verification)
 INTO dc,rc,vc,vrc,nc,nrc FROM appointment_system.email_reservations
 WHERE NOT counted_in_legacy_baseline AND reserved_at>=instant-interval '31 days';
 SELECT dc+coalesce(sum(total_count) FILTER(WHERE bucket_date>=(instant AT TIME ZONE 'UTC')::date),0),rc+coalesce(sum(total_count),0),
  vc+coalesce(sum(verification_count) FILTER(WHERE bucket_date>=(instant AT TIME ZONE 'UTC')::date),0),vrc+coalesce(sum(verification_count),0),
  nc+coalesce(sum(total_count-verification_count) FILTER(WHERE bucket_date>=(instant AT TIME ZONE 'UTC')::date),0),
  nrc+coalesce(sum(total_count-verification_count),0)
 INTO dc,rc,vc,vrc,nc,nrc FROM appointment_system.email_allowance_baselines
 WHERE installation_id=appointment_system.installation_value('installation_id')::uuid AND expires_at>instant;
 IF dc>=daily OR rc>=rolling OR (p_verification AND (vc>=vd OR vrc>=vr))
  OR (NOT p_verification AND (nc>=daily-vd OR nrc>=rolling-vr)) THEN RETURN 'email_budget_exhausted'; END IF;
 INSERT INTO appointment_system.email_reservations(job_id,enquiry_job_id,verification_job_id,verification)
 VALUES(p_booking,p_enquiry,p_code,p_verification);
 RETURN NULL;
END $$;
