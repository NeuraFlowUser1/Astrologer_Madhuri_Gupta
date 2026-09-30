-- Private support lookup and bounded requeue. No financial fact or receipt capability is invented.
ALTER TABLE sarsa_booking.staff_reviews ADD COLUMN action text NOT NULL DEFAULT 'note' CHECK(action IN ('note','retry','verified_refund'));
CREATE FUNCTION sarsa_booking.studio_booking_lookup(p_session text,p_client text,p_origin text,p_reference uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE b sarsa_booking.bookings%ROWTYPE;result jsonb;
BEGIN
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE request_id=p_reference;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','booking_unavailable');END IF;
 SELECT jsonb_build_object('code','ok','reference',b.request_id,'revision',b.revision,'state',b.state,'name',b.full_name,'email',b.email,'phone',b.phone,
 'service',b.service_snapshot->>'name','starts_at',b.starts_at,'ends_at',b.ends_at,'amount_paise',b.amount_paise,'currency',b.currency,
 'claim_id',(SELECT id FROM sarsa_booking.slot_claims WHERE booking_id=b.id),
 'unresolved_payments',(SELECT count(*) FROM sarsa_booking.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL),
 'payments',coalesce((SELECT jsonb_agg(x ORDER BY x.observed_at DESC,x.id DESC) FROM (SELECT id,payment_id,status,amount_paise,refunded_paise,currency,captured,observed_at FROM sarsa_booking.payment_observations WHERE booking_id=b.id ORDER BY observed_at DESC,id DESC LIMIT 20)x),'[]'::jsonb)) INTO result;
 RETURN result;
END $$;
CREATE FUNCTION sarsa_booking.studio_inbox_retry(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE a jsonb;prior sarsa_booking.staff_reviews%ROWTYPE;current_revision integer;identity uuid;booking uuid;enquiry uuid;b sarsa_booking.bookings%ROWTYPE;
 j sarsa_booking.delivery_jobs%ROWTYPE;e sarsa_booking.enquiry_delivery_jobs%ROWTYPE;p sarsa_booking.payment_orders%ROWTYPE;instant timestamptz;
BEGIN
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^(payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'
 OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]'
 THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-staff-review:'||p_item,0));
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM sarsa_booking.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'retry' OR prior.item_key<>p_item OR prior.actor<>a->>'actor' OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','retry_queued','revision',prior.revision);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.staff_items(a->>'role') WHERE item_key=p_item) THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM sarsa_booking.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.staff_reviews WHERE item_key=p_item AND action='retry' AND created_at>clock_timestamp()-interval '1 minute') THEN RETURN jsonb_build_object('code','retry_wait');END IF;
 identity:=split_part(p_item,':',2)::uuid;instant:=clock_timestamp();
 IF p_item LIKE 'delivery:%' THEN
  SELECT booking_id INTO booking FROM sarsa_booking.delivery_jobs WHERE id=identity;
  SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR SHARE;
  SELECT * INTO j FROM sarsa_booking.delivery_jobs WHERE id=identity FOR UPDATE;
  IF j.state NOT IN ('attention','failed','uncertain','pending','processing') OR j.lease_expires_at>instant THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  IF sarsa_booking.is_email_job(j.kind,j.recipient_role) THEN
   IF j.provider_id IS NOT NULL OR (j.first_attempt_at IS NOT NULL AND instant>=j.first_attempt_at+interval '23 hours')
    OR (j.send_deadline_at IS NOT NULL AND j.send_deadline_at<=instant)
    OR (j.kind IN ('booking_ack','booking_details') AND b.starts_at<=instant)
    OR (j.kind<>'payment_review' AND (j.booking_revision<>b.revision OR (j.kind='booking_cancelled' AND b.state<>'cancelled') OR(j.kind<>'booking_cancelled' AND b.state<>'confirmed')))
    OR EXISTS(SELECT 1 FROM sarsa_booking.email_observations o JOIN sarsa_booking.delivery_jobs d ON d.id=o.job_id WHERE d.destination=j.destination AND o.event_type IN ('email.bounced','email.complained','email.suppressed'))
   THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  ELSIF j.kind NOT IN ('booking_calendar','sheet_booking','booking_cancelled') THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE sarsa_booking.delivery_jobs SET state='pending',next_attempt_at=instant,lease_token=NULL,lease_expires_at=NULL WHERE id=identity;
 ELSIF p_item LIKE 'enquiry-delivery:%' THEN
  SELECT request_id INTO enquiry FROM sarsa_booking.enquiry_delivery_jobs WHERE id=identity;
  PERFORM 1 FROM sarsa_booking.enquiries WHERE request_id=enquiry FOR SHARE;
  SELECT * INTO e FROM sarsa_booking.enquiry_delivery_jobs WHERE id=identity FOR UPDATE;
  IF e.kind='verification' OR e.state NOT IN ('attention','failed','uncertain','pending','processing') OR e.lease_expires_at>instant OR e.deadline_at<=instant THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  IF e.kind IN ('acknowledgement','practice_notice') AND(e.provider_id IS NOT NULL OR(e.first_attempt_at IS NOT NULL AND instant>=e.first_attempt_at+interval '23 hours')
   OR EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations WHERE job_id=e.id AND event_type IN ('email.bounced','email.complained','email.suppressed')))
  THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE sarsa_booking.enquiry_delivery_jobs SET state='pending',next_attempt_at=instant,lease_token=NULL,lease_expires_at=NULL WHERE id=identity;
 ELSE
  IF a->>'role'<>'client' THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
  SELECT booking_id INTO booking FROM sarsa_booking.payment_cases WHERE id=identity AND resolved_at IS NULL;
  SELECT * INTO p FROM sarsa_booking.payment_orders WHERE booking_id=booking FOR UPDATE;
  IF NOT FOUND OR p.lease_expires_at>instant OR (p.resolved_at IS NOT NULL AND p.resolution<>'confirmed') THEN RETURN jsonb_build_object('code','retry_unavailable');END IF;
  UPDATE sarsa_booking.payment_orders SET recovery_followup=true,next_check_at=instant WHERE booking_id=booking;
 END IF;
 INSERT INTO sarsa_booking.staff_reviews(operation_id,item_key,revision,actor,note,action) VALUES(p_operation,p_item,current_revision+1,a->>'actor',p_note,'retry');
 RETURN jsonb_build_object('code','retry_queued','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_booking_lookup(text,text,text,uuid),sarsa_booking.studio_inbox_retry(text,text,text,uuid,text,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_booking_lookup(text,text,text,uuid),sarsa_booking.studio_inbox_retry(text,text,text,uuid,text,integer,text) TO sarsa_booking_runtime;

CREATE OR REPLACE FUNCTION sarsa_booking.studio_inbox_review(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE a jsonb;prior sarsa_booking.staff_reviews%ROWTYPE;current_revision integer;
BEGIN
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'
  OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000
  OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 -- Actor/session lock precedes per-item serialization; no provider call or money mutation.
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-staff-review:'||p_item,0));
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO prior FROM sarsa_booking.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'note' OR prior.item_key<>p_item OR prior.actor<>a->>'actor' OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
  RETURN jsonb_build_object('code','review_saved','revision',prior.revision);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.staff_items(a->>'role') WHERE item_key=p_item) THEN RETURN jsonb_build_object('code','item_unavailable'); END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM sarsa_booking.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed'); END IF;
 BEGIN
 INSERT INTO sarsa_booking.staff_reviews(operation_id,item_key,revision,actor,note) VALUES(p_operation,p_item,current_revision+1,a->>'actor',p_note);
 EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict'); END;
 RETURN jsonb_build_object('code','review_saved','revision',current_revision+1);
END $$;

CREATE OR REPLACE FUNCTION sarsa_booking.staff_items(p_role text)
RETURNS TABLE(item_key text,category text,state text,created_at timestamptz,reference text,subject text,reason text)
LANGUAGE sql STABLE SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
 SELECT 'enquiry:'||e.request_id,'enquiry','received',e.verified_at,e.request_id::text,e.payload->>'subject',NULL::text
 FROM sarsa_booking.enquiries e WHERE p_role='client' AND e.verified_at IS NOT NULL
 UNION ALL
 SELECT 'payment:'||c.id,'payment','needs_review',c.next_check_at,b.request_id::text,b.service_snapshot->>'name',c.reason
 FROM sarsa_booking.payment_cases c JOIN sarsa_booking.bookings b ON b.id=c.booking_id
 WHERE p_role='client' AND c.resolved_at IS NULL
 UNION ALL
 SELECT 'delivery:'||j.id,CASE WHEN j.recipient_role='agency_sheet' THEN 'agency_records'
  WHEN j.recipient_role='client_sheet' THEN 'client_records' WHEN j.recipient_role='calendar' THEN 'meeting' ELSE 'booking_email' END,
  CASE WHEN EXISTS(SELECT 1 FROM sarsa_booking.email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM sarsa_booking.email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))) THEN 'delivery_problem' ELSE j.state END,
  coalesce(j.first_attempt_at,j.next_attempt_at),CASE WHEN p_role='client' THEN b.request_id::text END,
  CASE WHEN p_role='client' THEN b.service_snapshot->>'name' END,j.last_error_code
 FROM sarsa_booking.delivery_jobs j JOIN sarsa_booking.bookings b ON b.id=j.booking_id
 WHERE (j.booking_revision=b.revision OR j.kind IN ('sheet_booking','booking_calendar') OR (j.kind='booking_cancelled' AND j.recipient_role='calendar'))
 AND (p_role='client' OR (p_role='agency' AND j.recipient_role='agency_sheet')) AND
  (j.state IN ('attention','failed','uncertain') OR
   (j.state IN ('pending','processing') AND j.next_attempt_at<statement_timestamp()-interval '5 minutes'
    AND (j.lease_expires_at IS NULL OR j.lease_expires_at<statement_timestamp())) OR
   EXISTS(SELECT 1 FROM sarsa_booking.email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM sarsa_booking.email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))))
 UNION ALL
 SELECT 'enquiry-delivery:'||j.id,CASE WHEN j.kind='agency_sheet' THEN 'agency_records'
  WHEN j.kind='client_sheet' THEN 'client_records' ELSE 'enquiry_email' END,
  CASE WHEN EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))) THEN 'delivery_problem' ELSE j.state END,
  j.created_at,CASE WHEN p_role='client' THEN j.request_id::text END,NULL::text,j.last_error_code
 FROM sarsa_booking.enquiry_delivery_jobs j JOIN sarsa_booking.enquiries e USING(request_id)
 WHERE j.kind<>'verification' AND e.verified_at IS NOT NULL
  AND (p_role='client' OR (p_role='agency' AND j.kind='agency_sheet')) AND
  (j.state IN ('attention','failed','uncertain') OR
   (j.state IN ('pending','processing') AND j.next_attempt_at<statement_timestamp()-interval '5 minutes'
    AND (j.lease_expires_at IS NULL OR j.lease_expires_at<statement_timestamp())) OR
   EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations o WHERE o.job_id=j.id AND (o.event_type IN ('email.bounced','email.complained','email.suppressed') OR (o.event_type='email.failed' AND NOT EXISTS(SELECT 1 FROM sarsa_booking.enquiry_email_observations delivered WHERE delivered.job_id=j.id AND delivered.event_type='email.delivered')))))
