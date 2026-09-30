"""Rollback-only checkout lease proof under the real website role."""
from pathlib import Path


def render():
    source = Path(__file__).with_name('reservation_database.sql').read_text()
    source = source.replace('DECLARE c1 uuid', 'DECLARE snapshot jsonb; job jsonb; c1 uuid', 1)
    source = source.replace('    BEGIN\n        -- Fixtures',
        '    BEGIN\n        ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.bookings);\n        -- Fixtures', 1)
    anchor = '        ASSERT sarsa_booking.abandon_unattempted(c1,b);'
    assert source.count(anchor) == 1
    checks = """
        BEGIN
            ASSERT sarsa_booking.claim_checkout_resume(b) IS NULL;
            ASSERT sarsa_booking.start_order_creation(c1,b);
            ASSERT sarsa_booking.record_order_creation(c1,b,'syntheticOnly','live','syntheticOnly','order_synthetic')='ready';
            ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
              'pay_resume','order_synthetic',repeat('7',64),'authorized',250000,'INR',0,false)='observed';
            EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING r2;
            ASSERT snapshot->'booking'->>'payment_state'='pending',snapshot::text;
            ASSERT sarsa_booking.observe_payment(c1,b,'syntheticOnly','live','syntheticOnly',
              'pay_resume','order_synthetic',repeat('8',64),'failed',250000,'INR',0,false)='observed';
            EXECUTE $receipt$QUERY$receipt$ INTO snapshot USING r2;
            ASSERT snapshot->'booking'->>'payment_state'='failed_observed',snapshot::text;
            job := sarsa_booking.claim_checkout_resume(b);
            ASSERT job->>'booking_id'=b::text,job::text;
            ASSERT sarsa_booking.claim_checkout_resume(b) IS NULL;
            ASSERT NOT sarsa_booking.finish_payment_recovery(b,gen_random_uuid(),15,0,0,NULL);
            ASSERT sarsa_booking.finish_payment_recovery(b,(job->>'lease_token')::uuid,15,0,0,NULL);
            ASSERT sarsa_booking.claim_checkout_resume(b) IS NULL;
            UPDATE sarsa_booking.payment_orders SET resume_started_at=clock_timestamp()-interval '16 seconds' WHERE booking_id=b;
            job := sarsa_booking.claim_checkout_resume(b);
            ASSERT job IS NOT NULL;
            UPDATE sarsa_booking.payment_orders SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE booking_id=b;
            ASSERT NOT sarsa_booking.finish_payment_recovery(b,(job->>'lease_token')::uuid,15,0,0,NULL);
            UPDATE sarsa_booking.payment_orders SET resume_started_at=clock_timestamp()-interval '16 seconds' WHERE booking_id=b;
            UPDATE sarsa_booking.bookings SET created_at=clock_timestamp()-interval '11 minutes',
              hold_expires_at=clock_timestamp()-interval '1 second' WHERE id=b;
            ASSERT sarsa_booking.claim_checkout_resume(b) IS NULL;
            RAISE EXCEPTION USING ERRCODE='P0981',MESSAGE='rollback resume fixture';
        EXCEPTION WHEN SQLSTATE 'P0981' THEN NULL;
        END;
"""
    query = (Path(__file__).parents[1]/'queries/receipt_snapshot.sql').read_text().replace('%s','$1')
    return source.replace(anchor, checks.replace('QUERY',query) + '\n' + anchor).replace('sarsa_booking_runtime', 'sarsa_booking_web')


if __name__ == '__main__': print(render())
