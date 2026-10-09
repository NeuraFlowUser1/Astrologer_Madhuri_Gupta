/** Merge original-source counters, audit every active file and enforce all four gates. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import coverage from 'istanbul-lib-coverage';
import {createInstrumenter} from 'istanbul-lib-instrument';
import {listFiles} from '../../scripts/check-public-site.mjs';
const root=resolve(import.meta.dirname,'../..'),directory=resolve(process.env.SARSA_EVIDENCE_DIR||resolve(root,'coverage/public-site'));
const map=coverage.createCoverageMap(JSON.parse(readFileSync(resolve(directory,'coverage-final.json'))));map.merge(JSON.parse(readFileSync(resolve(directory,'native-coverage.json'))));
const inventory=[...listFiles(resolve(root,'src')),...listFiles(resolve(root,'scripts'))].filter(file=>/\.(jsx?|mjs|tsx?)$/.test(file)).concat(['proxy.js','vite.config.js'].map(file=>resolve(root,file)));
const reexports=[];
for(const file of inventory){if(map.files().includes(file))continue;const source=readFileSync(file,'utf8');const instrumenter=createInstrumenter({esModules:true});instrumenter.instrumentSync(source,file);const coverage=instrumenter.lastFileCoverage();assert.equal(Object.keys(coverage.statementMap).length,0,'Uninstrumented active file: '+file);reexports.push(file.replace(root+'/',''));map.addFileCoverage(coverage);}
const totals=map.getCoverageSummary().toJSON();for(const key of ['statements','branches','functions','lines'])assert(totals[key].pct>=90,`${key}: ${totals[key].pct}% below 90%`);
const result={inventory:inventory.length,instrumented_files:map.files().length,reexport_only_files:reexports,totals};writeFileSync(resolve(directory,'merged-coverage.json'),JSON.stringify(map.toJSON()));writeFileSync(resolve(directory,'coverage-audit.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
