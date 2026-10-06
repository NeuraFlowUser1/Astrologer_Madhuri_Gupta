import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPaymentRecovery} from '../browser/booking/payment-recovery.mjs';
import {createRazorpay} from '../browser/booking/razorpay.mjs';
import {createReceiptStore} from '../browser/booking/credentials.mjs';
import {RequestError} from '../browser/transport.mjs';
import {installation_id,now,policy,receipt,checkout} from './booking-browser-fixture.mjs';

function fixture(){
 const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 const receipts=createReceiptStore({installation_id,environment:'test'}),credential=receipts.prepareReceipt(storage,policy());
 let enabled=true,time=now,fail=false,calls=0,release;
 const pending=[];
 const api=async(path,options)=>{calls++;pending.push(options);assert.equal(path,'/api/checkout/verify-payment');
  if(release)await release;if(fail)throw new RequestError();return {receipt:receipt(options.body.request_id)};};
 const recovery=createPaymentRecovery({installation_id,environment:'test',legacy_callbacks:[{key:'old-callbacks',project:'old'}],
  receipts,storage:()=>storage,api,enabled:()=>enabled,clock:()=>time});
 const signed={razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)};
 return {values,storage,receipts,credential,recovery,signed,pending,calls:()=>calls,setEnabled:value=>{enabled=value;},
  setTime:value=>{time=value;},setFailure:value=>{fail=value;},setPending:value=>{release=value;}};
}

