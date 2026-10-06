-- Versioned, minimized financial facts. This function never alters capacity or transfers money.
CREATE TABLE public.financial_resource_facts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), booking_id uuid NOT NULL REFERENCES public.bookings(id),
 merchant_id text NOT NULL, mode text NOT NULL CHECK(mode IN('test','live')), credential_version text NOT NULL,
 resource_id text NOT NULL CHECK(resource_id ~ '^(rfnd|disp)_[A-Za-z0-9]{1,64}$'),
 provenance text NOT NULL CHECK(provenance IN('signed_webhook','provider_fetch')),
 evidence_hash text NOT NULL CHECK(evidence_hash ~ '^[a-f0-9]{64}$'),
 fact jsonb NOT NULL CHECK(jsonb_typeof(fact)='object' AND octet_length(fact::text)<=4096),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(merchant_id,mode,resource_id,provenance,evidence_hash)
);
CREATE INDEX financial_facts_by_booking ON public.financial_resource_facts(booking_id,observed_at,id);
CREATE TABLE public.financial_resource_states (
 merchant_id text NOT NULL,mode text NOT NULL CHECK(mode IN('test','live')),resource_id text NOT NULL,
 booking_id uuid NOT NULL REFERENCES public.bookings(id), payment_id text NOT NULL,order_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN('refund','dispute')),status text NOT NULL,
 outcome text CHECK(outcome IN('won','lost')), amount_paise bigint NOT NULL CHECK(amount_paise>0),currency text NOT NULL CHECK(currency='INR'),
 fact jsonb NOT NULL,verified boolean NOT NULL,attention_reason text,
 latest_fact_id uuid NOT NULL REFERENCES public.financial_resource_facts(id),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(merchant_id,mode,resource_id)
);
REVOKE ALL ON public.financial_resource_facts,public.financial_resource_states FROM PUBLIC;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='astro_booking_app') THEN GRANT SELECT ON public.financial_resource_facts,public.financial_resource_states TO astro_booking_app; END IF;END $$;

