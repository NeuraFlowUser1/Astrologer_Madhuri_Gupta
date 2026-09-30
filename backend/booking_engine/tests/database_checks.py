"""Render rollback-only DB checks with the exact application-owned read query.

The existing reservation fixture supplies paid and late-payment records. This
adds assertions against the production query instead of copying its SQL.
"""

from pathlib import Path

ROOT=Path(__file__).parent


def receipt_query_check():
    fixture=(ROOT/'reservation_database.sql').read_text()
    fixture=fixture.replace('DECLARE c1 uuid', 'DECLARE snapshot jsonb; paid_request uuid; c1 uuid',1)
    query=(ROOT.parent/'queries/receipt_snapshot.sql').read_text()
    if query.count('%s')!=1 or '$receipt$' in query:
        raise ValueError('Receipt query placeholder changed; review this check.')
    assertion="""
        SELECT b.request_id INTO paid_request FROM sarsa_booking.bookings b
          JOIN sarsa_booking.accepted_payments p ON p.booking_id=b.id WHERE p.payment_id='pay_primary';
        ASSERT paid_request IS NOT NULL;
        EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING paid_request;
        ASSERT snapshot->'booking'->>'request_id'=paid_request::text;
        ASSERT snapshot->'booking'->>'state'='confirmed';
        ASSERT snapshot->'booking'->>'payment_state'='needs_attention';
        ASSERT snapshot->'booking'->>'acknowledgement_state'='pending';
        ASSERT snapshot->'booking'->>'meeting_email_state'='not_queued';
        ASSERT NOT (snapshot->'booking' ? 'email');
        ASSERT NOT (snapshot->'booking' ? 'phone');
        ASSERT NOT (snapshot->'booking' ? 'notes');
    """.replace('QUERY',query.replace('%s','$1'))
    anchor="        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');"
    if fixture.count(anchor)!=1:
        raise ValueError('Reservation fixture changed; review this check.')
    return fixture.replace(anchor,assertion+'\n'+anchor)


def recovery_check():
    fixture=receipt_query_check().replace('DECLARE snapshot jsonb;', 'DECLARE jobs jsonb; job jsonb; replacement jsonb; snapshot jsonb;',1)
    assertion="""
        jobs:=sarsa_booking.claim_payment_recovery(20);
        ASSERT jsonb_array_length(jobs)=2,jobs::text;
        ASSERT jsonb_array_length(sarsa_booking.claim_payment_recovery(20))=0;
        job:=jobs->0;
        ASSERT NOT sarsa_booking.finish_payment_recovery((job->>'booking_id')::uuid,gen_random_uuid(),15,0,0,NULL);
        UPDATE sarsa_booking.payment_orders SET lease_expires_at=clock_timestamp()-interval '1 second'
          WHERE booking_id=(job->>'booking_id')::uuid;
        ASSERT NOT sarsa_booking.finish_payment_recovery((job->>'booking_id')::uuid,(job->>'lease_token')::uuid,15,0,0,NULL);
        replacement:=sarsa_booking.claim_payment_recovery(1)->0;
        ASSERT replacement->>'booking_id'=job->>'booking_id';
        ASSERT replacement->>'lease_token'<>job->>'lease_token';
        ASSERT sarsa_booking.finish_payment_recovery((replacement->>'booking_id')::uuid,(replacement->>'lease_token')::uuid,15,0,0,NULL);
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
          VALUES('razorpay','syntheticOnly','live','evt_synthetic',repeat('a',64),
          '{"event":"payment.captured","payment_id":"pay_primary","order_id":"order_synthetic"}'::jsonb);
        jobs:=sarsa_booking.claim_payment_events(1);
        ASSERT jsonb_array_length(jobs)=1;
        ASSERT jsonb_array_length(sarsa_booking.claim_payment_events(1))=0;
        job:=jobs->0;
        ASSERT NOT sarsa_booking.finish_payment_event('syntheticOnly','live','evt_synthetic',gen_random_uuid(),true,15,NULL);
        ASSERT sarsa_booking.finish_payment_event('syntheticOnly','live','evt_synthetic',(job->>'lease_token')::uuid,true,15,NULL);
        ASSERT jsonb_array_length(sarsa_booking.claim_payment_events(1))=0;
    """
    anchor="        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');"
    return fixture.replace(anchor,assertion+'\n'+anchor)


