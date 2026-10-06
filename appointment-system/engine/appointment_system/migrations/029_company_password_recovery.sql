-- Protected owner recovery is separate from both first enrolment and public
-- sign-in. Retain immutable evidence without a password or password hash.
SET ROLE appointment_system_owner;
CREATE TABLE appointment_system.company_password_recoveries (
 operation_id uuid PRIMARY KEY CHECK(operation_id<>'00000000-0000-0000-0000-000000000000'::uuid),
 subject text NOT NULL REFERENCES appointment_system.company_credentials(subject),
 previous_revision bigint NOT NULL CHECK(previous_revision>0),
 resulting_revision bigint NOT NULL CHECK(resulting_revision=previous_revision+1),
 operator_role text NOT NULL CHECK(length(operator_role) BETWEEN 1 AND 63),
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 300),
 body_hash text NOT NULL CHECK(body_hash ~ '^[a-f0-9]{64}$'),
 happened_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON appointment_system.company_password_recoveries FROM PUBLIC;
GRANT SELECT ON appointment_system.company_password_recoveries TO appointment_system_backup_access;
CREATE TRIGGER company_password_recovery_immutable BEFORE UPDATE OR DELETE
 ON appointment_system.company_password_recoveries FOR EACH ROW
 EXECUTE FUNCTION appointment_system.control_protect_maintenance_evidence();
RESET ROLE;
