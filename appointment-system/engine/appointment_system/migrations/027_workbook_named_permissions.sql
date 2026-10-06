-- Saved named access is a file-specific approval, never a blanket user/group bypass.
SET ROLE appointment_system_owner;
CREATE FUNCTION appointment_system.valid_workbook_permissions(p_value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path TO 'pg_catalog','appointment_system','pg_temp' AS $$
DECLARE item jsonb; seen text[]:=ARRAY[]::text[]; email text;
BEGIN
 IF jsonb_typeof(p_value)<>'array' OR jsonb_array_length(p_value)>16 THEN RETURN false;END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_value) LOOP
  IF jsonb_typeof(item)<>'object' OR NOT item ?& ARRAY['type','role','emailAddress']
   OR item-ARRAY['type','role','emailAddress']<>'{}'::jsonb
   OR jsonb_typeof(item->'type')<>'string' OR item->>'type' NOT IN('user','group')
   OR jsonb_typeof(item->'role')<>'string' OR item->>'role' NOT IN('reader','commenter','writer')
   OR jsonb_typeof(item->'emailAddress')<>'string' THEN RETURN false;END IF;
  email:=lower(item->>'emailAddress');
  IF length(email)>254 OR email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
   OR email=ANY(seen) THEN RETURN false;END IF;
  seen:=array_append(seen,email);
 END LOOP;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION appointment_system.valid_workbook_permissions(jsonb) FROM PUBLIC;
ALTER TABLE appointment_system.google_workbook_volumes
 ADD COLUMN approved_permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
 ADD CONSTRAINT workbook_named_permissions_valid CHECK(appointment_system.valid_workbook_permissions(approved_permissions));
CREATE OR REPLACE FUNCTION appointment_system.protect_workbook_volume() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'appointment_system', 'pg_temp'
    AS $$
BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.role,NEW.volume_number,NEW.generation,NEW.layout_version,NEW.intent,NEW.subject,NEW.client_id,NEW.created_at,NEW.grant_id,NEW.workbook_protocol,NEW.approved_permissions)
  IS DISTINCT FROM ROW(OLD.role,OLD.volume_number,OLD.generation,OLD.layout_version,OLD.intent,OLD.subject,OLD.client_id,OLD.created_at,OLD.grant_id,OLD.workbook_protocol,OLD.approved_permissions)
  OR (OLD.spreadsheet_id IS NOT NULL AND NEW.spreadsheet_id IS DISTINCT FROM OLD.spreadsheet_id)
  OR (OLD.state='retired' AND NEW.state<>'retired')
  OR (OLD.state='ready' AND NEW.state NOT IN ('ready','retired')) THEN
  RAISE EXCEPTION USING ERRCODE='P0420',MESSAGE='immutable workbook identity';
 END IF;
 RETURN NEW;
END $$;
RESET ROLE;
