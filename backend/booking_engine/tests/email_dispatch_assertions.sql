        SELECT booking_id INTO b FROM sarsa_booking.accepted_payments WHERE payment_id='pay_primary';
        UPDATE sarsa_booking.delivery_jobs SET state='suppressed';
        UPDATE sarsa_booking.delivery_jobs SET state='pending' WHERE booking_id=b AND kind='booking_ack' AND recipient_role='customer';
        ej:=sarsa_booking.claim_email_delivery();
        ASSERT ej IS NOT NULL, 'Email database assertion 1';
        ASSERT sarsa_booking.claim_email_delivery() IS NULL, 'Email database assertion 2';
        msg:=jsonb_build_object('from','Sarsa Jyotish Sansthan <bookings@mail.sarsajyotishsansthan.com>',
          'to',jsonb_build_array(ej->>'destination'),'reply_to','sarsajyotish@gmail.com',
          'subject','Synthetic','text','Synthetic','html','<p>Synthetic</p>',
          'tags',jsonb_build_array(jsonb_build_object('name','project','value','sarsa004'),
           jsonb_build_object('name','job_id','value',ej->>'id')));
        ASSERT sarsa_booking.begin_email_send((ej->>'id')::uuid,(ej->>'lease_token')::uuid,msg,repeat('a',64)) IS NULL, 'Email database assertion 3';
        ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.email_reservations), 'Email database assertion 4';
        ASSERT NOT has_table_privilege(current_user,'sarsa_booking.email_policy','UPDATE'), 'Email database assertion 5';
        RESET ROLE;
        UPDATE sarsa_booking.email_policy SET daily_limit=1,monthly_limit=2;
        SET LOCAL ROLE sarsa_booking_runtime;
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=(ej->>'id')::uuid;
        ej:=sarsa_booking.claim_email_delivery();
        begun:=sarsa_booking.begin_email_send((ej->>'id')::uuid,(ej->>'lease_token')::uuid,msg,repeat('a',64));
        ASSERT begun->>'first_attempt_at' IS NOT NULL, 'Email database assertion 6';
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.email_reservations), 'Email database assertion 7';
        ASSERT sarsa_booking.begin_email_send((ej->>'id')::uuid,(ej->>'lease_token')::uuid,msg||'{"text":"changed"}',repeat('b',64)) IS NULL, 'Email database assertion 8';
        ASSERT NOT sarsa_booking.finish_email_delivery((ej->>'id')::uuid,gen_random_uuid(),NULL,'email_send_unconfirmed',false,30), 'Email database assertion 9';
        ASSERT sarsa_booking.finish_email_delivery((ej->>'id')::uuid,(ej->>'lease_token')::uuid,NULL,'email_send_unconfirmed',false,30), 'Email database assertion 10';
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=(ej->>'id')::uuid;
        ej:=sarsa_booking.claim_email_delivery();
        again:=sarsa_booking.begin_email_send((ej->>'id')::uuid,(ej->>'lease_token')::uuid,msg,repeat('a',64));
        ASSERT again->>'first_attempt_at'=begun->>'first_attempt_at', 'Email database assertion 11';
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.email_reservations), 'Email database assertion 12';
        -- Signed provider report can precede the HTTP completion; stale sent does not undo delivered.
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
          VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live','evt_email_delivered',repeat('d',64),
            jsonb_build_object('job_id',ej->>'id','email_id',mail_id,'event','email.delivered','occurred_at',clock_timestamp()));
        ASSERT sarsa_booking.reconcile_email_event(), 'Email database assertion 13';
        ASSERT sarsa_booking.email_delivery_state((ej->>'id')::uuid)='delivered', 'Email database assertion 14';
        ASSERT sarsa_booking.finish_email_delivery((ej->>'id')::uuid,(ej->>'lease_token')::uuid,mail_id,NULL,false,30), 'Email database assertion 15';
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
          VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live','evt_email_sent',repeat('e',64),
            jsonb_build_object('job_id',ej->>'id','email_id',mail_id,'event','email.sent','occurred_at',clock_timestamp()-interval '1 minute'));
        ASSERT sarsa_booking.reconcile_email_event(), 'Email database assertion 16';
        ASSERT sarsa_booking.email_delivery_state((ej->>'id')::uuid)='delivered', 'Email database assertion 17';
        ASSERT NOT sarsa_booking.reconcile_email_event(), 'Email database assertion 18';
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.email_observations), 'Email database assertion 19';
        -- Another message cannot consume the same exhausted allocation.
        UPDATE sarsa_booking.delivery_jobs SET state='pending' WHERE booking_id=b AND kind='booking_ack' AND recipient_role='client';
        other_job:=sarsa_booking.claim_email_delivery();
        msg:=jsonb_set(msg,'{to}',jsonb_build_array(other_job->>'destination'));
        msg:=jsonb_set(msg,'{tags,1,value}',to_jsonb(other_job->>'id'));
        ASSERT sarsa_booking.begin_email_send((other_job->>'id')::uuid,(other_job->>'lease_token')::uuid,msg,repeat('a',64)) IS NULL, 'Email database assertion 20';
        ASSERT (SELECT last_error_code='email_budget_exhausted' FROM sarsa_booking.delivery_jobs WHERE id=(other_job->>'id')::uuid), 'Email database assertion 21';
        ASSERT (SELECT count(*)=1 FROM sarsa_booking.email_reservations), 'Email database assertion 22';

        -- Attempt timestamps and exact frozen content cannot be rewritten after an ambiguous send.
        BEGIN
          UPDATE sarsa_booking.delivery_jobs SET first_attempt_at=clock_timestamp() WHERE id=(ej->>'id')::uuid;
          RAISE EXCEPTION 'Attempt identity rewrite unexpectedly allowed';
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
          VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live','evt_email_conflict',repeat('f',64),
            jsonb_build_object('job_id',ej->>'id','email_id',gen_random_uuid(),'event','email.delivered','occurred_at',clock_timestamp()));
        ASSERT NOT sarsa_booking.reconcile_email_event(), 'Email database assertion 23';
        ASSERT (SELECT last_error_code='email_event_provider_conflict' AND processed_at IS NULL
          FROM sarsa_booking.provider_inbox WHERE event_id='evt_email_conflict'), 'Email database assertion 24';
        ASSERT sarsa_booking.email_delivery_state((ej->>'id')::uuid)='delivered', 'Email database assertion 25';
        -- Refund amount is the maximum observed refund for the accepted payment, not a sum of repeated observations.
        INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,provider_order_id,
          evidence_hash,status,amount_paise,currency,refunded_paise,captured)
        SELECT gen_random_uuid(),o.booking_id,o.merchant_id,o.mode,o.payment_id,o.provider_order_id,
          repeat('8',64),'captured',o.amount_paise,o.currency,10000,true
          FROM sarsa_booking.accepted_payments a JOIN sarsa_booking.payment_observations o ON o.id=a.observation_id WHERE a.booking_id=b;
        UPDATE sarsa_booking.payment_cases SET resolved_at=clock_timestamp(),resolution_actor='synthetic',resolution_note='synthetic test' WHERE booking_id=b;
        EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING paid_request;
        ASSERT snapshot->'booking'->>'payment_state'='partially_refunded', 'Email database assertion 26';
        ASSERT snapshot->'booking'->>'captured_paise'='250000', 'Email database assertion 27';
        ASSERT snapshot->'booking'->>'refunded_paise'='10000', 'Email database assertion 28';
        ASSERT snapshot->'booking'->>'acknowledgement_state'='delivered', 'Email database assertion 29';
        -- Suppression remains independent of accepted/delivered evidence.
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
          VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live','evt_email_bounce',repeat('9',64),
            jsonb_build_object('job_id',ej->>'id','email_id',mail_id,'event','email.bounced','occurred_at',clock_timestamp()));
        ASSERT sarsa_booking.reconcile_email_event(), 'Bounce reconciliation';
        ASSERT sarsa_booking.email_delivery_state((ej->>'id')::uuid)='bounced', 'Bounce projection';
        -- A claimed but not attempted job must stop after cancellation.
        UPDATE sarsa_booking.delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second'
          WHERE id=(other_job->>'id')::uuid;
        other_job:=sarsa_booking.claim_email_delivery();
        UPDATE sarsa_booking.bookings SET state='cancelled',revision=revision+1 WHERE id=b;
        ASSERT sarsa_booking.begin_email_send((other_job->>'id')::uuid,(other_job->>'lease_token')::uuid,msg,repeat('a',64)) IS NULL, 'Cancelled job blocked';
        ASSERT (SELECT first_attempt_at IS NULL AND last_error_code='email_obsolete_revision'
          FROM sarsa_booking.delivery_jobs WHERE id=(other_job->>'id')::uuid), 'No attempt for obsolete job';
        -- Old leases cannot finish, and an old attempt cannot start a fresh retry window.
        UPDATE sarsa_booking.bookings SET state='confirmed',revision=revision-1 WHERE id=b;
        UPDATE sarsa_booking.delivery_jobs SET state='pending',next_attempt_at=clock_timestamp()-interval '1 second'
          WHERE id=(other_job->>'id')::uuid;
        other_job:=sarsa_booking.claim_email_delivery();
        UPDATE sarsa_booking.delivery_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'
          WHERE id=(other_job->>'id')::uuid;
        ASSERT NOT sarsa_booking.finish_email_delivery((other_job->>'id')::uuid,(other_job->>'lease_token')::uuid,NULL,'email_send_unconfirmed',false,30), 'Expired lease rejected';
        other_job:=sarsa_booking.claim_email_delivery();
        UPDATE sarsa_booking.delivery_jobs SET first_attempt_at=clock_timestamp()-interval '23 hours',message_snapshot=msg,message_hash=repeat('a',64)
          WHERE id=(other_job->>'id')::uuid;
        ASSERT sarsa_booking.begin_email_send((other_job->>'id')::uuid,(other_job->>'lease_token')::uuid,msg,repeat('a',64)) IS NULL, 'Retry window cannot reset';
        ASSERT (SELECT last_error_code='email_retry_window_closed' FROM sarsa_booking.delivery_jobs WHERE id=(other_job->>'id')::uuid), 'Expired send escalated';
