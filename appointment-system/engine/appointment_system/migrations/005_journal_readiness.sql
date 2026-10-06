-- The dedicated ingress login proves its exact private placement before pause.
CREATE FUNCTION appointment_system.journal_readiness(p_nonce uuid,p_release text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,appointment_system,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 PERFORM appointment_system.require_registered_caller(ARRAY['journal']);
 IF p_nonce IS NULL OR p_nonce='00000000-0000-0000-0000-000000000000' OR p_release IS NULL
  OR p_release !~ '^[a-f0-9]{64}$' THEN RETURN NULL; END IF;
 SELECT jsonb_build_object('installation_id',i.installation_id,'environment',i.environment,
   'database',current_database(),'login',session_user,'nonce',p_nonce,'release_digest',h.release_digest,
   'writer_contract',i.writer_contract) INTO result
 FROM appointment_system.installation i JOIN appointment_system.conversion_handover h
  ON h.installation_id=i.installation_id AND h.release_digest=p_release
 WHERE i.singleton AND h.phase='prepared';
 RETURN result;
END $$;
ALTER FUNCTION appointment_system.journal_readiness(uuid,text) OWNER TO appointment_system_owner;
REVOKE ALL ON FUNCTION appointment_system.journal_readiness(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION appointment_system.journal_readiness(uuid,text) TO appointment_system_journal_access;
