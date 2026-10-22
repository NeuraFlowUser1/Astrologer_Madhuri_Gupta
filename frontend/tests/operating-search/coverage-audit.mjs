/** Full app inventory: unit + actual native/server/browser evidence; no exclusions. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import coverage from 'istanbul-lib-coverage';
import {createInstrumenter} from 'istanbul-lib-instrument';
import {listFiles} from '../../scripts/check-public-site.mjs';
import {joinSourceCounters} from './source-coverage-join.mjs';
const root=resolve(import.meta.dirname,'../..'),directory=resolve(root,'coverage/operating-browser');mkdirSync(directory,{recursive:true});
const inventory=[...listFiles(resolve(root,'src')),...listFiles(resolve(root,'scripts'))].filter(file=>/\.(jsx?|mjs|tsx?)$/.test(file)).concat(['proxy.js','vite.config.js'].map(file=>resolve(root,file)));
const fingerprints=()=>Object.fromEntries(inventory.map(file=>[file,createHash('sha256').update(readFileSync(file)).digest('hex')]));
const read=file=>JSON.parse(readFileSync(resolve(root,file),'utf8'));
if(process.argv.includes('--checkpoint')){writeFileSync(resolve(directory,'unit-sources.json'),JSON.stringify(fingerprints()));console.log(JSON.stringify({checkpoint:'source hashes',owners:inventory.length}));}
else{
 assert.deepEqual(read('coverage/operating-browser/unit-sources.json'),fingerprints(),'Active source changed after the unit qualification checkpoint');
 for(const [file,hash] of Object.entries(read('coverage/operating-browser/source-fingerprints.json')))assert.equal(fingerprints()[file],hash,'Browser/server build source changed: '+file);
 const pool=read('coverage/public-site/coverage-final.json'),joins=[];
 for(const source of ['coverage/public-site/native-coverage.json','coverage/operating-browser/server-coverage.json','coverage/operating-browser/browser-coverage.json','coverage/operating-browser/native-source-coverage.json','coverage/operating-browser/public-build-coverage.json']){
  const supplemental=read(source);const receipt={source,matched:0,unmatched:0,owners:[]};
  for(const [file,value] of Object.entries(supplemental)){
   assert(inventory.includes(file),'A non-product owner cannot inflate coverage: '+file);
   if(!pool[file]){pool[file]=value;receipt.owners.push(file);continue;}
   const joined=joinSourceCounters(pool[file],value);pool[file]=joined.coverage;receipt.matched+=joined.receipt.matched;receipt.unmatched+=joined.receipt.unmatched;receipt.owners.push({file,...joined.receipt});
  }
  joins.push(receipt);
 }
 const instrumenter=createInstrumenter({esModules:true,parserPlugins:['jsx']});
 for(const file of inventory)if(!pool[file]){instrumenter.instrumentSync(readFileSync(file,'utf8'),file);pool[file]=instrumenter.lastFileCoverage();}
 assert.deepEqual(Object.keys(pool).sort(),inventory.sort(),'Every active file must remain in the denominator');
 const map=coverage.createCoverageMap(pool),totals=map.getCoverageSummary().toJSON();
 const result={inventory:inventory.length,files:map.files().length,threshold:90,excluded:[],totals,joins};
 writeFileSync(resolve(directory,'joined-coverage.json'),JSON.stringify(pool));writeFileSync(resolve(directory,'coverage-audit.json'),JSON.stringify(result,null,2)+'\n');
 for(const kind of ['statements','functions','branches','lines'])assert(totals[kind].pct>=90,kind+': '+totals[kind].pct+'% below 90%');
 console.log(JSON.stringify({inventory:result.inventory,files:result.files,threshold:90,excluded:[],totals}));
}
