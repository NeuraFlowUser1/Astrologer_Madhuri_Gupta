"""Database-backed application checks execute from a relocated whole package.

These are contained application/SQL proofs, not a hosted-provider or Chrome
claim. Production entry-point boot is covered separately by ContainedHost.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.install.package import build,identical,install,inventory
from .fixtures import business,installation


CHILD = r'''
import json,os,socket,sys,unittest
from pathlib import Path
project=Path(sys.argv[1]).absolute()
blocked=[Path(value).absolute() for value in sys.argv[2:]]
package=project/'appointment-system'
sys.path[:0]=[str(package),str(package/'engine')]
assert all(not (Path(value).absolute()==root or root in Path(value).absolute().parents)
           for value in sys.path if value for root in blocked)
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).absolute()
        if any(path==root or root in path.parents for root in blocked):
            raise AssertionError('External factory or client file accessed')
    if event=='socket.connect':
        raise AssertionError('External network connection attempted')
sys.addaudithook(audit)
from tools.install.package import verify
release=verify(package)
from appointment_system.configuration import configure,installation
from appointment_system.serialization import decode
configure(decode((project/'appointment-settings/project.json').read_bytes()),
          decode((project/'appointment-settings/business-settings.json').read_bytes()))
from tools.checks.sql_target import SQLTarget
target=SQLTarget(os.environ['BOOKING_SQL_TEST_TARGET'])
target.check_owned()
migrations=target.migrate()
subjects=[
 'tests.test_sql_checkout_flow.CheckoutFlowSQL',
 'tests.test_sql_booking_verification.BookingCodeSQL',
 'tests.test_sql_enquiry_flow.EnquiryFlowSQL',
 'tests.test_sql_company_http.CompanyHTTP',
 'tests.test_sql_company.CompanySQL',
 'tests.test_sql_publication.PublicationSQL',
 'tests.test_sql_staff.StaffSQL',
 'tests.test_sql_owned_records.OwnedRecordsSQL',
]
suite=unittest.defaultTestLoader.loadTestsFromNames(subjects)
result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(suite)
if not result.wasSuccessful() or result.skipped or result.testsRun<50:
    raise SystemExit('Contained native proof incomplete')
modules=[name for name in sys.modules if name=='appointment_system' or name.startswith('appointment_system.')]
for name in modules:
    path=getattr(sys.modules[name],'__file__',None)
    if path:
        assert package in Path(path).absolute().parents,(name,path)
assert verify(package)==release
print(json.dumps({'status':'passed','tests':result.testsRun,'migrations':migrations,
 'installation_id':installation()['installation_id'],'release_digest':release['content_digest']}))
'''


@unittest.skipUnless(os.environ.get('BOOKING_SQL_TEST_TARGET'),'Owned isolated SQL target required.')
class ContainedNative(unittest.TestCase):
    def test_relocated_copy_runs_database_backed_journeys_with_no_factory_or_other_client_access(self):
        with tempfile.TemporaryDirectory(prefix='abs-contained-native-') as temporary:
            root=Path(temporary)
            master=Path(__file__).absolute().parents[1]
            source=root/'removed-master'
            for name in inventory(master):
                destination=source/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(master/name,destination)
            release=build(source)
            project=root/'initial-client'
            project.mkdir()
            subprocess.run(['git','init','-q',str(project)],check=True)
            settings=project/'appointment-settings'
            settings.mkdir()
            facts=installation()
            (settings/'project.json').write_text(json.dumps(facts))
            (settings/'business-settings.json').write_text(json.dumps(business()))
            install(source,project,expected_root=project,installation_id=facts['installation_id'],project_id=facts['project_id'])
            moved=root/'new-owner'/'client'
            moved.parent.mkdir()
            shutil.move(project,moved)
            identical(source,moved/'appointment-system')
            shutil.rmtree(source)
            environment={name:value for name,value in os.environ.items()
                         if name not in ('PYTHONPATH','PYTHONHOME') and not name.startswith(('PG','VERCEL','BOOKING_'))}
            environment.update(PYTHONDONTWRITEBYTECODE='1',BOOKING_SQL_TEST_TARGET=os.environ['BOOKING_SQL_TEST_TARGET'])
            # Deny the real factory too, not just the temporary removed source.
            factory=next((parent for parent in master.parents if parent.name=='neuraflow-website-factory'),master)
            from tools.checks.sql_target import delegated_proof
            with delegated_proof(environment['BOOKING_SQL_TEST_TARGET']):
                reply=subprocess.run([sys.executable,'-c',CHILD,str(moved),str(source),str(factory),
                    '/tmp/booking-standardization-20261001'],cwd=moved,env=environment,
                    capture_output=True,text=True,timeout=600)
            self.assertEqual(reply.returncode,0,reply.stderr[-4500:])
            result=json.loads(reply.stdout)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['installation_id'],facts['installation_id'])
            self.assertEqual(result['release_digest'],release['content_digest'])
            self.assertGreaterEqual(result['tests'],50)
            self.assertEqual(result['migrations'],len(list((master/'engine/appointment_system/migrations').glob('[0-9][0-9][0-9]_*.sql'))))