$$;


ALTER TABLE sarsa_booking.staff_reviews ADD COLUMN evidence_id uuid REFERENCES sarsa_booking.payment_observations(id);
ALTER TABLE sarsa_booking.staff_reviews ADD CHECK((action='verified_refund')=(evidence_id IS NOT NULL));
CREATE FUNCTION sarsa_booking.studio_inbox_refund_verified(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;prior sarsa_booking.staff_reviews%ROWTYPE;c sarsa_booking.payment_cases%ROWTYPE;b sarsa_booking.bookings%ROWTYPE;
 p sarsa_booking.payment_orders%ROWTYPE;proof sarsa_booking.payment_observations%ROWTYPE;current_revision integer;booking uuid;identity uuid;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^payment:[a-f0-9-]{36}$' OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-staff-review:'||p_item,0));
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM sarsa_booking.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'verified_refund' OR prior.item_key<>p_item OR prior.actor<>actor OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','refund_verified','revision',prior.revision);
 END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM sarsa_booking.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 identity:=split_part(p_item,':',2)::uuid;
 SELECT booking_id INTO booking FROM sarsa_booking.payment_cases WHERE id=identity;
 SELECT * INTO b FROM sarsa_booking.bookings WHERE id=booking FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT * INTO p FROM sarsa_booking.payment_orders WHERE booking_id=booking FOR SHARE;
 SELECT * INTO c FROM sarsa_booking.payment_cases WHERE id=identity FOR UPDATE;
 IF c.resolved_at IS NOT NULL THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT * INTO proof FROM sarsa_booking.payment_observations WHERE booking_id=booking AND merchant_id=p.merchant_id AND mode=p.mode
 AND provider_order_id=p.provider_order_id AND payment_id=split_part(c.event_key,':',1) AND currency=b.currency AND amount_paise>0
 AND refunded_paise=amount_paise AND status='refunded' ORDER BY observed_at DESC,id DESC LIMIT 1;
 IF NOT FOUND OR (b.state='confirmed' AND EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=booking AND payment_id=proof.payment_id AND merchant_id=proof.merchant_id AND mode=proof.mode))
 THEN RETURN jsonb_build_object('code','refund_not_verified');END IF;
 INSERT INTO sarsa_booking.staff_reviews(operation_id,item_key,revision,actor,note,action,evidence_id) VALUES(p_operation,p_item,current_revision+1,actor,p_note,'verified_refund',proof.id);
 UPDATE sarsa_booking.payment_cases SET resolved_at=clock_timestamp(),resolution_actor=actor,
 resolution_note='Verified full refund observation '||proof.id||'. '||p_note WHERE id=identity;
 RETURN jsonb_build_object('code','refund_verified','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_inbox_refund_verified(text,text,text,uuid,text,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_inbox_refund_verified(text,text,text,uuid,text,integer,text) TO sarsa_booking_runtime;
