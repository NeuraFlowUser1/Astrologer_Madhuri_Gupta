"""Pin the real published legacy privacy boundary after final comparison.

This is offline owner-only conversion, never a second serving implementation.
The maintained schema contains hashes and references, never another payload copy.
"""
from psycopg import sql
from .source import ConversionError


def prepare(connection, layout, handover):
    if layout.identifier == 'legacy-003-16':
        # This published format contains accepted enquiries only. No approved
        # routine retention policy may erase these business records.
        return
    if layout.identifier != 'legacy-004-31':
        raise ConversionError('legacy_retention_layout_unproved')
    connection.execute("SET LOCAL TimeZone='UTC'")
    schema = sql.Identifier(layout.schema)
    connection.execute(sql.SQL('''
        INSERT INTO appointment_system.conversion_retained_enquiries
          (handover_id,request_id,source_schema,enquiry_hash,job_hashes)
        SELECT %s,e.request_id,%s,encode(sha256(convert_to(to_jsonb(e)::text,'UTF8')),'hex'),
          coalesce((SELECT jsonb_object_agg(j.id,encode(sha256(convert_to(to_jsonb(j)::text,'UTF8')),'hex'))
            FROM {}.enquiry_delivery_jobs j WHERE j.request_id=e.request_id),'{{}}'::jsonb)
        FROM {}.enquiries e WHERE e.verified_at IS NULL
        ''').format(schema,schema), (handover,layout.schema))
    connection.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO appointment_system_owner').format(schema))
    for table, trigger, columns in (
        ('enquiries','enquiry_identity',('payload','code_digest','code_ciphertext')),
        ('enquiry_delivery_jobs','enquiry_delivery_identity',
         ('destination','message_ciphertext','state','lease_token','lease_expires_at')),
    ):
        relation = sql.Identifier(layout.schema,table)
        connection.execute(sql.SQL('GRANT SELECT ON {} TO appointment_system_owner').format(relation))
        connection.execute(sql.SQL('GRANT UPDATE ({}) ON {} TO appointment_system_owner').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),relation))
        connection.execute(sql.SQL('DROP TRIGGER {} ON {}').format(sql.Identifier(trigger),relation))
        connection.execute(sql.SQL('CREATE TRIGGER retained_source_guard BEFORE INSERT OR UPDATE OR DELETE ON {} '
            'FOR EACH ROW EXECUTE FUNCTION appointment_system.retained_enquiry_guard()').format(relation))
