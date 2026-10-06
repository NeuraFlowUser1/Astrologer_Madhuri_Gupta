import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBookingController} from '../browser/booking/controller.mjs';
import {createReceiptStore} from '../browser/booking/credentials.mjs';
import {RequestError} from '../browser/transport.mjs';
import {checkedPolicy,checkedAvailability,checkedReceipt,checkedCheckout,rejectedWithoutBooking} from '../browser/booking/protocol.mjs';
import {installation_id,epoch,now,policy,availability,receipt,checkout} from './booking-browser-fixture.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};

async function fixture({otp=false,initialReceipt=null,overrides={},initialEnabled=true}={}){
 const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 const receipts=createReceiptStore({installation_id,environment:'test'}),p=policy();p.policy.booking_verification.email=otp;
 if(initialReceipt)receipts.prepareReceipt(storage,p);
 let product={enabled:initialEnabled,activation_epoch:epoch},notifyProduct,poll,callbacks,opened=0,closed=0,clock=now;
 const calls=[];
 const api=async(path,options={})=>{
  calls.push({path,...structuredClone({...options,signal:undefined})});
  if(overrides[path])return overrides[path](options);
  if(path==='/api/booking-policy')return structuredClone(p);
  if(path.startsWith('/api/availability')){const url=new URL(path,'https://fixture.invalid'),data=availability(p,Number(url.searchParams.get('questions')));
   data.date=url.searchParams.get('day');return data;}
  if(path==='/api/checkout-context')return {ready:true};
  if(path==='/api/checkout/status')return receipt(options.body.request_id);
  if(path==='/api/checkout' || path==='/api/checkout/resume')return checkout(options.body.request_id);
  if(path==='/api/booking-verification/start' || path==='/api/booking-verification/resend')return {code:'ok',state:'awaiting_verification',
   challenge_id:'e8e4b70f-d390-41c9-9b47-b3c50aac25b1',generation:path.endsWith('resend')?2:1,expires_at:new Date(now+300000).toISOString()};
  if(path==='/api/booking-verification/verify')return {code:'ok',state:'verified',verification_grant:'bv1.current.'+'a'.repeat(43),expires_at:new Date(now+300000).toISOString()};
  throw Error('Unimplemented fixture path '+path);
 };
 const payment={load:async()=>{},open:(_checkout,c)=>{opened++;callbacks=c;return()=>{closed++;};},
  rememberAndSubmit:async(c,signed,order)=>{calls.push({path:'payment-reference',c,signed,order});return {receipt:{...receipt(c.request_id),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000}};}};
 const controller=createBookingController({api,receipts,storage:()=>storage,payment,clock:()=>clock,
  product:{getSnapshot:()=>product,subscribe:fn=>{notifyProduct=fn;return()=>{};}},interval:fn=>{poll=fn;return 1;},clearInterval:()=>{},documentObject:{visibilityState:'visible'}});
 controller.start();await tick();
 return {controller,calls,p,values,receipts,storage,payment,overrides,poll:()=>poll(),setClock:value=>{clock=value;},
  opened:()=>opened,closed:()=>closed,callback:()=>callbacks,
  mode:(enabled,activation_epoch=epoch)=>{product={enabled,activation_epoch};notifyProduct();},
  draft:()=>{controller.details('full_name','Test Customer');controller.details('email','Customer@example.net');
   controller.details('phone','9876543210');controller.edit('slot',controller.getSnapshot().slots[0]);controller.acknowledge(true);},
 };
}

test('both configured verification modes use the same request and receipt coordinator',async()=>{
 for(const otp of [false,true]){
  const f=await fixture({otp});f.draft();
  if(otp){await f.controller.checkout();assert.equal(f.opened(),0);assert.match(f.controller.getSnapshot().error,/verify your email/);
   await f.controller.startVerification();await f.controller.verifyCode('123456');f.controller.acknowledge(true);}
  await f.controller.checkout();assert.equal(f.opened(),1);
  const submitted=f.calls.find(c=>c.path==='/api/checkout');assert.equal(submitted.body.email,'Customer@example.net');assert.equal(submitted.body.phone,'+919876543210');
  assert.equal(!!submitted.body.verification_grant,otp);assert.equal(submitted.body.normalization_version,2);
  assert.equal([...f.values.values()].some(value=>value.includes('Customer') || value.includes('9876543210')),false);
  await f.callback().onSuccess({razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)});
  assert.equal(f.controller.getSnapshot().receipt.appointment_state,'confirmed');f.controller.stop();
 }
});

