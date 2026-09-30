"""Development rollback proof: actual booking and enquiry admission share a cap."""
from .email_database_check import render as booking_fixture


def render():
    sql=booking_fixture().replace('DECLARE ej jsonb;', 'DECLARE contact_job jsonb; contact_request uuid:=gen_random_uuid(); ej jsonb;',1)
    anchor='        -- Another message cannot consume the same exhausted allocation.'
    before,after=sql.split(anchor)
    injection="""
        RESET ROLE;
        UPDATE sarsa_booking.contact_intake SET public_open=true;
        UPDATE sarsa_booking.email_policy SET contact_daily_limit=1,contact_monthly_limit=1;
        SET LOCAL ROLE sarsa_booking_runtime;
        PERFORM sarsa_booking.start_enquiry(contact_request,repeat('1',64),repeat('2',64),
          '{"name":"Synthetic","email":"contact-budget@example.com","phone":"","subject":"Test","message":"Synthetic only."}',repeat('3',64),repeat('x',120),repeat('4',64));
        contact_job:=sarsa_booking.claim_enquiry_delivery('email');
        ASSERT contact_job IS NOT NULL,'Contact budget fixture admitted';
        ASSERT sarsa_booking.begin_enquiry_send((contact_job->>'id')::uuid,(contact_job->>'lease_token')::uuid,repeat('y',150),repeat('5',64)) IS NULL,'Contact must count booking reservation';
        RESET ROLE;
        UPDATE sarsa_booking.email_policy SET daily_limit=2;
        SET LOCAL ROLE sarsa_booking_runtime;
        UPDATE sarsa_booking.enquiry_delivery_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=(contact_job->>'id')::uuid;
        contact_job:=sarsa_booking.claim_enquiry_delivery('email');
        ASSERT sarsa_booking.begin_enquiry_send((contact_job->>'id')::uuid,(contact_job->>'lease_token')::uuid,repeat('y',150),repeat('5',64)) IS NOT NULL,'Contact within shared allowance';
        ASSERT (SELECT count(*)=2 FROM sarsa_booking.email_reservations),'Both reservation kinds counted';
        ASSERT NOT sarsa_booking.finish_enquiry_delivery((contact_job->>'id')::uuid,(contact_job->>'lease_token')::uuid,mail_id::text,NULL,false,15),'Contact cannot claim booking provider identity';
        ASSERT (SELECT state='attention' AND provider_id IS NULL FROM sarsa_booking.enquiry_delivery_jobs WHERE id=(contact_job->>'id')::uuid),'Provider conflict retained for review';
"""
    # The remaining booking admission must now see one booking + one enquiry.
    after=after.replace('count(*)=1 FROM sarsa_booking.email_reservations','count(*)=2 FROM sarsa_booking.email_reservations')
    return before+injection+anchor+after


if __name__=='__main__':print(render())