test('signed success is saved before a lost response and recovered using only its original saved receipt',async()=>{
 const f=fixture();f.setFailure(true);await assert.rejects(f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture'));
 const raw=f.values.get(f.recovery.storageKey);assert.ok(raw.includes('pay_fixture'));assert.equal(raw.includes(f.credential.secret),false);
 f.setFailure(false);await f.recovery.recover();assert.equal(f.calls(),2);assert.equal(f.values.has(f.recovery.storageKey),false);
 assert.equal(f.pending[1].credential.request_id,f.credential.request_id);assert.deepEqual(f.pending[1].body,{request_id:f.credential.request_id,...f.signed});
});

test('OFF keeps evidence without contacting the application; reactivation can recover it',async()=>{
 const f=fixture();f.setEnabled(false);await assert.rejects(f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture'),error=>error.code==='booking_disabled');
 await f.recovery.recover();assert.equal(f.calls(),0);assert.ok(f.values.get(f.recovery.storageKey));
 f.setEnabled(true);await f.recovery.recover();assert.equal(f.calls(),1);
});

test('overlapping callbacks share a submission and a different signature cannot replace saved evidence',async()=>{
 const f=fixture();let release;f.setPending(new Promise(resolve=>{release=resolve;}));
 const first=f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture');
 const second=f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture');assert.equal(first,second);assert.equal(f.calls(),1);
 assert.throws(()=>f.recovery.save(f.credential,{...f.signed,razorpay_signature:'b'.repeat(64)},'order_fixture'),error=>error.code==='payment_reference_conflict');
 assert.throws(()=>f.recovery.save(f.credential,f.signed,'order_foreign'),error=>error.code==='payment_reference_invalid');
 release();await Promise.all([first,second]);
});

test('old callback formats are accepted only under their explicitly configured scope and matching receipt',async()=>{
 const f=fixture(),row={version:1,project:'old',request_id:f.credential.request_id,order_id:'order_fixture',payment_id:'pay_fixture',signature:'a'.repeat(64),created_at:now};
 f.values.set('old-callbacks',JSON.stringify([row,{...row,project:'foreign',payment_id:'pay_other'}]));
 await f.recovery.recover();assert.equal(f.calls(),1);assert.deepEqual(JSON.parse(f.values.get('old-callbacks')),[{...row,project:'foreign',payment_id:'pay_other'}]);
});

test('corrupt storage is preserved while a newly received callback can still be verified; blocked storage retains memory evidence',async()=>{
 const f=fixture();f.values.set(f.recovery.storageKey,'broken');
 await f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture');assert.equal(f.values.get(f.recovery.storageKey),'broken');
 const g=fixture();g.storage.setItem=()=>{throw Error('storage blocked');};g.setFailure(true);
 await assert.rejects(g.recovery.rememberAndSubmit(g.credential,g.signed,'order_fixture'));g.setFailure(false);await g.recovery.recover();assert.equal(g.calls(),2);
});

test('Razorpay script loader coalesces requests, retries a failed insertion, and does not load another provider URL',async()=>{
 const windowObject={},scripts=[];let fail=true;
 const documentObject={createElement:()=>({remove(){}}),head:{append:script=>{if(fail)throw Error();scripts.push(script);}}};
 const adapter=createRazorpay({name:'Example',description:'Consultation',color:'#26483d',windowObject,documentObject});
 await assert.rejects(adapter.load(),error=>error.code==='payment_unavailable');fail=false;
 const first=adapter.load(),second=adapter.load();assert.equal(first,second);assert.equal(scripts.length,1);
 assert.equal(scripts[0].src,'https://checkout.razorpay.com/v1/checkout.js');windowObject.Razorpay=function(){};scripts[0].onload();await first;
});

test('closing the payment UI never loses a later success, and repeated provider callbacks run only once',()=>{
 let options,closes=0,success=0,dismissals=0;
 const windowObject={Razorpay:function(value){options=value;this.open=()=>{};this.close=()=>{closes++;options.modal.ondismiss();};}};
 const adapter=createRazorpay({name:'Example',description:'Consultation',color:'#26483d',windowObject,documentObject:{}});
 const stop=adapter.open(checkout('id').checkout,{onSuccess:()=>{success++;},onClose:()=>{dismissals++;}});
 stop();stop();options.handler({});options.handler({});assert.equal(success,1);assert.equal(closes,1);assert.equal(dismissals,0);
});

test('payment recovery never overwrites oversize saved evidence and limits its in-memory queue',()=>{
 const f=fixture();f.values.set(f.recovery.storageKey,'x'.repeat(65537));f.recovery.save(f.credential,f.signed,'order_fixture');assert.equal(f.values.get(f.recovery.storageKey),'x'.repeat(65537));
 const g=fixture();g.values.set(g.recovery.storageKey,'{}');for(let n=0;n<128;n++)g.recovery.save(g.credential,{...g.signed,razorpay_payment_id:'pay_'+n},'order_fixture');
 assert.throws(()=>g.recovery.save(g.credential,{...g.signed,razorpay_payment_id:'pay_excess'},'order_fixture'),error=>error.code==='payment_reference_limit');assert.equal(g.values.get(g.recovery.storageKey),'{}');
});
test('conflicting historical payment signatures stop automatic recovery without dropping evidence',async()=>{
 const f=fixture(),row=f.recovery.save(f.credential,f.signed,'order_fixture');f.values.set('old-callbacks',JSON.stringify([{version:1,project:'old',request_id:row.request_id,order_id:row.order_id,payment_id:row.payment_id,signature:'b'.repeat(64),created_at:now}]));await f.recovery.recover();assert.equal(f.calls(),0);assert.ok(f.values.get('old-callbacks'));
});
test('failed acknowledgement storage cannot discard the payment and repeated recovery is rate limited',async()=>{
 const f=fixture();f.setFailure(true);await assert.rejects(f.recovery.rememberAndSubmit(f.credential,f.signed,'order_fixture'));f.storage.removeItem=()=>{throw Error('private');};f.setFailure(false);await f.recovery.recover();assert.equal(f.calls(),2);assert.ok(f.values.get(f.recovery.storageKey));await f.recovery.recover();assert.equal(f.calls(),2);f.setTime(now+60001);await f.recovery.recover();assert.equal(f.calls(),3);
});
test('concurrent recovery shares one request and registered browser listeners are removed on stop',async()=>{
 const f=fixture();f.recovery.save(f.credential,f.signed,'order_fixture');let release;f.setPending(new Promise(resolve=>{release=resolve;}));const a=f.recovery.recover(),b=f.recovery.recover();assert.equal(a,b);assert.equal(f.calls(),1);release();await a;
 const win=new EventTarget(),doc=new EventTarget();doc.visibilityState='hidden';f.setTime(now+60001);f.recovery.save(f.credential,{...f.signed,razorpay_payment_id:'pay_second'},'order_fixture');const stop=f.recovery.start(win,doc);win.dispatchEvent(new Event('focus'));assert.equal(f.calls(),1);doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));await new Promise(resolve=>setImmediate(resolve));assert.equal(f.calls(),2);stop();f.setTime(now+120002);f.recovery.save(f.credential,{...f.signed,razorpay_payment_id:'pay_third'},'order_fixture');win.dispatchEvent(new Event('pageshow'));await new Promise(resolve=>setImmediate(resolve));assert.equal(f.calls(),2);
});
test('invalid recovery configuration and malformed callback fields cannot reach the payment endpoint',()=>{
 const f=fixture(),base={installation_id,environment:'test',receipts:f.receipts,storage:()=>f.storage,api:()=>{throw Error('Must not send');},enabled:()=>true};
 for(const change of [{installation_id:'bad'},{environment:'other'},{enabled:null},{legacy_callbacks:{}},{legacy_callbacks:[{key:'same',project:'old'},{key:'same',project:'old'}]},{legacy_callbacks:[{key:'bad space',project:'old'}]}])assert.throws(()=>createPaymentRecovery({...base,...change}),error=>error.code==='invalid_configuration');
 for(const change of [{razorpay_order_id:'bad'},{razorpay_payment_id:'bad'},{razorpay_signature:'bad'}])assert.throws(()=>f.recovery.save(f.credential,{...f.signed,...change},'order_fixture'),error=>error.code==='payment_reference_invalid');
 assert.equal(f.calls(),0);
});