def google_delivery_check():
    fixture=receipt_query_check().replace('DECLARE snapshot jsonb;', 'DECLARE gj jsonb; gw jsonb; vals jsonb; assigned jsonb; ev text; snapshot jsonb;',1)
    query=(ROOT.parent/'queries/receipt_snapshot.sql').read_text().replace('%s','$1')
    assertion=(ROOT/'google_delivery_assertions.sql').read_text().replace('QUERY',query)
    anchor="        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');"
    return fixture.replace(anchor,assertion+'\n'+anchor)


def google_workbooks_check():
    from ..storage import Store
    store=object.__new__(Store)
    store._call=lambda statement,parameters: statement
    query=store.studio_connection_status('unused','unused','unused')
    if query.count('%s')!=3:
        raise ValueError('Studio status query changed; review this fixture.')
    for n in range(1,4):
        query=query.replace('%s','$'+str(n),1)
    assertion="""
    INSERT INTO sarsa_booking.studio_sessions(digest,role,subject,client_id,origin,expires_at)
      VALUES(repeat('a',64),'client','workbook-client','workbook-app','https://www.sarsajyotishsansthan.com',clock_timestamp()+interval '1 hour');
    EXECUTE $status$QUERY$status$ INTO status_result USING repeat('a',64),'workbook-app','https://www.sarsajyotishsansthan.com';
    ASSERT status_result->>'workbook_id'='client-sheet';
    ASSERT status_result->>'authorization_saved'='true';
    EXECUTE $status$QUERY$status$ INTO status_result USING repeat('a',64),'wrong-app','https://www.sarsajyotishsansthan.com';
    ASSERT status_result IS NULL;
    UPDATE sarsa_booking.studio_sessions SET revoked_at=clock_timestamp() WHERE digest=repeat('a',64);
    EXECUTE $status$QUERY$status$ INTO status_result USING repeat('a',64),'workbook-app','https://www.sarsajyotishsansthan.com';
    ASSERT status_result IS NULL;
    """.replace('QUERY',query)
    fixture=(ROOT/'google_workbooks_database.sql').read_text().replace('DECLARE first jsonb;', 'DECLARE status_result jsonb; first jsonb;',1)
    return fixture.replace('END\n$test$;',assertion+'END\n$test$;')


def email_events_check():
    from ..storage import Store
    store=object.__new__(Store)
    store._call=lambda statement,parameters: statement
    query=store.save_provider_event('unused','unused','live','unused','unused',{})
    if query.count('%s')!=6:
        raise ValueError('Provider inbox query changed; review fixture.')
    for n in range(1,7): query=query.replace('%s','$'+str(n),1)
    return """DO $test$
    DECLARE saved text; expected_payload jsonb := '{"event":"email.delivered","email_id":"00000000-0000-4000-8000-000000000001","job_id":"00000000-0000-4000-8000-000000000002","occurred_at":"2026-09-28T00:00:00+00:00"}';
    BEGIN
      EXECUTE $query$QUERY$query$ INTO saved USING 'resend','bookings@mail.sarsajyotishsansthan.com','live','msg_synthetic',repeat('a',64),expected_payload;
      ASSERT saved=repeat('a',64);
      EXECUTE $query$QUERY$query$ INTO saved USING 'resend','bookings@mail.sarsajyotishsansthan.com','live','msg_synthetic',repeat('a',64),expected_payload;
      ASSERT saved=repeat('a',64);
      EXECUTE $query$QUERY$query$ INTO saved USING 'resend','bookings@mail.sarsajyotishsansthan.com','live','msg_synthetic',repeat('b',64),'{}'::jsonb;
      ASSERT saved=repeat('a',64);
      ASSERT (SELECT count(*)=1 FROM sarsa_booking.provider_inbox WHERE provider='resend' AND event_id='msg_synthetic');
      ASSERT (SELECT p.payload=expected_payload AND p.processed_at IS NULL FROM sarsa_booking.provider_inbox p WHERE p.provider='resend' AND p.event_id='msg_synthetic');
    END $test$;""".replace('QUERY',query)


if __name__=='__main__':
    import sys
    print(email_events_check() if '--email-events' in sys.argv else google_workbooks_check() if '--workbooks' in sys.argv else google_delivery_check() if '--google' in sys.argv else recovery_check() if '--recovery' in sys.argv else receipt_query_check())