test('lost checkout reply preserves its exact operation and freezes edits; explicit retry never starts a second attempt',async()=>{
 let count=0;const f=await fixture({overrides:{'/api/checkout':async({body})=>{if(count++===0)throw new RequestError();return checkout(body.request_id);}}});
 f.draft();await f.controller.checkout();const first=f.calls.find(c=>c.path==='/api/checkout');
 assert.equal(f.controller.canRetryOriginal(),true);assert.ok(f.receipts.readReceipt(f.storage));
 f.controller.details('email','changed@example.net');f.controller.edit('day','2026-10-05');
 await f.controller.checkout();assert.equal(count,1);await f.controller.retryOriginal();assert.equal(count,2);
 const retried=f.calls.filter(c=>c.path==='/api/checkout')[1];assert.deepEqual(retried.body,first.body);assert.deepEqual(retried.credential,first.credential);
 assert.equal(f.controller.getSnapshot().details.email,'Customer@example.net');f.controller.stop();
});

test('known pre-commit rejection releases only the matching saved access; uncertainty and conflicts retain it',async()=>{
 for(const [code,status,clear] of [['time_unavailable',409,true],['payment_not_configured',503,true],['quote_changed',409,true],
  ['request_conflict',409,false],['context_expired',403,false],['invalid_request',503,false],['request_pending',503,false]]){
  const f=await fixture({overrides:{'/api/checkout':async()=>{throw new RequestError(code,{status});}}});f.draft();await f.controller.checkout();
  assert.equal(f.receipts.readReceipt(f.storage)===null,clear,code);assert.equal(f.controller.getSnapshot().credential===null,clear,code);f.controller.stop();
 }
});

test('reloaded saved access checks status without creating a context or a new booking',async()=>{
 const f=await fixture({initialReceipt:true});assert.equal(f.controller.getSnapshot().phase,'receipt');
 assert.equal(f.calls.filter(c=>c.path==='/api/checkout/status').length,1);
 assert.equal(f.calls.some(c=>['/api/checkout-context','/api/checkout'].includes(c.path)),false);f.controller.stop();
});

test('booking OFF prevents start, closes checkout and rejects a stale response after reactivation',async()=>{
 const pending=deferred(),f=await fixture({overrides:{'/api/checkout':()=>pending.promise}});f.draft();
 const attempt=f.controller.checkout();await tick();const saved=f.controller.getSnapshot().credential;
 f.mode(false);pending.resolve(checkout(saved.request_id));await attempt;assert.equal(f.opened(),0);
 assert.ok(f.receipts.readReceipt(f.storage));await f.controller.resume();assert.equal(f.opened(),0);
 f.mode(true,'fc66d158-203d-4eb7-83b6-1ab8faf2a8a8');await tick();await f.controller.resume();assert.equal(f.opened(),1);
 f.mode(false);assert.equal(f.closed(),1);await f.controller.checkout();assert.equal(f.opened(),1);f.controller.stop();
});

test('changing email invalidates verification; lost code replies retry one operation; unrelated fields preserve proof',async()=>{
 let attempts=0;const f=await fixture({otp:true,overrides:{'/api/booking-verification/start':async()=>{
  if(attempts++===0)throw new RequestError();return {code:'ok',state:'awaiting_verification',challenge_id:'e8e4b70f-d390-41c9-9b47-b3c50aac25b1',generation:1,expires_at:new Date(now+300000).toISOString()};}}});
 f.draft();await f.controller.startVerification();await f.controller.startVerification();
 const calls=f.calls.filter(c=>c.path==='/api/booking-verification/start');assert.deepEqual(calls[0].body,calls[1].body);
 await f.controller.verifyCode('123456');assert.ok(f.controller.getSnapshot().verification);
 f.controller.details('notes','Additional details');assert.ok(f.controller.getSnapshot().verification);
 f.controller.details('email','different@example.net');assert.equal(f.controller.getSnapshot().verification,null);
 assert.equal(f.controller.getSnapshot().challenge,null);f.controller.stop();
});

