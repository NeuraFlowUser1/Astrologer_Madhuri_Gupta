-- PostgreSQL SELECT FOR SHARE needs UPDATE on at least one column. Grant only
-- the fixed true singleton key: CHECK + PK prohibit changing or adding keys.
-- No runtime ability to change intake mode, merchant or approved policy.
GRANT UPDATE(singleton) ON sarsa_booking.intake_settings TO sarsa_booking_runtime;
