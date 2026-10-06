-- Group role only: no password or login credential is created in source.
-- A separately provisioned website login can inherit these exact privileges.
CREATE ROLE sarsa_booking_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA sarsa_booking TO sarsa_booking_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA sarsa_booking TO sarsa_booking_runtime;
GRANT INSERT, UPDATE ON sarsa_booking.checkout_contexts,
    sarsa_booking.checkout_admissions, sarsa_booking.bookings,
    sarsa_booking.slot_claims, sarsa_booking.payment_orders,
    sarsa_booking.payment_cases, sarsa_booking.delivery_jobs,
    sarsa_booking.provider_inbox TO sarsa_booking_runtime;
-- Financial observations and accepted-payment ownership are append-only for
-- the website role. Corrections are additional observations, never overwrites.
GRANT INSERT ON sarsa_booking.payment_observations,
    sarsa_booking.accepted_payments TO sarsa_booking_runtime;
GRANT EXECUTE ON FUNCTION sarsa_booking.expire_holds(),
    sarsa_booking.start_order_creation(uuid,uuid),
    sarsa_booking.abandon_unattempted(uuid,uuid) TO sarsa_booking_runtime;
