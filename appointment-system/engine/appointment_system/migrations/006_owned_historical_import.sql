-- A controlled historical import is not a payable public admission.
-- Only the separately declared migration owner, inside a recorded fenced
-- handover, may insert existing historical records while the product is OFF.
CREATE OR REPLACE FUNCTION appointment_system.control_guard_booking() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 IF NOT EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user)
  AND pg_has_role(session_user,'appointment_system_owner','MEMBER')
  AND EXISTS(SELECT 1 FROM appointment_system.installation i JOIN appointment_system.conversion_handover h
   ON h.installation_id=i.installation_id WHERE i.singleton AND h.phase='fenced'
    AND i.specification#>>'{database_targets,migration,role}'=session_user
    AND i.specification#>>'{database_targets,migration,database}'=current_database())
 THEN RETURN NEW; END IF;
 PERFORM appointment_system.control_admission(NEW.activation_epoch);
 RETURN NEW;
END $$;
