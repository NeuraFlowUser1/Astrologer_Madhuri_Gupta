-- Versioned, minimized financial facts. This function never alters capacity or transfers money.
CREATE TABLE sarsa_booking.financial_resource_facts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id),
 merchant_id text NOT NULL, mode text NOT NULL CHECK(mode IN('test','live')), credential_version text NOT NULL,
 resource_id text NOT NULL CHECK(resource_id ~ '^(rfnd|disp)_[A-Za-z0-9]{1,64}$'),
 provenance text NOT NULL CHECK(provenance IN('signed_webhook','provider_fetch')),
 evidence_hash text NOT NULL CHECK(evidence_hash ~ '^[a-f0-9]{64}$'),
 fact jsonb NOT NULL CHECK(jsonb_typeof(fact)='object' AND octet_length(fact::text)<=4096),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(merchant_id,mode,resource_id,provenance,evidence_hash)
);
CREATE INDEX financial_facts_by_booking ON sarsa_booking.financial_resource_facts(booking_id,observed_at,id);
CREATE TABLE sarsa_booking.financial_resource_states (
 merchant_id text NOT NULL,mode text NOT NULL CHECK(mode IN('test','live')),resource_id text NOT NULL,
 booking_id uuid NOT NULL REFERENCES sarsa_booking.bookings(id), payment_id text NOT NULL,order_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN('refund','dispute')),status text NOT NULL,
 outcome text CHECK(outcome IN('won','lost')), amount_paise bigint NOT NULL CHECK(amount_paise>0),currency text NOT NULL CHECK(currency='INR'),
 fact jsonb NOT NULL,verified boolean NOT NULL,attention_reason text,
 latest_fact_id uuid NOT NULL REFERENCES sarsa_booking.financial_resource_facts(id),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(merchant_id,mode,resource_id)
);
REVOKE ALL ON sarsa_booking.financial_resource_facts,sarsa_booking.financial_resource_states FROM PUBLIC,sarsa_booking_runtime;
GRANT SELECT ON sarsa_booking.financial_resource_facts,sarsa_booking.financial_resource_states TO sarsa_booking_runtime;

