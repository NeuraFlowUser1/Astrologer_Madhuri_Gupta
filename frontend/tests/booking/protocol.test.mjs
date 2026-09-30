import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { webcrypto } from 'node:crypto';
import { checkedPolicy, checkedAvailability, checkedReceipt, checkedCheckout, prepareReceipt, readReceipt,
  clearReceipt, STORAGE_KEY, api, rejectedWithoutBooking } from '../../src/booking/protocol.mjs';
const policy = JSON.parse(readFileSync(new URL('./policy.json', import.meta.url)));
const storage = () => { const values = new Map(); return { getItem:k=>values.get(k)??null,
  setItem:(k,v)=>values.set(k,v), removeItem:k=>values.delete(k) }; };
const id = '11111111-1111-4111-8111-111111111111';
const receipt = () => ({request_id:id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',
  service_name:'Kundli Prediction',currency:'INR',timezone:'Asia/Kolkata',amount_paise:250000,captured_paise:0,refunded_paise:0,
  starts_at:'2030-01-02T10:00:00+05:30',ends_at:'2030-01-02T10:30:00+05:30',server_now:'2030-01-01T09:00:00Z',
  hold_expires_at:'2030-01-01T09:10:00Z',next_actions:['resume_payment'],meeting_state:'not_created',meet_url:null});
test('policy rejects another client, duplicate services and untrusted amounts',()=>{
  assert.equal(checkedPolicy(policy),policy);
  for(const mutate of [p=>p.policy.project='003',p=>p.policy.services[1]=p.policy.services[0],p=>p.policy.services[0].amount_paise=-1]){
    const bad=structuredClone(policy);mutate(bad);assert.throws(()=>checkedPolicy(bad));
  }
});
test('availability rejects stale requests, duplicate slots and past slots',()=>{
  const good={date:'2030-01-02',service:{id:'kundli-prediction',quote_version:policy.quote_version,timezone:'Asia/Kolkata'},
    server_now:'2030-01-01T09:00:00Z',slots:[{starts_at:receipt().starts_at,ends_at:receipt().ends_at}]};
  const check=v=>checkedAvailability(v,'kundli-prediction','2030-01-02',policy.quote_version);
  assert.equal(check(good),good);
  for(const mutate of [v=>v.date='2030-01-03',v=>v.slots.push(v.slots[0]),v=>v.server_now='2030-01-03T09:00:00Z']){
    const bad=structuredClone(good);mutate(bad);assert.throws(()=>check(bad));
  }
});
test('receipt rejects money contradictions, wrong identity, reversed time and unsafe meeting links',()=>{
  assert.ok(checkedReceipt(receipt(),id));
  for(const mutate of [r=>r.refunded_paise=1,r=>r.request_id='other',r=>r.ends_at=r.starts_at,
    r=>r.meet_url='https://meet.google.com.evil.test/abc-defg-hij',r=>r.next_actions=['confirm_locally']]){
    const bad=receipt();mutate(bad);assert.throws(()=>checkedReceipt(bad,id));
  }
});
test('payment launch requires matching money, live key and a current held slot',()=>{
  const good={receipt:receipt(),checkout:{key_id:'rzp_live_example',order_id:'order_example',amount_paise:250000,currency:'INR'}};
  assert.ok(checkedCheckout(good,id));
  for(const mutate of [r=>r.checkout.amount_paise=100,r=>r.checkout.key_id='rzp_test_example',
    r=>r.receipt.appointment_state='confirmed',r=>r.receipt.hold_expires_at=r.receipt.server_now]){
    const bad=structuredClone(good);mutate(bad);assert.throws(()=>checkedCheckout(bad,id));
  }
});
test('private storage contains only a random receipt capability',()=>{
  const s=storage(),value=prepareReceipt(s,webcrypto);
  assert.deepEqual(Object.keys(value).sort(),['request_id','secret','version']);assert.equal(value.secret.length,43);
  assert.deepEqual(readReceipt(s),value);clearReceipt(s,value);assert.equal(readReceipt(s),null);
});
test('blocked or silently discarded storage prevents checkout preparation',()=>{
  assert.throws(()=>prepareReceipt({setItem(){throw Error()},getItem(){return null}},webcrypto),{code:'storage_unavailable'});
  assert.throws(()=>prepareReceipt({setItem(){},getItem(){return null}},webcrypto),{code:'storage_unavailable'});
});
test('malformed receipt is not reset and a different receipt cannot be cleared',()=>{
  const s=storage();s.setItem(STORAGE_KEY,'broken');assert.throws(()=>readReceipt(s));assert.equal(s.getItem(STORAGE_KEY),'broken');
  const value=prepareReceipt(s,webcrypto);assert.throws(()=>clearReceipt(s,{request_id:id}));assert.deepEqual(readReceipt(s),value);
});
test('uncertain responses are never treated as permission for another reservation',()=>{
  for(const code of ['temporarily_unavailable','request_conflict','checkout_in_progress','access_unavailable','invalid_response'])
    assert.equal(rejectedWithoutBooking(code),false);
});
test('API rejects external destinations before calling fetch',async()=>{
  await assert.rejects(api('https://example.com/api/checkout'),{code:'invalid_response'});
});
test('API applies receipt only as a header and bounds response size',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async(path,options)=>{
      assert.equal(path,'/api/checkout/status');assert.equal(options.headers['X-Booking-Receipt'],'private');
      assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
      assert.equal(options.body,JSON.stringify({request_id:id}));
      return new Response(JSON.stringify(receipt()),{headers:{'Content-Type':'application/json'}});
    };
    assert.equal((await api('/api/checkout/status',{body:{request_id:id},credential:{secret:'private'}})).request_id,id);
    globalThis.fetch=async()=>new Response('x'.repeat(65537),{headers:{'Content-Type':'application/json'}});
    await assert.rejects(api('/api/booking-policy'),{code:'invalid_response'});
  } finally {globalThis.fetch=original;}
});
