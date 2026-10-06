import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../engine/appointment_system/company_assets/command-journal.js',import.meta.url),'utf8');
const scope={installation_id:'1bbbc890-7c26-4ba6-b3ef-7c9b363c5bc2',environment:'test'};
const operation='ff519845-ab34-481a-8b3d-81b96e7e052e',generation='cb122b99-90c2-42ec-b165-f77e6d0caa22';
const command={operation_id:operation,generation,revision:'1',enabled:false,reason:'Company configuration'};
function storage(){const values=new Map();return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};}
function load(store=storage(),config=scope){const window={};vm.runInNewContext(source.replace('/*COMPANY_BROWSER_CONFIGURATION*/null',JSON.stringify(config)),{window,sessionStorage:store});return {journal:window.PracticeCompanyCommands,store};}
const plain=value=>JSON.parse(JSON.stringify(value));
const key=(purpose='mode',environment='test')=>`appointment-system:${scope.installation_id}:${environment}:company:${purpose}:v1`;
test('accepted command is independent of caller mutation and survives a page reload with the same identity',()=>{
 const {journal,store}=load();const input=structuredClone(command);journal.save('mode',input);input.enabled=true;
 assert.deepEqual(plain(load(store).journal.read('mode')),command);
 const result=journal.read('mode');result.operation_id=generation;
 assert.equal(journal.read('mode').operation_id,operation);
 journal.save('mode',null);assert.equal(load(store).journal.read('mode'),null);
});
test('project, environment and command purpose have separate storage',()=>{
 const {journal,store}=load();journal.save('mode',command);
 assert.equal(journal.read('business'),null);assert.equal(load(store,{...scope,environment:'production'}).journal.read('mode'),null);
 assert.equal(load(store,{...scope,installation_id:generation}).journal.read('mode'),null);
 const settings={operation_id:operation,revision:'1',settings:{services:[]},reason:'Change opening hours'};
 journal.save('business',settings);assert.deepEqual(plain(load(store).journal.read('business')),settings);
 assert.deepEqual([...store.values.keys()],[key(),key('business')]);
});
test('storage denial, discarded writes and failed removals never fall back to memory',()=>{
 for(const method of ['getItem','setItem']){
  const store=storage();store[method]=()=>{throw new Error('denied');};const {journal}=load(store);
  assert.throws(()=>journal.save('mode',command),/company_command_storage_unavailable/);
 }
 const store=storage();store.setItem=()=>{};assert.throws(()=>load(store).journal.save('mode',command),/storage_unavailable/);
 const normal=load();normal.journal.save('mode',command);normal.store.removeItem=()=>{};
 assert.throws(()=>normal.journal.save('mode',null),/storage_unavailable/);
 assert.equal(normal.journal.read('mode').operation_id,operation);
});
test('corrupt, oversized, foreign or wrongly typed saved records are not silently discarded',()=>{
 const {journal,store}=load();journal.save('mode',command);const original=store.values.get(key());const saved=JSON.parse(original);
 for(const raw of ['{','x'.repeat(65537),'null','[]',JSON.stringify({...saved,version:2}),
  JSON.stringify({...saved,installation_id:generation}),JSON.stringify({...saved,environment:'production'}),
  JSON.stringify({...saved,purpose:'business'}),JSON.stringify({...saved,extra:1}),
  JSON.stringify({...saved,command:{...command,enabled:'false'}})]){
  store.values.set(key(),raw);assert.throws(()=>journal.read('mode'),/storage_unavailable/);assert.equal(store.values.get(key()),raw);
 }
});
test('only declared command contracts may be saved',()=>{
 const {journal}=load();
 for(const value of [{},[],{...command,operation_id:'bad'},{...command,generation:'bad'},
  {...command,revision:1},{...command,revision:'0'},{...command,reason:'x'},{...command,reason:'x'.repeat(301)},
  {...command,extra:true},{...command,enabled:1}]){
  assert.throws(()=>journal.save('mode',value),/storage_unavailable/);
 }
 assert.throws(()=>journal.save('business',{operation_id:operation,revision:'1',settings:[],reason:'Change settings'}),/storage_unavailable/);
 assert.throws(()=>journal.save('business',{operation_id:operation,revision:'1',settings:{large:'x'.repeat(65536)},reason:'Change settings'}),/storage_unavailable/);
 for(const bad of [null,{}, {...scope,installation_id:'00000000-0000-0000-0000-000000000000'}, {...scope,environment:'other'}])
  assert.throws(()=>load(storage(),bad).journal.read('mode'),/storage_unavailable/);
 assert.throws(()=>journal.read('other'),/storage_unavailable/);
});
