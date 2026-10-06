import test from 'node:test';
import assert from 'node:assert/strict';
import {createBookingController} from '../../../appointment-system/browser/booking/controller.mjs';
import {createReceiptStore} from '../../../appointment-system/browser/booking/credentials.mjs';
import {RequestError} from '../../../appointment-system/browser/transport.mjs';
import {installation_id,epoch,now,policy,availability} from '../../../appointment-system/tests/booking-browser-fixture.mjs';
const settle=()=>new Promise(resolve=>setImmediate(resolve));
// The obsolete reducer is replaced by the actual shared coordinator. These
// preserve both original business intents, with fresh server selection rules.
async function fixture(){
 const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 const p=policy();p.policy.services.push({...p.policy.services[0],id:'other'});
 const receipts=createReceiptStore({installation_id,environment:'test'});let reject='payment_not_configured',slots=availability(p).slots;
 const api=async(path,options={})=>{
  if(path==='/api/booking-policy')return p;
  if(path.startsWith('/api/availability')){const query=new URL(path,'https://example.test').searchParams;
   return {...availability(p),slots,date:query.get('day'),service:{...availability(p).service,id:query.get('service_id')}};}
  if(path==='/api/checkout-context')return {ready:true};
  if(path==='/api/checkout')throw new RequestError(reject,{status:reject==='payment_not_configured'?503:0});
  throw Error('Unexpected synthetic API path');
 };
 const controller=createBookingController({api,receipts,storage:()=>storage,clock:()=>now,
  product:{getSnapshot:()=>({enabled:true,activation_epoch:epoch}),subscribe:()=>()=>{}},
  payment:{load:()=>assert.fail('No payment window expected'),open:()=>assert.fail('No payment window expected')},
  interval:()=>1,clearInterval:()=>{},documentObject:{visibilityState:'visible'}});
 controller.start();await settle();
 const draft=()=>{controller.details('full_name','Synthetic Visitor');controller.details('email','test@example.invalid');controller.details('phone','9876543210');controller.edit('slot',controller.getSnapshot().slots[0]);controller.acknowledge(true);};
 return {controller,draft,rejectWith:code=>{reject=code;},setSlots:value=>{slots=value;}};
}
test('proven rejection preserves entered details and date, but requires fresh server selection and agreement',async()=>{
 const f=await fixture();try{
  f.draft();const before=f.controller.getSnapshot();await f.controller.checkout();const rejected=f.controller.getSnapshot();
  assert.equal(rejected.credential,null);assert.equal(rejected.details,before.details);assert.equal(rejected.day,before.day);assert.equal(rejected.ack,false);
  assert.equal(rejected.slot,null);assert.equal(rejected.slots.length,1);
  f.controller.edit('slot',rejected.slots[0]);assert.deepEqual(f.controller.getSnapshot().slot,rejected.slots[0]);
  f.setSlots([]);await f.controller.loadSlots();assert.equal(f.controller.getSnapshot().slot,null);assert.deepEqual(f.controller.getSnapshot().slots,[]);
 }finally{f.controller.stop();}
});
test('service links cannot replace a saved unresolved attempt, and fresh service changes clear old selection',async()=>{
 const f=await fixture();try{
  f.draft();f.rejectWith('temporarily_unavailable');await f.controller.checkout();const saved=f.controller.getSnapshot();assert.ok(saved.credential);
  f.controller.edit('service','other');assert.equal(f.controller.getSnapshot(),saved);
 }finally{f.controller.stop();}
 const fresh=await fixture();try{fresh.draft();fresh.controller.edit('service','other');await settle();assert.equal(fresh.controller.getSnapshot().service,'other');assert.equal(fresh.controller.getSnapshot().slot,null);assert.equal(fresh.controller.getSnapshot().ack,false);}finally{fresh.controller.stop();}
});
