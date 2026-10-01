"""Explicit local reliability checks; never a publication gate or provider job."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from summarize import ROOT,summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--node',default=shutil.which('node'))
    parser.add_argument('--chrome',action='store_true',help='Also build and prove Chrome journeys against the actual isolated database.')
    args=parser.parse_args()
    if not args.node:parser.error('Install Node 24 and the frontend development dependencies first.')
    version=subprocess.check_output([args.node,'--version'],text=True,timeout=10).strip()
    if int(version.lstrip('v').split('.')[0])!=24:parser.error('Use the reviewed Node 24 runtime with --node or PATH.')
    vitest=ROOT/'frontend/node_modules/vitest/vitest.mjs'
    if not vitest.is_file():parser.error('Install the frontend development dependencies first.')
    os.chdir(ROOT);environment={**os.environ};environment.pop('NODE_TEST_CONTEXT',None)
    environment['PATH']=str(Path(args.node).resolve().parent)+os.pathsep+environment.get('PATH','')
    config='--rcfile=tools/verification/coverage.ini'
    def run(arguments):subprocess.run(arguments,cwd=ROOT,env=environment,check=True)
    # Each process owns only its synthetic resources. Database runners accept no
    # connection URL and clean up only their exact labelled temporary container.
    suites=('backend/booking_engine/tests','tools/backup','tools/worker-settings')
    for index,folder in enumerate(suites):
        run([sys.executable,'-m','coverage','run',config,*(['--append'] if index else []),'-m','unittest','discover','-s',folder,'-p','test_*.py','-q'])
    for runner in ('tools/verification/database_drill.py','tools/backup/check_restore.py'):
        run([sys.executable,'-m','coverage','run',config,'--append',runner])
    run([sys.executable,'-m','coverage','json',config])
    run([args.node,str(vitest),'run','--config','frontend/vitest.config.mjs','--coverage'])
    result=summarize()
    for name,value in result['domains'].items():print(name+': '+', '.join(f"{metric} {100*v['covered']/v['total']:.2f}%" for metric,v in value.items()))
    if not result['passed']:raise SystemExit('The 90% line/branch target has not been reached for every domain.')
    if args.chrome:
        npm=shutil.which('npm',path=environment['PATH'])
        if not npm:raise SystemExit('Install npm alongside the reviewed Node runtime first.')
        run([npm,'run','build','--prefix','frontend'])
        run([sys.executable,'tools/verification/chrome_check.py','--node',args.node])
    print('PASS: isolated reliability checks and both 90% coverage targets in all six domains.')


if __name__=='__main__':main()
