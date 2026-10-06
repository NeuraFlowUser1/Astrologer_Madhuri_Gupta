-- Immutable catalogue history; changing business policy requires a new version.
CREATE TABLE sarsa_booking.booking_policies (
    version text PRIMARY KEY CHECK (version ~ '^[a-f0-9]{64}$'),
    specification jsonb NOT NULL CHECK (jsonb_typeof(specification)='object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sarsa_booking.intake_settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    policy_version text NOT NULL REFERENCES sarsa_booking.booking_policies(version),
    public_open boolean NOT NULL DEFAULT false,
    merchant_id text,
    payment_mode text CHECK (payment_mode IN ('test','live')),
    credential_version text,
    CHECK (NOT public_open OR
      (length(btrim(merchant_id)) > 0 AND payment_mode='live'
       AND length(btrim(credential_version)) > 0
       AND merchant_id IS NOT NULL AND credential_version IS NOT NULL))
);
INSERT INTO sarsa_booking.booking_policies(version,specification) VALUES ('29824fcc90cabd9f8bd3245c787aa4b1694bd6270906fb65ba1eca3c2bd0fcd3','{"project":"004-sarsa-jyotish-sansthan","timezone":"Asia/Kolkata","weekdays":[0,1,2,3,4,5],"windows":[["10:00","12:00"],["15:00","18:00"]],"slot_step_minutes":30,"notice_minutes":30,"advance_days":10,"hold_minutes":10,"receipt_after_hours":24,"availability_authority":"website_staff_calendar","services":[{"id":"kundli-matching","name":"Kundli Matching","amount_paise":210000,"duration_minutes":30,"currency":"INR","meeting_platform":"Google Meet"},{"id":"kundli-prediction","name":"Kundli Prediction","amount_paise":250000,"duration_minutes":30,"currency":"INR","meeting_platform":"Google Meet"},{"id":"vastu-consultation","name":"Vastu Consultation","amount_paise":450000,"duration_minutes":30,"currency":"INR","meeting_platform":"Google Meet"},{"id":"numerology","name":"Numerology","amount_paise":210000,"duration_minutes":30,"currency":"INR","meeting_platform":"Google Meet"}]}'::jsonb);
INSERT INTO sarsa_booking.intake_settings(policy_version) VALUES ('29824fcc90cabd9f8bd3245c787aa4b1694bd6270906fb65ba1eca3c2bd0fcd3');

-- This runtime cannot open intake, change prices or rewrite policy history.
GRANT SELECT ON sarsa_booking.booking_policies,sarsa_booking.intake_settings TO sarsa_booking_runtime;
REVOKE ALL ON sarsa_booking.booking_policies,sarsa_booking.intake_settings FROM PUBLIC;

-- This is a per-context bound, additional to the browser/IP admission limiter.
-- Its transaction MUST commit before attempting the reservation transaction.
CREATE FUNCTION sarsa_booking.admit_checkout(
    p_context uuid, p_request uuid, p_receipt text, p_fingerprint text
) RETURNS text LANGUAGE plpgsql AS $body$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
        admission sarsa_booking.checkout_admissions%ROWTYPE;
        count_recent integer;
BEGIN
    SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
    IF NOT FOUND OR ctx.expires_at <= clock_timestamp() THEN RETURN 'context_expired'; END IF;
    SELECT * INTO admission FROM sarsa_booking.checkout_admissions WHERE request_id=p_request;
    IF FOUND THEN
        IF admission.context_id <> p_context OR admission.receipt_digest <> p_receipt
           OR admission.request_fingerprint <> p_fingerprint THEN RETURN 'request_conflict'; END IF;
        RETURN admission.outcome;
    END IF;
    SELECT count(*) INTO count_recent FROM sarsa_booking.checkout_admissions
      WHERE context_id=p_context AND created_at > clock_timestamp()-interval '1 hour';
    IF count_recent >= 6 THEN RETURN 'rate_limited'; END IF;
    BEGIN
        INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint)
          VALUES (p_request,p_context,p_receipt,p_fingerprint);
    EXCEPTION WHEN unique_violation THEN
        -- A different context raced the globally unique request ID. Never leak
        -- its booking or treat its admission as the current caller's admission.
        RETURN 'request_conflict';
    END;
    RETURN 'pending';
END
$body$;
REVOKE ALL ON FUNCTION sarsa_booking.admit_checkout(uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.admit_checkout(uuid,uuid,text,text) TO sarsa_booking_runtime;
