import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createTransport,RequestError} from '../browser/transport.mjs';
import {createReceiptStore} from '../browser/booking/credentials.mjs';

const allowed=p=>p==='/api/checkout';
const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json',...headers}});
const code=expected=>error=>error instanceof RequestError && error.code===expected;
const installation_id='991c0e85-4f14-4b18-850b-acab0d4d6da4';
const request_id='b2ca6d62-5e1e-4e18-ae5e-9a7447acb3bb';
const policy={receipt_access:{version:1,key_id:'receipt-2026'}};
const storage=()=>{const values=new Map();return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};
const store=()=>createReceiptStore({installation_id,environment:'test',legacy_receipts:[{key:'old-one',format:'id-hex64'},{key:'old-two',format:'request-url43'}]});

test('transport limits destinations and does not leak submitted fields in failures',async()=>{
 let calls=0;const request=createTransport({allowed,fetcher:async(path,options)=>{
  calls++;assert.equal(path,'/api/checkout');assert.equal(options.redirect,'error');assert.equal(options.credentials,'same-origin');
  assert.equal(options.cache,'no-store');assert.equal(options.method,'POST');assert.equal(options.body,'{"private":"not in errors"}');
  return json({code:'time_unavailable',private:'not in errors'},409,{'Retry-After':'9000'});
 }});
 for(const path of ['https://other.example/api/checkout','//other.example/api/checkout','/api/other','/api/checkout#x'])
  await assert.rejects(request(path),code('invalid_request'));
 await assert.rejects(request('/api/checkout',{body:{private:'not in errors'}}),error=>{
  assert.equal(error.message,'time_unavailable');assert.equal(error.status,409);assert.equal(error.retryAfter,3600);
  assert.equal(JSON.stringify(error).includes('not in errors'),false);return true;
 });assert.equal(calls,1);
});

test('transport bounds stalled fetches, stalled bodies, body size, encoding and response shape',async()=>{
 for(const fetcher of [()=>new Promise(()=>{}),async()=>new Response(new ReadableStream({start(){}}),{headers:{'Content-Type':'application/json'}})]){
  const request=createTransport({allowed,timeout:15,fetcher});
  await assert.rejects(request('/api/checkout'),code('temporarily_unavailable'));
 }
 await assert.rejects(createTransport({allowed,maximum:8,fetcher:async()=>json({large:'text'})})('/api/checkout'),code('invalid_response'));
 for(const response of [json([]),json(null),new Response('<html>'),new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}})])
  await assert.rejects(createTransport({allowed,fetcher:async()=>response})('/api/checkout'),RequestError);
 const result=await createTransport({allowed,fetcher:async()=>json({ready:true})})('/api/checkout');assert.deepEqual(result,{ready:true});
});

test('abort wins even if a provider ignores it, and an already aborted call never starts',async()=>{
 const controller=new AbortController();let calls=0;
 const request=createTransport({allowed,timeout:1000,fetcher:()=>{calls++;return new Promise(()=>{});}});
 const pending=request('/api/checkout',{signal:controller.signal});controller.abort();
 await assert.rejects(pending,code('request_cancelled'));assert.equal(calls,1);
 await assert.rejects(request('/api/checkout',{signal:controller.signal}),code('request_cancelled'));assert.equal(calls,1);
});

test('receipt credentials are installation bound and save only opaque access, never customer fields',()=>{
 const s=storage(),r=store(),saved=r.prepareReceipt(s,policy);
 assert.match(saved.secret,/^r1\.receipt-2026\.[A-Za-z0-9_-]{43}$/);
 assert.deepEqual(Object.keys(saved).sort(),['request_id','secret','version']);assert.deepEqual(r.readReceipt(s),saved);
 assert.equal(s.values.size,1);assert.throws(()=>r.prepareReceipt(s,policy),code('checkout_in_progress'));
 assert.throws(()=>r.clearReceipt(s,{...saved,secret:'wrong'}),code('receipt_conflict'));assert.deepEqual(r.readReceipt(s),saved);
 const other=createReceiptStore({installation_id:'a0377b64-600f-49d5-bdfb-8b9661e639b8',environment:'test'});
 assert.equal(other.readReceipt(s),null);
 s.setItem(other.storageKey,s.getItem(r.storageKey));assert.throws(()=>other.readReceipt(s),code('receipt_unavailable'));
 s.removeItem(other.storageKey);r.clearReceipt(s,saved);assert.equal(r.readReceipt(s),null);
});

test('legacy receipts retain exact secrets, refuse conflicting saved bookings and do not silently clear corruption',()=>{
 const s=storage(),r=store(),secret='a'.repeat(64);s.setItem('old-one',JSON.stringify({id:request_id,secret}));
 assert.deepEqual(r.readReceipt(s),{version:1,request_id,secret});
 s.setItem('old-two',JSON.stringify({version:1,request_id,secret:'b'.repeat(43)}));
 assert.throws(()=>r.readReceipt(s),code('receipt_conflict'));assert.throws(()=>r.clearReceipt(s,{request_id,secret}),code('receipt_conflict'));
 s.removeItem('old-two');r.clearReceipt(s,{request_id,secret});assert.equal(r.readReceipt(s),null);
 s.setItem('old-one','broken');assert.throws(()=>r.prepareReceipt(s,policy),code('receipt_unavailable'));assert.equal(s.getItem('old-one'),'broken');
});