CREATE FUNCTION public.observe_financial_resource(p_booking uuid,p_merchant text,p_mode text,p_version text,
 p_fact jsonb,p_provenance text,p_hash text,p_parent jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE owned record;prior public.financial_resource_states%ROWTYPE;previous_fact jsonb;
 identity text;payment text;family text;state text;chosen text;outcome text;reason text;fact_id uuid;total bigint;
 instant timestamptz:=clock_timestamp();p_refunded bigint;parent_hash text;verified boolean;projection jsonb;projection_id uuid;projection_time timestamptz;changed boolean;inserted integer;
BEGIN
 IF p_booking IS NULL OR p_merchant IS NULL OR p_merchant !~ '^[A-Za-z0-9]{1,64}$' OR p_mode IS NULL OR p_mode NOT IN('test','live')
 OR p_version IS NULL OR length(p_version) NOT BETWEEN 1 AND 128 OR p_provenance IS NULL OR p_provenance NOT IN('signed_webhook','provider_fetch')
 OR p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_fact) IS DISTINCT FROM 'object'
 OR octet_length(p_fact::text)>4096 OR (p_fact->>'version') IS DISTINCT FROM '1'
 OR (SELECT count(*) FROM jsonb_object_keys(p_fact))<>12 OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_fact)k WHERE k NOT IN
 ('version','kind','id','payment_id','status','amount','currency','created_at','updated_at','respond_by','speed_requested','speed_processed'))
 OR coalesce(p_fact->>'amount','') !~ '^[1-9][0-9]{0,9}$' OR coalesce(p_fact->>'created_at','') !~ '^[1-9][0-9]{0,9}$'
 OR jsonb_typeof(p_fact->'amount') IS DISTINCT FROM 'number' OR jsonb_typeof(p_fact->'created_at') IS DISTINCT FROM 'number'
 OR (p_fact->>'amount')::bigint>2147483647 OR (p_fact->>'created_at')::bigint>4102444800
 OR p_fact->>'currency' IS DISTINCT FROM 'INR' THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource';END IF;
 identity:=p_fact->>'id';payment:=p_fact->>'payment_id';family:=p_fact->>'kind';state:=p_fact->>'status';
 IF payment IS NULL OR payment !~ '^pay_[A-Za-z0-9]{1,64}$' OR family IS NULL OR identity IS NULL OR state IS NULL
 OR (family='refund' AND (identity !~ '^rfnd_[A-Za-z0-9]{1,64}$' OR state NOT IN('pending','processed','failed')))
 OR (family='dispute' AND (identity !~ '^disp_[A-Za-z0-9]{1,64}$' OR state NOT IN('open','under_review','won','lost','closed')))
 OR family NOT IN('refund','dispute') THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource identity';END IF;
 FOR projection IN SELECT jsonb_build_object('field',k,'value',p_fact->k) FROM unnest(ARRAY['updated_at','respond_by'])k LOOP
  IF jsonb_typeof(projection->'value')<>'null' AND (jsonb_typeof(projection->'value')<>'number'
   OR projection->>'value' !~ '^[1-9][0-9]{0,9}$' OR (projection->>'value')::bigint NOT BETWEEN (p_fact->>'created_at')::bigint AND 4102444800) THEN
   RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource time';END IF;
 END LOOP;
 IF (family='refund' AND p_fact->>'respond_by' IS NOT NULL)
 OR (family='dispute' AND (p_fact->>'speed_requested' IS NOT NULL OR p_fact->>'speed_processed' IS NOT NULL))
 OR (p_fact->>'speed_requested' IS NOT NULL AND p_fact->>'speed_requested' NOT IN('normal','optimum','instant'))
 OR (p_fact->>'speed_processed' IS NOT NULL AND p_fact->>'speed_processed' NOT IN('normal','optimum','instant')) THEN
  RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial resource metadata';END IF;
 -- Serialize resource projections per original booking. No remote request holds this lock.
 SELECT coalesce(o.merchant_id,p_merchant) AS merchant_id,o.mode,o.credential_version,o.order_id,b.amount_paise,b.currency,o.key_id INTO owned FROM public.payment_orders o JOIN public.bookings b ON b.id=o.booking_id
 WHERE b.id=p_booking FOR UPDATE OF o;
 IF NOT FOUND OR owned.merchant_id IS DISTINCT FROM p_merchant OR owned.mode IS DISTINCT FROM p_mode OR owned.credential_version IS DISTINCT FROM p_version
 OR owned.order_id IS NULL OR (p_fact->>'amount')::bigint>owned.amount_paise OR owned.currency<>'INR' THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial resource ownership mismatch';END IF;
 IF jsonb_typeof(p_parent) IS DISTINCT FROM 'object' OR octet_length(p_parent::text)>2048
 OR (SELECT count(*) FROM jsonb_object_keys(p_parent))<>8
 OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_parent)k WHERE k NOT IN('entity','id','order_id','status','amount','currency','amount_refunded','captured'))
 OR p_parent->>'entity' IS DISTINCT FROM 'payment' OR p_parent->>'id' IS DISTINCT FROM payment
 OR p_parent->>'order_id' IS DISTINCT FROM owned.order_id OR p_parent->>'currency' IS DISTINCT FROM owned.currency
 OR jsonb_typeof(p_parent->'amount') IS DISTINCT FROM 'number' OR coalesce(p_parent->>'amount','') !~ '^[1-9][0-9]{0,9}$'
 OR (p_parent->>'amount')::bigint IS DISTINCT FROM owned.amount_paise
 OR jsonb_typeof(p_parent->'amount_refunded') IS DISTINCT FROM 'number' OR coalesce(p_parent->>'amount_refunded','') !~ '^[0-9]{1,10}$'
 OR (p_parent->>'amount_refunded')::bigint NOT BETWEEN 0 AND owned.amount_paise
 OR jsonb_typeof(p_parent->'captured') IS DISTINCT FROM 'boolean'
 OR p_parent->>'status' IS NULL OR p_parent->>'status' NOT IN('created','authorized','captured','refunded','failed') THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial parent evidence mismatch';END IF;
 p_refunded:=(p_parent->>'amount_refunded')::bigint;
 parent_hash:=encode(sha256(convert_to(p_parent::text,'UTF8')),'hex');
 INSERT INTO public.payment_evidence_journal(id,key_id,mode,payment_id,booking_id,order_id,evidence_hash,status,amount_paise,currency,
 amount_refunded,captured,provenance,observed_at) VALUES(gen_random_uuid(),owned.key_id,p_mode,payment,p_booking,owned.order_id,parent_hash,
 p_parent->>'status',owned.amount_paise,owned.currency,p_refunded,(p_parent->>'captured')::boolean,'provider_fetch',instant)
 ON CONFLICT(key_id,mode,payment_id,evidence_hash) DO NOTHING;
 PERFORM pg_advisory_xact_lock(hashtextextended('project003-financial-resource:'||p_merchant||':'||p_mode||':'||identity,0));
 SELECT * INTO prior FROM public.financial_resource_states WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity FOR UPDATE;
 IF FOUND AND (prior.booking_id,prior.payment_id,prior.order_id,prior.kind,prior.amount_paise,prior.currency,prior.fact->>'created_at') IS DISTINCT FROM
 (p_booking,payment,owned.order_id,family,(p_fact->>'amount')::bigint,'INR',p_fact->>'created_at') THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial resource association changed';END IF;
 INSERT INTO public.financial_resource_facts(booking_id,merchant_id,mode,credential_version,resource_id,provenance,evidence_hash,fact)
 VALUES(p_booking,p_merchant,p_mode,p_version,identity,p_provenance,p_hash,p_fact) ON CONFLICT DO NOTHING RETURNING id INTO fact_id;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 IF fact_id IS NULL THEN
  SELECT id,fact INTO fact_id,previous_fact FROM public.financial_resource_facts WHERE merchant_id=p_merchant AND mode=p_mode
   AND resource_id=identity AND provenance=p_provenance AND evidence_hash=p_hash;
  IF previous_fact IS DISTINCT FROM p_fact THEN RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='financial evidence identity conflict';END IF;
 END IF;
 chosen:=state;projection:=p_fact;verified:=p_provenance='provider_fetch';outcome:=CASE WHEN family='dispute' AND state IN('won','lost') THEN state END;
 IF prior.verified AND p_provenance='signed_webhook' THEN
  chosen:=prior.status;projection:=prior.fact;verified:=true;outcome:=prior.outcome;reason:=prior.attention_reason;
 ELSIF prior.verified AND p_provenance='provider_fetch' THEN
  outcome:=coalesce(outcome,prior.outcome);
  IF (prior.fact->>'updated_at' IS NOT NULL AND p_fact->>'updated_at' IS NOT NULL
      AND (p_fact->>'updated_at')::bigint<(prior.fact->>'updated_at')::bigint)
   OR (family='refund' AND prior.status='processed' AND state<>'processed')
   OR (family='refund' AND prior.status='failed' AND state='pending')
   OR (family='dispute' AND prior.status IN('won','lost','closed') AND state IN('open','under_review'))
   OR (family='dispute' AND prior.status='under_review' AND state='open')
   OR (family='dispute' AND prior.outcome IS NOT NULL AND state IN('won','lost') AND state<>prior.outcome) THEN
    chosen:=prior.status;projection:=prior.fact;outcome:=prior.outcome;reason:='financial_resource_conflict';
  END IF;
 END IF;
 IF NOT verified THEN reason:='signed_resource_unfetched';END IF;
 projection_id:=fact_id;projection_time:=instant;
 IF prior.resource_id IS NOT NULL AND projection=prior.fact AND verified=prior.verified THEN
  projection_id:=prior.latest_fact_id;projection_time:=prior.observed_at;END IF;
 INSERT INTO public.financial_resource_states(merchant_id,mode,resource_id,booking_id,payment_id,order_id,kind,status,outcome,amount_paise,currency,
  fact,verified,attention_reason,latest_fact_id,observed_at) VALUES(p_merchant,p_mode,identity,p_booking,payment,owned.order_id,family,chosen,outcome,
  (p_fact->>'amount')::bigint,'INR',projection,verified,reason,projection_id,projection_time)
 ON CONFLICT(merchant_id,mode,resource_id) DO UPDATE SET status=excluded.status,outcome=excluded.outcome,fact=excluded.fact,verified=excluded.verified,
  attention_reason=excluded.attention_reason,latest_fact_id=excluded.latest_fact_id,observed_at=excluded.observed_at;
 IF family='refund' AND p_provenance='provider_fetch' THEN
  SELECT coalesce(sum(rs.amount_paise),0) INTO total FROM public.financial_resource_states rs WHERE rs.merchant_id=p_merchant AND rs.mode=p_mode
   AND rs.payment_id=payment AND rs.kind='refund' AND rs.status='processed' AND rs.verified;
  IF total>owned.amount_paise OR total>p_refunded THEN
   reason:='refund_totals_conflict';UPDATE public.financial_resource_states SET attention_reason=reason
     WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity;
  END IF;
 END IF;
 changed:=prior.resource_id IS NULL OR (prior.status,prior.outcome,prior.verified,prior.attention_reason) IS DISTINCT FROM (chosen,outcome,verified,reason);
 reason:=coalesce(reason,'financial_'||family||'_'||chosen);
 IF changed THEN
  INSERT INTO public.payment_cases(id,booking_id,key_id,external_reference,kind,created_at) VALUES(gen_random_uuid(),p_booking,owned.key_id,identity,CASE WHEN family='dispute' THEN 'dispute' ELSE 'refund' END,instant) ON CONFLICT(key_id,external_reference,kind) DO UPDATE SET state='open',handled_at=NULL,handled_by=NULL,resolution=NULL,note=NULL;
  IF p_provenance='provider_fetch' THEN
   INSERT INTO public.delivery_jobs(id,dedupe_key,kind,record_id,created_at,next_attempt_at,recipient_role,dispatch_after,message_version)
   VALUES(gen_random_uuid(),'payment_review:'||p_booking||':financial:'||identity||':'||chosen||':'||reason||':client',
    'payment_review',p_booking,instant,instant,'client',instant,1) ON CONFLICT(dedupe_key) DO NOTHING;
  END IF;
 END IF;
 RETURN jsonb_build_object('code','recorded','status',chosen,'outcome',outcome,'verified',verified,'attention_reason',CASE WHEN reason LIKE 'financial_refund_%' OR reason LIKE 'financial_dispute_%' THEN NULL ELSE reason END);
