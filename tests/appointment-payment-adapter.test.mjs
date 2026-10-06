import test from 'node:test';
import assert from 'node:assert/strict';
import {createRazorpay} from '../appointment-system/browser/booking/razorpay.mjs';

// Synthetic provider events only. No provider script is fetched or payment made.
function loaderFixture(){
 const windowObject={},scripts=[],removed=[],timers=new Map();let next=0,appends=0;
 const documentObject={createElement:()=>({remove(){removed.push(this);}}),head:{append(script){appends++;scripts.push(script);}}};
 const adapter=createRazorpay({name:'Synthetic practice',description:'Consultation',color:'#26483d',windowObject,documentObject,
  setTimer(callback,delay){assert.equal(delay,20000);const id=++next;timers.set(id,callback);return id;},
  clearTimer(id){timers.delete(id);}});
 return {adapter,windowObject,scripts,removed,timers,documentObject,appends:()=>appends};
}
test('official payment script loading is shared and requires the provider constructor',async()=>{
 const f=loaderFixture(),a=f.adapter.load(),b=f.adapter.load();assert.equal(a,b);assert.equal(f.appends(),1);
 assert.equal(f.scripts[0].src,'https://checkout.razorpay.com/v1/checkout.js');assert.equal(f.scripts[0].async,true);
 f.windowObject.Razorpay=function(){};f.scripts[0].onload();await a;
 assert.equal(f.timers.size,0);assert.equal(f.scripts[0].onerror,null);assert.equal(f.scripts[0].onload,null);
 await f.adapter.load();assert.equal(f.appends(),1);
});
for(const mode of ['error','missing-constructor','timeout','insertion-error'])test(`payment loader ${mode} removes the script and permits a clean retry`,async()=>{
 const f=loaderFixture();if(mode==='insertion-error')f.documentObject.head.append=()=>{throw Error('synthetic insertion failure');};
 const pending=f.adapter.load(),rejected=assert.rejects(pending,error=>error.code==='payment_unavailable');
 const script=mode==='insertion-error'?f.removed[0]:f.scripts[0];
 if(mode==='error')script.onerror();else if(mode==='missing-constructor')script.onload();else if(mode==='timeout')[...f.timers.values()][0]();
 await rejected;assert.equal(f.removed.length,1);assert.equal(f.timers.size,0);assert.equal(script.onload,null);assert.equal(script.onerror,null);
 f.documentObject.head.append=script=>f.scripts.push(script);
 const retry=f.adapter.load();assert.notEqual(retry,pending);f.windowObject.Razorpay=function(){};f.scripts.at(-1).onload();await retry;
});
for(const mode of ['success','dismiss','cleanup'])test(`signed success after ${mode} is delivered once without private provider fields`,()=>{
 let options,opens=0,closes=0;const signed={razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'a'.repeat(64),private_bank_data:'must not escape'};
 const successes=[],dismissals=[];
 const windowObject={Razorpay:function(value){options=value;this.open=()=>{opens++;};this.close=()=>{closes++;options.modal.ondismiss();};}};
 const adapter=createRazorpay({name:'Synthetic practice',description:'Consultation',color:'#26483d',windowObject,documentObject:{}});
 const cleanup=adapter.open({key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:100,currency:'INR'},
  {onSuccess:result=>successes.push(result),onClose:()=>dismissals.push(true)});
 assert.equal(opens,1);assert.equal(Object.hasOwn(options,'prefill'),false);
 assert.deepEqual([options.key,options.order_id,options.amount,options.currency],['rzp_live_synthetic','order_synthetic',100,'INR']);
 if(mode==='success')options.handler(signed);else if(mode==='dismiss')options.modal.ondismiss();else{cleanup();cleanup();}
 options.handler(signed);options.handler(signed);options.modal.ondismiss();
 assert.deepEqual(successes,[{razorpay_order_id:signed.razorpay_order_id,razorpay_payment_id:signed.razorpay_payment_id,razorpay_signature:signed.razorpay_signature}]);
 assert.equal(dismissals.length,mode==='dismiss'?1:0);assert.equal(closes,mode==='cleanup'?1:0);
});
for(const mode of ['constructor','open'])test(`payment ${mode} failure reports the supported payment error`,()=>{
 const windowObject={Razorpay:function(){if(mode==='constructor')throw Error('synthetic');this.open=()=>{throw Error('synthetic');};}};
 const adapter=createRazorpay({name:'Synthetic practice',description:'Consultation',color:'#26483d',windowObject,documentObject:{}});
 assert.throws(()=>adapter.open({key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:100,currency:'INR'},
  {onSuccess(){},onClose(){}}),error=>error.code==='payment_unavailable');
});
