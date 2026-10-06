-- Persist identities and digests, never a second copy of private source rows.
ALTER TABLE appointment_system.conversion_handover
 ADD COLUMN verification_manifest jsonb,
 ADD COLUMN verified_target_digest text CHECK(verified_target_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE appointment_system.conversion_handover ADD CONSTRAINT conversion_verification_shape
 CHECK((verification_manifest IS NULL AND verified_target_digest IS NULL)
  OR (jsonb_typeof(verification_manifest)='object' AND verified_target_digest IS NOT NULL));
ALTER TABLE appointment_system.conversion_handover ADD CONSTRAINT conversion_complete_verified
 CHECK(phase<>'complete' OR (verification_manifest IS NOT NULL AND verified_target_digest IS NOT NULL AND completed_at IS NOT NULL));
