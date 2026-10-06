-- Read a committed result by random operation ID. No mutation or customer secret.
CREATE FUNCTION sarsa_booking.studio_action_result(p_session text,p_client text,p_origin text,p_operation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sarsa_booking,booking_control,pg_temp AS $$
DECLARE principal_actor text; appointment sarsa_booking.staff_appointment_actions%ROWTYPE;
 recovery sarsa_booking.receipt_recoveries%ROWTYPE;review sarsa_booking.staff_reviews%ROWTYPE;
 target uuid;reference uuid;matches integer;result jsonb;
BEGIN
 principal_actor:=sarsa_booking.studio_calendar_actor(p_session,p_client,p_origin);
 IF principal_actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable');END IF;
 IF p_operation IS NULL THEN RETURN jsonb_build_object('code','invalid_change');END IF;
 SELECT * INTO appointment FROM sarsa_booking.staff_appointment_actions WHERE operation_id=p_operation AND staff_appointment_actions.actor=principal_actor;
 SELECT * INTO recovery FROM sarsa_booking.receipt_recoveries WHERE operation_id=p_operation AND receipt_recoveries.actor=principal_actor;
 SELECT * INTO review FROM sarsa_booking.staff_reviews WHERE operation_id=p_operation AND staff_reviews.actor=principal_actor;
 matches:=(CASE WHEN appointment.operation_id IS NOT NULL THEN 1 ELSE 0 END)
  +(CASE WHEN recovery.operation_id IS NOT NULL THEN 1 ELSE 0 END)+(CASE WHEN review.operation_id IS NOT NULL THEN 1 ELSE 0 END);
 IF matches=0 THEN RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 IF matches<>1 THEN RETURN jsonb_build_object('code','operation_conflict','operation_id',p_operation);END IF;
 IF appointment.operation_id IS NOT NULL THEN
  target:=appointment.booking_id;
  result:=jsonb_build_object('code',CASE WHEN appointment.action='cancel' THEN 'cancelled' ELSE 'rescheduled' END,
   'revision',appointment.revision,'operation_id',p_operation,'starts_at',appointment.new_starts_at,'ends_at',appointment.new_ends_at);
 ELSIF recovery.operation_id IS NOT NULL THEN
  SELECT id INTO target FROM sarsa_booking.bookings WHERE request_id=recovery.request_id;
  result:=jsonb_build_object('code','support_saved','revision',recovery.revision,'operation_id',p_operation,'reference',recovery.request_id,
   'expires_at',recovery.expires_at,'active',recovery.superseded_at IS NULL AND recovery.redeemed_at IS NULL AND recovery.attempts<5 AND recovery.expires_at>clock_timestamp());
 ELSE
  IF review.item_key NOT LIKE 'payment:%' OR review.action NOT IN('verified_refund','resource_reviewed') THEN
   RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
  SELECT booking_id INTO target FROM sarsa_booking.payment_cases WHERE id=substring(review.item_key FROM 9)::uuid;
  result:=jsonb_build_object('code',CASE WHEN review.action='verified_refund' THEN 'refund_verified' ELSE 'resource_reviewed' END,
   'revision',review.revision,'operation_id',p_operation);
 END IF;
 IF principal_actor LIKE 'company:%' AND NOT(EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=target)
   OR EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=target)) THEN
  RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation);END IF;
 SELECT request_id INTO reference FROM sarsa_booking.bookings WHERE id=target;
 RETURN result||jsonb_build_object('reference',reference);
END $$;
REVOKE ALL ON FUNCTION sarsa_booking.studio_action_result(text,text,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sarsa_booking.studio_action_result(text,text,text,uuid) TO sarsa_booking_runtime;
