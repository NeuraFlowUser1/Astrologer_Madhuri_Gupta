-- Independent refund/dispute follow-up shares the existing financial lane.
ALTER TABLE public.payment_cases ADD COLUMN next_check_at timestamptz NOT NULL DEFAULT clock_timestamp();
ALTER TABLE public.payment_cases ADD COLUMN financial_first_seen timestamptz NOT NULL DEFAULT clock_timestamp();
UPDATE public.payment_cases SET financial_first_seen=created_at;
ALTER TABLE public.payment_cases ADD COLUMN financial_lease_token uuid;
ALTER TABLE public.payment_cases ADD COLUMN financial_lease_until timestamptz;
ALTER TABLE public.payment_cases ADD COLUMN financial_attempts integer NOT NULL DEFAULT 0 CHECK(financial_attempts>=0);
ALTER TABLE public.payment_cases ADD COLUMN financial_error text;
ALTER TABLE public.payment_cases ADD CONSTRAINT paired_financial_lease CHECK((financial_lease_token IS NULL)=(financial_lease_until IS NULL));
CREATE INDEX financial_cases_due ON public.payment_cases(next_check_at,id) WHERE state='open';
CREATE FUNCTION public.claim_financial_resources(p_merchant text,p_mode text,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE result jsonb;inbox_due timestamptz;
BEGIN
 IF p_limit IS NULL OR p_limit<>1 OR (p_merchant IS NOT NULL AND p_merchant !~ '^[A-Za-z0-9]{1,64}$')
 OR (p_mode IS NOT NULL AND p_mode NOT IN('test','live')) THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial claim';END IF;
 SELECT coalesce((SELECT min(next_attempt_at) FROM public.payment_events WHERE processed_at IS NULL AND attempts<12 AND (p_merchant IS NULL OR merchant_scope=p_merchant) AND (p_mode IS NULL OR mode=p_mode)),clock_timestamp()) INTO inbox_due;
 WITH due AS(
  SELECT c.id FROM public.payment_cases c JOIN public.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=c.external_reference
  WHERE c.state='open' AND (NOT f.verified OR f.attention_reason IS NOT NULL OR f.status IN('pending','open','under_review'))
  AND (p_merchant IS NULL OR f.merchant_id=p_merchant) AND (p_mode IS NULL OR f.mode=p_mode)
  AND c.next_check_at<=clock_timestamp() AND c.next_check_at<=inbox_due
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
CREATE FUNCTION public.finish_financial_resource(p_case uuid,p_lease uuid,p_delay integer,p_error text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE changed integer;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 900 AND 86400 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$')
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial completion';END IF;
 UPDATE public.payment_cases SET financial_lease_token=NULL,financial_lease_until=NULL,
  next_check_at=clock_timestamp()+make_interval(secs=>p_delay),financial_error=p_error
 WHERE id=p_case AND financial_lease_token=p_lease AND financial_lease_until>clock_timestamp();
 GET DIAGNOSTICS changed=ROW_COUNT;RETURN changed=1;
END $$;
REVOKE ALL ON FUNCTION public.claim_financial_resources(text,text,integer),public.finish_financial_resource(uuid,uuid,integer,text) FROM PUBLIC;
