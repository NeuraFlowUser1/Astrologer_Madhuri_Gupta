-- Separate the whole-installation maintenance barrier from booking mode.
-- 83124/5 is outermost: shared for normal calls, exclusive for restore/setup.
-- 83124/4 retains all existing booking/session/control ordering. Ordinary
-- enquiry admission/verification takes only the outer shared barrier, so OFF
-- publication cannot stall unrelated enquiries. Restore still fences both.
-- Keep every existing function owner, signature, search_path and EXECUTE grant.
DO $migration$
DECLARE f record; body text; revised text; definition text; prefix text;
 maintenance text[]:=ARRAY['configure_installation','control_restore_barrier',
   'control_confirm_restore','control_privacy_replay_apply','privacy_finish_replay'];
 touched text[]:=ARRAY[]::text[];
BEGIN
 FOR f IN SELECT p.oid,p.proname,p.prosrc FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='appointment_system' AND p.prokind='f'
    AND (p.prosrc LIKE '%pg_advisory_xact_lock_shared(83124,4)%'
      OR p.prosrc LIKE '%pg_advisory_xact_lock(83124,4)%')
  ORDER BY p.oid
 LOOP
  body:=f.prosrc;
  IF body LIKE '%pg_advisory_xact_lock_shared(83124,5)%'
    OR body LIKE '%pg_advisory_xact_lock(83124,5)%' THEN
   RAISE EXCEPTION 'maintenance barrier already present; review migration history';
  END IF;
  IF f.proname='require_registered_caller' THEN
   revised:=replace(body,'pg_advisory_xact_lock_shared(83124,4)',
                        'pg_advisory_xact_lock_shared(83124,5)');
  ELSE
   prefix:=CASE WHEN f.proname=ANY(maintenance)
     THEN 'PERFORM pg_advisory_xact_lock(83124,5);'
     ELSE 'PERFORM pg_advisory_xact_lock_shared(83124,5);' END;
   revised:=replace(body,'PERFORM pg_advisory_xact_lock_shared(83124,4);',
     prefix||E'\n PERFORM pg_advisory_xact_lock_shared(83124,4);');
   revised:=replace(revised,'PERFORM pg_advisory_xact_lock(83124,4);',
     prefix||E'\n PERFORM pg_advisory_xact_lock(83124,4);');
  END IF;
  IF revised=body THEN RAISE EXCEPTION 'unrecognised barrier spelling'; END IF;
  definition:=pg_get_functiondef(f.oid);
  IF position(body IN definition)=0 THEN RAISE EXCEPTION 'function body unavailable'; END IF;
  EXECUTE replace(definition,body,revised);
  touched:=array_append(touched,f.proname);
 END LOOP;
 IF NOT (maintenance||ARRAY['require_registered_caller','control_command',
   'entry_control_command','control_finish_publication','entry_control_finish_publication',
   'require_worker_turn']) <@ touched THEN
  RAISE EXCEPTION 'required maintenance/control functions were not reviewed';
 END IF;
END $migration$;
