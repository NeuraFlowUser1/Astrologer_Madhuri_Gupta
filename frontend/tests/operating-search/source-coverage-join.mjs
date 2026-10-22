/** Join original-source counters across native/browser/Vitest remapping.
 * Never add an unmatched hit. All primary counters and uncovered code remain.
 * Source-map tools disagree about expression end columns; exact unique starts,
 * region kind, end line and ordered branch starts establish the same owner.
 */
import assert from 'node:assert/strict';
const point=p=>String(p?.line)+':'+String(p?.column);
const region=(a,b)=>a?.start?.line===b?.start?.line&&a?.start?.column===b?.start?.column&&a?.end?.line===b?.end?.line;
const key=(kind,m)=>kind==='branch'?JSON.stringify([m.type,point(m.loc?.start),m.locations.map(l=>point(l.start))]):point((kind==='fn'?m.loc:m).start);
function index(map,kind){const result=new Map();for(const[id,m]of Object.entries(map)){const k=key(kind,m);result.set(k,[...(result.get(k)||[]),id]);}return result;}
function valid(value){assert(value&&typeof value==='object');for(const [counter,field] of [['s','statementMap'],['f','fnMap'],['b','branchMap']]){assert.deepEqual(Object.keys(value[counter]).sort(),Object.keys(value[field]).sort(),'Counter ownership differs');for(const [id,entry] of Object.entries(value[counter])){if(counter==='b')assert.equal(entry.length,value[field][id].locations.length,'Branch alternatives differ');for(const n of [entry].flat())assert(Number.isSafeInteger(n)&&n>=0,'Invalid measured counter');}}}
export function joinSourceCounters(primary,supplement){
 valid(primary);valid(supplement);assert.equal(primary.path,supplement.path,'Another source owner cannot contribute counters');
 const result=structuredClone(primary),receipt={matched:0,unmatched:0,regions:[]};
 for(const [kind,field,counter]of[['statement','statementMap','s'],['fn','fnMap','f'],['branch','branchMap','b']]){
  const targets=index(result[field],kind),sources=index(supplement[field],kind);
  for(const[id,m]of Object.entries(supplement[field])){
   const k=key(kind,m),ids=targets.get(k)||[];
   if(ids.length!==1||sources.get(k).length!==1){receipt.unmatched++;continue;}
   const target=ids[0],t=result[field][target];
   const agrees=kind==='branch'?region(t.loc,m.loc)&&t.locations.length===m.locations.length&&t.locations.every((loc,i)=>region(loc,m.locations[i])):region(kind==='fn'?t.loc:t,kind==='fn'?m.loc:m);
   if(!agrees){receipt.unmatched++;continue;}
   if(kind==='branch')result[counter][target]=result[counter][target].map((n,i)=>n+supplement[counter][id][i]);else result[counter][target]+=supplement[counter][id];
   receipt.matched++;receipt.regions.push({kind,primary:target,supplement:id,start:(kind==='statement'?t:t.loc).start});
  }
 }
 return {coverage:result,receipt};
}
