import test from 'node:test';
import assert from 'node:assert/strict';
import {createPaymentRecovery} from '../appointment-system/browser/booking/payment-recovery.mjs';
import {createReceiptStore} from '../appointment-system/browser/booking/credentials.mjs';
import {installation_id,now,policy,receipt} from '../appointment-system/tests/booking-browser-fixture.mjs';

// Test-only settings and provider callbacks; the real contained production
// receipt store and recovery adapter are used. No network or payment is made.
function fixture(){
 const values=new Map(),calls=[];
 const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 const receipts=createReceiptStore({installation_id,environment:'test'}),credential=receipts.prepareReceipt(storage,policy());
 let time=now,enabled=true;
 let responder=async(_credential)=>({receipt:receipt(_credential.request_id)});
 const recovery=()=>createPaymentRecovery({installation_id,environment:'test',receipts,storage:()=>storage,enabled:()=>enabled,clock:()=>time,
  api:async(path,options)=>{assert.equal(path,'/api/checkout/verify-payment');calls.push({path,...options});return responder(options.credential,options.body);}});
 return {values,calls,storage,receipts,credential,recovery,setResponder:value=>{responder=value;},advance:()=>{time+=60001;},setEnabled:value=>{enabled=value;}};
}
const signed=(n=1)=>({razorpay_order_id:'order_original',razorpay_payment_id:'pay_'+n,razorpay_signature:'a'.repeat(64)});

test('lost payment reply survives reload with the original receipt and no second checkout',async()=>{
 const f=fixture(),first=f.recovery();f.setResponder(async()=>{throw Error('lost reply');});
 await assert.rejects(first.rememberAndSubmit(f.credential,signed(),'order_original'));
 assert.equal(f.calls.length,1);assert.equal(f.values.get(first.storageKey).includes(f.credential.secret),false);
 f.setResponder(async credential=>({receipt:receipt(credential.request_id)}));await f.recovery().recover();
 assert.equal(f.calls.length,2);assert.deepEqual(f.calls[1].credential,f.credential);
 assert.deepEqual(f.calls[1].body,{request_id:f.credential.request_id,...signed()});assert.equal(f.values.has(first.storageKey),false);
});
test('another saved receipt cannot submit the original callback or discard it',async()=>{
 const f=fixture(),r=f.recovery();r.save(f.credential,signed(),'order_original');
 const original=f.values.get(f.receipts.storageKey),foreign={...JSON.parse(original),request_id:'00000000-0000-4000-8000-000000000002'};
 f.values.set(f.receipts.storageKey,JSON.stringify(foreign));await r.recover();assert.equal(f.calls.length,0);assert.ok(f.values.get(r.storageKey));
 f.values.set(f.receipts.storageKey,original);await r.recover();assert.equal(f.calls.length,1);assert.equal(f.values.has(r.storageKey),false);
});
test('eight unresolved callbacks survive one failed send, and recovery stops that pass',async()=>{
 const f=fixture(),r=f.recovery();for(let n=1;n<=8;n++)r.save(f.credential,signed(n),'order_original');
 f.setResponder(async()=>{throw Error('unavailable');});await assert.rejects(r.recover());
 assert.equal(f.calls.length,1);assert.equal(JSON.parse(f.values.get(r.storageKey)).length,8);
 f.setResponder(async credential=>({receipt:receipt(credential.request_id)}));f.advance();await r.recover();
 assert.equal(f.calls.length,9);assert.equal(f.values.has(r.storageKey),false);
});
test('altered signature, wrong order and cross-installation saved callbacks cannot be adopted',async()=>{
 const f=fixture(),r=f.recovery();r.save(f.credential,signed(),'order_original');
 assert.throws(()=>r.save(f.credential,{...signed(),razorpay_signature:'b'.repeat(64)},'order_original'),error=>error.code==='payment_reference_conflict');
 assert.throws(()=>r.save(f.credential,signed(),'order_other'),error=>error.code==='payment_reference_invalid');
 const original=f.values.get(r.storageKey),rows=JSON.parse(original).map(row=>({...row,installation_id:'00000000-0000-4000-8000-000000000002'}));
 f.values.set(r.storageKey,JSON.stringify(rows));await f.recovery().recover();assert.equal(f.calls.length,0);assert.equal(f.values.get(r.storageKey),JSON.stringify(rows));
});
test('blocked callback storage still submits exact signed fields and never opens a second payment',async()=>{
 const f=fixture(),r=f.recovery();f.storage.setItem=()=>{throw Error('blocked');};
 await r.rememberAndSubmit(f.credential,{...signed(),private_bank_data:'must not escape'},'order_original');
 assert.equal(f.calls.length,1);assert.deepEqual(f.calls[0].body,{request_id:f.credential.request_id,...signed()});assert.deepEqual(f.calls[0].credential,f.credential);
});
test('parallel recovery sends once and leaves no callback for later focus events',async()=>{
 const f=fixture(),r=f.recovery();let release;f.setResponder(credential=>new Promise(resolve=>{release=()=>resolve({receipt:receipt(credential.request_id)});}));
 r.save(f.credential,signed(),'order_original');const a=r.recover(),b=r.recover();assert.equal(a,b);assert.equal(f.calls.length,1);release();await a;
 f.advance();await r.recover();assert.equal(f.calls.length,1);assert.equal(f.values.has(r.storageKey),false);
});
test('a wrong or malformed server receipt never acknowledges a signed callback',async()=>{
 const f=fixture(),r=f.recovery();f.setResponder(async()=>({receipt:receipt('00000000-0000-4000-8000-000000000002')}));
 await assert.rejects(r.rememberAndSubmit(f.credential,signed(),'order_original'),error=>error.code==='invalid_response');assert.ok(f.values.get(r.storageKey));
 f.setResponder(async()=>({receipt:{request_id:f.credential.request_id}}));f.advance();await assert.rejects(r.recover(),error=>error.code==='invalid_response');assert.ok(f.values.get(r.storageKey));
 f.setResponder(async credential=>({receipt:receipt(credential.request_id)}));f.advance();await r.recover();assert.equal(f.values.has(r.storageKey),false);
});
test('OFF prevents recovery calls and retains the same callback for ON',async()=>{
 const f=fixture(),r=f.recovery();f.setEnabled(false);
 await assert.rejects(r.rememberAndSubmit(f.credential,signed(),'order_original'),error=>error.code==='booking_disabled');await r.recover();
 assert.equal(f.calls.length,0);assert.ok(f.values.get(r.storageKey));f.setEnabled(true);await r.recover();assert.equal(f.calls.length,1);
});