test('server-time expiry prevents starting with an expired grant and policy quotations come from availability',async()=>{
 const f=await fixture({otp:true});f.p.policy.services[0].pricing={kind:'per_question',amount_paise:210000,maximum_questions:10};
 await f.controller.loadPolicy();f.controller.edit('questions',3);await tick();f.draft();
 assert.equal(f.controller.getSnapshot().quote.amount_paise,630000);await f.controller.startVerification();await f.controller.verifyCode('123456');
 f.controller.acknowledge(true);f.setClock(now+300001);await f.controller.checkout();assert.equal(f.opened(),0);
 assert.equal(f.calls.some(c=>c.path==='/api/checkout'),false);f.controller.stop();
});

test('a second click is ignored while the first operation is pending and browser polling is bounded',async()=>{
 const pending=deferred(),f=await fixture({overrides:{'/api/checkout':()=>pending.promise}});f.draft();
 const first=f.controller.checkout();await tick();await f.controller.checkout();assert.equal(f.calls.filter(c=>c.path==='/api/checkout').length,1);
 const id=f.controller.getSnapshot().credential.request_id;pending.resolve({receipt:receipt(id),checkout:null});await first;
 for(let n=0;n<40;n++){f.poll();await tick();}assert.equal(f.calls.filter(c=>c.path==='/api/checkout/status').length,24);f.controller.stop();
});

test('start-over rereads the saved booking and refuses a stale permission to discard it',async()=>{
 let checks=0;const f=await fixture({initialReceipt:true,overrides:{'/api/checkout/status':async({body})=>{
  checks++;return {...receipt(body.request_id),next_actions:checks===1?['choose_new_time']:['check_status']};}}});
 await f.controller.restart();assert.ok(f.controller.getSnapshot().credential);assert.ok(f.receipts.readReceipt(f.storage));f.controller.stop();
});

test('late signed payment evidence survives navigation, while the old controller cannot reopen or update the page',async()=>{
 const f=await fixture();f.draft();await f.controller.checkout();const callbacks=f.callback();f.controller.stop();
 const before=f.controller.getSnapshot();await callbacks.onSuccess({razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)});
 assert.equal(f.calls.filter(c=>c.path==='payment-reference').length,1);assert.equal(f.controller.getSnapshot(),before);assert.equal(f.closed(),1);
});

test('stopping a pending operation and restarting the page does not leave its controls permanently busy',async()=>{
 const pending=deferred(),f=await fixture({otp:true,overrides:{'/api/booking-verification/start':()=>pending.promise}});f.draft();
 const old=f.controller.startVerification();await tick();assert.equal(f.controller.getSnapshot().busy,true);f.controller.stop();f.controller.start();await tick();
 assert.equal(f.controller.getSnapshot().busy,false);pending.reject(new RequestError());await old;assert.equal(f.controller.getSnapshot().busy,false);f.controller.stop();
});

test('unavailable payment script keeps the saved booking for recovery and does not clear access',async()=>{
 const f=await fixture();f.payment.load=async()=>{throw Error('script unavailable');};f.draft();await f.controller.checkout();
 assert.equal(f.opened(),0);assert.ok(f.receipts.readReceipt(f.storage));assert.equal(f.controller.getSnapshot().phase,'receipt');
 assert.match(f.controller.getSnapshot().error,/payment window could not load/);f.controller.stop();
});

