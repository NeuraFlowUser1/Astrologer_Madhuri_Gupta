-- Serialize customer recovery claims/completion with OFF and isolated restore.
-- Keep worker completion authority separate; no provider I/O is in this lock.
CREATE OR REPLACE FUNCTION appointment_system.claim_checkout_resume(p_booking uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE context uuid; result jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 IF appointment_system.control_admission(NULL) IS NULL THEN RETURN NULL; END IF;
 SELECT context_id INTO context FROM appointment_system.bookings WHERE id=p_booking;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 PERFORM 1 FROM appointment_system.bookings WHERE id=p_booking FOR UPDATE;
 result:=appointment_system.entry_claim_checkout_resume(p_booking);
 IF result IS NOT NULL THEN
  UPDATE appointment_system.payment_orders SET resume_lease_token=lease_token
   WHERE booking_id=p_booking AND lease_token=(result->>'lease_token')::uuid;
 END IF;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION appointment_system.finish_checkout_resume(p_booking uuid,p_lease uuid,p_delay integer,p_cursor integer,p_skip integer,p_error text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE context uuid; changed boolean;
BEGIN
 PERFORM pg_advisory_xact_lock_shared(83124,4);
 PERFORM appointment_system.require_registered_caller(ARRAY['web']);
 SELECT context_id INTO context FROM appointment_system.bookings WHERE id=p_booking;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM 1 FROM appointment_system.checkout_contexts WHERE id=context FOR UPDATE;
 PERFORM 1 FROM appointment_system.bookings WHERE id=p_booking FOR UPDATE;
 PERFORM 1 FROM appointment_system.payment_orders WHERE booking_id=p_booking
  AND lease_token=p_lease AND resume_lease_token=p_lease AND lease_expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 changed:=appointment_system.entry_finish_payment_recovery(p_booking,p_lease,p_delay,p_cursor,p_skip,p_error);
 IF changed THEN UPDATE appointment_system.payment_orders SET resume_lease_token=NULL WHERE booking_id=p_booking; END IF;
 RETURN changed;
END $$;
