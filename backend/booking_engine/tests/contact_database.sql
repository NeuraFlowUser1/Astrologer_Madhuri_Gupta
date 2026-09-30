-- Synthetic enquiry proof; run in an enclosing rollback-only DEVELOPMENT transaction.
-- Fixture setup only: public switch is restored by rollback, no messages are sent.
UPDATE sarsa_booking.contact_intake SET public_open=true;
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE request_one uuid:=gen_random_uuid(); id2 uuid:=gen_random_uuid(); id3 uuid:=gen_random_uuid(); id4 uuid:=gen_random_uuid();
 op uuid:=gen_random_uuid(); receipt text:=repeat('a',64); fingerprint text:=repeat('b',64); cipher text:=repeat('x',120);
 payload jsonb:='{"name":"Synthetic","email":"synthetic@example.com","phone":"","subject":"Question","message":"Synthetic only."}';
 result jsonb; old_expiry timestamptz; used integer;
BEGIN
 IF has_column_privilege(current_user,'sarsa_booking.contact_intake','public_open','UPDATE') THEN
  RAISE EXCEPTION 'runtime may change contact intake'; END IF;
 BEGIN
  UPDATE sarsa_booking.contact_intake SET public_open=false;
  RAISE EXCEPTION 'runtime changed contact intake';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 result:=sarsa_booking.start_enquiry(request_one,receipt,fingerprint,payload,repeat('c',64),cipher,repeat('1',64));
 IF result->>'state' IS DISTINCT FROM 'awaiting_verification' THEN RAISE EXCEPTION 'start failed %',result; END IF;
 SELECT code_expires_at INTO old_expiry FROM sarsa_booking.enquiries WHERE request_id=request_one;
 result:=sarsa_booking.start_enquiry(request_one,receipt,fingerprint,payload,repeat('d',64),repeat('y',120),repeat('1',64));
 IF (SELECT code_digest FROM sarsa_booking.enquiries WHERE request_id=request_one)<>repeat('c',64)
  OR (SELECT code_expires_at FROM sarsa_booking.enquiries WHERE request_id=request_one)<>old_expiry THEN RAISE EXCEPTION 'retry replaced challenge'; END IF;
 IF (SELECT count(*) FROM sarsa_booking.enquiry_delivery_jobs WHERE request_id=request_one)<>1 THEN RAISE EXCEPTION 'duplicate verification job'; END IF;
 result:=sarsa_booking.start_enquiry(request_one,receipt,fingerprint,payload||'{"message":"Changed"}',repeat('c',64),cipher,repeat('1',64));
 IF result->>'code' IS DISTINCT FROM 'request_conflict' THEN RAISE EXCEPTION 'changed content admitted'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,repeat('0',64),1,repeat('c',64));
 IF result->>'code' IS DISTINCT FROM 'access_unavailable' THEN RAISE EXCEPTION 'wrong receipt accepted'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,receipt,2,repeat('c',64));
 IF result->>'code' IS DISTINCT FROM 'verification_changed' THEN RAISE EXCEPTION 'wrong generation'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,receipt,1,repeat('0',64));
 IF result->>'code' IS DISTINCT FROM 'verification_incorrect' OR (SELECT attempts FROM sarsa_booking.enquiries WHERE request_id=request_one)<>1 THEN RAISE EXCEPTION 'attempt not recorded'; END IF;
 result:=sarsa_booking.resend_enquiry(request_one,receipt,op,2,repeat('d',64),cipher);
 IF result->>'code' IS DISTINCT FROM 'please_wait' THEN RAISE EXCEPTION 'resend cooldown'; END IF;
 UPDATE sarsa_booking.enquiries SET resend_after=clock_timestamp()-interval '1 second' WHERE request_id=request_one;
 result:=sarsa_booking.resend_enquiry(request_one,receipt,op,2,repeat('d',64),cipher);
 IF result->>'generation' IS DISTINCT FROM '2' THEN RAISE EXCEPTION 'resend failed %',result; END IF;
 result:=sarsa_booking.resend_enquiry(request_one,receipt,op,3,repeat('e',64),cipher);
 IF result->>'generation' IS DISTINCT FROM '2' OR (SELECT code_digest FROM sarsa_booking.enquiries WHERE request_id=request_one)<>repeat('d',64) THEN RAISE EXCEPTION 'resend replay replaced code'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,receipt,1,repeat('c',64));
 IF result->>'code' IS DISTINCT FROM 'verification_changed' THEN RAISE EXCEPTION 'old code accepted'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,receipt,2,repeat('d',64));
 IF result->>'state' IS DISTINCT FROM 'received' THEN RAISE EXCEPTION 'verified enquiry not saved'; END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.enquiries WHERE request_id=request_one AND (code_digest IS NOT NULL OR code_ciphertext IS NOT NULL)) THEN RAISE EXCEPTION 'code retained'; END IF;
 IF (SELECT count(*) FROM sarsa_booking.enquiry_delivery_jobs WHERE request_id=request_one AND generation=0)<>4 THEN RAISE EXCEPTION 'delivery intents missing'; END IF;
 result:=sarsa_booking.verify_enquiry(request_one,receipt,2,repeat('d',64));
 IF result->>'state' IS DISTINCT FROM 'received' OR (SELECT count(*) FROM sarsa_booking.enquiry_delivery_jobs WHERE request_id=request_one AND generation=0)<>4 THEN RAISE EXCEPTION 'duplicate enquiry delivery'; END IF;
 IF result ? 'payload' OR result ? 'code_digest' OR result ? 'receipt_digest' THEN RAISE EXCEPTION 'private projection'; END IF;

 PERFORM sarsa_booking.start_enquiry(id2,receipt,fingerprint,payload,repeat('c',64),cipher,repeat('2',64));
 FOR i IN 1..5 LOOP result:=sarsa_booking.verify_enquiry(id2,receipt,1,repeat('0',64)); END LOOP;
 IF result->>'code' IS DISTINCT FROM 'verification_limit' THEN RAISE EXCEPTION 'attempt limit'; END IF;
 result:=sarsa_booking.verify_enquiry(id2,receipt,1,repeat('c',64));
 IF result->>'code' IS DISTINCT FROM 'verification_limit' OR (SELECT code_ciphertext FROM sarsa_booking.enquiries WHERE request_id=id2) IS NOT NULL THEN RAISE EXCEPTION 'locked code usable'; END IF;
 IF EXISTS(SELECT 1 FROM sarsa_booking.enquiry_delivery_jobs WHERE request_id=id2 AND state IN ('pending','processing')) THEN RAISE EXCEPTION 'locked code still queued'; END IF;
 UPDATE sarsa_booking.enquiries SET resend_after=clock_timestamp()-interval '1 second' WHERE request_id=id2;
 PERFORM sarsa_booking.resend_enquiry(id2,receipt,gen_random_uuid(),2,repeat('d',64),cipher);
 UPDATE sarsa_booking.enquiries SET resend_after=clock_timestamp()-interval '1 second' WHERE request_id=id2;
 PERFORM sarsa_booking.resend_enquiry(id2,receipt,gen_random_uuid(),3,repeat('e',64),cipher);
 result:=sarsa_booking.resend_enquiry(id2,receipt,gen_random_uuid(),3,repeat('f',64),cipher);
 IF result->>'code' IS DISTINCT FROM 'verification_limit' THEN RAISE EXCEPTION 'send limit'; END IF;
 PERFORM sarsa_booking.start_enquiry(id3,receipt,fingerprint,payload,repeat('c',64),cipher,repeat('3',64));
 UPDATE sarsa_booking.enquiries SET code_expires_at=clock_timestamp()-interval '1 second' WHERE request_id=id3;
 result:=sarsa_booking.verify_enquiry(id3,receipt,1,repeat('c',64));
 IF result->>'code' IS DISTINCT FROM 'verification_expired' OR (SELECT code_ciphertext FROM sarsa_booking.enquiries WHERE request_id=id3) IS NOT NULL THEN RAISE EXCEPTION 'expired code accepted'; END IF;
 PERFORM sarsa_booking.start_enquiry(id4,receipt,fingerprint,payload,repeat('c',64),cipher,repeat('4',64));
 UPDATE sarsa_booking.enquiries SET code_expires_at=clock_timestamp()-interval '1 second' WHERE request_id=id4;
 used:=sarsa_booking.expire_enquiry_codes();
 IF used<>1 OR EXISTS(SELECT 1 FROM sarsa_booking.enquiries WHERE request_id=id4 AND code_ciphertext IS NOT NULL) THEN RAISE EXCEPTION 'expiry cleanup'; END IF;
 -- Same email cannot evade the three-code budget by starting new requests.
 FOR i IN 1..3 LOOP
  result:=sarsa_booking.start_enquiry(gen_random_uuid(),receipt,fingerprint,payload,repeat('c',64),cipher,repeat('6',64));
  IF result->>'state' IS DISTINCT FROM 'awaiting_verification' THEN RAISE EXCEPTION 'email allowance rejected early'; END IF;
 END LOOP;
 result:=sarsa_booking.start_enquiry(gen_random_uuid(),receipt,fingerprint,payload,repeat('c',64),cipher,repeat('6',64));
 IF result->>'code' IS DISTINCT FROM 'please_wait' OR
   (SELECT count(*) FROM sarsa_booking.enquiries WHERE email_key=repeat('6',64))<>3 THEN RAISE EXCEPTION 'email quota bypass'; END IF;
 BEGIN
  UPDATE sarsa_booking.enquiries AS original SET payload=original.payload||'{"email":"other@example.com"}' WHERE request_id=request_one;
  RAISE EXCEPTION 'identity mutation admitted';
 EXCEPTION WHEN check_violation THEN NULL; END;
END $test$;
RESET ROLE;
UPDATE sarsa_booking.contact_intake SET public_open=false;
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE result jsonb;
BEGIN
 result:=sarsa_booking.start_enquiry(gen_random_uuid(),repeat('a',64),repeat('b',64),'{"email":"test@example.com"}',repeat('c',64),repeat('x',120),repeat('5',64));
 IF result->>'code' IS DISTINCT FROM 'contact_unavailable' THEN RAISE EXCEPTION 'closed intake admitted'; END IF;
END $test$;
RESET ROLE;
SELECT 'contact rollback fixture passed' result;
