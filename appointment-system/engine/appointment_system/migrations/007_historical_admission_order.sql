-- Apply the same narrowly owned import authority to all three linked rows.
-- Ordinary writes retain the exact context-derived activation checks.
CREATE FUNCTION appointment_system.historical_import_allowed() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 RETURN NOT EXISTS(SELECT 1 FROM appointment_system.caller_logins WHERE login_role=session_user)
  AND pg_has_role(session_user,'appointment_system_owner','MEMBER')
  AND EXISTS(SELECT 1 FROM appointment_system.installation i JOIN appointment_system.conversion_handover h
   ON h.installation_id=i.installation_id WHERE i.singleton AND h.phase='fenced'
    AND i.specification#>>'{database_targets,migration,role}'=session_user
    AND i.specification#>>'{database_targets,migration,database}'=current_database());
END $$;
ALTER FUNCTION appointment_system.historical_import_allowed() OWNER TO appointment_system_owner;
REVOKE ALL ON FUNCTION appointment_system.historical_import_allowed() FROM PUBLIC;

CREATE OR REPLACE FUNCTION appointment_system.control_guard_context() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
BEGIN
 IF appointment_system.historical_import_allowed() THEN RETURN NEW; END IF;
 NEW.activation_epoch:=appointment_system.control_admission(NEW.activation_epoch);RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION appointment_system.control_guard_checkout_admission() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE epoch uuid;
BEGIN
 IF appointment_system.historical_import_allowed() THEN RETURN NEW; END IF;
 SELECT activation_epoch INTO epoch FROM appointment_system.checkout_contexts WHERE id=NEW.context_id;
 IF NOT FOUND OR epoch IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0401',MESSAGE='checkout context required'; END IF;
 NEW.activation_epoch:=appointment_system.control_admission(epoch);RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION appointment_system.control_guard_booking() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE epoch uuid;
BEGIN
 IF appointment_system.historical_import_allowed() THEN RETURN NEW; END IF;
 SELECT activation_epoch INTO epoch FROM appointment_system.checkout_contexts WHERE id=NEW.context_id;
 NEW.activation_epoch:=appointment_system.control_admission(epoch);RETURN NEW;
END $$;
