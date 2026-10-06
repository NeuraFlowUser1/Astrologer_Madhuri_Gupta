-- One canonical Razorpay MID, without the webhook's acc_ prefix. Otherwise
-- aliases could evade tenant/order uniqueness or strand signed callbacks.
ALTER TABLE sarsa_booking.intake_settings ADD CONSTRAINT canonical_intake_merchant
    CHECK(merchant_id IS NULL OR merchant_id ~ '^[A-Za-z0-9]{1,64}$');
ALTER TABLE sarsa_booking.payment_orders ADD CONSTRAINT canonical_order_merchant
    CHECK(merchant_id ~ '^[A-Za-z0-9]{1,64}$');
ALTER TABLE sarsa_booking.payment_observations ADD CONSTRAINT canonical_observation_merchant
    CHECK(merchant_id ~ '^[A-Za-z0-9]{1,64}$');
ALTER TABLE sarsa_booking.accepted_payments ADD CONSTRAINT canonical_accepted_merchant
    CHECK(merchant_id ~ '^[A-Za-z0-9]{1,64}$');
ALTER TABLE sarsa_booking.provider_inbox ADD CONSTRAINT canonical_inbox_merchant
    CHECK(provider<>'razorpay' OR account_id ~ '^[A-Za-z0-9]{1,64}$');
