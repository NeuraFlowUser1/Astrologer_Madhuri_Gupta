"""Disconnected receiving Python entry proof; no actual runtime/provider import."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch
import coverage

here=Path(__file__).resolve().parent
project=here.parents[3]
entry=project/'api/index.py'
before=hashlib.sha256(entry.read_bytes()).hexdigest()
calls=[]
runtime=ModuleType('appointment_system.runtime')
sentinel=object()
def compose(config,environment):
    calls.append((config,environment))
    return sentinel
runtime.create_application=compose
package=ModuleType('appointment_system');package.__path__=[]
cases=[]
with tempfile.TemporaryDirectory(prefix='sarsa004-entry-proof-') as temporary:
    cov=coverage.Coverage(data_file=str(Path(temporary)/'.coverage'),source=[str(entry.parent)],branch=True,config_file=False)
    cov.start()
    original_path=sys.path[:]
    try:
        with patch.dict(sys.modules,{'appointment_system':package,'appointment_system.runtime':runtime}),patch.dict('os.environ',{'SARSA_QA_ENTRY':'controlled-local-only'},clear=True):
            result=runpy.run_path(str(entry))
            assert result['app'] is sentinel and len(calls)==1
            assert calls[0][0]==project/'appointment-settings/project.json'
            assert calls[0][1]=={'SARSA_QA_ENTRY':'controlled-local-only'}
            cases.append('Actual entry composes only its contained package/settings and copies the controlled environment')
            paths=[Path(temporary)/'linked-entry.py',Path(temporary)/'linked-parent']
            paths[0].symlink_to(entry);paths[1].symlink_to(project,target_is_directory=True)
            for path,label in [(paths[0],'entry'),(paths[1]/'api/index.py','parent')]:
                try:runpy.run_path(str(path))
                except RuntimeError as error:assert str(error)=='Project entry point links are forbidden.'
                else:raise AssertionError('Linked '+label+' did not refuse')
                assert len(calls)==1
                cases.append('Actual '+label+' symlink refuses before runtime import/composition')
    finally:
        sys.path[:]=original_path
        cov.stop();cov.save()
    raw=Path(temporary)/'coverage.json';cov.json_report(outfile=str(raw))
    report=json.loads(raw.read_text())
    assert len(report['files'])==1 and report['totals']['covered_lines']==report['totals']['num_statements']
    assert report['totals']['covered_branches']==report['totals']['num_branches']
    assert report['totals']['excluded_lines']==0
    assert hashlib.sha256(entry.read_bytes()).hexdigest()==before
    proof={'passed':True,'cases':cases,'owner':'api/index.py','sha256':before,'unchanged':True,'runtimeDouble':'Test-only composition recorder; actual source executed and no provider/runtime imported','excluded':[],**report}
    (here/'entry-contract-coverage.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'passed':True,'cases':len(cases),'owners':len(report['files']),'totals':report['totals'],'sourceUnchanged':True,'providerCalls':0}))
