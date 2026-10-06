/** Test-only JSON-line bridge to an actual isolated Python/SQL application.
 * The parent owns all responses; no network adapter or real provider is used.
 */
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
import {createBookingController} from '../browser/booking/controller.mjs';
import {createReceiptStore} from '../browser/booking/credentials.mjs';
import {RequestError} from '../browser/transport.mjs';
const lines=createInterface({input:process.stdin,crlfDelay:Infinity});
const pending=new Map();let sequence=0;
lines.on('line',line=>{const value=JSON.parse(line),resolve=pending.get(value.id);pending.delete(value.id);resolve(value);});
function bridge(path,options={}){return new Promise(resolve=>{
 const id=++sequence;pending.set(id,resolve);process.stdout.write(JSON.stringify({id,path,...options})+'\n');
}).then(response=>{if(response.status>=400)throw new RequestError(response.body.code,{status:response.status,retryAfter:response.retryAfter||0});return response.body;});}
const settings=await bridge('test:settings'),values=new Map();
const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
const receipts=createReceiptStore(settings);
let paymentOptions,opened=0;
const payment={load:async()=>{},open:(value,options)=>{opened++;paymentOptions={value,options};return()=>{};},
 rememberAndSubmit:async(c,signed)=>bridge('/api/checkout/verify-payment',{body:{request_id:c.request_id,...signed},credential:c})};
let enabled=true,changed;const product={getSnapshot:()=>({enabled,activation_epoch:settings.installation_id}),subscribe:fn=>{changed=fn;return()=>{};}};
const controller=createBookingController({api:(path,{signal,...options}={})=>bridge(path,options),receipts,storage:()=>storage,payment,product,
 interval:()=>1,clearInterval:()=>{},documentObject:{visibilityState:'visible'}});
const until=async(predicate,label)=>{const started=Date.now();while(!predicate()){
 if(Date.now()-started>20000)throw Error('Timed out: '+label+'; '+controller.getSnapshot().error);await new Promise(resolve=>setTimeout(resolve,10));}};
controller.start();await until(()=>!controller.getSnapshot().loadingPolicy,'policy');
assert.ok(controller.getSnapshot().policy);
const date=await bridge('test:date');controller.edit('day',date.value);await until(()=>controller.getSnapshot().slotsStatus==='ready','slots');
assert.ok(controller.getSnapshot().slots.length);
controller.details('full_name','Synthetic Customer');controller.details('email','Customer@example.com');controller.details('phone','9876543210');
controller.edit('slot',controller.getSnapshot().slots[0]);
if(controller.getSnapshot().policy.policy.booking_verification.email){
 await controller.startVerification();assert.ok(controller.getSnapshot().challenge);
 const code=await bridge('test:verification-code');await controller.verifyCode(code.value);assert.ok(controller.getSnapshot().verification);
}
controller.acknowledge(true);await controller.checkout();assert.equal(opened,1,controller.getSnapshot().error);
assert.equal(controller.getSnapshot().receipt.appointment_state,'held');
const signed=await bridge('test:payment-capture',{order:paymentOptions.value.order_id});
await paymentOptions.options.onSuccess(signed);assert.equal(controller.getSnapshot().receipt.appointment_state,'confirmed',controller.getSnapshot().error);
assert.equal(controller.getSnapshot().receipt.captured_paise,210000);
await controller.check();assert.equal(controller.getSnapshot().receipt.appointment_state,'confirmed');
enabled=false;changed();await controller.checkout();assert.equal(opened,1);
controller.stop();await bridge('test:finished');lines.close();
