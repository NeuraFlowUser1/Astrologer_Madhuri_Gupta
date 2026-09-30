-- Private projections and append-only human review. No financial/delivery mutation.
CREATE INDEX enquiries_verified_page ON sarsa_booking.enquiries(request_id) WHERE verified_at IS NOT NULL;
CREATE INDEX delivery_staff_page ON sarsa_booking.delivery_jobs(id) WHERE state IN ('pending','processing','failed','uncertain','attention','accepted','delivered');
CREATE INDEX enquiry_delivery_staff_page ON sarsa_booking.enquiry_delivery_jobs(id) WHERE kind<>'verification';
CREATE TABLE sarsa_booking.staff_reviews (
 operation_id uuid PRIMARY KEY,
 item_key text NOT NULL CHECK(item_key ~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$'),
 revision integer NOT NULL CHECK(revision>0),
 actor text NOT NULL,
 note text NOT NULL CHECK(length(btrim(note)) BETWEEN 2 AND 1000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(item_key,revision)
);
REVOKE ALL ON sarsa_booking.staff_reviews FROM PUBLIC,sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.staff_actor(p_session text,p_client text,p_origin text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE s sarsa_booking.studio_sessions%ROWTYPE;
BEGIN
 SELECT * INTO s FROM sarsa_booking.studio_sessions WHERE digest=p_session FOR SHARE;
 IF NOT FOUND OR s.client_id IS DISTINCT FROM p_client OR s.origin IS DISTINCT FROM p_origin
  OR s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp()
  OR NOT EXISTS(SELECT 1 FROM sarsa_booking.studio_identities i WHERE i.role=s.role AND i.subject=s.subject)
 THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('role',s.role,'actor',s.role||':'||encode(sha256(convert_to(s.subject,'UTF8')),'hex'));
END $$;

CREATE FUNCTION sarsa_booking.staff_items(p_role text)
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
 WHERE (j.booking_revision=b.revision OR (j.kind='booking_cancelled' AND j.recipient_role='calendar'))
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

CREATE FUNCTION sarsa_booking.studio_inbox_list(p_session text,p_client text,p_origin text,p_view text,p_after text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE a jsonb;result jsonb;
BEGIN
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL OR (p_view='enquiries' AND a->>'role'<>'client') THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_view IS NULL OR p_view NOT IN ('enquiries','issues') OR (p_after IS NOT NULL AND p_after !~ '^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$') THEN RETURN jsonb_build_object('code','invalid_request'); END IF;
 WITH page AS (
 SELECT i.*,coalesce((SELECT max(r.revision) FROM sarsa_booking.staff_reviews r WHERE r.item_key=i.item_key),0) review_revision
 FROM sarsa_booking.staff_items(a->>'role') i WHERE (i.category='enquiry')=(p_view='enquiries')
 AND (p_after IS NULL OR i.item_key>p_after) ORDER BY i.item_key LIMIT 51
 ),shown AS (SELECT * FROM page ORDER BY item_key LIMIT 50)
 SELECT jsonb_build_object('code','ok','view',p_view,'items',coalesce((SELECT jsonb_agg(to_jsonb(shown) ORDER BY item_key) FROM shown),'[]'::jsonb),
  'next_cursor',CASE WHEN (SELECT count(*) FROM page)>50 THEN (SELECT item_key FROM shown ORDER BY item_key DESC LIMIT 1) END) INTO result;
 RETURN result;
END $$;

CREATE FUNCTION sarsa_booking.studio_inbox_detail(p_session text,p_client text,p_origin text,p_item text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE a jsonb;item record;result jsonb;
BEGIN
 a:=sarsa_booking.staff_actor(p_session,p_client,p_origin);
 IF a IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO item FROM sarsa_booking.staff_items(a->>'role') WHERE item_key=p_item;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','item_unavailable'); END IF;
 result:=to_jsonb(item)||jsonb_build_object('review_revision',coalesce((SELECT max(revision) FROM sarsa_booking.staff_reviews WHERE item_key=p_item),0),
  'reviews',coalesce((SELECT jsonb_agg(x ORDER BY x.revision DESC) FROM
    (SELECT revision,split_part(actor,':',1) role,note,created_at FROM sarsa_booking.staff_reviews WHERE item_key=p_item ORDER BY revision DESC LIMIT 20) x),'[]'::jsonb));
 IF item.category='enquiry' THEN
  result:=result||jsonb_build_object('enquiry',(SELECT payload FROM sarsa_booking.enquiries WHERE request_id=item.reference::uuid AND verified_at IS NOT NULL));
 END IF;
 RETURN jsonb_build_object('code','ok','item',result);
END $$;

CREATE FUNCTION sarsa_booking.studio_inbox_review(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
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
  IF prior.item_key<>p_item OR prior.actor<>a->>'actor' OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict'); END IF;
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
REVOKE ALL ON FUNCTION sarsa_booking.staff_actor(text,text,text),sarsa_booking.staff_items(text),
 sarsa_booking.studio_inbox_list(text,text,text,text,text),sarsa_booking.studio_inbox_detail(text,text,text,text),
 sarsa_booking.studio_inbox_review(text,text,text,uuid,text,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_inbox_list(text,text,text,text,text),
 sarsa_booking.studio_inbox_detail(text,text,text,text),sarsa_booking.studio_inbox_review(text,text,text,uuid,text,integer,text) TO sarsa_booking_runtime;
