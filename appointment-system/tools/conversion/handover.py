"""Short, explicit same-database handover. Never runs during serving startup.

The old source is fenced and the final rows are read in one native transaction.
Original schemas/records stay in place for comparison, with all runtime writes
revoked. No role is disabled globally and no other database is altered.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib,re
from uuid import UUID,uuid4
import certifi,psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from appointment_system.connection import checked_config,StorageUnavailable
from appointment_system.configuration import installation as configured_installation
from appointment_system.provider_ingress import JournalStore
from .source import ConversionError,detect,read_rows,canonical,row_fingerprints,catalogue
from .records import Mapper,Bindings,Translation
from . import verification

HASH=re.compile(r'[a-f0-9]{64}\Z')
ROLE=re.compile(r'[a-z][a-z0-9_]{2,62}\Z')

@contextmanager
def migration_connection(dsn,installation):
 try:
  if configured_installation()!=installation.document:raise ConversionError('conversion_target_identity_mismatch')
  target=installation.document['database_targets']['migration']
  config=checked_config(dsn,target['host'],purpose='migration')
  config.update(sslmode='verify-full',sslrootcert=certifi.where(),channel_binding='require',
   connect_timeout=3,prepare_threshold=None,autocommit=True)
  with psycopg.connect(**config) as connection:yield connection
 except ConversionError:raise
 except (StorageUnavailable,psycopg.Error,KeyError):raise ConversionError('conversion_connection_unavailable') from None

class Handover:
 def __init__(self,connection,bindings,release_digest,writer_roles,*,expected_layout=None):
  if (not isinstance(bindings,Bindings) or type(release_digest) is not str or not HASH.fullmatch(release_digest)
      or type(writer_roles) is not tuple or not 1<=len(writer_roles)<=12
      or len(set(writer_roles))!=len(writer_roles) or any(type(role) is not str or not ROLE.fullmatch(role) for role in writer_roles)):
   raise ConversionError('conversion_authority_invalid')
  self.connection=connection;self.bindings=bindings;self.release_digest=release_digest;self.writer_roles=writer_roles
  if expected_layout is not None and (type(expected_layout) is not str or expected_layout not in {item.identifier for item in catalogue()}):
   raise ConversionError('conversion_source_layout_invalid')
  self.expected_layout=expected_layout

 def layout(self):
  layout=detect(self.connection)
  if self.expected_layout is not None and layout.identifier!=self.expected_layout:
   raise ConversionError('conversion_source_layout_mismatch')
  return layout

 @contextmanager
 def transaction(self,*,read_only=False):
  if not self.connection.autocommit:raise ConversionError('conversion_idle_connection_required')
  try:
   with self.connection.transaction():
    if read_only:
     self.connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    self.connection.execute("SET LOCAL lock_timeout='2000'; SET LOCAL statement_timeout='20000'")
    self.connection.execute('SELECT pg_advisory_xact_lock(83124,5)')
    self.connection.execute('SELECT pg_advisory_xact_lock(83124,4)')
    self.owner()
    yield
  except ConversionError:raise
  except psycopg.Error as failure:
   state=failure.sqlstate if type(failure.sqlstate) is str and re.fullmatch('[0-9A-Z]{5}',failure.sqlstate) else 'unknown'
   raise ConversionError('conversion_transaction_'+state) from None

 def preview(self):
  """Translate one consistent snapshot without saving rows or fencing writers.

  This is a diagnostic only. The actual conversion always reads a fresh final
  snapshot under its exclusive fence; preview hashes never replace that read.
  """
  with self.transaction(read_only=True):
   layout=self.layout();self.writer_privileges(layout)
   rows=read_rows(self.connection,layout)
   result=Mapper(layout,rows,self.bindings).translate().summary()
   fingerprints=row_fingerprints(rows)
   return result|{'phase':'preview','release_digest':self.release_digest,
                 'installation_id':self.bindings.installation.installation_id,
                 'environment':self.bindings.installation.document['environment'],
                 'structure_digest':layout.digest,
                 'source_counts':{name:len(values) for name,values in rows.items()},
                 'source_table_digests':fingerprints,
                 'records_changed':False,'writers_fenced':False}

 def checkpoint(self,identifier=None):
  """Recover a lost command response without repeating an import or exposing rows."""
  if identifier is not None:
   try:
    parsed=UUID(str(identifier))
    if parsed.int==0:raise ValueError()
    identifier=str(parsed)
   except (ValueError,TypeError,AttributeError):
    raise ConversionError('conversion_checkpoint_invalid') from None
  with self.transaction(read_only=True):
   clause=' AND id=%s' if identifier is not None else ''
   parameters=(self.bindings.installation.installation_id,identifier) if identifier is not None else (self.bindings.installation.installation_id,)
   row=self.connection.execute('SELECT id::text,phase,source_layout,release_digest,writer_roles,source_digest,target_digest,'+
    'verified_target_digest,source_counts,target_counts FROM appointment_system.conversion_handover '+
    'WHERE installation_id=%s'+clause+' ORDER BY created_at DESC,id DESC LIMIT 1',parameters).fetchone()
   if row is None:
    if identifier is not None:raise ConversionError('conversion_checkpoint_unavailable')
    return None
   if row[3]!=self.release_digest or tuple(row[4])!=self.writer_roles:
    raise ConversionError('conversion_authority_mismatch')
   if self.expected_layout is not None and row[2]!=self.expected_layout:
    raise ConversionError('conversion_source_layout_mismatch')
   fields=('id','phase','source_layout','release_digest','writer_roles','source_digest','target_digest',
           'verified_target_digest','source_counts','target_counts')
   return dict(zip(fields,row))

 def owner(self):
  target=self.bindings.installation.document['database_targets'].get('migration')
  if target is None:raise ConversionError('conversion_migration_target_required')
  row=self.connection.execute("SELECT current_database(),session_user,pg_has_role(session_user,'appointment_system_owner','MEMBER')").fetchone()
  if row!=(target['database'],target['role'],True):raise ConversionError('conversion_owner_required')
  current=self.connection.execute('SELECT specification FROM appointment_system.installation WHERE singleton').fetchone()
  if current is None or current[0]!=self.bindings.installation.document:raise ConversionError('conversion_target_identity_mismatch')

 def status(self,identifier,phase):
  row=self.connection.execute('SELECT source_layout,release_digest,writer_roles,provider_accounts FROM appointment_system.conversion_handover '+
   'WHERE id=%s AND installation_id=%s AND phase=%s FOR UPDATE',(identifier,self.bindings.installation.installation_id,phase)).fetchone()
  if row is None or row[1]!=self.release_digest or tuple(row[2])!=self.writer_roles:raise ConversionError('conversion_phase_conflict')
  return row

 def prepare(self,provider_accounts):
  expected=[{'provider':'razorpay','account_id':item.merchant_id,'mode':item.mode} for item in self.bindings.payment_readers]
  from .mail import MailTransfer
  if isinstance(self.bindings.mail_mapper,MailTransfer):
   expected.append({'provider':'resend','account_id':self.bindings.mail_mapper.connection.account_id,'mode':'live'})
  if (type(provider_accounts) is not list or not provider_accounts or len(provider_accounts)>16
      or any(type(item) is not dict or set(item)!={'provider','account_id','mode'}
       or item['provider'] not in ('razorpay','resend') or type(item['account_id']) is not str
       or not 1<=len(item['account_id'])<=320 or item['mode'] not in ('test','live')
       or item['provider']=='resend' and item['mode']!='live' for item in provider_accounts)
      or len({canonical(item) for item in provider_accounts})!=len(provider_accounts)
      or any(item not in provider_accounts for item in expected)):
   raise ConversionError('conversion_provider_binding_invalid')
  identifier=str(uuid4())
  with self.transaction():
   layout=self.layout();self.writer_privileges(layout)
   counts={table:self.connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*table.split('.')))).fetchone()[0]
    for table in layout.structure['relations']}
   self.connection.execute('INSERT INTO appointment_system.conversion_handover '+
    '(id,installation_id,source_layout,source_digest,phase,writer_roles,provider_accounts,source_counts,release_digest) '+
    "VALUES(%s,%s,%s,%s,'prepared',%s,%s,%s,%s)",
    (identifier,self.bindings.installation.installation_id,layout.identifier,layout.digest,list(self.writer_roles),Jsonb(provider_accounts),Jsonb(counts),self.release_digest))
  return identifier

 def enter_journal_only(self,identifier,journal):
  if (not isinstance(journal,JournalStore) or journal.cipher.ring.installation_id!=self.bindings.installation.installation_id
      or journal.cipher.ring.environment!=self.bindings.installation.document['environment']):
   raise ConversionError('conversion_journal_not_ready')
  nonce=str(uuid4());receipt=journal.readiness(nonce,self.release_digest)
  target=self.bindings.installation.document['database_targets'].get('journal')
  expected={'installation_id':self.bindings.installation.installation_id,'environment':self.bindings.installation.document['environment'],
    'database':target['database'],'login':target['role'],'nonce':nonce,'release_digest':self.release_digest,'writer_contract':1} if target else None
  if receipt!=expected:raise ConversionError('conversion_journal_not_ready')
  with self.transaction():
   self.status(identifier,'prepared')
   self.connection.execute("UPDATE appointment_system.conversion_handover SET phase='journal_only' WHERE id=%s",(identifier,))

 def writer_privileges(self,layout):
  # A runtime that can become an object owner/administrator cannot be fenced by
  # table grants. Refuse it rather than disable a cluster-wide owner login.
  for role in self.writer_roles:
   value=self.connection.execute('SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
   if value!=(True,False,False,False,False,False):raise ConversionError('conversion_legacy_writer_privileged')
   if self.connection.execute('SELECT %s=session_user OR EXISTS(SELECT 1 FROM pg_roles r WHERE '+
     "pg_has_role(%s,r.oid,'MEMBER') AND (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls))",(role,role)).fetchone()[0]:
    raise ConversionError('conversion_legacy_writer_privileged')
   for schema in {table.split('.')[0] for table in layout.structure['relations']}:
    if self.connection.execute("SELECT has_schema_privilege(%s,%s,'CREATE')",(role,schema)).fetchone()[0]:
     raise ConversionError('conversion_legacy_writer_can_change_schema')
   for qualified in layout.structure['relations']:
    if self.connection.execute("SELECT pg_has_role(%s,relowner,'MEMBER') FROM pg_class WHERE oid=%s::regclass",(role,qualified)).fetchone()[0]:
     raise ConversionError('conversion_legacy_writer_is_owner')

 def fence(self,layout):
  self.writer_privileges(layout)
  # The exclusive locks wait for already admitted transactions. Lock order is
  # deterministic. Any timeout rolls back all permission and record changes.
  source_tables=sorted(set(layout.structure['relations'])|{layout.schema+'.schema_migrations'})
  for qualified in source_tables:
   self.connection.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(sql.Identifier(*qualified.split('.'))))
  groups={role for role in self.writer_roles}
  for role in self.writer_roles:
   groups.update(row[0] for row in self.connection.execute("SELECT rolname FROM pg_roles WHERE pg_has_role(%s,oid,'MEMBER')",(role,)).fetchall())
  for qualified in source_tables:
   table=sql.Identifier(*qualified.split('.'))
   for role in sorted(groups):self.connection.execute(sql.SQL('REVOKE ALL ON TABLE {} FROM {}').format(table,sql.Identifier(role)))
   self.connection.execute(sql.SQL('REVOKE ALL ON TABLE {} FROM PUBLIC').format(table))
  # Function identifiers and arguments come from the inspected native catalogue,
  # never from an HTTP value. Includes inherited and PUBLIC old writer paths.
  for schema,name,args,_ in layout.structure['functions']:
   signature=sql.Identifier(schema,name)+sql.SQL('('+args+')')
   for role in sorted(groups):self.connection.execute(sql.SQL('REVOKE ALL ON FUNCTION {} FROM {}').format(signature,sql.Identifier(role)))
   self.connection.execute(sql.SQL('REVOKE ALL ON FUNCTION {} FROM PUBLIC').format(signature))
  for role in self.writer_roles:
   for qualified in source_tables:
    allowed=self.connection.execute("SELECT has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",(role,qualified)).fetchone()[0]
    if allowed:raise ConversionError('conversion_legacy_writer_not_fenced')
   for schema,name,args,_ in layout.structure['functions']:
    allowed=self.connection.execute("SELECT has_function_privilege(%s,p.oid,'EXECUTE') FROM pg_proc p "+
     'JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s '+
     'AND pg_get_function_identity_arguments(p.oid)=%s',(role,schema,name,args)).fetchall()
    if len(allowed)!=1 or allowed[0][0]:
     raise ConversionError('conversion_legacy_writer_not_fenced')

 def convert(self,identifier):
  with self.transaction():
   old=self.status(identifier,'journal_only');layout=self.layout()
   if layout.identifier!=old[0]:raise ConversionError('conversion_source_changed')
   self.fence(layout)
   if detect(self.connection).digest!=layout.digest:raise ConversionError('conversion_source_changed')
   self.connection.execute("UPDATE appointment_system.conversion_handover SET phase='fenced' WHERE id=%s",(identifier,))
   # Locks prevent legacy changes; one transaction supplies the final consistent
   # snapshot. Readiness does not replace this final read with an earlier export.
   rows=read_rows(self.connection,layout);translated=Mapper(layout,rows,self.bindings).translate()
   self.insert(translated)
   manifest=verification.capture(self.connection,translated.tables)
   verified_digest=verification.verify(self.connection,manifest)
   self.connection.execute("UPDATE appointment_system.conversion_handover SET phase='imported',source_digest=%s,target_digest=%s,"+
    'source_counts=%s,target_counts=%s,verification_manifest=%s,verified_target_digest=%s WHERE id=%s',
    (translated.source_digest,translated.target_digest,Jsonb({table:len(values) for table,values in rows.items()}),
     Jsonb(translated.summary()['target_counts']),Jsonb(manifest),verified_digest,identifier))
  return translated.summary()

 def insert(self,translated):
  if not isinstance(translated,Translation):raise ConversionError('conversion_result_invalid')
  tables=translated.tables;patches=[]
  for row in tables.get('checkout_contexts',[]):
   if row.get('active_checkout_id'):
    patches.append((row['id'],row['active_checkout_id']));row['active_checkout_id']=None
  remaining=set(tables);order=[]
  dependencies={table:set() for table in tables}
  # The active workbook INSERT has a seeding trigger. Explicit historical
  # volumes must exist first so that the trigger checks their exact identity.
  if tables.get('google_workbooks') and tables.get('google_workbook_volumes'):
   dependencies['google_workbooks'].add('google_workbook_volumes')
  for child,parent,fields in self.connection.execute("SELECT c.relname,p.relname,ARRAY(SELECT a.attname FROM unnest(k.conkey) key "+
    "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=key) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "+
    "JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='appointment_system' AND k.contype='f'").fetchall():
   if (child in dependencies and parent in dependencies and child!=parent
       and any(all(row.get(field) is not None for field in fields) for row in tables[child])):
    dependencies[child].add(parent)
  while remaining:
   available=sorted(table for table in remaining if not dependencies[table]&remaining)
   if not available:raise ConversionError('conversion_dependency_cycle')
   order.extend(available);remaining.difference_update(available)
  forbidden={'installation','caller_logins','company_credentials','company_password_recoveries','company_sessions','studio_sessions','google_attempts',
   'control_product_state','control_publications','conversion_handover','conversion_retained_enquiries',
   'schema_migrations','worker_runs','worker_release'}
  for table in order:
   if table in forbidden or not ROLE.fullmatch(table):raise ConversionError('conversion_target_forbidden')
   columns=self.connection.execute('SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid '+
    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='appointment_system' AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped",(table,)).fetchall()
   allowed={item[0] for item in columns}
   if not allowed:raise ConversionError('conversion_target_unrecognized')
   for row in tables[table]:
    if not row or set(row)-allowed:raise ConversionError('conversion_target_columns_unrecognized')
    names=sorted(row);target=sql.Identifier('appointment_system',table);fields=sql.SQL(',').join(map(sql.Identifier,names))
    if table=='booking_policies':
     existing=self.connection.execute('SELECT specification FROM appointment_system.booking_policies WHERE version=%s',(row['version'],)).fetchone()
     if existing is not None:
      if existing[0]!=row['specification']:raise ConversionError('conversion_policy_collision')
      continue
    if table=='google_resources':
     existing=self.connection.execute('SELECT owner_email,active_client,retained_clients,grant_id FROM appointment_system.google_resources WHERE resource=%s',
      (row['resource'],)).fetchone()
     if existing is not None:
      if existing[:3]!=(row['owner_email'],row['active_client'],row['retained_clients']) or existing[3] is not None:
       raise ConversionError('conversion_resource_collision')
      self.connection.execute('UPDATE appointment_system.google_resources SET grant_id=%s,revision=%s,updated_at=%s WHERE resource=%s',
       (row['grant_id'],row['revision'],row['updated_at'],row['resource']))
      continue
    self.connection.execute(sql.SQL('INSERT INTO {} ({}) SELECT {} FROM jsonb_populate_record(NULL::{},%s)')
       .format(target,fields,fields,target),(Jsonb(row),))
  for context,booking in patches:
   self.connection.execute('UPDATE appointment_system.checkout_contexts SET active_checkout_id=%s WHERE id=%s',(booking,context))

 def complete(self,identifier,expected_digest):
  if type(expected_digest) is not str or not HASH.fullmatch(expected_digest):raise ConversionError('conversion_result_invalid')
  with self.transaction():
   status=self.status(identifier,'imported')
   saved,manifest,verified_digest,source_digest=self.connection.execute('SELECT target_digest,verification_manifest,verified_target_digest,source_digest '+
    'FROM appointment_system.conversion_handover WHERE id=%s',(identifier,)).fetchone()
   if saved!=expected_digest:raise ConversionError('conversion_result_mismatch')
   if verification.verify(self.connection,manifest)!=verified_digest:raise ConversionError('conversion_result_mismatch')
   layout=self.layout()
   if layout.identifier!=status[0]:raise ConversionError('conversion_source_changed')
   self.fence(layout)
   if hashlib.sha256(canonical(row_fingerprints(read_rows(self.connection,layout)))).hexdigest()!=source_digest:
    raise ConversionError('conversion_source_records_changed')
   # Completing the handover never enables booking. The separate reviewed
   # publication/ON protocol must still acknowledge the actual website.
   if self.connection.execute('SELECT enabled FROM appointment_system.control_product_state WHERE singleton').fetchone()[0] is not False:
    raise ConversionError('conversion_activation_must_remain_off')
   # Only after exact source/target comparison may the retired source's update
   # guards change to the narrowly approved privacy-only path.
   from .retained import prepare
   prepare(self.connection,layout,identifier)
   self.connection.execute("UPDATE appointment_system.conversion_handover SET phase='complete',completed_at=clock_timestamp() WHERE id=%s",(identifier,))

 def abort_before_import(self,identifier):
  with self.transaction():
   row=self.connection.execute('SELECT phase,installation_id,release_digest,writer_roles FROM appointment_system.conversion_handover WHERE id=%s FOR UPDATE',(identifier,)).fetchone()
   if (row is None or row[0] not in ('prepared','journal_only') or str(row[1])!=self.bindings.installation.installation_id
       or row[2]!=self.release_digest or tuple(row[3])!=self.writer_roles):raise ConversionError('conversion_rollback_forbidden')
   if self.connection.execute('SELECT EXISTS(SELECT 1 FROM appointment_system.provider_inbox WHERE journal_envelope IS NOT NULL AND processed_at IS NULL)').fetchone()[0]:
    raise ConversionError('conversion_pending_notifications_require_resolution')
   self.connection.execute("UPDATE appointment_system.conversion_handover SET phase='aborted' WHERE id=%s",(identifier,))
