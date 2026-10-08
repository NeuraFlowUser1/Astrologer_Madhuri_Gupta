import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {createReceiptActions} from '../browser/booking/receipt-actions.mjs';
import {checkedReceipt,checkedEmailCopy} from '../browser/booking/protocol.mjs';
import {RequestError} from '../browser/transport.mjs';
import {receipt,epoch} from './booking-browser-fixture.mjs';
const defer=()=>{let resolve,reject;return {promise:new Promise((a,b)=>{resolve=a;reject=b;}),resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const copy=(email=true)=>({operation_id:null,booking_revision:null,state:'not_requested',has_booking_email:email,target_hint:null,next_request_at:null,remaining_requests:3,can_request:true,blocked_reason:null});
function fixture({email=true,post,pdfLoad,read,accept}={}){
 const credential={request_id:randomUUID(),secret:'r1.current.'+'a'.repeat(43)};
 let current={...receipt(credential.request_id),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,
  booking_revision:1,meeting_mode:'google_meet',meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',email_copy:copy(email)};
 let display={enabled:true,verified:true,checking:false,activation_epoch:epoch},listener,reads=0,timer,revoked=[],posts=[];
 const product={getSnapshot:()=>display,subscribe:fn=>{listener=fn;return()=>{listener=null;};}};
 const api=async(path,{body})=>{
  if(path==='/api/checkout/status'){reads++;return structuredClone(read?read(current):current);}
  assert.equal(path,'/api/checkout/email-details');posts.push(body);
  if(post)return post(body);
  current={...current,email_copy:{...current.email_copy,operation_id:body.operation_id,booking_revision:body.expected_revision,
   state:'pending',target_hint:'c***@example.test',remaining_requests:2,can_request:false,blocked_reason:'delivery_pending'}};
  return {code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,email_copy:current.email_copy};
 };
 const font={getCharacterSet:()=>Array.from({length:128},(_,i)=>i).concat(8377),widthOfTextAtSize:(s,n)=>s.length*n*.5};
 const PDFDocument={create:async()=>({registerFontkit(){},embedFont:async()=>font,addPage:()=>({drawText(){},node:{set(){}}}),
  context:{register:x=>x,obj:x=>x},save:async()=>new Uint8Array([37,80,68,70])})};
 const actions=createReceiptActions({api,product,getCredential:()=>credential,getReceipt:()=>current,onReceipt:r=>{current=accept?accept(current,r):r;actions.observe(current);},brand:'Synthetic practice',
  loadPDF:pdfLoad||(async()=>({PDFDocument,PDFName:{of:x=>x},PDFString:{of:x=>x},fontkit:{},fontBytes:new Uint8Array([1])})),
  urls:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL:value=>revoked.push(value)},setTimer:fn=>{timer=fn;return 1;},clearTimer:()=>{timer=null;}});
 actions.start();return {actions,posts,reads:()=>reads,current:()=>current,set:r=>{current=r;},
  expire:()=>timer?.(),revoked,mode:(enabled,checking=false)=>{display={...display,enabled,verified:!checking,checking};listener?.();}};
}
test('PDF exposes only after two owned reads, expires and is revoked while state is unknown',async()=>{
 const f=fixture();await f.actions.pdf();assert.equal(f.reads(),2);assert.equal(f.actions.canOpen(),true);
 f.expire();assert.equal(f.actions.canOpen(),false);await f.actions.pdf();assert.equal(f.reads(),4);
 f.mode(true,true);assert.equal(f.actions.canOpen(),false);assert.equal(f.actions.getSnapshot().pdfURL,null);
 await f.actions.pdf();assert.equal(f.reads(),4);f.actions.stop();
});
test('a changed revision while generating prevents the document from being offered',async()=>{
 const pending=defer(),f=fixture({pdfLoad:()=>pending.promise});const task=f.actions.pdf();await tick();
 f.set({...f.current(),booking_revision:2});pending.reject(Error('synthetic loader failure'));await task;
 assert.equal(f.actions.canOpen(),false);assert.equal(f.actions.getSnapshot().pdfBusy,false);f.actions.stop();
});
test('double clicks use one email operation and canonical bookings never accept a new destination',async()=>{
 const f=fixture();await Promise.all([f.actions.email('other@example.test'),f.actions.email('other@example.test')]);
 assert.equal(f.posts.length,1);assert.equal('email' in f.posts[0],false);assert.equal(f.actions.getSnapshot().emailUncertain,false);f.actions.stop();
});
test('no-email copies validate a deliberate address and do not modify saved contacts',async()=>{
 const f=fixture({email:false});await f.actions.email('bad');assert.equal(f.posts.length,0);assert.match(f.actions.getSnapshot().error,/valid email/);
 await f.actions.email(' copy@example.test ');assert.equal(f.posts[0].email,'copy@example.test');
 assert.equal(f.current().email_copy.has_booking_email,false);f.actions.stop();
});
test('network and server uncertainty retain exactly the same operation and address for explicit retry',async()=>{
 for(const error of [new RequestError(),new RequestError('temporarily_unavailable',{status:503}),new RequestError('request_pending',{status:503})]){
  let count=0;const f=fixture({email:false,post:body=>{if(count++===0)throw error;return {code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,
   email_copy:{...copy(false),operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',target_hint:'c***@example.test',can_request:false,blocked_reason:'delivery_pending'}};}});
  await f.actions.email('copy@example.test');assert.equal(f.actions.getSnapshot().emailUncertain,true);
  await f.actions.email('different@example.test');assert.deepEqual(f.posts[1],f.posts[0]);assert.equal(f.actions.getSnapshot().emailUncertain,false);f.actions.stop();
 }
});
test('known rejection releases the attempt so a new deliberate request has a new operation',async()=>{
 const f=fixture({post:()=>{throw new RequestError('revision_changed',{status:409});}});
 await f.actions.email();await f.actions.email();assert.notEqual(f.posts[0].operation_id,f.posts[1].operation_id);
 assert.equal(f.actions.getSnapshot().emailUncertain,false);f.actions.stop();
});
test('a concurrent status observation may resolve an email request before its HTTP reply',async()=>{
 const pending=defer(),f=fixture({post:()=>pending.promise});const task=f.actions.email();await tick();const body=f.posts[0];
 const saved={...copy(),operation_id:body.operation_id,booking_revision:1,state:'pending',can_request:false,blocked_reason:'delivery_pending'};
 f.actions.observe({...f.current(),email_copy:saved});pending.resolve({code:'receipt_copy_accepted',...body,booking_revision:1,email_copy:saved});
 await task;assert.equal(f.actions.getSnapshot().emailUncertain,false);assert.match(f.actions.getSnapshot().message,/saved/);f.actions.stop();
});
test('disposed actions ignore late writes and cannot expose an earlier PDF',async()=>{
 const pending=defer(),f=fixture({post:()=>pending.promise});await f.actions.pdf();const task=f.actions.email();await tick();f.actions.stop();
 pending.reject(new RequestError());await task;assert.equal(f.actions.getSnapshot().pdfURL,null);assert.equal(f.actions.canOpen(),false);
});
test('unsafe meeting links are removed without discarding valid saved payment facts',()=>{
 const f=fixture(),r=checkedReceipt({...f.current(),meet_url:'javascript:alert(1)'},f.current().request_id);
 assert.equal(r.meet_url,null);assert.equal(r.meeting_state,'needs_attention');assert.equal(r.captured_paise,210000);f.actions.stop();
});
test('copy projections reject raw addresses, unknown fields and contradictory permission',()=>{
 for(const change of [{target_hint:'customer@example.test'},{remaining_requests:true},{can_request:false},{extra:'private'},
  {operation_id:randomUUID(),booking_revision:1},{state:'delivered'},{next_request_at:'yesterday'}])assert.throws(()=>checkedEmailCopy({...copy(),...change}));
});

test('an older owned status response cannot offer a stale PDF over newer known booking facts',async()=>{
 const f=fixture({read:r=>({...r,booking_revision:1}),accept:(current,incoming)=>incoming.booking_revision<current.booking_revision?current:incoming});
 f.set({...f.current(),booking_revision:2});await f.actions.pdf();
 assert.equal(f.actions.canOpen(),false);assert.equal(f.actions.getSnapshot().pdfURL,null);
 assert.match(f.actions.getSnapshot().error,/changed/);f.actions.stop();
});

test('a failed delivery-status read cannot undo a validated email-copy acknowledgement',async()=>{
 const f=fixture({email:false,read:r=>{if(r.email_copy.operation_id)throw new RequestError('temporarily_unavailable',{status:503});return r;}});
 await f.actions.email('copy@example.test');
 assert.equal(f.posts.length,1);assert.equal(f.actions.getSnapshot().emailUncertain,false);
 assert.equal(f.actions.getSnapshot().error,'');assert.match(f.actions.getSnapshot().message,/request is saved/);
 assert.match(f.actions.getSnapshot().message,/Check booking status/);f.actions.stop();
});

test('a later owned observation clears the resolved email uncertainty without another send',async()=>{
 const f=fixture({email:false,post:()=>{throw new RequestError('temporarily_unavailable',{status:503});}});
 await f.actions.email('copy@example.test');assert.equal(f.actions.getSnapshot().emailUncertain,true);
 assert.match(f.actions.getSnapshot().error,/could not confirm/);const body=f.posts[0];
 const saved={...f.current(),email_copy:{...copy(false),operation_id:body.operation_id,booking_revision:body.expected_revision,
  state:'delivered',target_hint:'c***@example.test',remaining_requests:2}};
 f.set(saved);f.actions.observe(saved);
 assert.equal(f.actions.getSnapshot().emailUncertain,false);assert.equal(f.actions.getSnapshot().error,'');
 assert.equal(f.posts.length,1);assert.match(f.actions.getSnapshot().message,/saved/);f.actions.stop();
});

test('an owned observation keeps a saved copy resolved even if its HTTP reply is lost',async()=>{
 const pending=defer(),f=fixture({post:()=>pending.promise});const task=f.actions.email();await tick();const body=f.posts[0];
 const saved={...f.current(),email_copy:{...copy(),operation_id:body.operation_id,booking_revision:body.expected_revision,
  state:'pending',can_request:false,blocked_reason:'delivery_pending'}};
 f.set(saved);f.actions.observe(saved);pending.reject(new RequestError('temporarily_unavailable',{status:503}));await task;
 assert.equal(f.actions.getSnapshot().emailUncertain,false);assert.equal(f.actions.getSnapshot().error,'');
 assert.match(f.actions.getSnapshot().message,/saved/);assert.equal(f.posts.length,1);f.actions.stop();
});

test('resolving email uncertainty preserves an independent PDF error',async()=>{
 const f=fixture({post:()=>{throw new RequestError();},pdfLoad:()=>{throw Error('synthetic PDF failure');}});
 await f.actions.email();const body=f.posts[0];await f.actions.pdf();const pdfError=f.actions.getSnapshot().error;
 assert.match(pdfError,/PDF could not be prepared/);
 const saved={...f.current(),email_copy:{...copy(),operation_id:body.operation_id,booking_revision:body.expected_revision,
  state:'pending',can_request:false,blocked_reason:'delivery_pending'}};
 f.set(saved);f.actions.observe(saved);assert.equal(f.actions.getSnapshot().emailUncertain,false);
 assert.equal(f.actions.getSnapshot().error,pdfError);f.actions.stop();
});

test('invalid acknowledgements still preserve uncertainty and the exact retry identity',async()=>{
 for(const change of [{operation_id:randomUUID()},{booking_revision:2},{code:'not_accepted'},
  {email_copy:{...copy(),operation_id:randomUUID(),booking_revision:1,state:'delivered',target_hint:'private@example.test'}}]){
  const f=fixture({post:body=>({code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,
   email_copy:{...copy(),operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',can_request:false,blocked_reason:'delivery_pending'},...change})});
  await f.actions.email();assert.equal(f.actions.getSnapshot().emailUncertain,true);assert.doesNotMatch(f.actions.getSnapshot().message,/saved/);
  await f.actions.email();assert.deepEqual(f.posts[1],f.posts[0]);f.actions.stop();
 }
});

test('an observation for another booking or accepted revision cannot resolve this email operation',async()=>{
 for(const change of ['booking','revision']){
  const f=fixture({post:()=>{throw new RequestError();}});await f.actions.email();const body=f.posts[0];
  const observed={...f.current(),request_id:change==='booking'?randomUUID():body.request_id,
   email_copy:{...copy(),operation_id:body.operation_id,booking_revision:change==='revision'?2:body.expected_revision,
    state:'pending',can_request:false,blocked_reason:'delivery_pending'}};
  f.actions.observe(observed);assert.equal(f.actions.getSnapshot().emailUncertain,true);
  assert.match(f.actions.getSnapshot().error,/could not confirm/);
  await f.actions.email();assert.deepEqual(f.posts[1],f.posts[0]);f.actions.stop();
 }
});

test('a validated acknowledgement replaces the unchanged old copy facts before a failed follow-up read',async()=>{
 let reads=0;const f=fixture({email:false,read:r=>{if(++reads>1)throw new RequestError();return r;},
  post:body=>{f.set({...f.current(),email_copy:Object.fromEntries(Object.entries(f.current().email_copy).reverse())});return {code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,
   email_copy:{...copy(false),operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',
    can_request:false,blocked_reason:'delivery_pending',target_hint:'c***@example.test',remaining_requests:2}};}});
 const original=f.current();await f.actions.email('copy@example.test');
 assert.equal(f.current().email_copy.state,'pending');assert.equal(f.current().email_copy.has_booking_email,false);
 assert.equal(f.current().email_copy.operation_id,f.posts[0].operation_id);
 assert.deepEqual({...f.current(),email_copy:original.email_copy},original);
 assert.equal(f.actions.getSnapshot().error,'');assert.equal(f.posts.length,1);f.actions.stop();
});

test('an acknowledgement cannot replace newer booking facts or a concurrently observed copy',async()=>{
 for(const variant of ['revision','copy']){
  let reads=0,newest;const f=fixture({read:r=>{if(++reads>1)throw new RequestError();return r;},post:body=>{
   newest={...f.current(),booking_revision:variant==='revision'?2:1,
    email_copy:{...copy(),operation_id:randomUUID(),booking_revision:variant==='revision'?2:1,state:'delivered',target_hint:'c***@example.test'}};
   f.set(newest);return {code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,
    email_copy:{...copy(),operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',can_request:false,blocked_reason:'delivery_pending'}};
  }});
  await f.actions.email();assert.deepEqual(f.current(),newest);
  assert.equal(f.actions.getSnapshot().error,'');assert.equal(f.posts.length,1);f.actions.stop();
 }
});

test('an acknowledgement cannot change whether this booking has a saved email',async()=>{
 const f=fixture({post:body=>({code:'receipt_copy_accepted',...body,booking_revision:body.expected_revision,
  email_copy:{...copy(false),operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',
   can_request:false,blocked_reason:'delivery_pending'}})});
 await f.actions.email();assert.equal(f.actions.getSnapshot().emailUncertain,true);
 assert.equal(f.current().email_copy.has_booking_email,true);
 await f.actions.email();assert.deepEqual(f.posts[1],f.posts[0]);f.actions.stop();
});
