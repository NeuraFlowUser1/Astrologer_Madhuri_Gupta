import assert from 'node:assert/strict';
import test from 'node:test';
import {createPaymentRecovery} from '../../appointment-system/browser/booking/payment-recovery.mjs';
import {installation_id,receipt} from '../../appointment-system/tests/booking-browser-fixture.mjs';
const request='00000000-0000-4000-8000-000000000001';
const credential={request_id:request,secret:'private receipt secret'};
const signed=(n=1)=>({razorpay_order_id:'order_original',razorpay_payment_id:'pay_'+n,razorpay_signature:'a'.repeat(64)});
// Test-only storage/API adapters retain all original six payment scenarios.
function fixture(overrides={}) {
 const map=new Map();let now=100000,current=credential;const calls=[];
 const storageKey=`appointment:${installation_id}:test:signed-payment:v2`;
 const store={getItem:k=>map.get(k===storageKey?'callbacks':k)??null,
  setItem:(k,v)=>map.set(k===storageKey?'callbacks':k,v),removeItem:k=>map.delete(k===storageKey?'callbacks':k)};
 const make=(submit=async(c,r)=>{calls.push({c,r});return {confirmed:true};})=>createPaymentRecovery({
  installation_id,environment:'test',storage:overrides.storage||(()=>store),receipts:{readReceipt:()=>current},clock:()=>now,enabled:()=>true,
  api:async(path,{credential:owner,body})=>{
   assert.equal(path,'/api/checkout/verify-payment');
   await (overrides.submit||submit)(owner,{request_id:body.request_id,order_id:body.razorpay_order_id,payment_id:body.razorpay_payment_id,signature:body.razorpay_signature});
   return {receipt:receipt(owner.request_id)};
  }});
 return {map,make,calls,setCredential:c=>{current=c;},advance:()=>{now+=60001;}};
}
test('lost reply preserves original evidence and retries once after a page reload',async()=>{
  const f=fixture();let attempts=0;
  const first=f.make(async()=>{attempts++;throw Error('reply lost');});
  await assert.rejects(first.rememberAndSubmit(credential,signed(),'order_original'));
  assert.equal(attempts,1);assert(!f.map.get('callbacks').includes(credential.secret));
  const next=f.make();await next.recover();assert.equal(f.calls.length,1);
  assert.equal(f.calls[0].r.order_id,'order_original');assert.equal(f.map.size,0);
});
test('switching receipt never submits another person’s callback and never creates checkout',async()=>{
  const f=fixture();const recovery=f.make();recovery.save(credential,signed(),'order_original');
  f.setCredential({...credential,request_id:'00000000-0000-4000-8000-000000000002'});
  await recovery.recover();assert.equal(f.calls.length,0);assert.equal(f.map.size,1);
  f.setCredential(credential);await recovery.recover();assert.equal(f.calls.length,1);
});
test('more than four unresolved callbacks remain available and one failed send stops the pass',async()=>{
  const f=fixture();const recovery=f.make(async()=>{throw Error('unavailable');});
  for(let n=1;n<=8;n++)recovery.save(credential,signed(n),'order_original');
  assert.equal(JSON.parse(f.map.get('callbacks')).length,8);
  await assert.rejects(recovery.recover());assert.equal(JSON.parse(f.map.get('callbacks')).length,8);
});
test('changed signature/order and malformed or cross-project rows cannot be adopted',async()=>{
  const f=fixture();const recovery=f.make();recovery.save(credential,signed(),'order_original');
  assert.throws(()=>recovery.save(credential,{...signed(),razorpay_signature:'b'.repeat(64)},'order_original'));
  assert.throws(()=>recovery.save(credential,signed(),'order_other'));
  const rows=JSON.parse(f.map.get('callbacks'));f.map.set('callbacks',JSON.stringify(rows.map(r=>({...r,project:'003'}))));
  await f.make().recover();assert.equal(f.calls.length,0);
});
test('blocked browser storage still submits the exact callback without a second payment',async()=>{
  let seen;const f=fixture({storage:()=>{throw Error('storage denied');},submit:async(c,row)=>{seen={c,row};}});
  await f.make().rememberAndSubmit(credential,signed(),'order_original');
  assert.equal(seen.row.payment_id,'pay_1');assert.equal(seen.c.secret,credential.secret);
});
test('parallel recovery is single-flight and stale focus events do not trigger another submission',async()=>{
  const f=fixture();let release;let calls=0;
  const recovery=f.make(async()=>{calls++;await new Promise(r=>{release=r;});});
  recovery.save(credential,signed(),'order_original');const first=recovery.recover();const second=recovery.recover();
  assert.equal(first,second);assert.equal(calls,1);release();await first;
  await recovery.recover();assert.equal(calls,1);assert.equal(f.map.size,0);
});
