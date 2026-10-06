-- Independent refund/dispute follow-up shares the existing financial lane.
ALTER TABLE sarsa_booking.payment_cases ADD COLUMN financial_first_seen timestamptz NOT NULL DEFAULT clock_timestamp();
UPDATE sarsa_booking.payment_cases c SET financial_first_seen=(SELECT min(observed_at) FROM sarsa_booking.financial_resource_facts f WHERE f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2)) WHERE EXISTS(SELECT 1 FROM sarsa_booking.financial_resource_facts f WHERE f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2));
ALTER TABLE sarsa_booking.payment_cases ADD COLUMN financial_lease_token uuid;
ALTER TABLE sarsa_booking.payment_cases ADD COLUMN financial_lease_until timestamptz;
ALTER TABLE sarsa_booking.payment_cases ADD COLUMN financial_attempts integer NOT NULL DEFAULT 0 CHECK(financial_attempts>=0);
ALTER TABLE sarsa_booking.payment_cases ADD COLUMN financial_error text;
ALTER TABLE sarsa_booking.payment_cases ADD CONSTRAINT paired_financial_lease CHECK((financial_lease_token IS NULL)=(financial_lease_until IS NULL));
CREATE INDEX financial_cases_due ON sarsa_booking.payment_cases(next_check_at,id) WHERE resolved_at IS NULL;
CREATE FUNCTION sarsa_booking.claim_financial_resources(p_merchant text,p_mode text,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE result jsonb;inbox_due timestamptz;
BEGIN
 IF p_limit IS NULL OR p_limit<>1 OR (p_merchant IS NOT NULL AND p_merchant !~ '^[A-Za-z0-9]{1,64}$')
 OR (p_mode IS NOT NULL AND p_mode NOT IN('test','live')) THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial claim';END IF;
 SELECT coalesce((SELECT min(next_attempt_at) FROM sarsa_booking.provider_inbox WHERE provider='razorpay' AND processed_at IS NULL AND (p_merchant IS NULL OR account_id=p_merchant) AND (p_mode IS NULL OR environment=p_mode)),clock_timestamp()) INTO inbox_due;
 WITH due AS(
  SELECT c.id FROM sarsa_booking.payment_cases c JOIN sarsa_booking.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2)
  WHERE c.resolved_at IS NULL AND (NOT f.verified OR f.attention_reason IS NOT NULL OR f.status IN('pending','open','under_review'))
  AND (p_merchant IS NULL OR f.merchant_id=p_merchant) AND (p_mode IS NULL OR f.mode=p_mode)
  AND c.next_check_at<=clock_timestamp() AND c.next_check_at<=inbox_due
  AND (c.financial_lease_until IS NULL OR c.financial_lease_until<=clock_timestamp())
  ORDER BY c.next_check_at,c.id LIMIT 1 FOR UPDATE OF c SKIP LOCKED
 ),claimed AS(
  UPDATE sarsa_booking.payment_cases c SET financial_lease_token=gen_random_uuid(),financial_lease_until=clock_timestamp()+interval '90 seconds',
   financial_attempts=c.financial_attempts+1 FROM due WHERE c.id=due.id RETURNING c.*
 )SELECT coalesce(jsonb_agg(jsonb_build_object('case_id',c.id,'booking_id',c.booking_id,'lease_token',c.financial_lease_token,
  'attempts',c.financial_attempts,'created_at',c.financial_first_seen,'server_now',clock_timestamp(),'merchant_id',f.merchant_id,'mode',f.mode,
  'credential_version',o.credential_version,'payment_id',f.payment_id,'order_id',o.provider_order_id,'fact',f.fact,'amount_paise',b.amount_paise,'context_id',b.context_id)), '[]'::jsonb)
 INTO result FROM claimed c JOIN sarsa_booking.financial_resource_states f ON f.booking_id=c.booking_id AND f.resource_id=split_part(c.event_key,':',2)
 JOIN sarsa_booking.payment_orders o ON o.booking_id=c.booking_id JOIN sarsa_booking.bookings b ON b.id=c.booking_id;
 RETURN result;
END $$;
CREATE FUNCTION sarsa_booking.finish_financial_resource(p_case uuid,p_lease uuid,p_delay integer,p_error text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,pg_temp AS $$
DECLARE changed integer;
BEGIN
 IF p_delay IS NULL OR p_delay NOT BETWEEN 900 AND 86400 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$')
 THEN RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid financial completion';END IF;
 UPDATE sarsa_booking.payment_cases SET financial_lease_token=NULL,financial_lease_until=NULL,
  next_check_at=clock_timestamp()+make_interval(secs=>p_delay),financial_error=p_error
 WHERE id=p_case AND financial_lease_token=p_lease AND financial_lease_until>clock_timestamp();
 GET DIAGNOSTICS changed=ROW_COUNT;RETURN changed=1;
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.claim_financial_resources(text,text,integer),sarsa_booking.finish_financial_resource(uuid,uuid,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.claim_financial_resources(text,text,integer),sarsa_booking.finish_financial_resource(uuid,uuid,integer,text) TO sarsa_booking_runtime;

CREATE OR REPLACE FUNCTION sarsa_booking.finish_payment_recovery(p_booking uuid,p_lease uuid,p_delay integer,p_cursor integer,p_skip integer,p_error text)
RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 86400 OR p_delay IS NULL OR p_cursor IS NULL OR p_cursor<0 OR p_skip IS NULL OR p_skip<0 OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid recovery delay';
    END IF;
    UPDATE sarsa_booking.payment_orders SET lease_token=NULL,lease_expires_at=NULL,
      next_check_at=clock_timestamp()+make_interval(secs=>p_delay),recovery_cursor=p_cursor,order_search_skip=p_skip,recovery_followup=(p_cursor>0 OR p_error IS NOT NULL OR EXISTS(SELECT 1 FROM sarsa_booking.payment_cases c WHERE c.booking_id=p_booking AND c.resolved_at IS NULL)),last_recovery_error=p_error
      WHERE booking_id=p_booking AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;

CREATE OR REPLACE FUNCTION sarsa_booking.finish_payment_event(
    p_account text,p_mode text,p_event text,p_lease uuid,p_done boolean,p_delay integer,p_error text
) RETURNS boolean LANGUAGE plpgsql AS $body$
DECLARE changed integer;
BEGIN
    IF p_delay NOT BETWEEN 15 AND 86400 OR p_delay IS NULL OR p_done IS NULL
       OR (p_error IS NOT NULL AND p_error !~ '^[a-z_]{1,80}$') THEN
        RAISE EXCEPTION USING ERRCODE='P0503',MESSAGE='invalid event outcome';
    END IF;
    UPDATE sarsa_booking.provider_inbox SET lease_token=NULL,lease_expires_at=NULL,
      processed_at=CASE WHEN p_done THEN clock_timestamp() ELSE NULL END,
      next_attempt_at=clock_timestamp()+make_interval(secs=>p_delay),last_error_code=p_error
      WHERE provider='razorpay' AND account_id=p_account AND environment=p_mode AND event_id=p_event
        AND lease_token=p_lease AND lease_expires_at>clock_timestamp();
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed=1;
END
$body$;

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
        'environment',environment,'event_id',event_id,'payload',payload,'body_hash',body_hash,'received_at',received_at,'server_now',clock_timestamp(),'lease_token',lease_token,'attempts',attempts)), '[]'::jsonb)
        INTO result FROM claimed;
    RETURN result;
END
$body$;