CREATE FUNCTION sarsa_booking.observe_financial_resource(p_booking uuid,p_merchant text,p_mode text,p_version text,
 p_fact jsonb,p_provenance text,p_hash text,p_parent jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE owned record;prior sarsa_booking.financial_resource_states%ROWTYPE;previous_fact jsonb;
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
 SELECT o.merchant_id,o.mode,o.credential_version,o.provider_order_id AS order_id,b.amount_paise,b.currency INTO owned FROM sarsa_booking.payment_orders o JOIN sarsa_booking.bookings b ON b.id=o.booking_id
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
 INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,evidence_hash,status,
 amount_paise,currency,refunded_paise) VALUES(gen_random_uuid(),p_booking,p_merchant,p_mode,payment,owned.order_id,parent_hash,
 p_parent->>'status',owned.amount_paise,owned.currency,p_refunded)
 ON CONFLICT(merchant_id,mode,payment_id,evidence_hash) DO NOTHING;
 PERFORM pg_advisory_xact_lock(hashtextextended('project004-financial-resource:'||p_merchant||':'||p_mode||':'||identity,0));
 SELECT * INTO prior FROM sarsa_booking.financial_resource_states WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity FOR UPDATE;
 IF FOUND AND (prior.booking_id,prior.payment_id,prior.order_id,prior.kind,prior.amount_paise,prior.currency,prior.fact->>'created_at') IS DISTINCT FROM
 (p_booking,payment,owned.order_id,family,(p_fact->>'amount')::bigint,'INR',p_fact->>'created_at') THEN
  RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='financial resource association changed';END IF;
 INSERT INTO sarsa_booking.financial_resource_facts(booking_id,merchant_id,mode,credential_version,resource_id,provenance,evidence_hash,fact)
 VALUES(p_booking,p_merchant,p_mode,p_version,identity,p_provenance,p_hash,p_fact) ON CONFLICT DO NOTHING RETURNING id INTO fact_id;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 IF fact_id IS NULL THEN
  SELECT id,fact INTO fact_id,previous_fact FROM sarsa_booking.financial_resource_facts WHERE merchant_id=p_merchant AND mode=p_mode
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
 INSERT INTO sarsa_booking.financial_resource_states(merchant_id,mode,resource_id,booking_id,payment_id,order_id,kind,status,outcome,amount_paise,currency,
  fact,verified,attention_reason,latest_fact_id,observed_at) VALUES(p_merchant,p_mode,identity,p_booking,payment,owned.order_id,family,chosen,outcome,
  (p_fact->>'amount')::bigint,'INR',projection,verified,reason,projection_id,projection_time)
 ON CONFLICT(merchant_id,mode,resource_id) DO UPDATE SET status=excluded.status,outcome=excluded.outcome,fact=excluded.fact,verified=excluded.verified,
  attention_reason=excluded.attention_reason,latest_fact_id=excluded.latest_fact_id,observed_at=excluded.observed_at;
 IF family='refund' AND p_provenance='provider_fetch' THEN
  SELECT coalesce(sum(rs.amount_paise),0) INTO total FROM sarsa_booking.financial_resource_states rs WHERE rs.merchant_id=p_merchant AND rs.mode=p_mode
   AND rs.payment_id=payment AND rs.kind='refund' AND rs.status='processed' AND rs.verified;
  IF total>owned.amount_paise OR total>p_refunded THEN
   reason:='refund_totals_conflict';UPDATE sarsa_booking.financial_resource_states SET attention_reason=reason
     WHERE merchant_id=p_merchant AND mode=p_mode AND resource_id=identity;
  END IF;
 END IF;
 changed:=prior.resource_id IS NULL OR (prior.status,prior.outcome,prior.verified,prior.attention_reason) IS DISTINCT FROM (chosen,outcome,verified,reason);
 reason:=coalesce(reason,'financial_'||family||'_'||chosen);
 IF changed THEN
  INSERT INTO sarsa_booking.payment_cases(id,booking_id,event_key,reason) VALUES(gen_random_uuid(),p_booking,payment||':'||identity,reason) ON CONFLICT(booking_id,event_key) DO UPDATE SET reason=excluded.reason,resolved_at=NULL,resolution_actor=NULL,resolution_note=NULL;
  IF p_provenance='provider_fetch' THEN
   INSERT INTO sarsa_booking.delivery_jobs(id,booking_id,kind,recipient_role,booking_revision,event_key)
   SELECT gen_random_uuid(),p_booking,'payment_review','client',revision,'financial:'||identity||':'||chosen||':'||reason
   FROM sarsa_booking.bookings WHERE id=p_booking ON CONFLICT(kind,booking_id,recipient_role,booking_revision,event_key) DO NOTHING;
  END IF;
 END IF;
 RETURN jsonb_build_object('code','recorded','status',chosen,'outcome',outcome,'verified',verified,'attention_reason',CASE WHEN reason LIKE 'financial_refund_%' OR reason LIKE 'financial_dispute_%' THEN NULL ELSE reason END);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.observe_financial_resource(uuid,text,text,text,jsonb,text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.observe_financial_resource(uuid,text,text,text,jsonb,text,text,jsonb) TO sarsa_booking_runtime;

-- Original signed digest is retained when leasing a resource task.
CREATE OR REPLACE FUNCTION sarsa_booking.claim_payment_events(p_limit integer)
RETURNS jsonb LANGUAGE plpgsql AS $body$
DECLARE result jsonb;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 20 OR p_limit IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event batch';
    END IF;
    WITH due AS (
        SELECT provider,account_id,environment,event_id FROM sarsa_booking.provider_inbox
        WHERE provider='razorpay' AND processed_at IS NULL AND next_attempt_at<=clock_timestamp()
          AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
        ORDER BY next_attempt_at,received_at,event_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), claimed AS (
        UPDATE sarsa_booking.provider_inbox p SET lease_token=gen_random_uuid(),
          lease_expires_at=clock_timestamp()+interval '90 seconds',attempts=p.attempts+1
        FROM due d WHERE (p.provider,p.account_id,p.environment,p.event_id)=(d.provider,d.account_id,d.environment,d.event_id)
        RETURNING p.*
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('provider',provider,'account_id',account_id,
        'environment',environment,'event_id',event_id,'payload',payload,'body_hash',body_hash,'lease_token',lease_token,'attempts',attempts)), '[]'::jsonb)
        INTO result FROM claimed;
    RETURN result;
END
$body$;

