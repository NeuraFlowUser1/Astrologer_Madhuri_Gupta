import test from 'node:test';
import assert from 'node:assert/strict';
import {joinSourceCounters} from './source-coverage-join.mjs';
const loc=(column=0,end=10)=>({start:{line:1,column},end:{line:1,column:end}});
const sample=()=>({path:'/source.mjs',statementMap:{0:loc()},fnMap:{0:{name:'owner',loc:loc()}},branchMap:{0:{type:'if',loc:loc(),locations:[loc(),{start:{},end:{}}]}},s:{0:0},f:{0:0},b:{0:[0,0]}});
test('same source regions join measured counters without changing the denominator or inputs',()=>{
 const a=sample(),b=sample();b.s[0]=2;b.f[0]=3;b.b[0]=[4,0];b.statementMap[0].end.column=12;
 const result=joinSourceCounters(a,b);assert.equal(result.coverage.s[0],2);assert.equal(result.coverage.f[0],3);assert.deepEqual(result.coverage.b[0],[4,0]);assert.deepEqual(result.coverage.statementMap,a.statementMap);assert.equal(a.s[0],0);assert.equal(result.receipt.matched,3);
});
test('ambiguous or different source starts remain uncovered',()=>{
 const a=sample(),b=sample();a.statementMap[1]=loc();a.s[1]=0;b.s[0]=1;b.fnMap[0].loc=loc(2);b.f[0]=1;
 const result=joinSourceCounters(a,b);assert.equal(result.coverage.s[0],0);assert.equal(result.coverage.s[1],0);assert.equal(result.coverage.f[0],0);assert.equal(result.receipt.unmatched,2);
});
test('different branch type or ordered alternatives cannot supply a hit',()=>{
 for(const alter of [b=>b.branchMap[0].type='cond-expr',b=>b.branchMap[0].locations.reverse()]){const a=sample(),b=sample();b.b[0]=[1,1];alter(b);assert.deepEqual(joinSourceCounters(a,b).coverage.b[0],[0,0]);}
});
test('another file or invented invalid counter refuses before merge',()=>{
 const a=sample(),b=sample();b.path='/other.mjs';assert.throws(()=>joinSourceCounters(a,b),/source owner/);b.path=a.path;b.s[0]=-1;assert.throws(()=>joinSourceCounters(a,b),/measured counter/);b.s[0]=Infinity;assert.throws(()=>joinSourceCounters(a,b),/measured counter/);b.s[0]=1;b.b[0]=[1];assert.throws(()=>joinSourceCounters(a,b),/alternatives differ/);
});
