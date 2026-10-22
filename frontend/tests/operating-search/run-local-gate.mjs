/** Complete receiving gate. All writes stay in local build/ignored QA outputs. */
import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'../..'),output=resolve(root,'coverage/operating-browser');mkdirSync(output,{recursive:true});
// Every pool must come from this run, after its single source checkpoint.
// Remove only named ignored receipts; never clear source or prior dated evidence.
for(const file of ['unit-results.json','unit-sources.json','source-fingerprints.json','server-coverage.json','browser-coverage.json','browser-observations.json','native-source-coverage.json','public-build-coverage.json','joined-coverage.json','coverage-audit.json','gate-summary.json','gate-blocked.json'])rmSync(resolve(output,file),{force:true});
for(const file of ['coverage-final.json','native-coverage.json'])rmSync(resolve(root,'coverage/public-site',file),{force:true});
const phases=[];
function run(label,args,{allowPartialCoverage=false,env={}}={}){
 const result=spawnSync(process.execPath,args,{cwd:root,env:{...process.env,...env},encoding:'utf8',maxBuffer:32*1024*1024});
 writeFileSync(resolve(output,label+'.log'),(result.stdout||'')+(result.stderr||''));
 if(result.error)throw result.error;
 if(result.status!==0){
  if(!allowPartialCoverage)throw Error(label+' failed; inspect '+resolve(output,label+'.log'));
  const tests=JSON.parse(readFileSync(resolve(output,'unit-results.json')));
  assert.equal(result.status,1);assert.equal(tests.numFailedTests,0);assert.equal(tests.numFailedTestSuites,0);assert.equal(tests.numPendingTests,0);assert(tests.numPassedTests>200);assert(tests.testResults.every(suite=>suite.status==='passed'));
  assert(/Coverage for .* does not meet global threshold/.test(result.stdout+result.stderr),'A non-coverage failure cannot be treated as a partial measurement');
 }
 phases.push({label,status:result.status,partialMeasurement:result.status!==0});console.log(JSON.stringify(phases.at(-1)));
}
try{
 run('production-build',['node_modules/vite/bin/vite.js','build']);
 run('public-build',['scripts/public-pages.mjs']);
 run('source-checkpoint',['tests/operating-search/coverage-audit.mjs','--checkpoint']);
 run('unit-cases',['node_modules/vitest/vitest.mjs','run','--config','vitest.public-site.config.mjs','--coverage','--reporter=default','--reporter=json','--outputFile.json=coverage/operating-browser/unit-results.json'],{allowPartialCoverage:true});
 run('instrumented-source-build',['tests/operating-search/coverage-build.mjs']);
 run('actual-browser-cases',['tests/operating-search/coverage-browser.mjs']);
 run('native-cases',['--experimental-test-isolation=none','--test-reporter=spec','--import','./tests/operating-search/coverage-node-hook.mjs','--test','tests/routes.test.mjs','tests/operating-search/metadata.test.mjs','tests/operating-search/coverage-join.test.mjs']);
 run('native-public-generation',['--import','./tests/operating-search/coverage-node-hook.mjs','tests/operating-search/coverage-public-build.mjs'],{env:{SARSA_NATIVE_COVERAGE:'coverage/operating-browser/public-build-coverage.json'}});
 run('complete-source-audit',['tests/operating-search/coverage-audit.mjs']);
 const unit=JSON.parse(readFileSync(resolve(output,'unit-results.json'))),audit=JSON.parse(readFileSync(resolve(output,'coverage-audit.json'))),browser=JSON.parse(readFileSync(resolve(output,'browser-observations.json')));
 const result={passed:true,phases,unitCases:unit.numPassedTests,browserObservations:browser.length,serverPublicDocuments:24,sourceOwners:audit.inventory,threshold:90,excluded:[],totals:audit.totals,scope:'Disconnected local app only; supported package full qualification and official hosted/provider acceptance are separate.'};
 writeFileSync(resolve(output,'gate-summary.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){writeFileSync(resolve(output,'gate-blocked.json'),JSON.stringify({passed:false,phases,error:String(error)},null,2)+'\n');throw error;}
