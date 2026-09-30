-- Run with SET LOCAL ROLE sarsa_booking_web inside a rollback-only transaction.
-- No provider calls, real identities or persistent records.
DO $test$
DECLARE r record; result jsonb;
BEGIN
    IF current_user <> 'sarsa_booking_web' THEN RAISE EXCEPTION 'wrong role'; END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname=current_user;
    IF NOT r.rolcanlogin OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
       OR r.rolreplication OR r.rolbypassrls THEN RAISE EXCEPTION 'elevated login'; END IF;
    IF pg_has_role(current_user,'neon_superuser','MEMBER')
       OR pg_has_role(current_user,'neondb_owner','MEMBER') THEN
        RAISE EXCEPTION 'administrative membership';
    END IF;
    IF NOT pg_has_role(current_user,'sarsa_booking_runtime','USAGE') THEN
        RAISE EXCEPTION 'runtime inheritance missing';
    END IF;
    IF has_database_privilege(current_user,current_database(),'CREATE')
       OR has_schema_privilege(current_user,'public','CREATE')
       OR has_schema_privilege(current_user,'sarsa_booking','CREATE') THEN
        RAISE EXCEPTION 'schema creation allowed';
    END IF;
    IF has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE')
       OR has_table_privilege(current_user,'sarsa_booking.booking_policies','UPDATE')
       OR has_table_privilege(current_user,'sarsa_booking.schema_migrations','SELECT')
       OR has_table_privilege(current_user,'sarsa_booking.bookings','DELETE')
       OR has_table_privilege(current_user,'sarsa_booking.bookings','TRUNCATE')
       OR has_table_privilege(current_user,'sarsa_booking.studio_audit','UPDATE')
       OR has_table_privilege(current_user,'sarsa_booking.payment_observations','UPDATE')
       OR has_function_privilege(current_user,'sarsa_booking.close_calendar(uuid,text,text,timestamp with time zone,timestamp with time zone)','EXECUTE') THEN
        RAISE EXCEPTION 'protected operation allowed';
    END IF;
    BEGIN
        UPDATE sarsa_booking.intake_settings SET public_open=true;
        RAISE EXCEPTION 'intake update was allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        CREATE TABLE sarsa_booking.forbidden_runtime_table(id integer);
        RAISE EXCEPTION 'schema write was allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    result:=sarsa_booking.consume_request_limit('studio',repeat('9',64));
    IF result->>'allowed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'runtime access failed'; END IF;
END
$test$;
