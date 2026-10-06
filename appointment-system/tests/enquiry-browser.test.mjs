import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createEnquiryStore} from '../browser/enquiry/credentials.mjs';
import {createEnquiryController} from '../browser/enquiry/controller.mjs';
import {createEnquiryAPI,checkedReceipt} from '../browser/enquiry/protocol.mjs';
import {createEnquiryBrowser} from '../browser/enquiry/index.mjs';
import {RequestError} from '../browser/transport.mjs';

const installation_id='991c0e85-4f14-4b18-850b-acab0d4d6da4',environment='test',epoch=Date.parse('2026-10-03T05:00:00Z');
const fields={name:'Synthetic Customer',email:'customer@example.com',phone:'',subject:'General enquiry',message:'Synthetic question.',source:'home'};
const storage=()=>{const values=new Map();return {values,getItem:key=>values.get(key)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const receipt=(id,state='awaiting_verification',generation=1,at=epoch)=>({code:'ok',request_id:id,state,generation,sends_remaining:3-generation,
 verification_delivery:'queued',server_now:new Date(at).toISOString(),code_expires_at:new Date(at+300000).toISOString(),resend_after:new Date(at+60000).toISOString()});
function fixture({saved=storage(),overrides={}}={}){
 const receipts=createEnquiryStore({installation_id,environment,channel:'contact'}),calls=[];let at=epoch,poll;
 const documentObject={hidden:false};
 const api={policy:async()=>({version:1,receipt_key_id:'current'}),send:async(action,access,payload,signal)=>{
  calls.push({action,access:structuredClone(access),payload:structuredClone(payload),signal});
  if(overrides[action])return overrides[action](access,payload,signal);
  return {...receipt(access.request_id,action==='verify'?'received':'awaiting_verification',action==='resend'?2:1,action==='resend'?at:epoch),server_now:new Date(at).toISOString()};
 }};
 const controller=createEnquiryController({api,receipts,storage:()=>saved,clock:()=>at+86400000,monotonic:()=>at,
  interval:fn=>{poll=fn;return 1;},clearInterval:()=>{},documentObject});controller.start();
 return {controller,saved,calls,receipts,overrides,api,documentObject,advance:n=>{at+=n;poll();},poll:()=>poll()};
}

test('purpose and channel storage isolate enquiry references and preserve historical credentials',()=>{
 const s=storage(),policy={version:1,receipt_key_id:'current'},contact=createEnquiryStore({installation_id,environment,channel:'contact'});
 const prashna=createEnquiryStore({installation_id,environment,channel:'prashna'}),c=contact.create(s,policy);
 assert.match(c.secret,/^q1\.current\./);assert.equal(prashna.read(s),null);assert.throws(()=>contact.create(s,policy),/request_in_progress/);
 const r=createEnquiryStore({installation_id,environment,channel:'old',legacy_receipts:[{key:'old:/api/contact',format:'id-hex64'}]});
 s.setItem('old:/api/contact',JSON.stringify({id:c.request_id,secret:'a'.repeat(64)}));let old=r.read(s);
 old=r.save(s,{...old,resend_id:crypto.randomUUID(),resend_generation:1});assert.equal(r.read(s).resend_id,old.resend_id);
 assert.throws(()=>r.clear(s,{...old,secret:'b'.repeat(64)}),/receipt_conflict/);r.clear(s,old);assert.equal(r.read(s),null);
 const q=createEnquiryStore({installation_id,environment,channel:'url',legacy_receipts:[{key:'old:enquiry',format:'request-url43'}]});
 s.setItem('old:enquiry',JSON.stringify({version:1,request_id:c.request_id,secret:'z'.repeat(43),resend_id:crypto.randomUUID(),resend_generation:2}));
 assert.equal(q.read(s).credential_format,'url43');s.setItem('old:enquiry','{');assert.throws(()=>q.read(s),/receipt_unavailable/);
 assert.throws(()=>contact.save(s,{...c,request_id:crypto.randomUUID()}),/receipt_conflict/);
});

test('submits one frozen draft, verifies and confirms, then checks before clearing',async()=>{
 const f=fixture();await f.controller.submit(fields);assert.equal(f.calls.length,1);
 assert.equal(f.controller.getSnapshot().resendWait,60,'uses server time despite a wrong browser clock');
 await f.controller.submit({...fields,message:'Different'});assert.equal(f.calls.length,1);
 await f.controller.verify('123456');assert.equal(f.controller.getSnapshot().receipt.state,'received');
 assert.ok(!JSON.stringify([...f.saved.values]).includes('customer@example.com'));assert.ok(!JSON.stringify([...f.saved.values]).includes('123456'));
 f.overrides.status=async access=>receipt(access.request_id,'received');await f.controller.restart();assert.equal(f.controller.getSnapshot().started,false);
 assert.deepEqual(f.calls.map(c=>c.action),['start','verify','status']);assert.equal(f.saved.values.size,0);f.controller.stop();
});

test('lost start reply retries the identical frozen request, never edits or duplicates it',async()=>{
 const f=fixture({overrides:{start:async()=>{throw new RequestError();}}}),draft={...fields};
 await f.controller.submit(draft);draft.message='Mutated later';assert.equal(f.controller.getSnapshot().retry,'start');
 delete f.overrides.start;await f.controller.retryRequest();assert.deepEqual(f.calls[0].payload,f.calls[1].payload);
 assert.deepEqual(f.calls[0].access,f.calls[1].access);assert.equal(f.calls[1].payload.message,fields.message);f.controller.stop();
});

test('only first definite input rejection releases a new reference; uncertain retry preserves it',async()=>{
 const bad=()=>{throw new RequestError('invalid_request',{status:422});};
 const first=fixture({overrides:{start:bad}});await first.controller.submit(fields);assert.equal(first.controller.getSnapshot().started,false);
 assert.equal(first.saved.values.size,0);first.controller.stop();
 const lost=fixture({overrides:{start:()=>{throw new RequestError();}}});await lost.controller.submit(fields);
 lost.overrides.start=bad;await lost.controller.retryRequest();assert.equal(lost.controller.getSnapshot().started,true);assert.equal(lost.saved.values.size,1);lost.controller.stop();
});

test('reload only checks status; an unconfirmed code is never automatically retried',async()=>{
 const a=fixture();await a.controller.submit(fields);a.controller.stop();
 const b=fixture({saved:a.saved,overrides:{verify:()=>{throw new RequestError();}}});await tick();assert.deepEqual(b.calls.map(c=>c.action),['status']);
 await b.controller.verify('123456');await b.controller.retryRequest();assert.deepEqual(b.calls.map(c=>c.action),['status','verify','status']);
 assert.equal(b.controller.getSnapshot().receipt.state,'awaiting_verification');b.controller.stop();
});

test('resend operation survives reload and repeated lost responses without another generation',async()=>{
 const a=fixture({overrides:{resend:()=>{throw new RequestError();}}});await a.controller.submit(fields);a.advance(60000);await tick();
 await a.controller.resend();const operation=a.calls.find(c=>c.action==='resend').payload.operation_id;a.controller.stop();
 const b=fixture({saved:a.saved});await tick();assert.equal(b.controller.getSnapshot().retry,'resend');
 await b.controller.retryRequest();assert.equal(b.calls.at(-1).payload.operation_id,operation);
 assert.equal(b.controller.getSnapshot().receipt.generation,2);assert.equal(b.receipts.read(b.saved).resend_id,undefined);b.controller.stop();
});

test('late results cannot mutate an unmounted or remounted coordinator',async()=>{
 const pending=deferred(),f=fixture({overrides:{start:()=>pending.promise}}),work=f.controller.submit(fields);await tick();
 const id=f.calls[0].access.request_id;f.controller.stop();f.controller.start();await tick();
 assert.equal(f.controller.getSnapshot().busy,false);pending.resolve(receipt(id,'received'));await work;
 assert.equal(f.controller.getSnapshot().receipt.state,'awaiting_verification');f.controller.stop();
});

test('duplicate clicks, rate limits, expiry and bounded visible polling do not create sends',async()=>{
 const pending=deferred(),f=fixture({overrides:{start:()=>pending.promise}}),a=f.controller.submit(fields);await tick();
 await f.controller.submit(fields);assert.equal(f.calls.length,1);pending.resolve(receipt(f.calls[0].access.request_id));await a;
 f.documentObject.hidden=true;for(let i=0;i<10;i++){f.advance(10000);await tick();}assert.equal(f.calls.length,1);
 f.documentObject.hidden=false;for(let i=0;i<12;i++){f.advance(10000);await tick();}assert.equal(f.calls.filter(c=>c.action==='status').length,6);
 f.overrides.verify=()=>{throw new RequestError('please_wait',{status:429,retryAfter:60});};await f.controller.verify('123456');
 const count=f.calls.length;await f.controller.verify('123456');assert.equal(f.calls.length,count);assert.equal(f.controller.getSnapshot().waiting,60);
 f.advance(400000);await f.controller.verify('123456');assert.equal(f.calls.length,count);f.controller.stop();
});

test('contact transport remains an independent exact route contract and validates receipts',async()=>{
 const access={request_id:crypto.randomUUID(),secret:'q1.current.'+'a'.repeat(43)},calls=[];
 const api=createEnquiryAPI({fetcher:async(path,options)=>{calls.push({path,options});return new Response(JSON.stringify(path.endsWith('policy')?
  {version:1,receipt_key_id:'current'}:{...receipt(access.request_id),accidental_private_field:'discard'}),{headers:{'content-type':'application/json'}});}});
 await api.policy();const result=await api.send('start',access,fields);assert.equal(result.accidental_private_field,undefined);
 assert.equal(calls[1].options.headers['X-Enquiry-Receipt'],access.secret);assert.equal(calls[1].options.credentials,'same-origin');
 await assert.rejects(api.send('checkout',access),/invalid_request/);assert.throws(()=>checkedReceipt({...receipt(access.request_id),generation:4},access.request_id),/invalid_response/);
 const browser=createEnquiryBrowser({version:1,installation_id,environment,channels:{contact:{legacy_receipts:[]}}},{storage});
 assert.throws(()=>browser.controller('not-configured'),/invalid_configuration/);
});

test('enquiry credentials reject corrupt scope, resend identities and old data without erasing it',()=>{
 const profile={installation_id,environment,channel:'contact'},r=createEnquiryStore(profile),s=storage(),saved=r.create(s,{version:1,receipt_key_id:'current'});
 const original=s.getItem(r.storageKey);
 for(const changed of [{version:2},{environment:'production'},{channel:'other'},{credential_format:'unknown'},{resend_id:crypto.randomUUID()},{resend_id:'bad',resend_generation:1},{resend_id:crypto.randomUUID(),resend_generation:3},{extra:'private'}]){
  s.setItem(r.storageKey,JSON.stringify({...JSON.parse(original),...changed}));assert.throws(()=>r.read(s),/receipt_unavailable/);
 }
 for(const value of ['x'.repeat(4097),'[]','null','true']){s.setItem(r.storageKey,value);assert.throws(()=>r.read(s),/receipt_unavailable/);assert.equal(s.getItem(r.storageKey),value);}
 s.setItem(r.storageKey,original);s.removeItem=()=>{};assert.throws(()=>r.clear(s,saved),/storage_unavailable/);
 const absent=storage();assert.throws(()=>r.clear(absent,saved),/receipt_conflict/);absent.setItem=()=>{};assert.throws(()=>r.create(absent,{version:1,receipt_key_id:'current'}),/storage_unavailable/);
 assert.throws(()=>r.read({getItem(){throw Error('private');}}),/storage_unavailable/);
 for(const changed of [{installation_id:null},{installation_id:'00000000-0000-0000-0000-000000000000'},{environment:'other'},{channel:'invalid/channel'},{legacy_receipts:{}},{legacy_receipts:[{key:'a',format:'bad'}]},{legacy_receipts:[{key:'a',format:'id-hex64'},{key:'a',format:'id-hex64'}]}])assert.throws(()=>createEnquiryStore({...profile,...changed}),/invalid_configuration/);
 assert.throws(()=>r.create(storage(),{version:2,receipt_key_id:'current'}),/invalid_response/);
});
test('old enquiry credential shapes and different saved references never silently replace one another',()=>{
 const legacy={key:'old',format:'request-url43'},r=createEnquiryStore({installation_id,environment,channel:'contact',legacy_receipts:[legacy]}),s=storage();
 for(const old of [{version:2,request_id:crypto.randomUUID(),secret:'a'.repeat(43)},{version:1,request_id:'bad',secret:'a'.repeat(43)},{version:1,request_id:crypto.randomUUID(),secret:2}]){s.setItem('old',JSON.stringify(old));assert.throws(()=>r.read(s),/receipt_unavailable/);}
 s.removeItem('old');const saved=r.create(s,{version:1,receipt_key_id:'current'});s.setItem('old',JSON.stringify({version:1,request_id:crypto.randomUUID(),secret:'a'.repeat(43)}));assert.throws(()=>r.read(s),/receipt_conflict/);assert.throws(()=>r.clear(s,saved),/receipt_conflict/);
});
test('enquiry actions without a request or after confirmed receipt cannot send extra mail',async()=>{
 const f=fixture();let observed=0;const unsubscribe=f.controller.subscribe(()=>observed++);f.controller.start();await f.controller.check();await f.controller.verify('123456');await f.controller.resend();await f.controller.retryRequest();await f.controller.restart();assert.equal(f.calls.length,0);
 await f.controller.submit(fields);for(const value of [123456,'12345','invalid'])await f.controller.verify(value);assert.equal(f.calls.filter(c=>c.action==='verify').length,0);
 await f.controller.resend();assert.equal(f.calls.filter(c=>c.action==='resend').length,0);await f.controller.verify('123456');await f.controller.resend();assert.equal(f.calls.filter(c=>c.action==='resend').length,0);
 assert.ok(observed);unsubscribe();const count=observed;await f.controller.check();assert.equal(observed,count);f.controller.stop();
});
test('policy failure and blocked storage never begin a contact request',async()=>{
 const f=fixture();f.api.policy=async()=>{throw new RequestError();};await f.controller.submit(fields);assert.equal(f.calls.length,0);assert.equal(f.saved.values.size,0);assert.ok(f.controller.getSnapshot().error);f.controller.stop();
 const blocked=fixture({saved:{getItem(){throw Error('private');}}});assert.equal(blocked.controller.getSnapshot().blocked,true);await blocked.controller.submit(fields);assert.equal(blocked.calls.length,0);blocked.controller.stop();
});
test('an interrupted policy response cannot save a new enquiry and stale received state cannot clear it',async()=>{
 const pending=deferred(),f=fixture();f.api.policy=()=>pending.promise;const attempt=f.controller.submit(fields);f.controller.stop();pending.resolve({version:1,receipt_key_id:'current'});await attempt;assert.equal(f.saved.values.size,0);
 const g=fixture();await g.controller.submit(fields);await g.controller.verify('123456');g.overrides.status=async access=>receipt(access.request_id,'awaiting_verification');await g.controller.restart();assert.equal(g.controller.getSnapshot().started,true);assert.ok(g.receipts.read(g.saved));g.controller.stop();
});
test('enquiry profile refuses absent channels, unknown settings and malformed installations',()=>{
 const good={version:1,installation_id,environment,channels:{contact:{legacy_receipts:[]}}};
 for(const value of [null,{}, {...good,version:2},{...good,channels:[]},{...good,channels:{}},{...good,channels:{contact:{}}},{...good,channels:{contact:{legacy_receipts:[],extra:true}}}])assert.throws(()=>createEnquiryBrowser(value),/invalid_configuration/);
 const browser=createEnquiryBrowser(good,{storage});const controller=browser.controller();assert.equal(controller.getSnapshot().started,false);controller.stop();
});
