        -- Existing paid fixture supplies the real payment-finalization jobs.
        SELECT booking_id INTO b FROM sarsa_booking.accepted_payments WHERE payment_id='pay_primary';
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()+interval '1 hour' WHERE kind='sheet_booking';
        gj:=sarsa_booking.claim_google_delivery();
        ASSERT gj->>'kind'='booking_calendar',gj::text;
        ASSERT (gj->>'booking_id')::uuid=b;
        ASSERT sarsa_booking.claim_google_delivery() IS NULL;
        ev:='sarsa'||encode(sha256(convert_to('004-sarsa-jyotish-sansthan:'||b::text||':1','UTF8')),'hex');
        ASSERT NOT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,gen_random_uuid(),'done',ev,'https://meet.google.com/abc-defg-hij',NULL,15);
        ASSERT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'waiting',ev,NULL,NULL,15);
        ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='booking_details');
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=(gj->>'id')::uuid;
        gj:=sarsa_booking.claim_google_delivery();
        ASSERT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'done',ev,'https://meet.google.com/abc-defg-hij',NULL,15);
        ASSERT NOT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'done',ev,'https://meet.google.com/abc-defg-hij',NULL,15);
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='booking_details');
        EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING paid_request;
        ASSERT snapshot->'booking'->>'meeting_state'='ready';
        ASSERT snapshot->'booking'->>'meet_url'='https://meet.google.com/abc-defg-hij';
        -- Each owner's immutable row assignment survives retry and rejects a
        -- changed payload; neither owner can target the other's job.
        INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES('client','sheet-client'),('agency','sheet-agency');
        INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at)
          VALUES('client','sheet-client','sheet-app',1,repeat('x',120),clock_timestamp()),('agency','sheet-agency','sheet-app',1,repeat('y',120),clock_timestamp());
        gw:=sarsa_booking.claim_google_workbook('client','sheet-app');
        ASSERT sarsa_booking.finish_google_workbook('client',(gw->>'lease')::uuid,'client-sheet');
        gw:=sarsa_booking.claim_google_workbook('agency','sheet-app');
        ASSERT sarsa_booking.finish_google_workbook('agency',(gw->>'lease')::uuid,'agency-sheet');
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second'
          WHERE booking_id=b AND kind='sheet_booking' AND recipient_role='client_sheet';
        gj:=sarsa_booking.claim_google_delivery();
        ASSERT gj->>'recipient_role'='client_sheet';
        vals:=jsonb_build_array('004-sarsa-jyotish-sansthan',gj->>'id',b::text,'1','confirmed','Consultation','start','end','Name','test@example.invalid','+919876543210','2500');
        assigned:=sarsa_booking.assign_sheet_row('client',(gj->>'id')::uuid,vals);
        ASSERT assigned->>'row'='2';
        ASSERT assigned=sarsa_booking.assign_sheet_row('client',(gj->>'id')::uuid,vals);
        ASSERT sarsa_booking.assign_sheet_row('agency',(gj->>'id')::uuid,vals) IS NULL;
        ASSERT sarsa_booking.assign_sheet_row('client',(gj->>'id')::uuid,jsonb_set(vals,'{8}','"Changed"')) IS NULL;
        ASSERT sarsa_booking.assign_sheet_row('client',(gj->>'id')::uuid,jsonb_set(vals,'{0}','null')) IS NULL;
        ASSERT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'done','client-sheet',NULL,NULL,15);
        -- A late old-revision Calendar result queues cleanup, not a new email.
        UPDATE sarsa_booking.delivery_jobs SET state='pending',next_attempt_at=clock_timestamp()-interval '1 second'
          WHERE booking_id=b AND kind='booking_calendar';
        gj:=sarsa_booking.claim_google_delivery();
        UPDATE sarsa_booking.bookings SET revision=2 WHERE id=b;
        ASSERT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'done',ev,'https://meet.google.com/abc-defg-hij',NULL,15);
        ASSERT (SELECT state='suppressed' FROM sarsa_booking.delivery_jobs WHERE id=(gj->>'id')::uuid);
        gj:=sarsa_booking.claim_google_delivery();
        ASSERT gj->>'kind'='booking_cancelled';
        ASSERT gj->'payload'->>'revision'='1';
        ASSERT sarsa_booking.finish_google_delivery((gj->>'id')::uuid,(gj->>'lease_token')::uuid,'done',NULL,NULL,NULL,15);
        ASSERT (SELECT state='cancelled' AND meet_url IS NULL FROM sarsa_booking.meeting_events WHERE booking_id=b AND booking_revision=1);
        EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING paid_request;
        ASSERT snapshot->'booking'->>'meeting_state'='preparing';
        ASSERT snapshot->'booking'->>'meet_url' IS NULL;
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.delivery_jobs WHERE booking_id=b AND kind='booking_details');
