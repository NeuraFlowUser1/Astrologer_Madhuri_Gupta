// Use GitHub's own expression evaluator, including its null/boolean coercion.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
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

// Exercise the official renderer's real output with GitHub's expression engine.
const packageRoot=fileURLToPath(new URL('..',import.meta.url));
const renderer='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from tools.automation.production import render_workflow;name=sys.argv[2];print(render_workflow(name,(Path(sys.argv[1])/"deploy/workflows"/name).read_bytes(),"prod").decode(),end="")';
const prodGuards=sources.flatMap(name=>{
 const source=execFileSync(process.env.ABS_PYTHON||'python3',['-c',renderer,packageRoot,name],{encoding:'utf8'});
 if(name==='appointment-backup-validation.yml')assert(source.includes('branches: [prod]'));
 return [...source.matchAll(/^    if: (.+)$/gm)].map((match,index)=>({name:name+':'+index,expression:match[1],source}));
});
test('rendered prod workflows keep four independent guards and standard runner boundaries',()=>{
 assert.equal(prodGuards.length,4);
 for(const guard of prodGuards){
  assert(!guard.source.includes('refs/heads/main'));
  assert(guard.source.includes('persist-credentials: false'));
  assert(!guard.source.includes('secrets: inherit')&&!guard.source.includes('pull_request_target'));
 }
});
for(const guard of prodGuards){
 test('prod '+guard.name+' accepts its owned branch and refuses main, dev, tags, PRs and foreign authority',()=>{
  const own=fixture();own.github.ref='refs/heads/prod';assert(evaluate(guard,own));
  const scheduled=structuredClone(own);
  scheduled.github.event_name=guard.name.startsWith(sources[1])?'workflow_run':'schedule';
  if(guard.name.startsWith(sources[2]))scheduled.github.event.schedule='8,23,38,53 * * * *';
  assert(evaluate(guard,scheduled));
  for(const ref of ['refs/heads/main','refs/heads/dev','refs/tags/prod','refs/pull/1/merge']){
   const other=structuredClone(own);other.github.ref=ref;assert(!evaluate(guard,other));
  }
  for(const field of ['private','fork'])for(const value of [true,null,0,'false',undefined]){
   const other=structuredClone(own);other.github.event.repository[field]=value;assert(!evaluate(guard,other));
  }
  for(const change of [{repository:'Foreign/Repo'},{event_name:'pull_request'},{event_name:'push'}]){
   const other=structuredClone(own);Object.assign(other.github,change);assert(!evaluate(guard,other));
  }
 });
}
