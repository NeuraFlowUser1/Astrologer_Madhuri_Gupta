"""Run the shipped setup commands from a relocated, factory-independent copy.

The only substituted boundary is the database transport: an owned local Unix
socket replaces production TLS. Password prompts use synthetic test input.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import psycopg
from psycopg import sql
from tools.checks.sql_target import SQLTarget, ROOT
from tools.install.package import build, inventory, install
from .fixtures import installation, business

DATABASE = 'abs_setup_contained'
CHILD = r'''
import builtins, importlib.util, json, os, socket, sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import psycopg

project=Path(sys.argv[1]);db_socket=sys.argv[2];blocked=Path(sys.argv[3])
root=project/'appointment-system'
sys.path[:0]=[str(root),str(root/'engine')]
def audit(event,args):
    if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).absolute()
        if path==blocked or blocked in path.parents:raise AssertionError('Factory access attempted')
sys.addaudithook(audit)
def no_network(*args,**kwargs):raise AssertionError('External provider access attempted')
socket.create_connection=no_network
socket.socket.connect=no_network
from appointment_system.configuration import load
profile=load(project/'appointment-settings/project.json')
assert profile.installation.document['environment']=='test'
assert profile.installation.document['database_targets']['migration']['database']=='abs_setup_contained'
from tools.conversion import handover
@contextmanager
def isolated_connection(dsn,declared):
    assert dsn=='synthetic-owned-socket'
    assert declared==profile.installation
    with psycopg.connect(host=db_socket,dbname='abs_setup_contained',user='postgres',autocommit=True) as connection:
        yield connection
spec=importlib.util.spec_from_file_location('contained_setup',root/'tools/setup.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
environment={'BOOKING_MIGRATION_DATABASE_URL':'synthetic-owned-socket'}
with patch.object(handover,'migration_connection',isolated_connection):
    for action in ('install-schema','install-schema','initialize','initialize','register-logins'):
        assert module.main([action],environment)==0,action
    with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',return_value='company.owner'), patch('getpass.getpass',return_value='Synthetic isolated company credential'):
        assert module.main(['enroll-company'],environment)==0
    from tools import company_recovery
    with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',return_value='company.owner'), patch('getpass.getpass',return_value='Synthetic recovered company credential'):
        assert company_recovery.main(['inspect'],environment)==0
        command=['recover','--operation-id','1257662b-c555-4ce5-bd4f-0eab2bfe89b8',
            '--expected-revision','1','--reason','Verified synthetic owner recovery']
        assert company_recovery.main(command,environment)==0
        assert company_recovery.main(command,environment)==0
        assert company_recovery.main(['inspect'],environment)==0
from appointment_system.runtime import contained_release
package,digest=contained_release()
assert package==root
assert all(str(blocked) not in value for value in sys.path)
print(json.dumps({'status':'contained_setup_passed','release_digest':digest}))
'''


@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'), 'Owned isolated SQL target required.')
class ContainedSetup(unittest.TestCase):
    def test_complete_setup_runs_from_relocated_copy_without_factory_or_provider_access(self):
        target=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET']);target.check_owned();db_socket=target.native_socket()
        with psycopg.connect(host=db_socket,dbname='postgres',user='postgres',autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(DATABASE)))
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DATABASE)))
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);source=home/'master';project=home/'client'
            for name in inventory(ROOT):
                destination=source/name;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,destination)
            release=build(source)
            project.mkdir();subprocess.run(['git','init','-q',str(project)],check=True)
            facts=installation()
            for declared in facts['database_targets'].values():declared['database']=DATABASE
            facts['database_targets']['migration']=dict(facts['database_targets']['web'],role='postgres',pooling=False)
            settings=project/'appointment-settings';settings.mkdir()
            (settings/'project.json').write_text(json.dumps(facts))
            (settings/'business-settings.json').write_text(json.dumps(business()))
            install(source,project,expected_root=project,installation_id=facts['installation_id'],project_id=facts['project_id'])
            moved=home/'handed-over';shutil.move(project,moved);shutil.rmtree(source)
            environment={key:value for key,value in os.environ.items()
                if key not in ('PYTHONPATH','PYTHONHOME') and not key.startswith(('BOOKING_','PG','VERCEL'))}
            environment['PYTHONDONTWRITEBYTECODE']='1'
            result=subprocess.run([sys.executable,'-c',CHILD,str(moved),db_socket,str(ROOT)],
                cwd=moved,env=environment,text=True,capture_output=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr[-3000:])
            self.assertNotIn('Synthetic isolated company credential',result.stdout+result.stderr)
            self.assertNotIn('Synthetic recovered company credential',result.stdout+result.stderr)
            output=[json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([row['status'] for row in output],
                ['schema_verified','schema_verified','initialized','existing','registered','enrolled',
                 'inspected','recovered','existing','inspected','contained_setup_passed'])
            self.assertEqual(output[-2]['credential_revision'],2)
            self.assertEqual(output[-1]['release_digest'],release['content_digest'])
        with psycopg.connect(host=db_socket,dbname=DATABASE,user='postgres',autocommit=True) as connection:
            self.assertIs(connection.execute('SELECT enabled FROM appointment_system.control_product_state').fetchone()[0],False)
            self.assertEqual(connection.execute('SELECT username FROM appointment_system.company_credentials').fetchall(),[('company.owner',)])
            self.assertEqual(connection.execute('SELECT count(*) FROM appointment_system.control_company_sessions').fetchone()[0],0)
            self.assertEqual(connection.execute('SELECT previous_revision,resulting_revision FROM appointment_system.company_password_recoveries').fetchall(),[(1,2)])
            applied=dict(connection.execute('SELECT version,sha256 FROM appointment_system.schema_migrations').fetchall())
            expected={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (ROOT/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql')}
            self.assertEqual(applied,expected)
