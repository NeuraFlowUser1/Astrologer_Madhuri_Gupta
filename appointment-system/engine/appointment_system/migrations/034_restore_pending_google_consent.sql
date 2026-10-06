-- Expire unfinished Google resource approval using its existing terminal enum.
-- Replace only the restore body anchor; preserve the same function identity,
-- owner, access grants, security settings, locking and all other recovery work.
DO $migration$
DECLARE target oid; original text; definition text; revised text;
 anchor text:=$old$encrypted_grant=NULL,result=jsonb_build_object('code','restore_invalidated') WHERE finished_at IS NULL;$old$;
 replacement text:=$new$encrypted_grant=NULL,result='changed' WHERE finished_at IS NULL;$new$;
BEGIN
 SELECT p.oid,p.prosrc INTO STRICT target,original FROM pg_proc p
 JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='appointment_system' AND p.proname='control_restore_barrier' AND p.prokind='f';
 IF (length(original)-length(replace(original,anchor,'')))<>length(anchor) THEN
  RAISE EXCEPTION 'restore consent source differs; review migration history';
 END IF;
 revised:=replace(original,anchor,replacement);
 definition:=pg_get_functiondef(target);
 IF position(original IN definition)=0 THEN RAISE EXCEPTION 'restore consent body unavailable'; END IF;
 EXECUTE replace(definition,original,revised);
END $migration$;
