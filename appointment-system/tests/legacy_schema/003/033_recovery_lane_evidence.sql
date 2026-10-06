-- No public/observer read touches this table. Work and the existing rescue
-- plan retain small durable lane evidence; queue publication is not success.
CREATE TABLE public.recovery_lanes(
 lane text PRIMARY KEY CHECK(lane IN ('verification','financial_resources','booking','payment','payment_events','inquiry','sheets','maintenance','control_publication')),
 latest_run uuid,last_attempt_at timestamptz,last_completed_at timestamptz,
 active_until timestamptz,outcome text NOT NULL DEFAULT 'unchecked' CHECK(outcome IN ('unchecked','attempted','completed','failed')),
 processed integer NOT NULL DEFAULT 0 CHECK(processed BETWEEN 0 AND 2)
);
INSERT INTO public.recovery_lanes(lane) SELECT unnest(ARRAY['verification','financial_resources','booking','payment','payment_events','inquiry','sheets','maintenance','control_publication']);
CREATE TABLE public.recovery_lane_incidents(
 lane text NOT NULL REFERENCES public.recovery_lanes(lane),code text NOT NULL CHECK(code IN ('execution_failed','result_invalid','result_stale')),
 first_seen_at timestamptz NOT NULL,last_seen_at timestamptz NOT NULL,occurrences integer NOT NULL CHECK(occurrences>0),PRIMARY KEY(lane,code)
);
CREATE FUNCTION public.begin_recovery_lane(p_lane text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $body$
DECLARE id uuid:=gen_random_uuid();
BEGIN
 UPDATE public.recovery_lanes SET latest_run=id,last_attempt_at=clock_timestamp(),
   active_until=clock_timestamp()+interval '90 seconds',outcome='attempted'
 WHERE lane=p_lane AND (active_until IS NULL OR active_until<=clock_timestamp());
 IF NOT FOUND THEN RETURN NULL; END IF; RETURN id;
END $body$;
CREATE FUNCTION public.finish_recovery_lane(p_lane text,p_run uuid,p_success boolean,p_processed integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $body$
BEGIN
 IF p_success IS NULL OR p_processed IS NULL OR p_processed<0 OR p_processed>1 THEN RETURN false; END IF;
 UPDATE public.recovery_lanes SET outcome=CASE WHEN p_success THEN 'completed' ELSE 'failed' END,
   last_completed_at=CASE WHEN p_success THEN clock_timestamp() ELSE last_completed_at END,processed=p_processed,active_until=NULL
 WHERE lane=p_lane AND latest_run=p_run AND outcome='attempted' AND active_until>clock_timestamp();
 IF NOT FOUND THEN RETURN false; END IF;
 IF NOT p_success THEN
  INSERT INTO public.recovery_lane_incidents(lane,code,first_seen_at,last_seen_at,occurrences)
   VALUES(p_lane,'execution_failed',clock_timestamp(),clock_timestamp(),1) ON CONFLICT(lane,code) DO UPDATE
   SET last_seen_at=excluded.last_seen_at,occurrences=least(2147483647,public.recovery_lane_incidents.occurrences::bigint+1)::integer;
 END IF;RETURN true;
END $body$;
CREATE FUNCTION public.recovery_progress(p_hints jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $body$
DECLARE evidence jsonb;
BEGIN
 IF jsonb_typeof(p_hints) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='recovery manifest invalid'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_hints))<>9 OR
   EXISTS(SELECT 1 FROM jsonb_object_keys(p_hints) k WHERE NOT EXISTS(SELECT 1 FROM public.recovery_lanes WHERE lane=k)) THEN
   RAISE EXCEPTION USING ERRCODE='P0400',MESSAGE='recovery manifest invalid'; END IF;
 -- An empty durable lane is a completed check. Deferred or failed work does
 -- not manufacture completion, and an active attempt cannot be overwritten.
 UPDATE public.recovery_lanes SET outcome='completed',last_attempt_at=clock_timestamp(),last_completed_at=clock_timestamp(),processed=0
 WHERE p_hints->lane='null'::jsonb AND (active_until IS NULL OR active_until<=clock_timestamp());
 SELECT jsonb_object_agg(lane,jsonb_build_object('attempted_at',floor(extract(epoch FROM last_attempt_at)*1000)::bigint,
   'completed_at',floor(extract(epoch FROM last_completed_at)*1000)::bigint,'outcome',outcome,'processed',processed)) INTO evidence FROM public.recovery_lanes;
 RETURN evidence;
END $body$;
REVOKE ALL ON public.recovery_lanes,public.recovery_lane_incidents FROM PUBLIC;
REVOKE ALL ON FUNCTION public.begin_recovery_lane(text),public.finish_recovery_lane(text,uuid,boolean,integer),public.recovery_progress(jsonb) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.begin_recovery_lane(text),public.finish_recovery_lane(text,uuid,boolean,integer) TO astro_booking_control;

-- The split financial lane cannot be held back by unrelated webhook backlog.
CREATE FUNCTION public.claim_financial_resources_v2(p_merchant text,p_mode text,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF p_limit IS NULL OR p_limit<>1 OR (p_merchant IS NOT NULL AND p_merchant !~ '^[A-Za-z0-9]{1,64}$')
 OR (p_mode IS NOT NULL AND p_mode NOT IN('test','live')) THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial claim';END IF;
 WITH due AS(
  SELECT c.id FROM public.payment_cases c JOIN public.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=c.external_reference
  WHERE c.state='open' AND (NOT f.verified OR f.attention_reason IS NOT NULL OR f.status IN('pending','open','under_review'))
  AND (p_merchant IS NULL OR f.merchant_id=p_merchant) AND (p_mode IS NULL OR f.mode=p_mode)
  AND c.next_check_at<=clock_timestamp()
  AND (c.financial_lease_until IS NULL OR c.financial_lease_until<=clock_timestamp())
  ORDER BY c.next_check_at,c.id LIMIT 1 FOR UPDATE OF c SKIP LOCKED
 ),claimed AS(
  UPDATE public.payment_cases c SET financial_lease_token=gen_random_uuid(),financial_lease_until=clock_timestamp()+interval '90 seconds',
   financial_attempts=c.financial_attempts+1 FROM due WHERE c.id=due.id RETURNING c.*
 )SELECT coalesce(jsonb_agg(jsonb_build_object('case_id',c.id,'booking_id',c.booking_id,'lease_token',c.financial_lease_token,
  'attempts',c.financial_attempts,'created_at',c.financial_first_seen,'server_now',clock_timestamp(),'merchant_id',f.merchant_id,'mode',f.mode,
  'credential_version',o.credential_version,'payment_id',f.payment_id,'order_id',o.order_id,'fact',f.fact,'amount_paise',b.amount_paise)), '[]'::jsonb)
 INTO result FROM claimed c JOIN public.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=c.external_reference
 JOIN public.payment_orders o ON o.booking_id=c.booking_id JOIN public.bookings b ON b.id=c.booking_id;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.claim_financial_resources_v2(text,text,integer) FROM PUBLIC;
