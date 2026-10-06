-- PostgreSQL greatest/least ignore NULL arguments. Preserve an empty queue.
CREATE OR REPLACE FUNCTION booking_control.publication_schedule() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,booking_control,pg_temp AS $body$
 SELECT jsonb_build_object('due',
  (SELECT CASE WHEN min(greatest(next_attempt_at,coalesce(lease_until,next_attempt_at))) IS NULL THEN NULL ELSE
    greatest(0,least(900,ceil(extract(epoch FROM min(greatest(next_attempt_at,
      coalesce(lease_until,next_attempt_at)))-statement_timestamp()))))::integer END
   FROM booking_control.publications WHERE state='pending'),
  'attention',EXISTS(SELECT 1 FROM booking_control.publications
   WHERE state='attention' OR (state='pending' AND last_error IS NOT NULL
     AND next_attempt_at<statement_timestamp()-interval '5 minutes')))
$body$;
