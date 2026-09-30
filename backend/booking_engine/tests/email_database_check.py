"""Render development-only rollback assertions around production SQL functions."""
from pathlib import Path
from .database_checks import receipt_query_check


def render():
    fixture=receipt_query_check().replace('DECLARE snapshot jsonb;',
        'DECLARE ej jsonb; begun jsonb; again jsonb; other_job jsonb; msg jsonb; mail_id uuid:=gen_random_uuid(); snapshot jsonb;',1)
    # The base fixture contains a full refund. Use a partial refund for this
    # projection test; no live financial row is edited.
    fixture=fixture.replace("'refunded',250000,'INR',250000,true)","'captured',250000,'INR',10000,true)")
    anchor="        ASSERT NOT has_column_privilege(current_user,'sarsa_booking.intake_settings','public_open','UPDATE');"
    assert fixture.count(anchor)==1
    return fixture.replace(anchor,Path(__file__).with_name('email_dispatch_assertions.sql').read_text().replace('QUERY',(Path(__file__).parents[1]/'queries/receipt_snapshot.sql').read_text().replace('%s','$1'))+'\n'+anchor)


if __name__=='__main__':print(render())
