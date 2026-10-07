-- Booking-code notifications use a local UUID named provider and an inbox
-- column with the same name. Qualify only the three inbox predicates so the
-- actual worker can consume matching signed events without changing identity,
-- ownership, security, permissions or the local UUID's intended uses.
DO $migration$
DECLARE target oid; original text; revised text; definition text;
 anchor text:=$old$WHERE provider=$old$;
 replacement text:=$new$WHERE provider_inbox.provider=$new$;
BEGIN
 SELECT p.oid,p.prosrc INTO STRICT target,original FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='appointment_system'
  AND p.proname='reconcile_booking_code_email_event' AND p.prokind='f';
 IF encode(sha256(convert_to(original,'UTF8')),'hex')
  IS DISTINCT FROM '41e4df9a8570ded7bed4cb3e2739545c95ec902d0cdbbf7bbeb034a080a5a392' THEN
  RAISE EXCEPTION 'booking code event provider source differs; review migration history';
 END IF;
 IF (length(original)-length(replace(original,anchor,'')))<>3*length(anchor) THEN
  RAISE EXCEPTION 'booking code event provider source differs; review migration history';
 END IF;
 revised:=replace(original,anchor,replacement);
 definition:=pg_get_functiondef(target);
 IF position(original IN definition)=0 THEN
  RAISE EXCEPTION 'booking code event function body unavailable';
 END IF;
 EXECUTE replace(definition,original,revised);
END $migration$;
