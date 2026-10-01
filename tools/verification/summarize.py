"""Require line AND branch coverage per domain, without averaging away gaps."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ARTIFACTS=ROOT/'tools/verification/artifacts'
PYTHON={'booking_backend':'backend/booking_engine/','backup_helpers':'tools/backup/','worker_setting_helpers':'tools/worker-settings/'}
JAVASCRIPT={'customer_logic':'frontend/src/','staff_logic':'backend/booking_engine/studio_assets/','recovery_worker':'workers/booking-recovery/'}
REQUIRED_JS={
    'frontend/src/booking/'+name for name in ('state.mjs','protocol.mjs','razorpay.mjs','useBooking.jsx')
}|{'frontend/src/pages/Booking.jsx'}|{
    'frontend/src/contact/'+name for name in ('protocol.mjs','useEnquiry.jsx','ContactForm.jsx')
}|{'frontend/src/site/'+name for name in ('routes.mjs','page-metadata.mjs')}|{
    'backend/booking_engine/studio_assets/'+name for name in ('interface.js','calendar.js','appointments.js','inbox.js','recovery.js')
}|{'workers/booking-recovery/'+name for name in ('worker.mjs','monitor.mjs')}


def summarize(minimum=90):
    python=json.loads((ARTIFACTS/'python-coverage.json').read_text())['files']
    js_raw=json.loads((ARTIFACTS/'javascript/coverage-summary.json').read_text())
    javascript={str(Path(path).resolve().relative_to(ROOT)):value for path,value in js_raw.items() if path!='total'}
    if set(javascript)!=REQUIRED_JS:raise ValueError('JavaScript coverage scope is incomplete or unexpected.')
    for prefix in PYTHON.values():
        expected={str(path.relative_to(ROOT)) for path in (ROOT/prefix).rglob('*.py')
                  if 'tests' not in path.parts and not path.name.startswith('test_')}
        if not expected.issubset(python):raise ValueError('Python coverage omitted active source files.')
    domains={}
    for name,prefix in PYTHON.items():
        selected=[value['summary'] for path,value in python.items() if path.startswith(prefix)]
        domains[name]={'lines':{'covered':sum(v['covered_lines'] for v in selected),'total':sum(v['num_statements'] for v in selected)},
                       'branches':{'covered':sum(v['covered_branches'] for v in selected),'total':sum(v['num_branches'] for v in selected)}}
    for name,prefix in JAVASCRIPT.items():
        selected=[value for path,value in javascript.items() if path.startswith(prefix)]
        domains[name]={metric:{key:sum(value[metric][key] for value in selected) for key in ('covered','total')} for metric in ('lines','branches')}
    passed=True
    for value in domains.values():
        for metric in value.values():
            if metric['total']<=0:raise ValueError('Empty coverage domain cannot pass.')
            metric['percent']=round(100*metric['covered']/metric['total'],4)
            metric['passed']=metric['covered']*100>=minimum*metric['total'];passed&=metric['passed']
    files=sorted(set(python)|set(javascript))
    evidence={'measured_at':datetime.now(timezone.utc).isoformat(),'minimum_per_metric':minimum,'passed':passed,
              'domains':domains,'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in files},
              'collectors':{'python':'coverage.py, branch=True','javascript':'Istanbul with shared classic-script counters'},
              'excluded':['test code','third-party libraries','decorative motion','other marketing-page composition','CSS','static artwork/copy','retired legacy backend','design-review prototypes'],
              'separate_evidence':['SQL and PL/pgSQL assertions and role permissions','Windows secure handoff','Chrome rendering and navigation','hosted provider acceptance','actual notification receipt']}
    (ARTIFACTS/'coverage-result.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return evidence


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--minimum',type=float,default=90);args=parser.parse_args()
    if not 0<=args.minimum<=100:parser.error('Minimum must be between zero and 100.')
    result=summarize(args.minimum)
    for name,value in result['domains'].items():
        print(name+': '+', '.join(f"{metric} {v['percent']:.2f}% ({v['covered']}/{v['total']})" for metric,v in value.items()))
    if not result['passed']:raise SystemExit('Coverage target not met in every domain.')
    print('PASS: every measured domain meets both coverage targets.')


if __name__=='__main__':main()
