-- Reading the appointment schedule does not require a payment merchant.
-- Payable admission retains its existing merchant constraints and emergency switch.
ALTER TABLE sarsa_booking.intake_settings
 ADD COLUMN schedule_browsing_open boolean NOT NULL DEFAULT true;

-- Preserve admission identity before classifying a missing payment configuration.
-- The caller first commits admit_checkout; this function serializes matching retries
-- with reservation/cancellation using the existing context -> capacity -> settings order.
CREATE FUNCTION sarsa_booking.reserve_configured_checkout(
 p_context uuid,p_request uuid,p_receipt text,p_fingerprint text,p_input jsonb,p_expected jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,sarsa_booking,pg_temp AS $body$
DECLARE ctx sarsa_booking.checkout_contexts%ROWTYPE;
 a sarsa_booking.checkout_admissions%ROWTYPE;
 settings sarsa_booking.intake_settings%ROWTYPE;
BEGIN
 SELECT * INTO ctx FROM sarsa_booking.checkout_contexts WHERE id=p_context FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('code','context_expired'); END IF;
 SELECT * INTO a FROM sarsa_booking.checkout_admissions WHERE request_id=p_request;
 IF NOT FOUND OR a.context_id IS DISTINCT FROM p_context
  OR a.receipt_digest IS DISTINCT FROM p_receipt OR a.request_fingerprint IS DISTINCT FROM p_fingerprint THEN
  RETURN jsonb_build_object('code','request_conflict');
 END IF;
 -- Existing commitments are independent of today's configuration and retain
 -- their pinned order identity. The original function handles exact replay.
 IF a.outcome='committed' THEN
  RETURN sarsa_booking.reserve_checkout(p_context,p_request,p_receipt,p_fingerprint,p_input);
 END IF;
 IF a.outcome='rejected' THEN RETURN jsonb_build_object('code','request_rejected'); END IF;
 IF ctx.expires_at<=clock_timestamp() THEN RETURN jsonb_build_object('code','context_expired'); END IF;
 PERFORM pg_advisory_xact_lock(4004002);
 SELECT * INTO settings FROM sarsa_booking.intake_settings WHERE singleton FOR SHARE;
 IF NOT FOUND OR p_expected IS NULL OR p_expected IS DISTINCT FROM
  jsonb_build_object('merchant_id',settings.merchant_id,'mode',settings.payment_mode,'credential_version',settings.credential_version) THEN
  UPDATE sarsa_booking.checkout_admissions SET outcome='rejected' WHERE request_id=p_request;
  RETURN jsonb_build_object('code','payment_not_configured');
 END IF;
 RETURN sarsa_booking.reserve_checkout(p_context,p_request,p_receipt,p_fingerprint,p_input);
END $body$;
REVOKE ALL ON FUNCTION sarsa_booking.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.reserve_configured_checkout(uuid,uuid,text,text,jsonb,jsonb) TO sarsa_booking_runtime;
-- Runtime must use the fenced entry point. The security-definer wrapper can
-- invoke the old implementation; no obsolete overload remains an API bypass.
REVOKE EXECUTE ON FUNCTION sarsa_booking.reserve_checkout(uuid,uuid,text,text,jsonb) FROM sarsa_booking_runtime;
