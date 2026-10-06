"""Portable native legacy DDL, confined to fixed synthetic proof databases.

Original source hashes and effective business structure are checked unchanged.
Only standalone cluster-role creation is made repeatable; the original literal
Connect grant is redirected to this proof database, never a customer database.
"""
from dataclasses import replace
import hashlib,re
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from appointment_system.settings import Installation
from tools.checks.sql_target import ROOT
from tools.conversion.source import catalogue,detect
from .test_conversion_records import bindings
from tools.conversion.configuration import ConfigurationTransfer

DATABASES={'legacy-004-31':'abs_handover_004','legacy-004-52':'abs_handover_004_full'}
OLD_ROLES={'sarsa_booking_runtime':False,'sarsa_booking_web':True,'sarsa_booking_control':False}
ROLE_CREATION=re.compile(r'^CREATE ROLE ([a-z][a-z0-9_]+)\b[^;]+;',re.M)

def create(target,identifier):
 target.check_owned()
 layout=next(item for item in catalogue() if item.identifier==identifier)
 if identifier not in DATABASES or int(target.name[-2:])!=layout.major:raise AssertionError('Native fixture identity differs.')
 database=DATABASES[identifier];socket=target.native_socket()
 with psycopg.connect(host=socket,dbname='postgres',user='postgres',autocommit=True) as admin:
  admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(database)))
  admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
 connection=psycopg.connect(host=socket,dbname=database,user='postgres',autocommit=True)
 try:
  for name,digest in layout.ledger.items():
   path=ROOT/'tests/legacy_schema'/layout.project/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
   body=path.read_text()
   def role(match):
    name=match.group(1)
    if name not in OLD_ROLES:raise AssertionError('Unreviewed legacy fixture role.')
    found=connection.execute('SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '+
     'FROM pg_roles WHERE rolname=%s',(name,)).fetchone()
    if found is None:return match.group(0)
    if found!=(OLD_ROLES[name],False,False,False,False,False):raise AssertionError('Existing fixture role differs.')
    return ''
   body=ROLE_CREATION.sub(role,body)
   body=body.replace('GRANT CONNECT ON DATABASE neondb TO ',sql.SQL('GRANT CONNECT ON DATABASE {} TO ').format(sql.Identifier(database)).as_string(connection))
   connection.execute(body,prepare=False)
   connection.execute('INSERT INTO sarsa_booking.schema_migrations(version,sha256) VALUES(%s,%s)',(name,digest))
  assert detect(connection).identifier==identifier
  for path in sorted((ROOT/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql')):
   connection.execute(path.read_text(),prepare=False)
   connection.execute('INSERT INTO appointment_system.schema_migrations(version,sha256) VALUES(%s,%s)',
    (path.name,hashlib.sha256(path.read_bytes()).hexdigest()))
  bound=bindings(quota_mapper=ConfigurationTransfer());profile=bound.installation.document
  for declared in profile['database_targets'].values():declared['database']=database
  profile['database_targets']['migration']=dict(profile['database_targets']['web'],role='postgres',pooling=False)
  bound=replace(bound,installation=Installation.parse(profile),receipt_formats=dict(bound.receipt_formats))
  connection.execute('SELECT appointment_system.configure_installation(%s,%s,false)',(Jsonb(profile),Jsonb(bound.business.document)))
  for purpose,declared in profile['database_targets'].items():
   if purpose!='migration':connection.execute('SELECT appointment_system.provision_login(%s,%s)',(declared['role'],purpose))
  assert detect(connection).identifier==identifier
  return connection,bound,database
 except BaseException:
  connection.close();raise