test('storage failures stop checkout before money can move; malformed configuration cannot change storage scope',()=>{
 const r=store();assert.throws(()=>r.readReceipt({getItem(){throw Error('private');}}),code('storage_unavailable'));
 const s=storage();s.setItem=()=>{};assert.throws(()=>r.prepareReceipt(s,policy),code('storage_unavailable'));
 assert.throws(()=>r.prepareReceipt(storage(),{receipt_access:{version:1,key_id:'../wrong'}}),code('invalid_response'));
 assert.throws(()=>createReceiptStore({installation_id,environment:'test',legacy_receipts:[{key:'x',format:'unknown'}]}),code('invalid_configuration'));
 assert.throws(()=>createTransport({allowed,timeout:Infinity}),TypeError);
});

test('receipt readers reject malformed and mixed historical formats without deleting saved data',()=>{
 for(const [key,values] of [['old-one',[[],null,{id:request_id,secret:'z'.repeat(64)},{id:'bad',secret:'a'.repeat(64)},{id:request_id,secret:123}]],['old-two',[{version:2,request_id,secret:'a'.repeat(43)},{version:1,request_id,secret:123},{version:1,request_id,secret:'a'.repeat(42)}]]]){
  for(const value of values){const s=storage(),r=store();s.setItem(key,JSON.stringify(value));assert.throws(()=>r.readReceipt(s),code('receipt_unavailable'));assert.equal(s.getItem(key),JSON.stringify(value));}
 }
 for(const options of [{installation_id:null,environment:'test'},{installation_id:'00000000-0000-0000-0000-000000000000',environment:'test'},{installation_id,environment:'unknown'},{installation_id,environment:'test',legacy_receipts:{}},{installation_id,environment:'test',legacy_receipts:Array(5).fill({key:'x',format:'id-hex64'})},{installation_id,environment:'test',legacy_receipts:[{key:'x',format:'id-hex64'},{key:'x',format:'id-hex64'}]}])assert.throws(()=>createReceiptStore(options),code('invalid_configuration'));
});
test('failed receipt removal and recovery commit retain recoverable state instead of claiming success',()=>{
 const s=storage(),r=store(),saved=r.prepareReceipt(s,policy);s.removeItem=()=>{};assert.throws(()=>r.clearReceipt(s,saved),code('storage_unavailable'));assert.deepEqual(r.readReceipt(s),saved);
 s.removeItem=()=>{throw Error('Synthetic storage failure');};assert.throws(()=>r.clearReceipt(s,saved),code('storage_unavailable'));
 const v=storage(),recovery=r.prepareRecovery(v,request_id,policy);v.removeItem=()=>{};assert.throws(()=>r.commitRecovery(v,recovery),code('storage_unavailable'));assert.deepEqual(r.readRecovery(v),recovery);assert.deepEqual(r.readReceipt(v),recovery);
});
test('recovery does not replace a different pending booking or accept a mismatched staged secret',()=>{
 const r=store(),s=storage();assert.throws(()=>r.prepareRecovery(s,'invalid',policy),code('invalid_request'));
 assert.throws(()=>r.commitRecovery(s,null),code('receipt_conflict'));
 const staged=r.prepareRecovery(s,request_id,policy);assert.deepEqual(r.prepareRecovery(s,request_id,policy),staged);assert.throws(()=>r.prepareReceipt(s,policy),code('checkout_in_progress'));
 assert.throws(()=>r.commitRecovery(s,{...staged,secret:'different'}),code('receipt_conflict'));
 s.setItem('old-one',JSON.stringify({id:'11111111-1111-4111-8111-111111111111',secret:'a'.repeat(64)}));assert.throws(()=>r.commitRecovery(s,staged),code('receipt_conflict'));assert.deepEqual(r.readRecovery(s),staged);
});
test('recovery storage write readback and read errors prevent committing unverified credentials',()=>{
 const r=store(),s=storage();s.setItem=()=>{};assert.throws(()=>r.prepareRecovery(s,request_id,policy),code('storage_unavailable'));
 assert.throws(()=>r.readRecovery({getItem(){throw Error('private');}}),code('storage_unavailable'));
 const v=storage(),staged=r.prepareRecovery(v,request_id,policy);v.setItem=()=>{};assert.throws(()=>r.commitRecovery(v,staged),code('storage_unavailable'));assert.deepEqual(r.readRecovery(v),staged);
 const legacy=storage();legacy.setItem('old-two',JSON.stringify({version:1,request_id,secret:'a'.repeat(43)}));const updated=r.prepareRecovery(legacy,request_id,policy);assert.deepEqual(r.commitRecovery(legacy,updated),updated);assert.equal(legacy.getItem('old-two'),null);assert.equal(r.readRecovery(legacy),null);
});
