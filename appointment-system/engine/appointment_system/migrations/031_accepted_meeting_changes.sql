-- Meeting defaults apply to new bookings. Moves/cancellations must use the
-- choice saved with the accepted appointment, including its exact cleanup.
-- Replace only the reviewed enqueue predicates; retain transaction ordering,
-- signatures, owner, fixed search_path and existing EXECUTE permissions.
DO $migration$
DECLARE target oid; name text; original text; revised text; definition text;
 cleanup text:=$old$VALUES(gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot)$old$;
 saved_cleanup text:=$new$SELECT gen_random_uuid(),b.id,'booking_cancelled','calendar',b.revision,old_snapshot
 WHERE b.service_snapshot->>'meeting'='google_meet'$new$;
 old_default text:=$old$OR spec->>'meeting'='google_meet'$old$;
 saved_default text:=$new$OR b.service_snapshot->>'meeting'='google_meet'$new$;
BEGIN
 FOREACH name IN ARRAY ARRAY['entry_studio_appointment_reschedule','entry_studio_appointment_cancel'] LOOP
  SELECT p.oid,p.prosrc INTO STRICT target,original FROM pg_proc p
   JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='appointment_system' AND p.proname=name AND p.prokind='f';
  IF (length(original)-length(replace(original,cleanup,'')))<>length(cleanup) THEN
   RAISE EXCEPTION 'saved meeting cleanup source differs; review migration history';
  END IF;
  revised:=replace(original,cleanup,saved_cleanup);
  IF name='entry_studio_appointment_reschedule' THEN
   IF (length(original)-length(replace(original,old_default,'')))<>length(old_default) THEN
    RAISE EXCEPTION 'saved meeting reschedule source differs; review migration history';
   END IF;
   revised:=replace(revised,old_default,saved_default);
  END IF;
  definition:=pg_get_functiondef(target);
  IF position(original IN definition)=0 THEN RAISE EXCEPTION 'saved meeting function body unavailable'; END IF;
  EXECUTE replace(definition,original,revised);
 END LOOP;
END $migration$;
