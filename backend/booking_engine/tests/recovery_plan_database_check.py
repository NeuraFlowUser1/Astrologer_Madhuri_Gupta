"""Development-only rollback proof using the exact runtime scheduling query."""
from pathlib import Path
from .database_checks import receipt_query_check


def render():
    fixture=receipt_query_check().replace('DECLARE snapshot jsonb;', 'DECLARE recovery jsonb; snapshot jsonb;',1)
    fixture=fixture.replace('    BEGIN\n        -- Fixtures',
        "    BEGIN\n        ASSERT NOT EXISTS(SELECT 1 FROM sarsa_booking.bookings);\n        -- Fixtures",1)
    query=(Path(__file__).parents[1]/'queries/recovery_plan.sql').read_text()
    assertions="""
        EXECUTE $plan$QUERY$plan$ INTO recovery;
        ASSERT recovery->'lanes'->>'email'='0',recovery::text;
        ASSERT recovery->'lanes'->>'google'='0',recovery::text;
        ASSERT recovery->>'attention'='true',recovery::text;
        UPDATE sarsa_booking.delivery_jobs SET state='processing',lease_token=gen_random_uuid(),
          lease_expires_at=statement_timestamp()+interval '120 seconds';
        EXECUTE $plan$QUERY$plan$ INTO recovery;
        ASSERT (recovery->'lanes'->>'email')::integer=120,recovery::text;
        ASSERT (recovery->'lanes'->>'google')::integer=120,recovery::text;
        UPDATE sarsa_booking.payment_orders SET next_check_at=statement_timestamp()+interval '1 hour';
        EXECUTE $plan$QUERY$plan$ INTO recovery;
        ASSERT recovery->'lanes'->>'payment'='900',recovery::text;
        INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload,next_attempt_at,lease_token,lease_expires_at)
          VALUES('resend','bookings@mail.sarsajyotishsansthan.com','live','synthetic_recovery_plan',repeat('a',64),
          '{}'::jsonb,statement_timestamp()+interval '30 seconds',gen_random_uuid(),statement_timestamp()+interval '180 seconds');
        EXECUTE $plan$QUERY$plan$ INTO recovery;
        ASSERT recovery->'lanes'->>'email_events'='180',recovery::text;
        ASSERT recovery->'lanes'->>'payment_events' IS NULL,recovery::text;
        UPDATE sarsa_booking.delivery_jobs SET state='attention',lease_token=NULL,lease_expires_at=NULL;
        EXECUTE $plan$QUERY$plan$ INTO recovery;
        ASSERT recovery->'lanes'->>'email' IS NULL,recovery::text;
        ASSERT recovery->'lanes'->>'google' IS NULL,recovery::text;
        ASSERT recovery->>'attention'='true',recovery::text;
    """.replace('QUERY',query)
    anchor="        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');"
    assert fixture.count(anchor)==1
    return fixture.replace(anchor,assertions+'\n'+anchor).replace('sarsa_booking_runtime','sarsa_booking_web')


if __name__=='__main__':print(render())
