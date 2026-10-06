-- Metadata belongs to the booking; only its credential digest belongs to admission.
-- Keep the earlier migration immutable and replace the function atomically.
SET LOCAL ROLE appointment_system_owner;
CREATE OR REPLACE FUNCTION appointment_system.redeem_receipt_recovery(p_reference uuid,p_code text,p_receipt text,p_receipt_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_receipt_key IS NULL OR p_receipt_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$' THEN
  RETURN jsonb_build_object('code','access_unavailable'); END IF;
 result:=appointment_system.entry_redeem_receipt_recovery(p_reference,p_code,p_receipt);
 IF result->>'code'='receipt_restored' THEN
  UPDATE appointment_system.bookings SET receipt_format='v1',receipt_key_id=p_receipt_key WHERE request_id=p_reference;
 END IF;
 RETURN result;
END $$;
RESET ROLE;
