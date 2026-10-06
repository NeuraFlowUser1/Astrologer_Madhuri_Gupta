import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../engine/appointment_system/studio_assets/staff-actions.js',import.meta.url),'utf8');
const installation='1bbbc890-7c26-4ba6-b3ef-7c9b363c5bc2',one='ff519845-ab34-481a-8b3d-81b96e7e052e',two='cb122b99-90c2-42ec-b165-f77e6d0caa22';
const config={version:1,installation_id:installation,environment:'production',legacy:{client:['old:client'],company:[],calendar:[],inbox:[],enquiry:[]}};
const key=(purpose='client',env='production')=>`appointment-system:${installation}:${env}:staff:${purpose}:v1`;
function storage(){const map=new Map();return {map,getItem:name=>map.get(name)??null,setItem:(name,value)=>map.set(name,value),removeItem:name=>map.delete(name)};}
function locks(){const pending=new Map();return {request(name,options,fn){const promise=(pending.get(name)||Promise.resolve()).then(fn);pending.set(name,promise.catch(()=>{}));return promise;}};}
function load({store=storage(),config:settings=config,lock=locks()}={}){const window={};vm.runInNewContext(source.replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify(settings)),{window,localStorage:store,navigator:{locks:lock},Date,Map,JSON,Number,Error,Promise});return {journal:window.PracticeStaffActions,store};}
const clean=value=>JSON.parse(JSON.stringify(value));
test('legacy opaque IDs merge once into own installation and survive a fresh process',async()=>{
 const store=storage();store.map.set('old:client',JSON.stringify([{operation_id:one,created_at:10}]));const {journal}=load({store});
 assert.deepEqual(clean(journal('client').get()),[{operation_id:one,created_at:10}]);assert.equal(store.map.has('old:client'),true);
 await journal('client').remember(two);assert.equal(store.map.has('old:client'),false);assert.equal(load({store}).journal('client').get().length,2);
 await journal('client').forget(one);assert.equal(load({store}).journal('client').get()[0].operation_id,two);
 assert.deepEqual([...store.map.keys()],[key()]);assert.equal(journal('client'),journal('client'));
});
test('purposes, environment and a different installation never share new saved actions',async()=>{
 const store=storage(),a=load({store});await a.journal('client').remember(one);await a.journal('company').remember(two);
 assert.equal(a.journal('client').get()[0].operation_id,one);assert.equal(a.journal('company').get()[0].operation_id,two);
 for(const patch of [{environment:'test'},{installation_id:'519fe7a1-4487-452f-a770-5ee6b6b611e7'}])assert.equal(load({store,config:{...config,...patch}}).journal('client').get().length,0);
 assert.throws(()=>a.journal('public'));assert.throws(()=>load({config:{...config,environment:'unknown'}}));
});
test('blocked, corrupt and silently discarded storage refuses mutation without deleting evidence',async()=>{
 for(const mode of ['denied','corrupt','discarded','no-lock','extra-field','invalid-date']){
  const store=storage(),raw= mode==='extra-field'?JSON.stringify([{operation_id:one,created_at:1,email:'private@example.test'}]):mode==='invalid-date'?JSON.stringify([{operation_id:one,created_at:-1}]):'{broken';
  if(['corrupt','extra-field','invalid-date'].includes(mode))store.map.set(key(),raw);
  if(mode==='denied')store.getItem=()=>{throw Error('denied');};if(mode==='discarded')store.setItem=()=>{};
  const {journal}=load({store,lock:mode==='no-lock'?null:locks()});const saved=journal('client');saved.get();await assert.rejects(saved.remember(one),/could not safely save/);
  if(['corrupt','extra-field','invalid-date'].includes(mode))assert.equal(store.map.get(key()),raw);
  assert.ok(saved.error);assert.deepEqual(clean(saved.get()),[]);
 }
});
test('two tabs serialize merge and deletion without losing the other pending operation',async()=>{
 const store=storage(),lock=locks(),a=load({store,lock}).journal('client'),b=load({store,lock}).journal('client');
 await Promise.all([a.remember(one),b.remember(two)]);assert.equal(a.get().length,2);
 await Promise.all([a.forget(one),b.remember(two)]);assert.deepEqual(clean(b.get()).map(row=>row.operation_id),[two]);
});
test('legacy inconsistencies, overflow and invalid operation IDs remain preserved',async()=>{
 const store=storage();store.map.set(key(),JSON.stringify([{operation_id:one,created_at:20}]));store.map.set('old:client',JSON.stringify([{operation_id:one,created_at:30}]));
 const j=load({store}).journal('client');assert.equal(j.get()[0].created_at,30);await j.remember(one);assert.equal(j.get().length,1);
 await assert.rejects(j.remember('email@example.test'));await assert.rejects(j.forget('invalid'));
 store.map.set(key(),JSON.stringify(Array.from({length:32},(_,i)=>({operation_id:`${i.toString(16).padStart(8,'0')}-ab34-481a-8b3d-81b96e7e052e`,created_at:i}))));
 const before=store.map.get(key());await assert.rejects(j.remember(two));assert.equal(store.map.get(key()),before);
});
test('a changed legacy value is not erased; a failed removal is recoverable on next read',async()=>{
 const store=storage();store.map.set('old:client',JSON.stringify([{operation_id:one,created_at:1}]));
 const original=store.setItem;store.setItem=(name,value)=>{original(name,value);store.map.set('old:client',JSON.stringify([{operation_id:two,created_at:2}]));};
 const j=load({store}).journal('client');await j.remember(one);assert.equal(store.map.has('old:client'),true);assert.equal(j.get().length,2);
 store.setItem=original;store.removeItem=()=>{throw Error('blocked');};await assert.rejects(j.remember(two));assert.equal(j.get().length,2);
 store.removeItem=name=>store.map.delete(name);await j.remember(two);assert.equal(j.error,null);assert.equal(j.get().length,2);
});
test('result checks preserve unknown, mismatched and recent missing outcomes; verified results retire once',async()=>{
 const store=storage(),j=load({store}).journal('client');await j.remember(one);
 for(const result of [{operation_id:two,code:'closed'},{operation_id:one,code:'wrong'},{operation_id:one,code:'operation_not_found'}]){
  await assert.rejects(j.check(async()=>result,['closed']));assert.equal(j.get().length,1);
 }
 assert.equal(await j.check(async()=>{throw Error('must not call');},['closed'],()=>false),null);
 let current=true;assert.equal(await j.check(async()=>{current=false;return{operation_id:one,code:'closed'};},['closed'],()=>current),null);assert.equal(j.get().length,1);
 assert.equal((await j.check(async()=>({operation_id:one,code:'closed'}),['closed'])).length,1);assert.equal(j.get().length,0);
 store.map.set(key(),JSON.stringify([{operation_id:two,created_at:Date.now()-300001}]));
 await j.check(async()=>({operation_id:two,code:'operation_not_found'}),['closed']);assert.equal(j.get().length,0);
});
