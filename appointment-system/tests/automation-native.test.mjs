// Use GitHub's own expression evaluator, including its null/boolean coercion.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Lexer,Parser,Evaluator,data} from '../tools/checks/node_modules/@actions/expressions/dist/index.js';
function value(input){
 if(input===null||input===undefined)return new data.Null();
 if(typeof input==='string')return new data.StringData(input);
 if(typeof input==='boolean')return new data.BooleanData(input);
 if(typeof input==='number')return new data.NumberData(input);
 if(typeof input==='object'&&!Array.isArray(input))return new data.Dictionary(...Object.entries(input).map(([key,item])=>({key,value:value(item)})));
 throw new Error('Undeclared fixture type');
}
const sources=['appointment-database-backup.yml','appointment-backup-validation.yml','appointment-background-monitor.yml'];
const guards=sources.flatMap(name=>{
 const source=readFileSync(new URL('../deploy/workflows/'+name,import.meta.url),'utf8');
 return [...source.matchAll(/^    if: (.+)$/gm)].map((match,index)=>({name:name+':'+index,expression:match[1],source}));
});
function fixture(){return {
 github:{repository:'ExampleOwner/ExamplePractice',ref:'refs/heads/main',event_name:'workflow_dispatch',
  event:{repository:{visibility:'public',private:false,fork:false},schedule:'37 1 * * *',workflow_run:{conclusion:'success'}}},
 vars:{BOOKING_REPOSITORY:'ExampleOwner/ExamplePractice',BOOKING_BACKUP_CRON:'37 1 * * *'},needs:{verify:{result:'success'}}};}
function evaluate(guard,context){
 const tree=new Parser(new Lexer(guard.expression).lex().tokens,['github','vars','needs'],[]).parse();
 return new Evaluator(tree,value(context)).evaluate().coerceString()==='true';
}
test('every job has an independent pre-allocation guard and standard bounded runner',()=>{
 assert.equal(guards.length,4);
 for(const name of sources){
  const source=readFileSync(new URL('../deploy/workflows/'+name,import.meta.url),'utf8');
  assert.equal([...source.matchAll(/^    runs-on: ubuntu-24\.04$/gm)].length,[...source.matchAll(/^    if: /gm)].length);
  assert(!source.includes('upload-artifact')&&!source.includes('secrets: inherit')&&!source.includes('pull_request_target'));
  assert(source.includes('persist-credentials: false'));
 }
});
for(const guard of guards){
 test(guard.name+' accepts only the configured owned public main run',()=>{
  assert(evaluate(guard,fixture()));
  const scheduled=fixture();const monitor=guard.name.startsWith(sources[2]);
  scheduled.github.event_name=guard.name.startsWith(sources[1])?'workflow_run':'schedule';
  if(monitor)scheduled.github.event.schedule='8,23,38,53 * * * *';
  assert(evaluate(guard,scheduled));
  if(scheduled.github.event_name==='schedule'){
   scheduled.github.event.schedule='2 3 * * *';assert(!evaluate(guard,scheduled));
  }else if(guard.name.endsWith(':0')){
   scheduled.github.event.workflow_run.conclusion='failure';assert(!evaluate(guard,scheduled));
  }
 });
 test(guard.name+' refuses forks, private, absent and loosely false metadata before allocation',()=>{
  for(const field of ['private','fork'])for(const input of [true,null,0,'false','',undefined]){
   const context=fixture();if(input===undefined)delete context.github.event.repository[field];else context.github.event.repository[field]=input;
   assert.equal(evaluate(guard,context),false,field+':'+String(input));
  }
  for(const visibility of ['private','internal','',null,undefined]){
   const context=fixture();context.github.event.repository.visibility=visibility;assert(!evaluate(guard,context));
  }
  for(const change of [{repository:'ForkOwner/Practice'},{ref:'refs/heads/feature'},{ref:'refs/pull/1/merge'},{event_name:'push'}]){
   const context=fixture();Object.assign(context.github,change);assert(!evaluate(guard,context));
  }
  const context=fixture();context.vars.BOOKING_REPOSITORY='';assert(!evaluate(guard,context));
 });
}
test('dependent retention cannot allocate after failed, skipped or cancelled validation',()=>{
 for(const status of ['failure','skipped','cancelled',null]){
  const context=fixture();context.needs.verify.result=status;assert(!evaluate(guards[2],context));
 }
});
