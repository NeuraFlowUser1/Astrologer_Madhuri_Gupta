-- DEVELOPMENT only, enclosing transaction MUST roll back. No provider calls.
UPDATE sarsa_booking.contact_intake SET public_open=true;
UPDATE sarsa_booking.email_policy SET daily_limit=2,monthly_limit=2,contact_daily_limit=2,contact_monthly_limit=2;
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE req uuid:=gen_random_uuid(); req2 uuid:=gen_random_uuid(); req3 uuid:=gen_random_uuid();
 receipt text:=repeat('a',64); fingerprint text:=repeat('b',64);code_hash text:=repeat('c',64);
 code_cipher text:=repeat('x',120);message_cipher text:=repeat('y',150);message_digest text:=repeat('d',64);
 payload jsonb:='{"name":"Synthetic","email":"synthetic@example.com","phone":"","subject":"Test","message":"Synthetic enquiry only."}';
 j jsonb;again jsonb;begun jsonb;result jsonb;sent uuid:=gen_random_uuid();event_key text:=gen_random_uuid()::text;
 sheet_job uuid;values_row jsonb;assigned jsonb;reconciled boolean;
BEGIN
 PERFORM sarsa_booking.start_enquiry(req,receipt,fingerprint,payload,code_hash,code_cipher,repeat('1',64));
 j:=sarsa_booking.claim_enquiry_delivery('email');
 IF j->>'kind' IS DISTINCT FROM 'verification' OR j->>'destination' IS DISTINCT FROM 'synthetic@example.com' THEN RAISE EXCEPTION 'claim identity'; END IF;
 IF sarsa_booking.begin_enquiry_send((j->>'id')::uuid,gen_random_uuid(),message_cipher,message_digest) IS NOT NULL THEN RAISE EXCEPTION 'wrong lease admitted'; END IF;
 begun:=sarsa_booking.begin_enquiry_send((j->>'id')::uuid,(j->>'lease_token')::uuid,message_cipher,message_digest);
 IF begun->>'first_attempt_at' IS NULL OR (SELECT count(*) FROM sarsa_booking.email_reservations)<>1 THEN RAISE EXCEPTION 'send admission'; END IF;
 IF NOT sarsa_booking.finish_enquiry_delivery((j->>'id')::uuid,(j->>'lease_token')::uuid,NULL,'email_send_unconfirmed',false,15) THEN RAISE EXCEPTION 'uncertainty save'; END IF;
 UPDATE sarsa_booking.enquiry_delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=(j->>'id')::uuid;
 again:=sarsa_booking.claim_enquiry_delivery('email');
 IF again->>'id' IS DISTINCT FROM j->>'id' THEN RAISE EXCEPTION 'retry identity changed'; END IF;
 IF sarsa_booking.begin_enquiry_send((again->>'id')::uuid,(again->>'lease_token')::uuid,repeat('z',150),message_digest) IS NOT NULL THEN RAISE EXCEPTION 'changed snapshot admitted'; END IF;
 result:=sarsa_booking.begin_enquiry_send((again->>'id')::uuid,(again->>'lease_token')::uuid,message_cipher,message_digest);
 IF result->>'first_attempt_at' IS DISTINCT FROM begun->>'first_attempt_at' OR (SELECT count(*) FROM sarsa_booking.email_reservations)<>1 THEN RAISE EXCEPTION 'retry charged/reset'; END IF;
 IF NOT sarsa_booking.finish_enquiry_delivery((again->>'id')::uuid,(again->>'lease_token')::uuid,sent::text,NULL,false,15) THEN RAISE EXCEPTION 'accepted save'; END IF;
 IF (SELECT message_ciphertext FROM sarsa_booking.enquiry_delivery_jobs WHERE id=(j->>'id')::uuid) IS NOT NULL THEN RAISE EXCEPTION 'accepted code message retained'; END IF;
 IF sarsa_booking.enquiry_view(req,receipt)->>'verification_delivery' IS DISTINCT FROM 'accepted' THEN RAISE EXCEPTION 'acceptance falsely reported as delivery'; END IF;
 INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
 VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live',event_key,repeat('f',64),jsonb_build_object('job_id',j->>'id','email_id',sent,'event','email.bounced','occurred_at',clock_timestamp()));
 IF sarsa_booking.reconcile_email_event() THEN RAISE EXCEPTION 'booking consumer claimed contact event'; END IF;
 IF (SELECT attempts FROM sarsa_booking.provider_inbox WHERE event_id=event_key)<>0 THEN RAISE EXCEPTION 'contact event postponed by booking consumer'; END IF;
 reconciled:=sarsa_booking.reconcile_enquiry_email_event();
 IF NOT reconciled OR NOT sarsa_booking.email_recipient_suppressed('SYNTHETIC@example.com') THEN RAISE EXCEPTION 'event/suppression missing % %',reconciled,(SELECT last_error_code FROM sarsa_booking.provider_inbox WHERE event_id=event_key); END IF;
 IF sarsa_booking.enquiry_view(req,receipt)->>'verification_delivery' IS DISTINCT FROM 'failed' THEN RAISE EXCEPTION 'bounce not visible'; END IF;
 IF sarsa_booking.reconcile_enquiry_email_event() THEN RAISE EXCEPTION 'event reprocessed'; END IF;

 PERFORM sarsa_booking.start_enquiry(req2,receipt,fingerprint,payload||'{"email":"second@example.com"}',code_hash,code_cipher,repeat('2',64));
 j:=sarsa_booking.claim_enquiry_delivery('email');
 begun:=sarsa_booking.begin_enquiry_send((j->>'id')::uuid,(j->>'lease_token')::uuid,message_cipher,message_digest);
 IF begun IS NULL THEN RAISE EXCEPTION 'second allowance missing'; END IF;
 -- A resend invalidates an already admitted worker and its encrypted snapshot.
 UPDATE sarsa_booking.enquiries SET resend_after=clock_timestamp()-interval '1 second' WHERE request_id=req2;
 PERFORM sarsa_booking.resend_enquiry(req2,receipt,gen_random_uuid(),2,repeat('e',64),code_cipher);
 IF sarsa_booking.finish_enquiry_delivery((j->>'id')::uuid,(j->>'lease_token')::uuid,gen_random_uuid()::text,NULL,false,15) THEN RAISE EXCEPTION 'stale generation completion'; END IF;
 IF (SELECT message_ciphertext FROM sarsa_booking.enquiry_delivery_jobs WHERE id=(j->>'id')::uuid) IS NOT NULL THEN RAISE EXCEPTION 'superseded code snapshot retained'; END IF;
 j:=sarsa_booking.claim_enquiry_delivery('email');
 IF sarsa_booking.begin_enquiry_send((j->>'id')::uuid,(j->>'lease_token')::uuid,message_cipher,message_digest) IS NOT NULL THEN RAISE EXCEPTION 'shared budget exceeded'; END IF;
 IF (SELECT last_error_code FROM sarsa_booking.enquiry_delivery_jobs WHERE id=(j->>'id')::uuid) IS DISTINCT FROM 'email_budget_exhausted' THEN RAISE EXCEPTION 'budget deferral lost'; END IF;

 -- Verified content owns distinct Google delivery identities and stable rows.
 PERFORM sarsa_booking.verify_enquiry(req,receipt,1,code_hash);
 INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','synthetic-client'),('agency','synthetic-agency');
 INSERT INTO sarsa_booking.google_workbooks(role,subject,client_id,state,spreadsheet_id,connection_revision)
 VALUES('client','synthetic-client','synthetic-google','ready','synthetic-client-file',1),('agency','synthetic-agency','synthetic-google','ready','synthetic-agency-file',1);
 SELECT id INTO sheet_job FROM sarsa_booking.enquiry_delivery_jobs WHERE request_id=req AND kind='client_sheet';
 values_row:=jsonb_build_array('004-sarsa-jyotish-sansthan',sheet_job::text,req::text,(SELECT verified_at FROM sarsa_booking.enquiries WHERE request_id=req),'Synthetic','synthetic@example.com','','Test','Synthetic enquiry only.','received');
 IF sarsa_booking.assign_enquiry_row('agency',sheet_job,values_row) IS NOT NULL THEN RAISE EXCEPTION 'wrong sheet owner admitted'; END IF;
 assigned:=sarsa_booking.assign_enquiry_row('client',sheet_job,values_row);
 IF assigned->>'row' IS DISTINCT FROM '2' OR assigned->>'spreadsheet_id' IS DISTINCT FROM 'synthetic-client-file' THEN RAISE EXCEPTION 'row assignment'; END IF;
 IF sarsa_booking.assign_enquiry_row('client',sheet_job,values_row) IS DISTINCT FROM assigned THEN RAISE EXCEPTION 'duplicate row'; END IF;
 IF sarsa_booking.assign_enquiry_row('client',sheet_job,jsonb_set(values_row,'{8}','"changed"')) IS NOT NULL THEN RAISE EXCEPTION 'row rewrite admitted'; END IF;
 IF (SELECT next_row FROM sarsa_booking.google_workbooks WHERE role='client')<>2 THEN RAISE EXCEPTION 'enquiry used booking rows'; END IF;
END $test$;
RESET ROLE;
SELECT 'Contact delivery rollback fixture passed' result;