test('protocol rejects wrong quote, time, receipt and payment-launch identities',()=>{
 const p=policy(),id='b2ca6d62-5e1e-4e18-ae5e-9a7447acb3bb',selection={service:'consultation',day:'2026-10-03',questions:1,policy:p};
 assert.equal(checkedPolicy(p),p);assert.ok(checkedAvailability(availability(p),selection));
 assert.throws(()=>checkedAvailability(availability(p),{...selection,questions:2}));
 assert.throws(()=>checkedAvailability({...availability(p),slots:[{starts_at:'2026-10-04T01:00:00Z',ends_at:'2026-10-04T01:45:00Z'}]},selection));
 assert.throws(()=>checkedReceipt(receipt(id),'another-booking'));
 for(const change of [{key_id:'rzp_test_synthetic'},{amount_paise:1},{currency:'USD'},{order_id:'foreign'}]){
  const value=checkout(id);Object.assign(value.checkout,change);assert.throws(()=>checkedCheckout(value,id));
 }
 assert.equal(rejectedWithoutBooking(new RequestError('time_unavailable',{status:409})),true);
 assert.equal(rejectedWithoutBooking(new Error('time_unavailable')),false);
});

test('invalid edits leave the exact selection intact and listeners can unsubscribe',async()=>{
 const f=await fixture();let observed=0;const off=f.controller.subscribe(()=>observed++);const before=f.controller.getSnapshot();
 for(const [name,value] of [['service','missing'],['day','bad'],['questions',0],['questions',2],['questions',1.5],['slot',null],['unknown','value']])f.controller.edit(name,value);
 f.controller.details('unknown','value');f.controller.details('email',null);assert.equal(f.controller.getSnapshot(),before);
 f.controller.edit('service',before.service);await tick();assert.ok(observed);off();const saved=observed;f.controller.report('Example error');assert.equal(observed,saved);assert.equal(f.controller.getSnapshot().error,'Example error');f.controller.report('a'.repeat(501));f.controller.report(null);assert.equal(f.controller.getSnapshot().error,'Example error');f.controller.stop();
});
test('no enabled service offers no checkout and a failed policy or availability read cannot reuse an old quote',async()=>{
 const f=await fixture();f.p.policy.services[0].enabled=false;await f.controller.loadPolicy();assert.equal(f.controller.getSnapshot().service,'');await f.controller.checkout();assert.equal(f.opened(),0);
 f.p.policy.services[0].enabled=true;f.overrides['/api/booking-policy']=async()=>{throw new RequestError();};await f.controller.loadPolicy();assert.equal(f.controller.getSnapshot().loadingPolicy,false);assert.ok(f.controller.getSnapshot().error);
 delete f.overrides['/api/booking-policy'];await f.controller.loadPolicy();const path=f.calls.filter(c=>c.path.startsWith('/api/availability')).at(-1).path;f.overrides[path]=async()=>{throw new RequestError();};await f.controller.loadSlots();assert.equal(f.controller.getSnapshot().slotsStatus,'error');assert.equal(f.controller.getSnapshot().quote,null);f.controller.stop();
});
test('a newer availability request wins even when the old request ignores cancellation',async()=>{
 const f=await fixture(),pending=deferred();const oldPath=f.calls.find(c=>c.path.startsWith('/api/availability')).path;f.overrides[oldPath]=()=>pending.promise;
 const old=f.controller.loadSlots();f.controller.edit('day','2026-10-04');await tick();const current=f.controller.getSnapshot();pending.resolve(availability(f.p));await old;assert.equal(f.controller.getSnapshot(),current);assert.equal(current.day,'2026-10-04');f.controller.stop();
});
test('email code resend changes its generation while malformed verification cannot send a code check',async()=>{
 const f=await fixture({otp:true});await f.controller.verifyCode('123456');assert.equal(f.calls.some(c=>c.path==='/api/booking-verification/verify'),false);
 f.draft();await f.controller.resendVerification();assert.equal(f.calls.some(c=>c.path==='/api/booking-verification/resend'),false);
 await f.controller.startVerification();await f.controller.resendVerification();assert.equal(f.controller.getSnapshot().challenge.generation,2);
 for(const code of [123456,'12345','abcdef'])await f.controller.verifyCode(code);assert.equal(f.calls.some(c=>c.path==='/api/booking-verification/verify'),false);
 await f.controller.verifyCode('123456');assert.equal(f.calls.find(c=>c.path==='/api/booking-verification/verify').body.generation,2);f.controller.stop();
});
test('invalid checkout context never stores access or starts payment',async()=>{
 const f=await fixture({overrides:{'/api/checkout-context':async()=>({ready:false})}});f.draft();await f.controller.checkout();assert.equal(f.receipts.readReceipt(f.storage),null);assert.equal(f.opened(),0);assert.equal(f.calls.some(c=>c.path==='/api/checkout'),false);f.controller.stop();
});
test('foreign country phones and optional missing phone retain the submitted meaning',async()=>{
 for(const phone of ['+44 1234 567890','']){const f=await fixture();f.draft();f.controller.details('country','other');f.controller.details('phone',phone);f.controller.details('birth_date','2000-01-01');f.controller.acknowledge(true);await f.controller.checkout();const body=f.calls.find(c=>c.path==='/api/checkout').body;assert.equal(body.phone,phone);assert.equal(body.birth_date,'2000-01-01');f.controller.stop();}
});
test('payment closure checks the same saved booking and signed evidence failure preserves recovery',async()=>{
 const f=await fixture();f.draft();await f.controller.checkout();f.payment.rememberAndSubmit=async()=>{throw new RequestError();};await f.callback().onSuccess({});assert.equal(f.controller.getSnapshot().phase,'receipt');assert.ok(f.controller.getSnapshot().error);assert.ok(f.receipts.readReceipt(f.storage));
 await f.controller.resume();f.callback().onClose();await tick();assert.equal(f.controller.getSnapshot().phase,'receipt');assert.ok(f.calls.some(c=>c.path==='/api/checkout/status'));f.controller.stop();
});
test('payment construction failure leaves the recoverable receipt visible',async()=>{
 const f=await fixture();f.payment.open=()=>{throw Error('Synthetic payment constructor failure');};f.draft();await f.controller.checkout();assert.equal(f.controller.getSnapshot().phase,'receipt');assert.match(f.controller.getSnapshot().error,/payment window/);assert.ok(f.receipts.readReceipt(f.storage));f.controller.stop();
});
test('resume obeys provider retry delay and only a fresh permitted status can start over',async()=>{
 const f=await fixture({initialReceipt:true,overrides:{'/api/checkout/resume':async({body})=>({receipt:receipt(body.request_id),checkout:null,retry_after:30})}});
 await f.controller.resume();assert.equal(f.controller.getSnapshot().retryAt,now+30000);const count=f.calls.length;f.poll();await f.controller.check();assert.equal(f.calls.length,count);
 f.setClock(now+30001);f.overrides['/api/checkout/status']=async({body})=>({...receipt(body.request_id),next_actions:['choose_new_time']});await f.controller.check();await f.controller.restart();assert.equal(f.controller.getSnapshot().credential,null);assert.equal(f.receipts.readReceipt(f.storage),null);assert.equal(f.controller.getSnapshot().phase,'draft');f.controller.stop();
});
test('settled receipt states stop automatic checks and OFF makes every new action inert',async()=>{
 for(const changes of [{appointment_state:'cancelled'},{appointment_state:'payment_review'},{appointment_state:'expired'},{appointment_state:'confirmed',meeting_state:'ready'}]){
  const f=await fixture({initialReceipt:true,overrides:{'/api/checkout/status':async({body})=>({...receipt(body.request_id),...changes})}});const count=f.calls.length;f.poll();await tick();assert.equal(f.calls.length,count);f.controller.stop();
 }
 const f=await fixture({initialEnabled:false});await f.controller.loadPolicy();await f.controller.checkout();await f.controller.resume();await f.controller.restart();await f.controller.startVerification();assert.equal(f.calls.length,0);f.controller.stop();
});
