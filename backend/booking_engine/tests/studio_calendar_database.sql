-- Rollback-only, synthetic records, dedicated development branch.
INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES ('client','calendar-test-client'),('agency','calendar-test-agency');
INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES
 (repeat('a',64),'client','calendar-test-client','test-calendar','https://calendar.example',clock_timestamp()+interval '1 hour'),
 (repeat('b',64),'agency','calendar-test-agency','test-calendar','https://calendar.example',clock_timestamp()+interval '1 hour'),
 (repeat('c',64),'client','calendar-test-client','test-calendar','https://calendar.example',clock_timestamp()-interval '1 minute');
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE op uuid:=gen_random_uuid(); op2 uuid:=gen_random_uuid(); claim uuid; c uuid:=gen_random_uuid(); r uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); appointment_claim uuid:=gen_random_uuid(); result jsonb;
 start_at timestamptz:=date_trunc('day',clock_timestamp())+interval '2 days 10 hours';
BEGIN
 IF has_function_privilege(current_user,'sarsa_booking.close_calendar(uuid,text,text,timestamptz,timestamptz)','EXECUTE') THEN RAISE EXCEPTION 'raw closure grant'; END IF;
 IF has_function_privilege(current_user,'sarsa_booking.studio_calendar_actor(text,text,text)','EXECUTE') THEN RAISE EXCEPTION 'actor helper grant'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('b',64),'test-calendar','https://calendar.example',op,'Not allowed',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency authorized'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('c',64),'test-calendar','https://calendar.example',op,'Not allowed',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'expired authorized'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'wrong','https://calendar.example',op,'Not allowed',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'wrong audience'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',op,'Personal commitment',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'closed' THEN RAISE EXCEPTION 'close failed %',result; END IF;
 claim:=(result->>'claim_id')::uuid;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',op,'Personal commitment',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'existing' OR (result->>'claim_id')::uuid<>claim THEN RAISE EXCEPTION 'replay changed'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',op,'Changed reason',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'request_conflict' THEN RAISE EXCEPTION 'changed replay'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',gen_random_uuid(),'Overlap',start_at+interval '30 minutes',start_at+interval '90 minutes');
 IF result->>'code'<>'time_already_reserved' THEN RAISE EXCEPTION 'overlap admitted'; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF result->>'code'<>'ok' OR jsonb_array_length(result->'items')<>1 OR result->'items'->0->>'kind'<>'closure' THEN RAISE EXCEPTION 'list failed %',result; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,claim);
 IF jsonb_array_length(result->'items')<>0 THEN RAISE EXCEPTION 'cursor repeated'; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('b',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency saw appointments'; END IF;
 result:=sarsa_booking.studio_calendar_reopen(repeat('a',64),'test-calendar','https://calendar.example',op2,claim,'Available again');
 IF result->>'code'<>'reopened' THEN RAISE EXCEPTION 'reopen failed'; END IF;
 result:=sarsa_booking.studio_calendar_reopen(repeat('a',64),'test-calendar','https://calendar.example',op2,claim,'Available again');
 IF result->>'code'<>'existing' THEN RAISE EXCEPTION 'reopen replay'; END IF;
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',op,'Personal commitment',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'existing' OR result->>'active'<>'false' THEN RAISE EXCEPTION 'stale close replay truth'; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF jsonb_array_length(result->'items')<>0 THEN RAISE EXCEPTION 'released claim shown'; END IF;
 INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at) VALUES(c,repeat('e',64),clock_timestamp()+interval '1 day');
 INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint) VALUES(r,c,repeat('e',64),repeat('f',64));
 INSERT INTO sarsa_booking.bookings(id,request_id,context_id,state,service_id,policy_version,service_snapshot,amount_paise,currency,
  starts_at,ends_at,practice_timezone,full_name,email,phone,hold_expires_at,receipt_expires_at)
 VALUES(b,r,c,'confirmed','synthetic-test',repeat('a',64),'{}',100,'INR',start_at,start_at+interval '1 hour','Asia/Kolkata',
  'Synthetic Person','not-for-calendar@example.com','+919876543210',clock_timestamp()+interval '10 minutes',start_at+interval '2 days');
 INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at) VALUES(appointment_claim,b,start_at,start_at+interval '1 hour');
 result:=sarsa_booking.studio_calendar_close(repeat('a',64),'test-calendar','https://calendar.example',gen_random_uuid(),'Over appointment',start_at,start_at+interval '1 hour');
 IF result->>'code'<>'time_already_reserved' THEN RAISE EXCEPTION 'appointment displaced'; END IF;
 result:=sarsa_booking.studio_calendar_reopen(repeat('a',64),'test-calendar','https://calendar.example',gen_random_uuid(),appointment_claim,'Unsafe attempt');
 IF result->>'code'<>'closure_not_found' THEN RAISE EXCEPTION 'appointment reopened'; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF result->'items'->0->>'kind'<>'appointment' OR result->'items'->0->>'name'<>'Synthetic Person' THEN RAISE EXCEPTION 'appointment list missing'; END IF;
 IF result::text LIKE '%not-for-calendar%' OR result::text LIKE '%9876543210%' THEN RAISE EXCEPTION 'unnecessary customer fields'; END IF;

 FOR i IN 1..51 LOOP
   INSERT INTO sarsa_booking.slot_claims(id,closure_reason,starts_at,ends_at)
    VALUES(gen_random_uuid(),'Synthetic pagination',start_at+interval '2 hours'+i*interval '2 minutes',start_at+interval '2 hours'+i*interval '2 minutes'+interval '1 minute');
 END LOOP;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF jsonb_array_length(result->'items')<>50 OR result->>'next_cursor' IS NULL THEN RAISE EXCEPTION 'page bound'; END IF;
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,(result->>'next_cursor')::uuid);
 IF jsonb_array_length(result->'items')<>2 OR result->>'next_cursor' IS NOT NULL THEN RAISE EXCEPTION 'page continuation'; END IF;
 UPDATE sarsa_booking.studio_sessions SET revoked_at=clock_timestamp() WHERE digest=repeat('a',64);
 result:=sarsa_booking.studio_calendar_list(repeat('a',64),'test-calendar','https://calendar.example',(start_at AT TIME ZONE 'Asia/Kolkata')::date,NULL);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'revoked list'; END IF;
END $test$;
RESET ROLE;
SELECT 'calendar rollback fixture passed' result;
