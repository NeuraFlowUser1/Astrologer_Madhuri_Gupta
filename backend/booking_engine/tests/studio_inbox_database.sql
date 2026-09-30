-- Synthetic development fixture, must roll back. No provider calls.
INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES ('client','inbox-client'),('agency','inbox-agency');
INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at) VALUES
 (repeat('a',64),'client','inbox-client','inbox-test','https://inbox.example',clock_timestamp()+interval '1 hour'),
 (repeat('b',64),'agency','inbox-agency','inbox-test','https://inbox.example',clock_timestamp()+interval '1 hour'),
 (repeat('c',64),'client','inbox-client','inbox-test','https://inbox.example',clock_timestamp()-interval '1 second');
INSERT INTO sarsa_booking.enquiries(request_id,email_key,receipt_digest,request_fingerprint,payload,code_expires_at,resend_after,verified_at)
 SELECT gen_random_uuid(),repeat('d',64),repeat('e',64),repeat('f',64),
 '{"name":"Synthetic private name","email":"private@example.com","phone":"","subject":"Before booking","message":"Private synthetic enquiry text."}',clock_timestamp(),clock_timestamp(),CASE WHEN n<=51 THEN clock_timestamp() END FROM generate_series(1,52) n;
INSERT INTO sarsa_booking.enquiry_delivery_jobs(id,request_id,kind,generation,state,deadline_at,last_error_code)
 SELECT gen_random_uuid(),request_id,'agency_sheet',0,'attention',clock_timestamp()+interval '1 day','google_reconnect_required'
 FROM sarsa_booking.enquiries WHERE verified_at IS NOT NULL LIMIT 1;
SET LOCAL ROLE sarsa_booking_web;
DO $test$
DECLARE result jsonb;item text;op uuid:=gen_random_uuid();a_item text;
BEGIN
 IF has_function_privilege(current_user,'sarsa_booking.staff_items(text)','EXECUTE') OR has_table_privilege(current_user,'sarsa_booking.staff_reviews','INSERT') THEN RAISE EXCEPTION 'raw staff authority exposed'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('b',64),'inbox-test','https://inbox.example','enquiries',NULL);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'agency read enquiries'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('c',64),'inbox-test','https://inbox.example','issues',NULL);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'expired session'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('a',64),'wrong','https://inbox.example','issues',NULL);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'wrong client'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('a',64),'inbox-test','https://inbox.example','enquiries',NULL);
 IF jsonb_array_length(result->'items')<>50 OR result->>'next_cursor' IS NULL OR result::text LIKE '%private@example.com%' OR result::text LIKE '%Private synthetic%' THEN RAISE EXCEPTION 'pagination/privacy'; END IF;
 item:=result->'items'->0->>'item_key';
 result:=sarsa_booking.studio_inbox_list(repeat('a',64),'inbox-test','https://inbox.example','enquiries',result->>'next_cursor');
 IF jsonb_array_length(result->'items')<>1 OR result->>'next_cursor' IS NOT NULL THEN RAISE EXCEPTION 'cursor duplicates/unverified shown'; END IF;
 result:=sarsa_booking.studio_inbox_detail(repeat('a',64),'inbox-test','https://inbox.example',item);
 IF result->'item'->'enquiry'->>'email'<>'private@example.com' OR result::text LIKE '%receipt_digest%' THEN RAISE EXCEPTION 'detail contract'; END IF;
 result:=sarsa_booking.studio_inbox_detail(repeat('b',64),'inbox-test','https://inbox.example',item);
 IF result->>'code'<>'item_unavailable' THEN RAISE EXCEPTION 'agency bypass detail'; END IF;
 result:=sarsa_booking.studio_inbox_review(repeat('a',64),'inbox-test','https://inbox.example',op,item,0,'Reviewed the saved question');
 IF result->>'code'<>'review_saved' OR result->>'revision'<>'1' THEN RAISE EXCEPTION 'save review'; END IF;
 result:=sarsa_booking.studio_inbox_review(repeat('a',64),'inbox-test','https://inbox.example',op,item,0,'Reviewed the saved question');
 IF result->>'code'<>'review_saved' OR result->>'revision'<>'1' THEN RAISE EXCEPTION 'review replay'; END IF;
 result:=sarsa_booking.studio_inbox_review(repeat('a',64),'inbox-test','https://inbox.example',op,item,0,'Different note');
 IF result->>'code'<>'request_conflict' THEN RAISE EXCEPTION 'changed replay'; END IF;
 result:=sarsa_booking.studio_inbox_review(repeat('a',64),'inbox-test','https://inbox.example',gen_random_uuid(),item,0,'Another review');
 IF result->>'code'<>'revision_changed' THEN RAISE EXCEPTION 'stale revision'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('b',64),'inbox-test','https://inbox.example','issues',NULL);
 IF jsonb_array_length(result->'items')<>1 OR result->'items'->0->>'reference' IS NOT NULL OR result::text LIKE '%private@example.com%' THEN RAISE EXCEPTION 'agency projection'; END IF;
 a_item:=result->'items'->0->>'item_key';
 result:=sarsa_booking.studio_inbox_review(repeat('b',64),'inbox-test','https://inbox.example',gen_random_uuid(),a_item,0,'Checked own connection');
 IF result->>'code'<>'review_saved' THEN RAISE EXCEPTION 'agency technical review'; END IF;
 result:=sarsa_booking.studio_inbox_list(repeat('b',64),'inbox-test','https://inbox.example','issues',NULL);
 IF jsonb_array_length(result->'items')<>1 THEN RAISE EXCEPTION 'review erased problem'; END IF;
 UPDATE sarsa_booking.studio_sessions SET revoked_at=clock_timestamp() WHERE digest=repeat('a',64);
 result:=sarsa_booking.studio_inbox_detail(repeat('a',64),'inbox-test','https://inbox.example',item);
 IF result->>'code'<>'access_unavailable' THEN RAISE EXCEPTION 'revoked session'; END IF;
END $test$;
RESET ROLE;
DO $projection$
DECLARE job uuid:=gen_random_uuid();provider uuid:=gen_random_uuid();request uuid;
BEGIN
 SELECT request_id INTO request FROM sarsa_booking.enquiries WHERE verified_at IS NOT NULL LIMIT 1;
 INSERT INTO sarsa_booking.enquiry_delivery_jobs(id,request_id,kind,generation,state,deadline_at,provider_id)
 VALUES(job,request,'acknowledgement',0,'accepted',clock_timestamp()+interval '1 day',provider);
 INSERT INTO sarsa_booking.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
 VALUES('inbox-failed',job,provider,'email.failed',clock_timestamp());
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.staff_items('client') WHERE item_key='enquiry-delivery:'||job) THEN RAISE EXCEPTION 'failed mail hidden'; END IF;
 INSERT INTO sarsa_booking.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
 VALUES('inbox-delivered',job,provider,'email.delivered',clock_timestamp());
 IF EXISTS(SELECT 1 FROM sarsa_booking.staff_items('client') WHERE item_key='enquiry-delivery:'||job) THEN RAISE EXCEPTION 'delivery did not supersede failure'; END IF;
 INSERT INTO sarsa_booking.enquiry_email_observations(event_id,job_id,provider_id,event_type,occurred_at)
 VALUES('inbox-bounced',job,provider,'email.bounced',clock_timestamp());
 IF NOT EXISTS(SELECT 1 FROM sarsa_booking.staff_items('client') WHERE item_key='enquiry-delivery:'||job) THEN RAISE EXCEPTION 'bounce hidden by earlier delivery'; END IF;
END $projection$;
SELECT 'Staff inbox rollback fixture passed' result;