END $$;
REVOKE ALL ON FUNCTION public.observe_financial_resource(uuid,text,text,text,jsonb,text,text,jsonb) FROM PUBLIC;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='astro_booking_app') THEN GRANT EXECUTE ON FUNCTION public.observe_financial_resource(uuid,text,text,text,jsonb,text,text,jsonb) TO astro_booking_app; END IF;END $$;

ALTER TABLE public.payment_events ADD COLUMN resource_fact jsonb CHECK(resource_fact IS NULL OR (jsonb_typeof(resource_fact)='object' AND octet_length(resource_fact::text)<=4096));
ALTER TABLE public.payment_events ADD COLUMN order_id text CHECK(order_id IS NULL OR order_id ~ '^order_[A-Za-z0-9]{1,64}$');
ALTER TABLE public.payment_events ALTER COLUMN payment_id DROP NOT NULL;
ALTER TABLE public.payment_events ADD CONSTRAINT provider_event_reference CHECK(payment_id IS NOT NULL OR order_id IS NOT NULL);
ALTER TABLE public.payment_events ADD COLUMN merchant_scope text GENERATED ALWAYS AS
 (CASE WHEN left(account_id,4)='acc_' THEN substr(account_id,5) ELSE account_id END) STORED;
ALTER TABLE public.payment_events ADD COLUMN mode text GENERATED ALWAYS AS (split_part(key_id,'_',2)) STORED;
ALTER TABLE public.payment_events ADD CONSTRAINT provider_event_scope CHECK(merchant_scope ~ '^[A-Za-z0-9]{1,64}$' AND mode IN('test','live'));
-- If historical duplicates disagree, stop for reconciliation; do not delete or guess.
CREATE UNIQUE INDEX provider_event_account_identity ON public.payment_events(merchant_scope,mode,event_id);

ALTER TABLE public.payment_case_actions ADD COLUMN financial_evidence_id uuid REFERENCES public.financial_resource_facts(id);
