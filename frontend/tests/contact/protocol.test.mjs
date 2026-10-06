import test from 'node:test';
import assert from 'node:assert/strict';
import {createEnquiryStore} from '../../../appointment-system/browser/enquiry/credentials.mjs';
import {checkedReceipt,createEnquiryAPI} from '../../../appointment-system/browser/enquiry/protocol.mjs';
import {installation_id} from '../../../appointment-system/tests/booking-browser-fixture.mjs';
const receipts=createEnquiryStore({installation_id,environment:'test',channel:'contact'});
const createAccess=storage=>receipts.create(storage,{version:1,receipt_key_id:'current'});
const readAccess=receipts.read,saveAccess=receipts.save,clearAccess=receipts.clear,STORAGE_KEY=receipts.storageKey;
const contactApi=(...args)=>createEnquiryAPI().send(...args);


const storage=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};
const access=createAccess(storage());
const receipt=()=>({code:'ok',request_id:access.request_id,state:'awaiting_verification',generation:1,sends_remaining:2,
 verification_delivery:'queued',server_now:new Date().toISOString(),code_expires_at:new Date().toISOString(),resend_after:new Date().toISOString()});

test('storage roundtrip contains no customer details and clearing checks identity',()=>{
 const memory=storage(),saved=createAccess(memory);
 assert.deepEqual(Object.keys(saved).sort(),['credential_format','request_id','secret']);
 assert.match(saved.secret,/^q1\.current\.[A-Za-z0-9_-]{43}$/);assert.equal(saved.credential_format,'q1');assert.deepEqual(readAccess(memory),saved);
 assert.throws(()=>clearAccess(memory,access),/receipt_conflict/);
 assert.throws(()=>saveAccess(memory,{...saved,email:'private@example.com'}),/receipt_unavailable/);
 assert.deepEqual(readAccess(memory),saved);
 const pending={...saved,resend_id:crypto.randomUUID(),resend_generation:1};saveAccess(memory,pending);assert.deepEqual(readAccess(memory),pending);
 assert.throws(()=>saveAccess(memory,{...pending,resend_generation:3}),/receipt_unavailable/);
 saveAccess(memory,saved);clearAccess(memory,saved);assert.equal(readAccess(memory),null);
});
test('disabled or corrupted storage fails closed',()=>{
 assert.throws(()=>createAccess({setItem(){throw Error();}}),/storage_unavailable/);
 const memory=storage();memory.setItem(STORAGE_KEY,'{broken');assert.throws(()=>readAccess(memory),/receipt_unavailable/);
});
test('receipt rejects identity swaps and impossible or incomplete states',()=>{
 for(const change of [{request_id:crypto.randomUUID()},{state:'confirmed'},{generation:4},{sends_remaining:0},{verification_delivery:'sent-maybe'},{server_now:'2026-01-01'}]){
  assert.throws(()=>checkedReceipt({...receipt(),...change},access.request_id),/invalid_response/);
 }
 assert.equal(checkedReceipt(receipt(),access.request_id).state,'awaiting_verification');
});
test('transport uses only local contracts and its own receipt identity',async t=>{
 let sent;
 t.mock.method(globalThis,'fetch',async(url,options)=>{sent={url,options};return Response.json(receipt());});
 await contactApi('status',access,{request_id:crypto.randomUUID()});
 assert.equal(sent.url,'/api/contact/status');assert.equal(sent.options.headers['X-Enquiry-Receipt'],access.secret);
 assert.equal(JSON.parse(sent.options.body).request_id,access.request_id);assert.equal(sent.options.redirect,'error');
 await assert.rejects(contactApi('https://other.example',access),/invalid_request/);
});
test('oversize, HTML, malformed and foreign responses never become a receipt',async t=>{
 let response;
 t.mock.method(globalThis,'fetch',async()=>response);
 for(const body of ['x'.repeat(8193),'{bad',JSON.stringify({...receipt(),request_id:crypto.randomUUID()})]){
  response=new Response(body,{headers:{'Content-Type':'application/json'}});
  await assert.rejects(contactApi('status',access));
 }
 response=new Response('<html>error</html>',{headers:{'Content-Type':'text/html'}});await assert.rejects(contactApi('status',access));
});
test('retry advice is bounded and provider error details are not displayed',async t=>{
 t.mock.method(globalThis,'fetch',async()=>Response.json({code:'please_wait',detail:'private'}, {status:429,headers:{'Retry-After':'9000'}}));
 await assert.rejects(contactApi('status',access),e=>e.code==='please_wait'&&e.retryAfter===3600&&!e.message.includes('private'));
});
