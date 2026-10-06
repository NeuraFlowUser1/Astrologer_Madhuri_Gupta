-- Dedicated website login, initially without a password. The owner sets the
-- password through Neon's protected console and transfers it directly to Vercel.
-- Creating this role with SQL avoids Neon's console-created admin membership.
CREATE ROLE sarsa_booking_web LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD NULL;
GRANT sarsa_booking_runtime TO sarsa_booking_web;
GRANT CONNECT ON DATABASE neondb TO sarsa_booking_web;
ALTER ROLE sarsa_booking_web SET search_path = pg_catalog;
ALTER ROLE sarsa_booking_web SET statement_timeout = '10s';
ALTER ROLE sarsa_booking_web SET lock_timeout = '5s';
ALTER ROLE sarsa_booking_web SET idle_in_transaction_session_timeout = '20s';
-- Only the maintenance owner needs migration history, not customer requests.
REVOKE SELECT ON sarsa_booking.schema_migrations FROM sarsa_booking_runtime;