-- Full refund closure cannot be used to close a dispute or an uncertain resource.
CREATE OR REPLACE FUNCTION sarsa_booking.studio_inbox_refund_verified(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
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
 IF split_part(c.event_key,':',2) ~ '^disp_' OR c.reason LIKE 'financial_dispute_%'
 OR EXISTS(SELECT 1 FROM sarsa_booking.financial_resource_states f WHERE f.booking_id=booking
  AND f.payment_id=split_part(c.event_key,':',1) AND (NOT f.verified OR f.attention_reason IS NOT NULL OR (f.kind='refund' AND f.status='pending'))) THEN
  RETURN jsonb_build_object('code','refund_not_verified');END IF;

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

-- Minimal resource visibility inherits existing client/company authorization.
ALTER FUNCTION sarsa_booking.studio_inbox_detail(text,text,text,text) RENAME TO studio_inbox_detail_before_resources;
REVOKE ALL ON FUNCTION sarsa_booking.studio_inbox_detail_before_resources(text,text,text,text) FROM PUBLIC,sarsa_booking_runtime;
CREATE FUNCTION sarsa_booking.studio_inbox_detail(p_session text,p_client text,p_origin text,p_item text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE result jsonb;booking uuid;resources jsonb;
BEGIN
 result:=sarsa_booking.studio_inbox_detail_before_resources(p_session,p_client,p_origin,p_item);
 IF result->>'code'<>'ok' OR result#>>'{item,category}'<>'payment' THEN RETURN result;END IF;
 SELECT booking_id INTO booking FROM sarsa_booking.payment_cases WHERE id=split_part(p_item,':',2)::uuid;
 SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) INTO resources FROM
 (SELECT resource_id AS id,kind,status,outcome,amount_paise,currency,verified,attention_reason,
  fact->'respond_by' AS respond_by,fact->'created_at' AS created_at
  FROM sarsa_booking.financial_resource_states WHERE booking_id=booking ORDER BY resource_id LIMIT 20)r;
 result:=jsonb_set(result,'{item,financial_resources}',resources,true);
 RETURN jsonb_set(result,'{item,financial_resource_id}',coalesce((SELECT to_jsonb(split_part(event_key,':',2)) FROM sarsa_booking.payment_cases WHERE id=split_part(p_item,':',2)::uuid),'null'::jsonb),true);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_inbox_detail(text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_inbox_detail(text,text,text,text) TO sarsa_booking_runtime;

ALTER TABLE sarsa_booking.staff_reviews DROP CONSTRAINT staff_reviews_action_check;
ALTER TABLE sarsa_booking.staff_reviews ADD CONSTRAINT staff_reviews_action_check CHECK(action IN('note','retry','verified_refund','resource_reviewed'));
ALTER TABLE sarsa_booking.staff_reviews ADD COLUMN resource_evidence_id uuid REFERENCES sarsa_booking.financial_resource_facts(id);
ALTER TABLE sarsa_booking.staff_reviews ADD CONSTRAINT recorded_resource_review CHECK((action='resource_reviewed')=(resource_evidence_id IS NOT NULL));
CREATE FUNCTION sarsa_booking.studio_inbox_resource_reviewed(p_session text,p_client text,p_origin text,p_operation uuid,p_item text,p_revision integer,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE actor text;prior sarsa_booking.staff_reviews%ROWTYPE;c sarsa_booking.payment_cases%ROWTYPE;f sarsa_booking.financial_resource_states%ROWTYPE;
 current_revision integer;booking uuid;identity uuid;
BEGIN
 actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL OR p_item IS NULL OR p_item !~ '^payment:[a-f0-9-]{36}$' OR p_revision IS NULL OR p_revision<0 OR p_revision>=2147483647
 OR coalesce(length(btrim(p_note)),0) NOT BETWEEN 2 AND 1000 OR p_note ~ '[[:cntrl:]]' THEN RETURN jsonb_build_object('code','invalid_request');END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('sarsa004-staff-review:'||p_item,0));
 IF sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 SELECT * INTO prior FROM sarsa_booking.staff_reviews WHERE operation_id=p_operation;
 IF FOUND THEN
  IF prior.action<>'resource_reviewed' OR prior.item_key<>p_item OR prior.actor<>actor OR prior.note<>p_note OR prior.revision<>p_revision+1 THEN RETURN jsonb_build_object('code','request_conflict');END IF;
  RETURN jsonb_build_object('code','resource_reviewed','revision',prior.revision);
 END IF;
 SELECT coalesce(max(revision),0) INTO current_revision FROM sarsa_booking.staff_reviews WHERE item_key=p_item;
 IF current_revision<>p_revision THEN RETURN jsonb_build_object('code','revision_changed');END IF;
 identity:=split_part(p_item,':',2)::uuid;
 SELECT booking_id INTO booking FROM sarsa_booking.payment_cases WHERE id=identity;
 PERFORM 1 FROM sarsa_booking.payment_orders WHERE booking_id=booking FOR SHARE;
 SELECT * INTO c FROM sarsa_booking.payment_cases WHERE id=identity FOR UPDATE;
 IF NOT FOUND OR c.resolved_at IS NOT NULL THEN RETURN jsonb_build_object('code','item_unavailable');END IF;
 SELECT * INTO f FROM sarsa_booking.financial_resource_states WHERE booking_id=booking AND resource_id=split_part(c.event_key,':',2);
 IF NOT FOUND OR f.kind<>'dispute' OR NOT f.verified OR f.attention_reason IS NOT NULL OR f.status NOT IN('won','lost','closed') THEN
  RETURN jsonb_build_object('code','resource_not_verified');END IF;
 INSERT INTO sarsa_booking.staff_reviews(operation_id,item_key,revision,actor,note,action,resource_evidence_id)
 VALUES(p_operation,p_item,current_revision+1,actor,p_note,'resource_reviewed',f.latest_fact_id);
 UPDATE sarsa_booking.payment_cases SET resolved_at=clock_timestamp(),resolution_actor=actor,
 resolution_note='Recorded dispute outcome '||f.status||' from evidence '||f.latest_fact_id||'. '||p_note WHERE id=identity;
 RETURN jsonb_build_object('code','resource_reviewed','revision',current_revision+1);
EXCEPTION WHEN unique_violation THEN RETURN jsonb_build_object('code','request_conflict');
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_inbox_resource_reviewed(text,text,text,uuid,text,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_inbox_resource_reviewed(text,text,text,uuid,text,integer,text) TO sarsa_booking_runtime;

-- Company writes still require their separate capability, CSRF and fresh sign-in.
CREATE OR REPLACE FUNCTION booking_control.obligation_action(p_session text,p_csrf text,p_client text,p_action text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
DECLARE principal text; target uuid; owned boolean;
 private_origin text:='https://www.sarsajyotishsansthan.com/company/booking-support';
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_action IS NULL OR p_action NOT IN ('lookup','detail','cancel','reschedule','support','verified_refund','resource_reviewed')
  OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 principal:=booking_control.authorize(p_session,'obligation_handler',p_csrf,p_action NOT IN ('lookup','detail'));
 IF booking_control.obligation_actor(p_session,p_client,private_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_action IN ('lookup','support') THEN
  SELECT id INTO target FROM sarsa_booking.bookings WHERE request_id=(p_data->>'reference')::uuid;
 ELSIF p_action IN('verified_refund','resource_reviewed') THEN
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
 ELSIF p_action='resource_reviewed' THEN
  RETURN sarsa_booking.studio_inbox_resource_reviewed(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSE
  RETURN sarsa_booking.studio_inbox_refund_verified(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 END IF;
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

CREATE OR REPLACE FUNCTION booking_control.obligation_summary(p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,booking_control,sarsa_booking,pg_temp AS $$
BEGIN
 PERFORM booking_control.authorize(p_session,'obligation_handler');
 RETURN jsonb_build_object('code','ok','appointments',coalesce((
  SELECT jsonb_agg(row) FROM (SELECT b.request_id AS reference,b.full_name AS name,b.service_snapshot->>'name' AS service,
   b.starts_at,b.ends_at,b.state,b.revision,
   (SELECT id FROM sarsa_booking.slot_claims WHERE booking_id=b.id) AS claim_id
   FROM sarsa_booking.bookings b WHERE EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=b.id)
   AND b.state='confirmed' AND b.ends_at>=clock_timestamp() ORDER BY b.starts_at,b.id LIMIT 50)row),'[]'::jsonb),
  'reviews',coalesce((SELECT jsonb_agg(row) FROM(SELECT c.id AS case_id,b.request_id AS reference,c.reason,f.kind AS resource_kind,f.status AS resource_status,f.verified AS resource_verified,f.attention_reason AS resource_attention,
    coalesce((SELECT max(revision) FROM sarsa_booking.staff_reviews WHERE item_key='payment:'||c.id),0) AS revision
    FROM sarsa_booking.payment_cases c JOIN sarsa_booking.bookings b ON b.id=c.booking_id
    LEFT JOIN sarsa_booking.financial_resource_states f ON f.booking_id=b.id AND f.resource_id=split_part(c.event_key,':',2)
    WHERE c.resolved_at IS NULL ORDER BY c.next_check_at,c.id LIMIT 50)row),'[]'::jsonb));
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

