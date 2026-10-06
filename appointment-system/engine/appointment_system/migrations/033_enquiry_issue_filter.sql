-- The enquiry-only dashboard selects delivery purpose from the item identity.
-- Its displayed categories describe the failed destination (email or records),
-- so comparing that category to 'enquiry-delivery' always returned no issues.
-- Preserve the existing role checks, cursor, page limits and function contract.
DO $migration$
DECLARE target oid; original text; definition text; revised text;
 anchor text:=$old$WHEN p_view='enquiry-issues' THEN i.category='enquiry-delivery'$old$;
 replacement text:=$new$WHEN p_view='enquiry-issues' THEN i.item_key LIKE 'enquiry-delivery:%'$new$;
BEGIN
 SELECT p.oid,p.prosrc INTO STRICT target,original FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='appointment_system' AND p.proname='entry_studio_inbox_list' AND p.prokind='f';
 IF (length(original)-length(replace(original,anchor,'')))<>length(anchor) THEN
  RAISE EXCEPTION 'enquiry issue source differs; review migration history';
 END IF;
 revised:=replace(original,anchor,replacement);
 definition:=pg_get_functiondef(target);
 IF position(original IN definition)=0 THEN RAISE EXCEPTION 'enquiry issue body unavailable'; END IF;
 EXECUTE replace(definition,original,revised);
END $migration$;
