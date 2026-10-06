"""Native read-only historical schema adapter, for owned paused proof fixtures.

Separate psql sessions are sufficient for these frozen structural assertions.
It is not evidence of a cross-query consistent live export or handover.
"""
import fcntl,json,subprocess
from psycopg import sql
from tools.checks.sql_target import IMAGES as CANONICAL_IMAGES

TARGETS={
 'legacy-003-16':('abs-legacy-003','abs_prefix_003',16),
 'legacy-003-40':('abs-legacy-003','neondb',16),
 'legacy-004-31':('abs-legacy-prefix-004','neondb',18),
 'legacy-004-52':('abs-legacy-004','neondb',18),
}
IMAGES={major:CANONICAL_IMAGES['abs-implementation-pg'+str(major)] for major in (16,18)}

class Rows:
 def __init__(self,values):self.values=values
 def fetchall(self):return [tuple(row.values()) for row in self.values]
 def fetchone(self):return self.fetchall()[0] if self.values else None

class LegacyTarget:
 def __init__(self,identifier):
  self.name,self.database,self.major=TARGETS[identifier]
  self.lock=open('/tmp/'+self.name+'-'+self.database+'-legacy-proof.lock','a')
  fcntl.flock(self.lock.fileno(),fcntl.LOCK_EX)
  result=subprocess.run(['docker','inspect',self.name],capture_output=True,text=True,timeout=15)
  if result.returncode:raise AssertionError('Owned historical proof target is missing.')
  detail=json.loads(result.stdout)[0]
  if (detail['Config']['Labels'].get('neuraflow-purpose')!='abs-isolated-legacy-inspection'
      or detail['HostConfig']['NetworkMode']!='none' or detail['HostConfig']['PortBindings']
      or detail['Config']['Image']!=IMAGES[self.major]):
   raise AssertionError('Historical proof target ownership/network/image differs.')

 def close(self):self.lock.close()

 def run(self,body):
  result=subprocess.run(['docker','exec','-i','--user','postgres',self.name,'psql','-X','-U','postgres',
    '-d',self.database,'-Atq','-v','ON_ERROR_STOP=1'],input=body,capture_output=True,text=True,timeout=45)
  if result.returncode:raise AssertionError('Owned historical proof SQL failed; no SQL values are printed.')
  return result.stdout.strip()

 def execute(self,query,parameters=()):
  query=query.as_string() if isinstance(query,sql.Composable) else query
  parts=query.split('%s')
  if len(parts)!=len(parameters)+1:raise AssertionError('Historical proof parameter shape differs.')
  query=parts[0]+''.join(sql.Literal(value).as_string()+part for value,part in zip(parameters,parts[1:]))
  if not query.lstrip().startswith(('SELECT ','WITH ')):raise AssertionError('Only read statements use this adapter.')
  # A CTE is used by the real reader to fix timestamp serialization to UTC.
  # Enforce read-only in PostgreSQL itself; a SELECT prefix alone would not
  # prevent a write hidden inside a CTE or stored function.
  result=self.run("BEGIN READ ONLY; SELECT coalesce(json_agg(row_to_json(t)),'[]'::json) FROM ("+query.rstrip(';')+") t; COMMIT;")
  return Rows(json.loads(result))
