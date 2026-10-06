-- Preserve an already attempted old order; do not make a new provider attempt.
CREATE OR REPLACE FUNCTION appointment_system.control_guard_order_attempt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE epoch uuid;
BEGIN
 IF TG_OP='INSERT' AND appointment_system.historical_import_allowed() THEN RETURN NEW; END IF;
 IF NEW.attempted_at IS NOT NULL AND (TG_OP='INSERT' OR OLD.attempted_at IS NULL) THEN
  SELECT activation_epoch INTO epoch FROM appointment_system.bookings WHERE id=NEW.booking_id;
  PERFORM appointment_system.control_admission(epoch);
 END IF;
 RETURN NEW;
END $$;
