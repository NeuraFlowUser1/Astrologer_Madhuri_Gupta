-- Operational backup login; separate from website schema migrations.
-- Run as neondb_owner, only on the selected Sarsa branch. No password is logged.
DO $body$
BEGIN
 IF current_user <> 'neondb_owner' OR current_database() <> 'neondb'
    OR to_regclass('sarsa_booking.schema_migrations') IS NULL THEN
  RAISE EXCEPTION 'Unexpected backup provisioning target';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='sarsa_booking_backup') THEN
  RAISE EXCEPTION 'Backup role already exists; inspect rather than overwrite';
 END IF;
 CREATE ROLE sarsa_booking_backup LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
   NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD NULL;
END $body$;
GRANT CONNECT ON DATABASE neondb TO sarsa_booking_backup;
GRANT USAGE ON SCHEMA sarsa_booking TO sarsa_booking_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA sarsa_booking TO sarsa_booking_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA sarsa_booking TO sarsa_booking_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA sarsa_booking
 GRANT SELECT ON TABLES TO sarsa_booking_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA sarsa_booking
 GRANT SELECT ON SEQUENCES TO sarsa_booking_backup;
ALTER ROLE sarsa_booking_backup SET search_path=pg_catalog;
ALTER ROLE sarsa_booking_backup SET default_transaction_read_only=on;
ALTER ROLE sarsa_booking_backup SET statement_timeout='120s';
ALTER ROLE sarsa_booking_backup SET lock_timeout='10s';
ALTER ROLE sarsa_booking_backup SET idle_in_transaction_session_timeout='30s';
DO $body$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='sarsa_booking' AND c.relkind IN ('r','p') AND
   (NOT has_table_privilege('sarsa_booking_backup',c.oid,'SELECT') OR
    has_table_privilege('sarsa_booking_backup',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER'))) THEN
  RAISE EXCEPTION 'Backup read permissions are not isolated';
 END IF;
 IF has_schema_privilege('sarsa_booking_backup','sarsa_booking','CREATE') OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='sarsa_booking_backup')) OR
    EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='sarsa_booking' AND p.prosecdef AND
        has_function_privilege('sarsa_booking_backup',p.oid,'EXECUTE')) THEN
  RAISE EXCEPTION 'Backup role has unexpected privileged access';
 END IF;
END $body$;
