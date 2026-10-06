-- Recover opaque action IDs without keeping private form bodies in browser storage.
SET LOCAL ROLE appointment_system_owner;
CREATE FUNCTION appointment_system.studio_pending_result(p_session text,p_client text,p_origin text,p_operation uuid,p_purpose text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO pg_catalog,appointment_system,pg_temp AS $$
DECLARE principal_actor text;principal jsonb;closure appointment_system.staff_calendar_actions%ROWTYPE;review appointment_system.staff_reviews%ROWTYPE;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['staff']);
 IF p_operation IS NULL OR p_purpose IS NULL OR p_purpose NOT IN ('calendar','inbox','enquiry') THEN
  RETURN jsonb_build_object('code','invalid_request'); END IF;
 IF p_purpose='calendar' THEN
  principal_actor:=appointment_system.studio_calendar_actor(p_session,p_client,p_origin);
  IF principal_actor IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
  SELECT * INTO closure FROM appointment_system.staff_calendar_actions WHERE operation_id=p_operation AND staff_calendar_actions.actor=principal_actor;
  IF NOT FOUND THEN RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation); END IF;
  RETURN jsonb_build_object('code',CASE WHEN closure.action='close' THEN 'closed' ELSE 'reopened' END,'operation_id',p_operation);
 END IF;
 principal:=appointment_system.staff_actor(p_session,p_client,p_origin,CASE WHEN p_purpose='enquiry' THEN 'enquiry' ELSE 'booking' END);
 IF principal IS NULL THEN RETURN jsonb_build_object('code','access_unavailable'); END IF;
 SELECT * INTO review FROM appointment_system.staff_reviews WHERE operation_id=p_operation AND staff_reviews.actor=principal->>'actor';
 IF NOT FOUND OR (p_purpose='enquiry' AND review.item_key NOT LIKE 'enquiry:%' AND review.item_key NOT LIKE 'enquiry-delivery:%') THEN
  RETURN jsonb_build_object('code','operation_not_found','operation_id',p_operation); END IF;
 RETURN jsonb_build_object('code',CASE review.action WHEN 'note' THEN 'review_saved' WHEN 'retry' THEN 'retry_queued'
   WHEN 'verified_refund' THEN 'refund_verified' WHEN 'resource_reviewed' THEN 'resource_reviewed' END,
   'revision',review.revision,'operation_id',p_operation);
END $$;
REVOKE ALL ON FUNCTION appointment_system.studio_pending_result(text,text,text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.studio_pending_result(text,text,text,uuid,text) TO appointment_system_staff_access;
RESET ROLE;
