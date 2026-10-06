-- Imported codes retain their declared historical reader. Normal issuance stays v1.
SET LOCAL ROLE appointment_system_owner;
ALTER TABLE appointment_system.receipt_recoveries DROP CONSTRAINT receipt_recoveries_code_protection;
ALTER TABLE appointment_system.receipt_recoveries ADD CONSTRAINT receipt_recoveries_code_protection
 CHECK((code_format='unclassified' AND code_key_id IS NULL) OR
       (code_format<>'unclassified' AND code_format ~ '^[a-z0-9][a-z0-9-]{0,63}$'
        AND code_key_id IS NOT NULL AND code_key_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$'));
RESET ROLE;
