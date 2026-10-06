"""Re-read imported native records without persisting their private contents.

The saved manifest contains only primary identities, field names and digests.
It is separate from the translator's proposed content digest. Completing a
handover reads those exact records again while normal writers remain paused.
"""
import hashlib,re
from psycopg import sql
from psycopg.types.json import Jsonb
from .source import ConversionError,canonical

NAME=re.compile(r'[a-z][a-z0-9_]{0,62}\Z')
HASH=re.compile(r'[a-f0-9]{64}\Z')
NULLABLE_IDENTITIES={'email_reservations':['job_id','enquiry_job_id','verification_job_id']}
MAX_BATCH=100
MAX_BATCH_BYTES=262144

def identity_fields(connection,table):
 if type(table) is not str or not NAME.fullmatch(table):raise ConversionError('conversion_verification_invalid')
 result=connection.execute("SELECT a.attname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "+
  "JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL unnest(k.conkey) WITH ORDINALITY key(attnum,position) "+
  "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=key.attnum WHERE n.nspname='appointment_system' "+
  "AND c.relname=%s AND k.contype='p' ORDER BY key.position",(table,)).fetchall()
 if not result:
  if table in NULLABLE_IDENTITIES:return NULLABLE_IDENTITIES[table][:]
  raise ConversionError('conversion_verification_identity_missing')
 return [item[0] for item in result]

def read(connection,table,fields,keys):
 target=sql.Identifier('appointment_system',table)
 match=sql.SQL(' AND ').join(sql.SQL('t.{} IS NOT DISTINCT FROM e.{}').format(sql.Identifier(field),sql.Identifier(field)) for field in fields)
 statement=sql.SQL("WITH utc AS MATERIALIZED (SELECT set_config('TimeZone','UTC',true)) "+
  'SELECT to_jsonb(t),to_jsonb(e) FROM utc CROSS JOIN {} t JOIN '+
  'jsonb_populate_recordset(NULL::{},%s) e ON {}').format(target,target,match)
 result=[];batch=[];size=2
 for key in keys:
  length=len(canonical(key))+1
  if length+2>MAX_BATCH_BYTES:raise ConversionError('conversion_verification_record_too_large')
  if batch and (len(batch)>=MAX_BATCH or size+length>MAX_BATCH_BYTES):
   result.extend(connection.execute(statement,(Jsonb(batch),)).fetchall());batch=[];size=2
  batch.append(key);size+=length
 if batch:result.extend(connection.execute(statement,(Jsonb(batch),)).fetchall())
 return result

def fingerprint(rows):return hashlib.sha256(canonical(sorted(canonical(row).decode() for row in rows))).hexdigest()

def capture(connection,tables):
 manifest={}
 for table,rows in sorted(tables.items()):
  if not rows:continue
  fields=identity_fields(connection,table)
  if any(not valid_key(table,fields,{field:row.get(field) for field in fields}) for row in rows):raise ConversionError('conversion_verification_identity_missing')
  keys=[{field:row.get(field) for field in fields} for row in rows]
  if len({canonical(key) for key in keys})!=len(keys):raise ConversionError('conversion_verification_duplicate_identity')
  saved=read(connection,table,fields,rows)
  if len(saved)!=len(rows):raise ConversionError('conversion_verification_missing_record')
  # PostgreSQL casts historical strings/numbers into the target's real types.
  # Compare the explicitly translated fields against that typed representation.
  desired={canonical(tuple(str(row.get(field)) for field in fields)):row for row in rows}
  actual=[];normalized=[]
  for row,typed in saved:
   key=canonical(tuple(str(typed[field]) for field in fields));source=desired.get(key)
   if source is None:raise ConversionError('conversion_verification_identity_changed')
   compared=set(source)-({'created_at'} if table=='booking_policies' else set())
   changed=sorted(field for field in compared if row[field]!=typed[field])
   if changed:raise ConversionError('conversion_verification_content_changed:'+table+':'+','.join(changed))
   actual.append(row);normalized.append({field:row[field] for field in fields})
  manifest[table]={'fields':fields,'keys':normalized,'count':len(actual),'sha256':fingerprint(actual)}
 return manifest

def verify(connection,manifest):
 if type(manifest) is not dict:raise ConversionError('conversion_verification_invalid')
 for table,entry in sorted(manifest.items()):
  if (type(table) is not str or not NAME.fullmatch(table) or type(entry) is not dict
      or set(entry)!={'fields','keys','count','sha256'} or type(entry['fields']) is not list
      or type(entry['keys']) is not list or type(entry['count']) is not int or entry['count']<1
      or entry['count']!=len(entry['keys']) or type(entry['sha256']) is not str or not HASH.fullmatch(entry['sha256'])
      or entry['fields']!=identity_fields(connection,table)
      or any(not valid_key(table,entry['fields'],key) for key in entry['keys'])
      or len({canonical(key) for key in entry['keys']})!=entry['count']):
   raise ConversionError('conversion_verification_invalid')
  rows=read(connection,table,entry['fields'],entry['keys'])
  if len(rows)!=entry['count'] or fingerprint([row[0] for row in rows])!=entry['sha256']:
   raise ConversionError('conversion_verification_content_changed')
 return hashlib.sha256(canonical(manifest)).hexdigest()

def valid_key(table,fields,key):
 if type(key) is not dict or set(key)!=set(fields):return False
 if table in NULLABLE_IDENTITIES:return sum(value is not None for value in key.values())==1
 return all(value is not None for value in key.values())
