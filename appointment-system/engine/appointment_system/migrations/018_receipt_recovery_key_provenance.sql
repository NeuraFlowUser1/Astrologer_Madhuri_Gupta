-- Retain the key used for an issued support code and update replacement receipt metadata.
-- Existing unclassified rows are not assigned invented keys; legacy conversion must supply provenance.
SET LOCAL ROLE appointment_system_owner;
ALTER TABLE appointment_system.receipt_recoveries ADD COLUMN code_format text NOT NULL DEFAULT 'unclassified';
ALTER TABLE appointment_system.receipt_recoveries ADD COLUMN code_key_id text;
ALTER TABLE appointment_system.receipt_recoveries ADD CONSTRAINT receipt_recoveries_code_protection
 CHECK((code_format='unclassified' AND code_key_id IS NULL) OR
       (code_format='v1' AND code_key_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$' AND code_key_id IS NOT NULL));

CREATE FUNCTION appointment_system.recovery_protection(p_reference uuid,p_operation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE item appointment_system.receipt_recoveries%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web','staff','company']);
 IF p_reference IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO item FROM appointment_system.receipt_recoveries WHERE request_id=p_reference
  AND ((p_operation IS NOT NULL AND operation_id=p_operation) OR
       (p_operation IS NULL AND superseded_at IS NULL)) ORDER BY created_at DESC,operation_id DESC LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('format',item.code_format,'key_id',item.code_key_id);
END $$;
REVOKE ALL ON FUNCTION appointment_system.recovery_protection(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.recovery_protection(uuid,uuid) TO appointment_system_web_access,appointment_system_staff_access,appointment_system_company_access;

CREATE FUNCTION appointment_system.studio_support_change(p_session text,p_client text,p_origin text,p_operation uuid,
 p_reference uuid,p_revision integer,p_action text,p_reason text,p_payment text,p_email text,p_phone text,p_digest text,p_code_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE result jsonb;previous appointment_system.receipt_recoveries%ROWTYPE;existed boolean;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['staff','company']);
 IF p_operation IS NULL OR p_code_key IS NULL OR p_code_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$' THEN
  RETURN jsonb_build_object('code','invalid_change'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('support-operation:'||p_operation::text,0));
 SELECT * INTO previous FROM appointment_system.receipt_recoveries WHERE operation_id=p_operation;existed:=FOUND;
 IF existed AND (previous.code_format<>'v1' OR previous.code_key_id IS DISTINCT FROM p_code_key) THEN
  RETURN jsonb_build_object('code','request_conflict'); END IF;
 result:=appointment_system.entry_studio_support_change(p_session,p_client,p_origin,p_operation,p_reference,p_revision,
  p_action,p_reason,p_payment,p_email,p_phone,p_digest);
 IF result->>'code'='support_saved' AND NOT existed THEN
  UPDATE appointment_system.receipt_recoveries SET code_format='v1',code_key_id=p_code_key WHERE operation_id=p_operation;
 END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text,text) TO appointment_system_staff_access,appointment_system_company_access;
REVOKE EXECUTE ON FUNCTION appointment_system.studio_support_change(text,text,text,uuid,uuid,integer,text,text,text,text,text,text) FROM appointment_system_staff_access,appointment_system_company_access;

CREATE FUNCTION appointment_system.redeem_receipt_recovery(p_reference uuid,p_code text,p_receipt text,p_receipt_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF p_receipt_key IS NULL OR p_receipt_key !~ '^[a-z0-9][a-z0-9_-]{0,31}$' THEN
  RETURN jsonb_build_object('code','access_unavailable'); END IF;
 result:=appointment_system.entry_redeem_receipt_recovery(p_reference,p_code,p_receipt);
 IF result->>'code'='receipt_restored' THEN
  UPDATE appointment_system.checkout_admissions SET receipt_format='v1',receipt_key_id=p_receipt_key WHERE request_id=p_reference;
 END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text,text) TO appointment_system_web_access;
REVOKE EXECUTE ON FUNCTION appointment_system.redeem_receipt_recovery(uuid,text,text) FROM appointment_system_web_access;

CREATE OR REPLACE FUNCTION appointment_system.entry_control_obligation_action(p_session text, p_csrf text, p_client text, p_action text, p_data jsonb) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
DECLARE principal text; target uuid; owned boolean;
 private_origin text:=(appointment_system.installation_value('origin')||'/company/booking-support');
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF p_action IS NULL OR p_action NOT IN ('lookup','detail','cancel','reschedule','support','verified_refund','resource_reviewed')
  OR jsonb_typeof(p_data) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
 principal:=appointment_system.control_authorize(p_session,'obligation_handler',p_csrf,p_action NOT IN ('lookup','detail'));
 IF appointment_system.control_obligation_actor(p_session,p_client,private_origin) IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 IF p_action IN ('lookup','support') THEN
  SELECT id INTO target FROM appointment_system.bookings WHERE request_id=(p_data->>'reference')::uuid;
 ELSIF p_action IN('verified_refund','resource_reviewed') THEN
  SELECT booking_id INTO target FROM appointment_system.payment_cases WHERE id=(p_data->>'case_id')::uuid;
 ELSE SELECT booking_id INTO target FROM appointment_system.slot_claims WHERE id=(p_data->>'claim_id')::uuid; END IF;
 owned:=EXISTS(SELECT 1 FROM appointment_system.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM appointment_system.payment_cases WHERE booking_id=target);
 IF target IS NULL OR NOT owned THEN RETURN jsonb_build_object('code','booking_unavailable'); END IF;
 IF p_action='lookup' THEN
  RETURN appointment_system.studio_booking_lookup(p_session,p_client,private_origin,(p_data->>'reference')::uuid);
 ELSIF p_action='detail' THEN
  RETURN appointment_system.studio_appointment_detail(p_session,p_client,private_origin,(p_data->>'claim_id')::uuid);
 ELSIF p_action='cancel' THEN
  RETURN appointment_system.studio_appointment_cancel(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSIF p_action='reschedule' THEN
  RETURN appointment_system.studio_appointment_reschedule(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'claim_id')::uuid,(p_data->>'expected_revision')::integer,p_data->>'reason',(p_data->>'starts_at')::timestamptz);
 ELSIF p_action='support' THEN
  IF p_data->'verification_confirmed' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('code','invalid_change'); END IF;
  RETURN appointment_system.studio_support_change(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   (p_data->>'reference')::uuid,(p_data->>'expected_revision')::integer,p_data->>'action',p_data->>'reason',
   p_data->>'verified_payment_id',p_data->>'email',p_data->>'phone',p_data->>'code_digest',p_data->>'code_key_id');
 ELSIF p_action='resource_reviewed' THEN
  RETURN appointment_system.studio_inbox_resource_reviewed(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 ELSE
  RETURN appointment_system.studio_inbox_refund_verified(p_session,p_client,private_origin,(p_data->>'operation_id')::uuid,
   'payment:'||(p_data->>'case_id'),(p_data->>'expected_revision')::integer,p_data->>'reason');
 END IF;
EXCEPTION WHEN SQLSTATE 'P0401' THEN RETURN jsonb_build_object('code','access_unavailable');
END $$;

RESET ROLE;
