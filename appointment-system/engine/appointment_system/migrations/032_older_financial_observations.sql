-- A slower verified provider read may finish after a newer read and after
-- staff resolve its case. Keep both immutable observations, but do not replace
-- the newer projection or erase a resolution for a provably older resource.
-- Missing/equal/newer timestamps still take the existing conflict checks.
-- Preserve the function identity, ownership, permissions and transaction locks.
DO $migration$
DECLARE target oid; original text; revised text; definition text;
 anchor text:=$old$ chosen:=state;projection:=p_fact;verified:=p_provenance='provider_fetch';$old$;
 replacement text:=$new$ IF prior.verified AND p_provenance='provider_fetch'
 AND prior.fact->>'updated_at' IS NOT NULL AND p_fact->>'updated_at' IS NOT NULL
 AND (p_fact->>'updated_at')::bigint<(prior.fact->>'updated_at')::bigint THEN
  RETURN jsonb_build_object('code','recorded','status',prior.status,'outcome',prior.outcome,
   'verified',prior.verified,'attention_reason',prior.attention_reason);
 END IF;
 chosen:=state;projection:=p_fact;verified:=p_provenance='provider_fetch';$new$;
 old_condition text:=$old$IF (prior.fact->>'updated_at' IS NOT NULL AND p_fact->>'updated_at' IS NOT NULL
      AND (p_fact->>'updated_at')::bigint<(prior.fact->>'updated_at')::bigint)
   OR (family='refund' AND prior.status='processed' AND state<>'processed')$old$;
 new_condition text:=$new$IF (family='refund' AND prior.status='processed' AND state<>'processed')$new$;
BEGIN
 SELECT p.oid,p.prosrc INTO STRICT target,original FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='appointment_system' AND p.proname='entry_observe_financial_resource' AND p.prokind='f';
 IF (length(original)-length(replace(original,anchor,'')))<>length(anchor)
 OR (length(original)-length(replace(original,old_condition,'')))<>length(old_condition) THEN
  RAISE EXCEPTION 'financial observation source differs; review migration history';
 END IF;
 revised:=replace(replace(original,anchor,replacement),old_condition,new_condition);
 definition:=pg_get_functiondef(target);
 IF position(original IN definition)=0 THEN RAISE EXCEPTION 'financial observation body unavailable'; END IF;
 EXECUTE replace(definition,original,revised);
END $migration$;
