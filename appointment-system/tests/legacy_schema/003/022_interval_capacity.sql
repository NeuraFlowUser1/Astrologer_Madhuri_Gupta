-- Preserve accepted slots; extend their protection to the complete interval.
-- Any legacy overlap is a preflight failure, never an instruction to erase one.
ALTER TABLE slot_claims ADD COLUMN ends_at timestamptz;
UPDATE slot_claims s SET ends_at=coalesce((SELECT b.starts_at+make_interval(mins=>b.duration_minutes)
 FROM bookings b WHERE b.id=s.booking_id),s.starts_at+interval '30 minutes');
ALTER TABLE slot_claims ALTER COLUMN ends_at SET NOT NULL;
ALTER TABLE slot_claims ADD CONSTRAINT capacity_positive_interval CHECK(ends_at>starts_at);
ALTER TABLE slot_claims ADD CONSTRAINT capacity_intervals_exclusive
 EXCLUDE USING gist(tstzrange(starts_at,ends_at,'[)') WITH &&);
CREATE FUNCTION bind_capacity_interval() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE expected_end timestamptz; expected_start timestamptz;
BEGIN
 IF NEW.booking_id IS NULL THEN expected_end:=NEW.starts_at+interval '30 minutes';
 ELSE SELECT starts_at,starts_at+make_interval(mins=>duration_minutes) INTO expected_start,expected_end
  FROM public.bookings WHERE id=NEW.booking_id;
  IF NOT FOUND OR NEW.starts_at IS DISTINCT FROM expected_start THEN
   RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='booking interval mismatch'; END IF;
 END IF;
 IF NEW.ends_at IS NOT NULL AND NEW.ends_at IS DISTINCT FROM expected_end THEN
  RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='capacity interval mismatch'; END IF;
 NEW.ends_at:=expected_end;RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION bind_capacity_interval() FROM PUBLIC;
CREATE TRIGGER capacity_interval_binding BEFORE INSERT ON slot_claims
 FOR EACH ROW EXECUTE FUNCTION bind_capacity_interval();
